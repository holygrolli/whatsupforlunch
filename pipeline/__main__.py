"""Pipeline CLI entry point.

Usage::

    python -m pipeline <location> <stage> [options]

Stages: scrape | download | prepare | extract | publish | all | migrate-state

Exit codes (plan section 3.3):
    0  success / nothing to do
    1  processing failure
    2  configuration error
    3  state-backend unavailable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, LocationConfig, load_location
from .manifest import Manifest
from .stages import scrape as scrape_stage
from .stages.download import DownloadError, download_items
from .stages.extract import ExtractError, extract
from .stages.prepare import PrepareError, prepare_one
from .stages.publish import PublishError, publish
from .stages.scrape import ScrapeError, scrape

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2
EXIT_STATE = 3

STAGES = ("scrape", "download", "prepare", "extract", "publish", "all",
          "migrate-state")


def _state_backend(args):
    """Build the state backend; ``--no-state`` selects a null backend."""
    import os

    if getattr(args, "no_state", False) or os.environ.get("PIPELINE_NO_STATE"):
        return None
    from .state.dynamodb import LinkState, StateBackendUnavailable

    try:
        return LinkState()
    except StateBackendUnavailable as exc:
        print(f"state backend unavailable: {exc}", file=sys.stderr)
        sys.exit(EXIT_STATE)


def _select_variant(cfg: LocationConfig, state) -> tuple[dict, dict]:
    """Try variants in order; first whose discovery succeeds wins (3.5).

    A variant wins when scraping completes without error and yields at least
    one link. A variant with only already-processed links is a valid win
    ("format still active, nothing new").
    """
    last_error = None
    for variant in cfg.variants:
        try:
            result = scrape(variant, cfg.website["url"], state=state)
            return variant, result
        except ScrapeError as exc:
            print(f"variant '{variant['name']}' lost: {exc}", file=sys.stderr)
            last_error = exc
    raise ScrapeError(
        f"all {len(cfg.variants)} variant(s) lost; last error: {last_error}"
    )


def _item_key(variant: dict) -> str:
    return (variant.get("scrape", {}).get("spider", {}) or {}).get(
        "item_key", "link"
    )


def cmd_scrape(cfg, args, manifest) -> int:
    state = _state_backend(args)
    variant, result = _select_variant(cfg, state)
    manifest.data["variant"] = variant["name"]
    manifest.data["links_discovered"] = result["links"]
    manifest.data["links_new"] = result["new_links"]
    manifest.data["scrape_items"] = result["items"]
    manifest.stage_done("scrape")
    manifest.write()
    for link in result["new_links"]:
        print(link)
    if not result["new_links"]:
        print("no new links", file=sys.stderr)
    return EXIT_OK


def cmd_download(cfg, args, manifest) -> int:
    if not Manifest.exists(args.run_dir):
        return cmd_scrape(cfg, args, manifest) or cmd_download(cfg, args, manifest)
    manifest = Manifest.load(args.run_dir)
    variant = _variant_by_name(cfg, manifest.data.get("variant"))
    records = download_items(
        manifest.data.get("scrape_items", []),
        manifest.data["links_new"],
        _item_key(variant),
        args.run_dir,
    )
    manifest.data["files_downloaded"] = records
    manifest.stage_done("download")
    manifest.write()
    for record in records:
        print(record["file"])
    return EXIT_OK


def _variant_by_name(cfg, name) -> dict:
    for variant in cfg.variants:
        if variant["name"] == name:
            return variant
    return cfg.default_variant


def _prepare_record(run_dir: Path, record: dict, variant: dict) -> list[str]:
    steps = variant.get("prepare") or []
    if not steps:
        # No prepare pipeline: the downloaded file is the extraction input.
        extract_cfg = variant.get("extract", {})
        target = run_dir / extract_cfg.get("input_file", "chatgpt_user.txt")
        source = run_dir / record["file"]
        if source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())
        return [target.name]
    return prepare_one(run_dir, record["file"], steps)


def cmd_prepare(cfg, args, manifest) -> int:
    manifest = Manifest.load(args.run_dir)
    variant = _variant_by_name(cfg, manifest.data.get("variant"))
    run_dir = Path(args.run_dir)
    prepared = []
    for record in manifest.data.get("files_downloaded", []):
        files = _prepare_record(run_dir, record, variant)
        prepared.append({"link": record["link"], "source": record["file"],
                         "files": files})
    manifest.data["files_prepared"] = prepared
    manifest.stage_done("prepare")
    manifest.write()
    for entry in prepared:
        for f in entry["files"]:
            print(f)
    return EXIT_OK


def cmd_extract(cfg, args, manifest) -> int:
    manifest = Manifest.load(args.run_dir)
    variant = _variant_by_name(cfg, manifest.data.get("variant"))
    extract_cfg = variant.get("extract", {})
    run_dir = Path(args.run_dir)
    results = []
    prepared = manifest.data.get("files_prepared", [])
    if not prepared:
        print("nothing prepared; skipping extract", file=sys.stderr)
        return EXIT_OK
    failures = 0
    for entry in prepared:
        for f in entry["files"]:
            work_dir = run_dir
            input_file = extract_cfg.get("input_file", "chatgpt_user.txt")
            if f != input_file:
                # Multiple prepared files (e.g. separated PDF pages): run the
                # extraction per file in its own subdirectory.
                work_dir = run_dir / Path(f).stem
                work_dir.mkdir(parents=True, exist_ok=True)
                target = work_dir / input_file
                target.write_bytes((run_dir / f).read_bytes())
            try:
                menu = extract(
                    work_dir, extract_cfg, cfg.prompts(), cfg.location_dir,
                    base_url=args.model_base_url, api_key=args.model_api_key,
                    model_override=args.model,
                )
                results.append({"link": entry["link"], "file": f,
                                "work_dir": str(work_dir), "ok": True,
                                "menu": menu})
            except (ExtractError, Exception) as exc:  # noqa: BLE001
                failures += 1
                results.append({"link": entry["link"], "file": f,
                                "work_dir": str(work_dir), "ok": False,
                                "error": str(exc)})
                print(f"extraction failed for {f}: {exc}", file=sys.stderr)
    manifest.data["extraction_results"] = [
        {k: v for k, v in r.items() if k != "menu"} for r in results
    ]
    manifest.stage_done("extract")
    manifest.write()
    # persist menus for the publish stage
    menus = []
    for r in results:
        if r["ok"]:
            menus.append({"link": r["link"], "file": r["file"], "menu": r["menu"]})
    with open(run_dir / "menus.json", "w", encoding="utf-8") as fh:
        json.dump(menus, fh, ensure_ascii=False)
    return EXIT_FAILURE if failures and not menus else EXIT_OK


def cmd_publish(cfg, args, manifest) -> int:
    manifest = Manifest.load(args.run_dir)
    variant = _variant_by_name(cfg, manifest.data.get("variant"))
    publish_cfg = variant.get("publish", {})
    state = _state_backend(args)
    run_dir = Path(args.run_dir)
    menus_file = run_dir / "menus.json"
    if not menus_file.is_file():
        print("no menus.json; nothing to publish", file=sys.stderr)
        return EXIT_OK
    with open(menus_file, "r", encoding="utf-8") as fh:
        menus = json.load(fh)
    marked = []
    failures = 0
    for entry in menus:
        try:
            target = publish(
                entry["menu"], cfg.data_dir, entry.get("link"), state,
                ttl_weeks=publish_cfg.get("ttl_weeks", 8),
                week_key_source=publish_cfg.get("week_key_from", "first_date"),
            )
            marked.append(entry.get("link"))
            print(target)
        except PublishError as exc:
            failures += 1
            print(f"publish failed for {entry.get('link')}: {exc}",
                  file=sys.stderr)
    manifest.data["links_marked"] = [m for m in marked if m]
    manifest.stage_done("publish")
    manifest.write()
    return EXIT_FAILURE if failures else EXIT_OK


def cmd_all(cfg, args, manifest) -> int:
    state = _state_backend(args)
    try:
        variant, result = _select_variant(cfg, state)
    except ScrapeError as exc:
        print(f"scrape failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    manifest.data["variant"] = variant["name"]
    manifest.data["links_discovered"] = result["links"]
    manifest.data["links_new"] = result["new_links"]
    manifest.data["scrape_items"] = result["items"]
    manifest.stage_done("scrape")
    manifest.write()
    if not result["new_links"]:
        print(f"{cfg.location}: no new links; nothing to do")
        return EXIT_OK
    for stage_fn in (cmd_download, cmd_prepare, cmd_extract, cmd_publish):
        rc = stage_fn(cfg, args, manifest)
        if rc != EXIT_OK:
            return rc
        manifest = Manifest.load(args.run_dir)
    return EXIT_OK


def cmd_migrate_state(cfg, args, manifest) -> int:
    """One-time backfill of scraped_done.txt entries into DynamoDB (section 4).

    Dry-run by default; ``--apply`` writes. Entries already present and
    unexpired are skipped. Failures abort the migration for this location.
    """
    from .state.dynamodb import StateBackendUnavailable

    done_file = cfg.data_dir / "scraped_done.txt"
    if not done_file.is_file():
        print(f"{cfg.location}: no scraped_done.txt; nothing to migrate")
        return EXIT_OK
    links = [line.strip() for line in done_file.read_text().splitlines()
             if line.strip()]
    print(f"{cfg.location}: {len(links)} entries in scraped_done.txt")
    if not args.apply:
        for link in links:
            print(f"DRY-RUN would add: {link} (ttl={args.ttl_weeks}w)")
        print("dry-run; re-run with --apply to write")
        return EXIT_OK
    state = _state_backend(args)
    added = skipped = failed = 0
    for link in links:
        try:
            if state.link_exists(link):
                skipped += 1
                continue
            state.add_link(link, ttl_weeks=args.ttl_weeks)
            added += 1
        except StateBackendUnavailable as exc:
            failed += 1
            print(f"failed: {link}: {exc}", file=sys.stderr)
            break  # abort this location, not the others
    print(f"{cfg.location}: added={added} skipped={skipped} failed={failed}")
    return EXIT_FAILURE if failed else EXIT_OK


STAGE_FUNCS = {
    "scrape": cmd_scrape,
    "download": cmd_download,
    "prepare": cmd_prepare,
    "extract": cmd_extract,
    "publish": cmd_publish,
    "all": cmd_all,
    "migrate-state": cmd_migrate_state,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline",
                                     description=__doc__)
    parser.add_argument("location", help="location name (directory under locations/)")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--run-dir", default="tmp",
                        help="run directory for manifest and artifacts (default: tmp)")
    parser.add_argument("--no-state", action="store_true",
                        help="disable the DynamoDB state backend (local testing)")
    parser.add_argument("--apply", action="store_true",
                        help="migrate-state: actually write (default is dry-run)")
    parser.add_argument("--ttl-weeks", type=int, default=8,
                        help="TTL override in weeks (default: 8, decision 4)")
    parser.add_argument("--model-base-url", default=None,
                        help="override the model provider base URL (testing/proxies)")
    parser.add_argument("--model-api-key", default=None,
                        help="override the model provider API key (testing/proxies)")
    parser.add_argument("--model", default=None,
                        help="override the model id for both text and vision calls")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_location(args.location)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    manifest = Manifest(cfg.location, args.run_dir)
    try:
        return STAGE_FUNCS[args.stage](cfg, args, manifest)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (ScrapeError, DownloadError, PrepareError, PublishError) as exc:
        print(f"{args.stage} failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
