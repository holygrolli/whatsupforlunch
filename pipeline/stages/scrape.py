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
    clean_html = spider_cfg.get("clean_html", False)
    safe_attrs = spider_cfg.get("safe_attrs") or ["src", "alt", "href", "title"]
    minify = spider_cfg.get("minify", False)

    class GeneratedSpider(scrapy.Spider):
        name = "pipeline_generated"
        custom_settings = {
            "LOG_ENABLED": False,
            # some sites rate-limit/reject the default Scrapy user agent
            "USER_AGENT": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
        }

        def __init__(self, *args, items=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.allowed_domains = list(allowed_domains)
            self.start_urls = [start_url]
            self._collected = items if items is not None else []

        def parse(self, response):
            selections = response.xpath(link_xpath)
            if expected_count is not None and len(selections) != expected_count:
                raise CloseSpider(
                    f"expected {expected_count} selections, got {len(selections)}"
                )
            if len(selections) == 0:
                raise CloseSpider("no_links_found")
            if select_index is not None:
                selections = [selections[select_index]]
            for sel in selections:
                value = sel.get()
                if clean_html:
                    value = self._clean(value)
                if follow:
                    yield scrapy.Request(
                        url=response.urljoin(value),
                        callback=self.parse_followed,
                        cb_kwargs={"source_url": response.urljoin(value)},
                    )
                else:
                    item = {item_key: value}
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


def run_scrapy_spider(spider_cfg: dict, start_url: str) -> list[dict]:
    """Execute the generated spider in-process; return yielded items."""
    from scrapy.crawler import CrawlerProcess

    spider_cls = _build_spider_class(spider_cfg, start_url)
    items: list[dict] = []
    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            process = CrawlerProcess(settings={"LOG_ENABLED": False})
            crawler = process.create_crawler(spider_cls)
            process.crawl(crawler, items=items)
            process.start()
    except Exception as exc:
        raise ScrapeError(f"scrapy crawl failed: {exc}") from exc
    if not items:
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
        items = run_scrapy_spider(scrape_cfg["spider"], website_url)
        item_key = scrape_cfg["spider"].get("item_key", "link")
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
