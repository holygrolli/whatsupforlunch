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
import re
import sys
import urllib.request
from contextlib import redirect_stdout
from html.parser import HTMLParser

from ..solvegate import SolveGateError, solve_waf


class ScrapeError(Exception):
    """Raised when discovery fails (a variant 'loses', plan section 3.5)."""


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
    challenge_cfg = spider_cfg.get("challenge") or {}
    challenge_attempts = challenge_cfg.get("max_attempts", 1)

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
        }

        def __init__(self, *args, items=None, diagnostics=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.allowed_domains = list(allowed_domains)
            self.start_urls = [start_url]
            self._collected = items if items is not None else []
            self._diagnostics = diagnostics if diagnostics is not None else []

        def parse(self, response):
            is_challenge, detection = self._waf_detection(response)
            if is_challenge:
                try:
                    attempt = response.meta.get("_solvegate_attempts", 0)
                except AttributeError:
                    # Direct unit-test responses are not tied to a Request.
                    attempt = 0
                diagnostic = {
                    "kind": "waf_challenge",
                    "url": response.url,
                    "status": response.status,
                    "detection": detection,
                    "attempt": attempt,
                    "body": response.text,
                }
                self._diagnostics.append(diagnostic)
                if not challenge_cfg:
                    diagnostic["outcome"] = "not configured"
                    raise CloseSpider("cloudflare_challenge")
                if attempt >= challenge_attempts:
                    diagnostic["outcome"] = "attempt limit reached"
                    raise CloseSpider("cloudflare_challenge_after_retry")
                try:
                    clearance = solve_waf(
                        response.url,
                        api_key_env=challenge_cfg.get("api_key_env", "SOLVEGATE_API_KEY"),
                        sitekey=challenge_cfg.get("sitekey", "waf"),
                    )
                except SolveGateError as exc:
                    # CloseSpider's reason is not consistently visible when
                    # Scrapy is embedded in CrawlerProcess. Keep the safe
                    # error in diagnostics so CI explains the failed solve.
                    diagnostic["outcome"] = "solve failed"
                    diagnostic["solvegate_error"] = str(exc)
                    raise CloseSpider(f"solvegate_failed: {exc}") from exc
                diagnostic["outcome"] = "retry scheduled"
                yield scrapy.Request(
                    response.url,
                    callback=self.parse,
                    cookies=clearance.cookies,
                    headers=clearance.headers,
                    dont_filter=True,
                    meta={"_solvegate_attempts": attempt + 1},
                )
                return
            selections = response.xpath(link_xpath)
            if expected_count is not None and len(selections) != expected_count:
                raise CloseSpider(
                    f"expected {expected_count} selections, got {len(selections)}"
                )
            if len(selections) == 0:
                # Keep the response available to the caller. This makes bot
                # checks, error pages, and changed markup visible in CI logs.
                self._diagnostics.append({
                    "kind": "no_links",
                    "url": response.url,
                    "status": response.status,
                    "detection": self._waf_detection(response)[1],
                    "challenge_configured": bool(challenge_cfg),
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
        def _waf_detection(response) -> tuple[bool, str]:
            mitigated = response.headers.get(b"cf-mitigated")
            if mitigated is None:
                mitigated = response.headers.get("cf-mitigated")
            if isinstance(mitigated, bytes):
                mitigated = mitigated.decode("ascii", errors="ignore")
            if str(mitigated).lower() == "challenge":
                return True, "cf-mitigated: challenge"

            # Some Cloudflare responses omit cf-mitigated and return a 200
            # challenge page. Check strong challenge markers independently of
            # status. The generic ``/cdn-cgi/challenge-platform`` path is not
            # sufficient: ordinary pages can include Cloudflare's telemetry
            # script at ``.../scripts/jsd/main.js``.
            body = response.text.lower()
            markers = (
                "<title>just a moment",
                "enable javascript and cookies to continue",
                "window._cf_chl_opt",
                "__cf_chl_tk",
                "cf-chl-widget",
                "/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page",
            )
            found = [marker for marker in markers if marker in body]
            if found:
                return True, "body markers: " + ", ".join(found)

            header_value = str(mitigated) if mitigated is not None else "missing"
            return (
                False,
                f"status={response.status}, cf-mitigated={header_value}, "
                "recognized body markers=none",
            )

        @staticmethod
        def _is_waf_challenge(response) -> bool:
            """Return whether a response looks like a Cloudflare challenge."""
            return GeneratedSpider._waf_detection(response)[0]

        @staticmethod
        def _clean(html: str):
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


def run_scrapy_spider(spider_cfg: dict, start_url: str) -> list[dict]:
    """Execute the generated spider in-process; return yielded items.

    When the configured selector matches nothing, print the response body to
    stderr before raising. The scrape/download job uploads no manifest when
    discovery fails, so the log is the only useful diagnostic available in CI.
    """
    from scrapy.crawler import CrawlerProcess

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
        if not diagnostics:
            print(
                "scrapy produced no items and no response diagnostics; "
                "the callback may not have run",
                file=sys.stderr,
            )
        for response in diagnostics:
            kind = response.get("kind", "no_links")
            print(
                "scrapy response produced no links "
                f"(kind={kind}, status={response['status']}, url={response['url']})",
                file=sys.stderr,
            )
            if response.get("detection"):
                print(
                    f"cloudflare detection: {response['detection']}",
                    file=sys.stderr,
                )
            if "challenge_configured" in response:
                print(
                    f"solvegate configured: {response['challenge_configured']}",
                    file=sys.stderr,
                )
            if "attempt" in response:
                print(
                    f"solvegate attempt: {response['attempt']}",
                    file=sys.stderr,
                )
            if response.get("outcome"):
                print(
                    f"solvegate outcome: {response['outcome']}",
                    file=sys.stderr,
                )
            if response.get("solvegate_error"):
                print(
                    f"solvegate error: {response['solvegate_error']}",
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
        spider_cfg = dict(scrape_cfg["spider"])
        if scrape_cfg.get("challenge") is not None:
            spider_cfg["challenge"] = scrape_cfg["challenge"]
        items = run_scrapy_spider(spider_cfg, website_url)
        item_key = spider_cfg.get("item_key", "link")
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
