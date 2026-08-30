"""Download stage: fetch new content into the run directory.

For scrapy items carrying inline HTML (``follow: true`` spiders) the HTML is
written to a per-link file instead of performing another HTTP download.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from pathlib import Path


class DownloadError(Exception):
    pass


def filename_for_link(link: str, default_ext: str = "") -> str:
    """Derive a safe local filename for a link (mirrors ``curl -sOL``)."""
    path = urllib.parse.urlparse(link).path
    name = Path(urllib.parse.unquote(path)).name
    if not name:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", link).strip("_") or "download"
    if default_ext and not name.endswith(default_ext):
        name += default_ext
    return name


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def download_link(link: str, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / filename_for_link(link)
    try:
        request = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
    except Exception as exc:
        raise DownloadError(f"failed to download {link}: {exc}") from exc
    return target


def download_items(items: list[dict], new_links: list[str], item_key: str,
                   run_dir: str | Path) -> list[dict]:
    """Download content for every new link.

    Returns a list of ``{"link", "file"}`` records (``file`` relative to the
    run directory).
    """
    run_dir = Path(run_dir)
    records = []
    by_link = {item.get(item_key): item for item in items}
    for link in new_links:
        item = by_link.get(link, {})
        if item.get("html") is not None:
            # followed page: content already fetched by the spider
            run_dir.mkdir(parents=True, exist_ok=True)
            name = filename_for_link(link)
            if not name.endswith(".html"):
                name += ".html"
            target = run_dir / name
            target.write_text(item["html"], encoding="utf-8")
        else:
            target = download_link(link, run_dir)
        records.append({"link": link, "file": target.name})
    return records
