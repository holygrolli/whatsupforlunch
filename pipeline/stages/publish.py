"""Publish stage: write data/<loc>/ JSONs and mark links processed.

A link is marked processed (``add_link``, TTL from config) only after its menu
JSON has been written and validated — a failed extraction never marks a link
processed, preserving today's retry semantics.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

DATE_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WEEK_KEY_RE = re.compile(r"^\d{4}-W\d{2}$")


class PublishError(Exception):
    pass


def validate_menu_json(menu: dict) -> None:
    """Validate the existing menu JSON contract (decision 2: unchanged shape)."""
    if not isinstance(menu, dict) or not menu:
        raise PublishError("menu JSON must be a non-empty object")
    has_day = any(DATE_KEY_RE.match(k) for k in menu)
    has_week = any(WEEK_KEY_RE.match(k) for k in menu)
    if not (has_day or has_week):
        raise PublishError(
            "menu JSON must contain at least one YYYY-MM-DD day key or "
            "YYYY-Www week key"
        )
    for key, meals in menu.items():
        if not isinstance(meals, list):
            raise PublishError(f"menu[{key!r}] must be a list of meals")
        for meal in meals:
            if not isinstance(meal, dict) or "desc" not in meal:
                raise PublishError(
                    f"menu[{key!r}] entries must be meal objects with a 'desc' key"
                )


def week_key_for(menu: dict, source: str = "first_date", now: datetime | None = None) -> str:
    """Derive the output ``YYYY-WW.json`` name (mirrors the workflow shell)."""
    if source == "first_date":
        dates = sorted(k for k in menu if DATE_KEY_RE.match(k))
        if not dates:
            raise PublishError(
                "no YYYY-MM-DD key in menu JSON to derive the week from"
            )
        first = datetime.strptime(dates[0], "%Y-%m-%d")
        return first.strftime("%G-W%V")
    if source == "week_key":
        weeks = sorted(k for k in menu if WEEK_KEY_RE.match(k))
        if not weeks:
            raise PublishError("no YYYY-Www key in menu JSON")
        return weeks[0]
    if source == "current_week":
        now = now or datetime.today()
        week_start = now - timedelta(days=now.weekday())
        if now.weekday() > 4:  # weekend -> next week (same as extract stage)
            week_start += timedelta(days=7)
        return week_start.strftime("%G-W%V")
    raise PublishError(f"unknown week_key_from source {source!r}")


def publish(menu: dict, data_dir: str | Path, link: str | None, state,
            ttl_weeks: int = 8, week_key_source: str = "first_date",
            now: datetime | None = None) -> Path:
    """Validate, write ``<week>.json`` into ``data_dir``, then mark the link.

    Returns the path of the written file.
    """
    validate_menu_json(menu)
    week_key = week_key_for(menu, week_key_source, now=now)
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / f"{week_key}.json"
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(menu, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    if link is not None and state is not None:
        state.add_link(link, ttl_weeks=ttl_weeks)
    return target
