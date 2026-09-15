"""Scrape stage: discover content links for a location variant.

Supports three scrape types (plan section 3.2):

- ``scrapy``: a spider generated from the ``scrape.spider`` config block,
  executed in-process via the Scrapy API.
- ``static``: a fixed URL (e.g. galeria's weekly PDF).
- ``meta_refresh``: the website URL itself, used when change detection happens
  via the page's ``article:modified_time`` meta tag (moritzbastei).

Discovered links are filtered against the state backend; only unprocessed
links are emitted as "new".
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
from contextlib import redirect_stdout
from html.parser import HTMLParser


class ScrapeError(Exception):
    """Raised when discovery fails (a variant 'loses', plan section 3.5)."""


class CloudflareContentMiddleware:
    """Render Scrapy requests through Cloudflare Browser Run's content API.

    The middleware is installed only when a location explicitly enables it in
    its scrape configuration. Credentials are read from the environment so
    they never need to be stored in a location YAML file.
    """

    def __init__(self, config: dict):
        self.config = config
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not self.account_id or not self.api_token:
            raise ScrapeError(
                "Cloudflare middleware requires CLOUDFLARE_ACCOUNT_ID and "
                "CLOUDFLARE_API_TOKEN"
            )
        # Keep this diagnostic secret-free so a production run proves that
        # Scrapy instantiated the middleware before any page is fetched.
        print(
            "Cloudflare Browser Run middleware initialized "
            "(credentials present)",
            file=sys.stderr,
        )

    @classmethod
    def from_crawler(cls, crawler):
        config = crawler.settings.getdict("PIPELINE_CLOUDFLARE_CONFIG")
        return cls(config)

    def _render(self, request):
        payload = {"url": request.url}
        wait_until = self.config.get("wait_until")
        if wait_until:
            payload["gotoOptions"] = {"waitUntil": wait_until}
        for key, api_key in (
            ("wait_for_timeout", "waitForTimeout"),
            ("action_timeout", "actionTimeout"),
        ):
            if self.config.get(key) is not None:
                payload[api_key] = self.config[key]

        endpoint = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/browser-rendering/content"
        )
        api_request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(api_request, timeout=180) as response:
                raw = response.read()
                status = response.status
        except Exception as exc:
            raise ScrapeError(
                f"Cloudflare Browser Run request failed for {request.url}: {exc}"
            ) from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScrapeError("Cloudflare Browser Run returned invalid JSON") from exc
        if not result.get("success") or not isinstance(result.get("result"), str):
            errors = result.get("errors") or result.get("messages") or result
            raise ScrapeError(f"Cloudflare Browser Run returned an error: {errors}")
        # The content endpoint returns HTML in result. The final URL is in meta
        # on current API responses, but request.url remains the safe fallback.
        html = result["result"]
        final_url = (result.get("meta") or {}).get("finalUrl", request.url)
        from scrapy.http import HtmlResponse

        return HtmlResponse(
            url=final_url,
            status=(result.get("meta") or {}).get("status", status),
            headers={
                k.encode(): str(v).encode()
                for k, v in ((result.get("meta") or {}).get("headers") or {}).items()
            },
            body=html.encode("utf-8"),
            encoding="utf-8",
            request=request,
        )

    def process_request(self, request, spider):
        # Keep the reactor responsive while waiting on Cloudflare's remote
        # browser. Scrapy waits for this Deferred before downloading normally.
        # This marker is intentionally secret-free and makes middleware usage
        # independently verifiable in the Actions log.
        print(
            f"Cloudflare Browser Run middleware active for {request.url}",
            file=sys.stderr,
        )
        from twisted.internet.threads import deferToThread

        return deferToThread(self._render, request)


class _ModifiedTimeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.modified_time = None

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attrs = dict(attrs)
        if attrs.get("property") == "article:modified_time":
            self.modified_time = attrs.get("content")


def fetch_modified_time(url: str) -> str | None:
    """Return the page's article:modified_time meta value, or None."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise ScrapeError(f"failed to fetch {url}: {exc}") from exc
    parser = _ModifiedTimeParser()
    parser.feed(html)
    if parser.modified_time and re.match(r"\d{4}", parser.modified_time):
        return parser.modified_time
    return None


def _build_spider_class(spider_cfg: dict, start_url: str):
    import scrapy
    from scrapy.exceptions import CloseSpider

    link_xpath = spider_cfg["link_xpath"]
    allowed_domains = spider_cfg.get("allowed_domains") or []
    item_key = spider_cfg.get("item_key", "link")
    expected_count = spider_cfg.get("count")
    select_index = spider_cfg.get("select_index")
    follow = spider_cfg.get("follow", False)
    inline = spider_cfg.get("inline", False)
    clean_html = spider_cfg.get("clean_html", False)
    safe_attrs = spider_cfg.get("safe_attrs") or ["src", "alt", "href", "title"]
    minify = spider_cfg.get("minify", False)
    cloudflare_cfg = spider_cfg.get("_cloudflare")

    class GeneratedSpider(scrapy.Spider):
        name = "pipeline_generated"
        custom_settings = {
            "LOG_ENABLED": False,
            # Let parse inspect error pages too, so a 403/404 response is
            # printed when it contains no links instead of being discarded by
            # Scrapy's HttpErrorMiddleware.
            "HTTPERROR_ALLOW_ALL": True,
            # some sites rate-limit/reject the default Scrapy user agent
            "USER_AGENT": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            **(
                {
                    "DOWNLOADER_MIDDLEWARES": {
                        "pipeline.stages.scrape.CloudflareContentMiddleware": 543,
                    },
                    "PIPELINE_CLOUDFLARE_CONFIG": cloudflare_cfg,
                }
                if cloudflare_cfg and cloudflare_cfg.get("enabled", True)
                else {}
            ),
        }

        def __init__(self, *args, items=None, diagnostics=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.allowed_domains = list(allowed_domains)
            self.start_urls = [start_url]
            self._collected = items if items is not None else []
            self._diagnostics = diagnostics if diagnostics is not None else []

        def parse(self, response):
            selections = response.xpath(link_xpath)
            if expected_count is not None and len(selections) != expected_count:
                raise CloseSpider(
                    f"expected {expected_count} selections, got {len(selections)}"
                )
            if len(selections) == 0:
                # Keep the response available to the caller. This makes bot
                # checks, error pages, and changed markup visible in CI logs.
                self._diagnostics.append({
                    "url": response.url,
                    "status": response.status,
                    "body": response.text,
                })
                raise CloseSpider("no_links_found")
            if select_index is not None:
                selections = [selections[select_index]]
            for sel in selections:
                value = sel.get()
                resolved = response.urljoin(value)
                if follow:
                    yield scrapy.Request(
                        url=resolved,
                        callback=self.parse_followed,
                        cb_kwargs={"source_url": resolved},
                    )
                else:
                    if inline:
                        # The selected value is content, not a URL.  Track the
                        # page URL while carrying the selected HTML to the
                        # download stage.
                        item = {
                            item_key: response.url,
                            "html": self._clean(value) if clean_html else value,
                        }
                    else:
                        item = {item_key: resolved}
                    self._collected.append(item)
                    yield item

        def parse_followed(self, response, source_url=None):
            item = {item_key: source_url, "html": response.text}
            self._collected.append(item)
            yield item

        @staticmethod
        def _clean(html: str) -> str:
            from lxml_html_clean import Cleaner

            cleaner = Cleaner(
                safe_attrs_only=True,
                safe_attrs=set(safe_attrs),
                kill_tags=["object", "iframe"],
            )
            cleaned = cleaner.clean_html(html)
            if minify:
                from htmlmin import minify as html_minify

                cleaned = html_minify(cleaned)
            return cleaned

    return GeneratedSpider


def run_scrapy_spider(
    spider_cfg: dict, start_url: str, middleware_cfg: dict | None = None
) -> list[dict]:
    """Execute the generated spider in-process; return yielded items.

    When the configured selector matches nothing, print the response body to
    stderr before raising. The scrape/download job uploads no manifest when
    discovery fails, so the log is the only useful diagnostic available in CI.
    """
    from scrapy.crawler import CrawlerProcess

    spider_cfg = dict(spider_cfg)
    if middleware_cfg is not None:
        cloudflare_cfg = middleware_cfg.get("cloudflare")
        spider_cfg["_cloudflare"] = cloudflare_cfg
        if cloudflare_cfg and cloudflare_cfg.get("enabled", True):
            print(
                "Cloudflare Browser Run middleware configured for "
                f"{start_url}",
                file=sys.stderr,
            )
    spider_cls = _build_spider_class(spider_cfg, start_url)
    items: list[dict] = []
    diagnostics: list[dict] = []
    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            process = CrawlerProcess(settings={"LOG_ENABLED": False})
            crawler = process.create_crawler(spider_cls)
            process.crawl(crawler, items=items, diagnostics=diagnostics)
            process.start()
    except Exception as exc:
        raise ScrapeError(f"scrapy crawl failed: {exc}") from exc
    if not items:
        for response in diagnostics:
            print(
                "scrapy response when no links were found "
                f"(status={response['status']}, url={response['url']})",
                file=sys.stderr,
            )
            print(
                f"scrapy selector: {spider_cfg['link_xpath']}",
                file=sys.stderr,
            )
            print("----- BEGIN SCRAPY RESPONSE BODY -----", file=sys.stderr)
            # Prefix each line so arbitrary HTML cannot be interpreted as a
            # GitHub Actions workflow command in the job log.
            body = response["body"]
            print("\n".join(f"| {line}" for line in body.splitlines()), file=sys.stderr)
            print("----- END SCRAPY RESPONSE BODY -----", file=sys.stderr)
        raise ScrapeError("scrapy spider discovered no links")
    return items


def scrape(variant: dict, website_url: str, state=None) -> dict:
    """Run discovery for one variant.

    Returns ``{"links": [...], "items": [...]}`` with all discovered links.
    Raises :class:`ScrapeError` when discovery fails or finds zero links.
    """
    scrape_cfg = variant.get("scrape") or {}
    stype = scrape_cfg.get("type")

    if stype == "scrapy":
        items = run_scrapy_spider(
            scrape_cfg["spider"], website_url, scrape_cfg.get("middleware")
        )
        item_key = scrape_cfg["spider"].get("item_key", "link")
        # Scrapy can yield the same href more than once.  Keep first-seen
        # records so one source is downloaded and extracted exactly once.
        unique_items = []
        seen = set()
        for item in items:
            link = item.get(item_key)
            if link and link not in seen:
                seen.add(link)
                unique_items.append(item)
        items = unique_items
        links = [item[item_key] for item in items]
    elif stype == "static":
        url = scrape_cfg.get("url", website_url)
        items = [{"link": url}]
        links = [url]
    elif stype == "meta_refresh":
        # Change detection via the page's modified_time meta tag; the "link"
        # tracked in the state backend is the website URL itself.
        fetch_modified_time(website_url)  # raises ScrapeError when unreachable
        items = [{"link": website_url}]
        links = [website_url]
    else:
        raise ScrapeError(f"unsupported scrape type {stype!r}")

    if not links:
        raise ScrapeError("discovery found zero links")

    new_links = links
    if state is not None:
        new_links = [link for link in links if not state.link_exists(link)]

    return {"links": links, "new_links": new_links, "items": items}
