"""Location configuration loading and validation.

Loads ``locations/<name>/location.yaml``, merges it with the shared defaults in
``pipeline/defaults.yaml`` and validates the result against the versioned schema
(``schema_version: 1``). Raises :class:`ConfigError` with a precise message on
unknown keys, wrong types, or missing required keys.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCATIONS_DIR = REPO_ROOT / "locations"
DEFAULTS_FILE = Path(__file__).resolve().parent / "defaults.yaml"

# The seven supported locations (plan section 1, decision 1).
SUPPORTED_LOCATIONS = (
    "augustiner",
    "emilundmoritz",
    "galeria",
    "lecasino",
    "leos",
    "moritzbastei",
    "ratskeller",
)

SCRAPE_TYPES = ("scrapy", "scrapy-patchright", "static", "meta_refresh")
EXTRACT_TYPES = ("vision", "text")
MODEL_PROVIDERS = ("openai", "google")
PREPARER_TYPES = ("pdfseparate", "pdftoppm", "pdftotext", "html_to_text", "reduce_to_text")
WEEK_KEY_SOURCES = ("first_date", "week_key", "current_week")

# Known keys per mapping, used for unknown-key validation. ``None`` means the
# mapping values are free-form (e.g. spider settings passed through to scrapy).
_SCHEMA = {
    "": {
        "schema_version", "name", "enabled", "website", "scrape", "download",
        "prepare", "extract", "publish", "schedule", "formats",
    },
    "website": {"url", "details"},
    "scrape": {"type", "spider", "url", "middleware", "patchright"},
    "scrape.patchright": {
        "enabled", "wait_until", "wait_for_selector", "navigation_timeout_ms",
        "wait_for_timeout_ms", "launch_options",
    },
    "scrape.patchright.launch_options": {"headless"},
    "scrape.middleware": {"cloudflare"},
    "scrape.middleware.cloudflare": {
        "enabled", "wait_until", "wait_for_timeout", "action_timeout",
    },
    "scrape.spider": None,
    "download": {"formats"},
    "extract": {
        "type", "input_file", "prompt_file", "prompt", "prompt_prefix",
        "add_current_date", "add_current_weekdays", "max_tokens", "model",
    },
    "extract.model": {"provider", "vision_model", "text_model"},
    "publish": {"week_key_from", "ttl_weeks"},
    "schedule": {"cron"},
    "formats[]": {"name", "scrape", "download", "prepare", "extract", "publish"},
}


class ConfigError(Exception):
    """Raised for any location configuration problem (exit code 2)."""


def _load_yaml(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge ``override`` onto ``base`` (override wins per key)."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _check_keys(mapping: dict, allowed, context: str) -> None:
    if allowed is None or not isinstance(mapping, dict):
        return
    unknown = set(mapping) - allowed
    if unknown:
        raise ConfigError(
            f"unknown key(s) {sorted(unknown)} in '{context}'; "
            f"allowed: {sorted(allowed)}"
        )


def _require(mapping: dict, key: str, context: str) -> None:
    if key not in mapping or mapping[key] is None:
        raise ConfigError(f"missing required key '{key}' in '{context}'")


def _check_type(mapping: dict, key: str, types, context: str) -> None:
    if key in mapping and mapping[key] is not None and not isinstance(mapping[key], types):
        raise ConfigError(
            f"key '{key}' in '{context}' must be of type "
            f"{[t.__name__ for t in types] if isinstance(types, tuple) else types.__name__}, "
            f"got {type(mapping[key]).__name__}"
        )


def _validate_variant(variant: dict, context: str, full: bool) -> None:
    """Validate one scrape/download/prepare/extract/publish variant.

    ``full`` is True for the default variant (website/scrape required) and
    False for ``formats:`` entries (which only override blocks).
    """
    if not full:
        _check_keys(variant, _SCHEMA["formats[]"], context)

    scrape = variant.get("scrape")
    if full and scrape is None:
        raise ConfigError(f"missing required key 'scrape' in '{context}'")
    if scrape is not None:
        _check_keys(scrape, _SCHEMA["scrape"], f"{context}.scrape")
        _require(scrape, "type", f"{context}.scrape")
        stype = scrape["type"]
        if stype not in SCRAPE_TYPES:
            raise ConfigError(
                f"scrape.type in '{context}' must be one of {SCRAPE_TYPES}, got {stype!r}"
            )
        middleware = scrape.get("middleware")
        if middleware is not None:
            _check_keys(middleware, _SCHEMA["scrape.middleware"], f"{context}.scrape.middleware")
            cloudflare = middleware.get("cloudflare")
            if cloudflare is not None:
                _check_keys(
                    cloudflare,
                    _SCHEMA["scrape.middleware.cloudflare"],
                    f"{context}.scrape.middleware.cloudflare",
                )
                _check_type(
                    cloudflare, "enabled", bool,
                    f"{context}.scrape.middleware.cloudflare",
                )
                wait_until = cloudflare.get("wait_until")
                if wait_until is not None and wait_until not in (
                    "load", "domcontentloaded", "networkidle0", "networkidle2",
                ):
                    raise ConfigError(
                        f"wait_until in '{context}.scrape.middleware.cloudflare' "
                        f"must be a supported Cloudflare wait condition, got {wait_until!r}"
                    )
                _check_type(
                    cloudflare, "wait_for_timeout", int,
                    f"{context}.scrape.middleware.cloudflare",
                )
                _check_type(
                    cloudflare, "action_timeout", int,
                    f"{context}.scrape.middleware.cloudflare",
                )
        patchright = scrape.get("patchright")
        if patchright is not None:
            _check_keys(
                patchright, _SCHEMA["scrape.patchright"],
                f"{context}.scrape.patchright",
            )
            _check_type(patchright, "enabled", bool, f"{context}.scrape.patchright")
            _check_type(patchright, "wait_until", str, f"{context}.scrape.patchright")
            if patchright.get("wait_until", "domcontentloaded") not in {
                "commit", "domcontentloaded", "load", "networkidle"
            }:
                raise ConfigError(
                    f"scrape.patchright.wait_until in '{context}' has an unsupported value"
                )
            _check_type(
                patchright, "wait_for_selector", str,
                f"{context}.scrape.patchright",
            )
            _check_type(
                patchright, "navigation_timeout_ms", int,
                f"{context}.scrape.patchright",
            )
            if patchright.get("navigation_timeout_ms", 60000) <= 0:
                raise ConfigError(
                    f"scrape.patchright.navigation_timeout_ms in '{context}' must be positive"
                )
            _check_type(
                patchright, "wait_for_timeout_ms", int,
                f"{context}.scrape.patchright",
            )
            if patchright.get("wait_for_timeout_ms", 0) < 0:
                raise ConfigError(
                    f"scrape.patchright.wait_for_timeout_ms in '{context}' must not be negative"
                )
            launch_options = patchright.get("launch_options")
            if launch_options is not None:
                if not isinstance(launch_options, dict):
                    raise ConfigError(
                        f"scrape.patchright.launch_options in '{context}' must be a mapping"
                    )
                _check_keys(
                    launch_options, _SCHEMA["scrape.patchright.launch_options"],
                    f"{context}.scrape.patchright.launch_options",
                )
                _check_type(
                    launch_options, "headless", bool,
                    f"{context}.scrape.patchright.launch_options",
                )

        browser_scrape = stype in ("scrapy", "scrapy-patchright")
        if stype == "scrapy-patchright":
            if patchright is None:
                raise ConfigError(
                    f"scrape.patchright is required for scrapy-patchright in '{context}'"
                )
            if patchright.get("enabled", True) is False:
                raise ConfigError(
                    f"scrape.patchright.enabled in '{context}' cannot be false for scrapy-patchright"
                )
        if browser_scrape:
            spider = scrape.get("spider")
            if not isinstance(spider, dict) or not spider.get("link_xpath"):
                raise ConfigError(
                    f"scrape.spider.link_xpath is required for scrapy in '{context}'"
                )
            _check_type(spider, "allowed_domains", list, f"{context}.scrape.spider")
            _check_type(spider, "follow", bool, f"{context}.scrape.spider")
            _check_type(spider, "inline", bool, f"{context}.scrape.spider")
            _check_type(spider, "item_key", str, f"{context}.scrape.spider")
            _check_type(spider, "count", int, f"{context}.scrape.spider")
        if stype in ("static", "meta_refresh"):
            _check_type(scrape, "url", str, f"{context}.scrape")

    download = variant.get("download")
    if download is not None:
        _check_keys(download, _SCHEMA["download"], f"{context}.download")
        _check_type(download, "formats", list, f"{context}.download")

    prepare = variant.get("prepare")
    if prepare is not None:
        if not isinstance(prepare, list):
            raise ConfigError(f"prepare in '{context}' must be a list of preparers")
        for i, step in enumerate(prepare):
            if not isinstance(step, dict) or len(step) != 1:
                raise ConfigError(
                    f"prepare[{i}] in '{context}' must be a single-key mapping "
                    f"(one of {PREPARER_TYPES})"
                )
            name = next(iter(step))
            if name not in PREPARER_TYPES:
                raise ConfigError(
                    f"unknown preparer {name!r} in '{context}'; allowed: {PREPARER_TYPES}"
                )

    extract = variant.get("extract")
    if full and extract is None:
        raise ConfigError(f"missing required key 'extract' in '{context}'")
    if extract is not None:
        _check_keys(extract, _SCHEMA["extract"], f"{context}.extract")
        etype = extract.get("type")
        if etype is not None and etype not in EXTRACT_TYPES:
            raise ConfigError(
                f"extract.type in '{context}' must be one of {EXTRACT_TYPES}, got {etype!r}"
            )
        _check_type(extract, "input_file", str, f"{context}.extract")
        _check_type(extract, "prompt_file", str, f"{context}.extract")
        _check_type(extract, "prompt", str, f"{context}.extract")
        _check_type(extract, "prompt_prefix", str, f"{context}.extract")
        _check_type(extract, "add_current_date", bool, f"{context}.extract")
        _check_type(extract, "add_current_weekdays", bool, f"{context}.extract")
        _check_type(extract, "max_tokens", int, f"{context}.extract")
        model = extract.get("model")
        if model is not None:
            _check_keys(model, _SCHEMA["extract.model"], f"{context}.extract.model")
            provider = model.get("provider")
            if provider is not None and provider not in MODEL_PROVIDERS:
                raise ConfigError(
                    f"extract.model.provider in '{context}' must be one of "
                    f"{MODEL_PROVIDERS}, got {provider!r}"
                )

    publish = variant.get("publish")
    if publish is not None:
        _check_keys(publish, _SCHEMA["publish"], f"{context}.publish")
        src = publish.get("week_key_from")
        if src is not None and src not in WEEK_KEY_SOURCES:
            raise ConfigError(
                f"publish.week_key_from in '{context}' must be one of "
                f"{WEEK_KEY_SOURCES}, got {src!r}"
            )
        ttl = publish.get("ttl_weeks")
        if ttl is not None and (not isinstance(ttl, int) or ttl <= 0):
            raise ConfigError(
                f"publish.ttl_weeks in '{context}' must be a positive int, got {ttl!r}"
            )


def validate(raw: dict, location: str) -> None:
    """Validate a raw (unmerged) location YAML mapping."""
    if not isinstance(raw, dict):
        raise ConfigError(f"location.yaml for '{location}' must be a mapping")
    _check_keys(raw, _SCHEMA[""], location)

    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ConfigError(
            f"unsupported schema_version {version!r} in '{location}'; "
            f"expected {SCHEMA_VERSION}"
        )

    _require(raw, "name", location)
    _check_type(raw, "name", str, location)
    _check_type(raw, "enabled", bool, location)

    website = raw.get("website")
    if not isinstance(website, dict):
        raise ConfigError(f"missing required key 'website' in '{location}'")
    _check_keys(website, _SCHEMA["website"], f"{location}.website")
    _require(website, "url", f"{location}.website")
    _check_type(website, "url", str, f"{location}.website")
    _check_type(website, "details", list, f"{location}.website")

    _validate_variant(raw, location, full=True)

    formats = raw.get("formats", [])
    if formats is None:
        formats = []
    if not isinstance(formats, list):
        raise ConfigError(f"formats in '{location}' must be a list")
    seen = set()
    for i, variant in enumerate(formats):
        if not isinstance(variant, dict):
            raise ConfigError(f"formats[{i}] in '{location}' must be a mapping")
        name = variant.get("name")
        if not name or not isinstance(name, str):
            raise ConfigError(f"formats[{i}] in '{location}' requires a string 'name'")
        if name in seen:
            raise ConfigError(f"duplicate format variant name {name!r} in '{location}'")
        seen.add(name)
        _validate_variant(variant, f"{location}.formats[{name}]", full=False)

    schedule = raw.get("schedule")
    if schedule is not None:
        _check_keys(schedule, _SCHEMA["schedule"], f"{location}.schedule")
        _check_type(schedule, "cron", str, f"{location}.schedule")


def load_defaults() -> dict:
    defaults = _load_yaml(DEFAULTS_FILE)
    if not isinstance(defaults, dict):
        raise ConfigError(f"defaults file {DEFAULTS_FILE} must be a mapping")
    return defaults


class LocationConfig:
    """Validated, merged configuration for one location."""

    def __init__(self, location: str, raw: dict, defaults: dict):
        self.location = location
        self.raw = raw
        self.defaults = defaults
        self.name = raw["name"]
        self.enabled = raw.get("enabled", True)
        self.website = raw["website"]
        self.schedule = raw.get("schedule") or {}

        # Default variant: raw blocks merged with shared defaults.
        self.default_variant = self._build_variant(raw, "default")
        # Additional format variants, in declared order (plan section 3.5).
        self.variants = [self.default_variant]
        for entry in raw.get("formats") or []:
            self.variants.append(self._build_variant(entry, entry["name"]))

    def _build_variant(self, source: dict, name: str) -> dict:
        variant = {"name": name}
        for block in ("scrape", "download", "prepare", "extract", "publish"):
            if block in source:
                variant[block] = _merge(
                    {block: self.defaults.get(block)}, {block: source[block]}
                )[block] if isinstance(self.defaults.get(block), dict) else copy.deepcopy(
                    source[block]
                )
            elif block in self.defaults:
                variant[block] = copy.deepcopy(self.defaults[block])
        # variants without their own publish block inherit the default variant's
        if "publish" not in variant and name != "default":
            variant["publish"] = copy.deepcopy(self.raw.get("publish", self.defaults.get("publish", {})))
        return variant

    def variant_names(self):
        return [v["name"] for v in self.variants]

    @property
    def data_dir(self) -> Path:
        return REPO_ROOT / "data" / self.location

    @property
    def location_dir(self) -> Path:
        return LOCATIONS_DIR / self.location

    def ttl_weeks(self) -> int:
        """Default TTL in weeks (decision 4: omitted override always means 8)."""
        publish = self.default_variant.get("publish") or {}
        return publish.get("ttl_weeks", 8)

    def prompts(self) -> dict:
        return self.defaults.get("prompts", {})


def load_location(location: str) -> LocationConfig:
    """Load, validate and merge the configuration for one location."""
    if location not in SUPPORTED_LOCATIONS:
        raise ConfigError(
            f"unknown location {location!r}; supported: {list(SUPPORTED_LOCATIONS)}"
        )
    path = LOCATIONS_DIR / location / "location.yaml"
    if not path.is_file():
        raise ConfigError(f"no location.yaml found at {path}")
    raw = _load_yaml(path)
    validate(raw, location)
    return LocationConfig(location, raw, load_defaults())


def load_all() -> dict:
    """Load all supported locations; returns {location: LocationConfig}."""
    return {loc: load_location(loc) for loc in SUPPORTED_LOCATIONS}
