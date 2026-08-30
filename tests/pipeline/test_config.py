"""Unit tests for pipeline.config: schema validation and defaults merging."""

import unittest

from pipeline.config import (
    SUPPORTED_LOCATIONS,
    ConfigError,
    load_all,
    load_location,
    validate,
)


def minimal_raw(**overrides):
    raw = {
        "name": "Test Location",
        "website": {"url": "https://example.com/menu"},
        "scrape": {
            "type": "scrapy",
            "spider": {"link_xpath": "//a/@href"},
        },
        "extract": {"type": "text"},
    }
    raw.update(overrides)
    return raw


class TestSchemaValidation(unittest.TestCase):
    def test_minimal_valid(self):
        validate(minimal_raw(), "test")

    def test_missing_name(self):
        raw = minimal_raw()
        del raw["name"]
        with self.assertRaisesRegex(ConfigError, "name"):
            validate(raw, "test")

    def test_missing_website_url(self):
        raw = minimal_raw(website={})
        with self.assertRaisesRegex(ConfigError, "url"):
            validate(raw, "test")

    def test_unknown_top_level_key(self):
        with self.assertRaisesRegex(ConfigError, "unknown key.*bogus"):
            validate(minimal_raw(bogus=1), "test")

    def test_unknown_nested_key(self):
        raw = minimal_raw()
        raw["extract"]["bogus"] = True
        with self.assertRaisesRegex(ConfigError, "unknown key.*bogus"):
            validate(raw, "test")

    def test_wrong_schema_version(self):
        with self.assertRaisesRegex(ConfigError, "schema_version"):
            validate(minimal_raw(schema_version=99), "test")

    def test_bad_scrape_type(self):
        raw = minimal_raw()
        raw["scrape"]["type"] = "selenium"
        with self.assertRaisesRegex(ConfigError, "scrape.type"):
            validate(raw, "test")

    def test_scrapy_requires_link_xpath(self):
        raw = minimal_raw()
        raw["scrape"]["spider"] = {}
        with self.assertRaisesRegex(ConfigError, "link_xpath"):
            validate(raw, "test")

    def test_bad_extract_type(self):
        with self.assertRaisesRegex(ConfigError, "extract.type"):
            validate(minimal_raw(extract={"type": "magic"}), "test")

    def test_bad_provider(self):
        raw = minimal_raw(extract={"type": "text", "model": {"provider": "acme"}})
        with self.assertRaisesRegex(ConfigError, "provider"):
            validate(raw, "test")

    def test_bad_ttl(self):
        with self.assertRaisesRegex(ConfigError, "ttl_weeks"):
            validate(minimal_raw(publish={"ttl_weeks": 0}), "test")

    def test_unknown_preparer(self):
        with self.assertRaisesRegex(ConfigError, "unknown preparer"):
            validate(minimal_raw(prepare=[{"frobnicate": {}}]), "test")

    def test_format_variant_requires_name(self):
        with self.assertRaisesRegex(ConfigError, "name"):
            validate(minimal_raw(formats=[{"scrape": {"type": "static"}}]), "test")

    def test_format_variant_duplicate_name(self):
        variants = [{"name": "a"}, {"name": "a"}]
        with self.assertRaisesRegex(ConfigError, "duplicate"):
            validate(minimal_raw(formats=variants), "test")

    def test_format_variant_valid(self):
        variants = [{
            "name": "pdf",
            "scrape": {"type": "scrapy", "spider": {"link_xpath": "//a/@href"}},
            "extract": {"type": "vision"},
        }]
        validate(minimal_raw(formats=variants), "test")


class TestLoadLocations(unittest.TestCase):
    def test_all_seven_locations_validate(self):
        cfgs = load_all()
        self.assertEqual(set(cfgs), set(SUPPORTED_LOCATIONS))
        self.assertEqual(len(cfgs), 7)

    def test_unknown_location(self):
        with self.assertRaisesRegex(ConfigError, "unknown location"):
            load_location("milchbarpinguin")

    def test_defaults_applied(self):
        cfg = load_location("augustiner")
        extract = cfg.default_variant["extract"]
        self.assertTrue(extract["add_current_weekdays"])
        self.assertEqual(extract["max_tokens"], 5000)
        self.assertEqual(
            extract["model"]["text_model"], "azure/gpt-5-mini@francecentral"
        )
        self.assertFalse(extract["add_current_date"])

    def test_ttl_default_eight_weeks(self):
        for loc in SUPPORTED_LOCATIONS:
            self.assertEqual(load_location(loc).ttl_weeks(), 8, loc)

    def test_lecasino_has_pdf_fallback_variant(self):
        cfg = load_location("lecasino")
        self.assertEqual(cfg.variant_names(), ["default", "pdf"])
        pdf = cfg.variants[1]
        self.assertEqual(pdf["extract"]["type"], "vision")
        self.assertEqual(
            [next(iter(s)) for s in pdf["prepare"]], ["pdfseparate", "pdftoppm"]
        )

    def test_variant_inherits_defaults(self):
        cfg = load_location("lecasino")
        pdf = cfg.variants[1]
        self.assertEqual(pdf["publish"]["ttl_weeks"], 8)
        self.assertEqual(pdf["publish"]["week_key_from"], "first_date")


class TestEffectiveConfigEquivalence(unittest.TestCase):
    """The rendered effective config must equal today's config.py +
    prompt_overrides + workflow shell behavior (phase 1 gate)."""

    def test_augustiner(self):
        cfg = load_location("augustiner").default_variant
        self.assertEqual(
            cfg["extract"]["prompt_prefix"],
            "The input only includes day offers and no week offers! The input is:\n",
        )
        self.assertFalse(cfg["extract"]["add_current_date"])
        self.assertEqual(
            cfg["scrape"]["spider"]["link_xpath"],
            '//a[contains(@href,"pdf") and contains(@href,"Mittag")]/@href',
        )
        self.assertEqual([next(iter(s)) for s in cfg["prepare"]], ["pdftotext"])

    def test_galeria(self):
        cfg = load_location("galeria").default_variant
        model = cfg["extract"]["model"]
        self.assertEqual(model["provider"], "google")
        self.assertEqual(
            model["vision_model"], "vertex/gemini-2.5-flash-lite@europe-central2"
        )
        self.assertEqual(cfg["extract"]["max_tokens"], 2000)
        self.assertEqual(cfg["scrape"]["type"], "static")
        self.assertEqual(
            cfg["scrape"]["url"],
            "https://galeria-restaurant.de/wp-content/uploads/wochenkarte_lunchdeal.pdf",
        )
        pdftoppm = cfg["prepare"][0]["pdftoppm"]
        self.assertEqual(pdftoppm["resolution"], 100)
        self.assertEqual(pdftoppm["format"], "jpeg")

    def test_ratskeller(self):
        cfg = load_location("ratskeller").default_variant
        self.assertEqual(cfg["extract"]["model"]["provider"], "google")
        self.assertEqual(
            cfg["extract"]["model"]["vision_model"],
            "vertex/gemini-2.5-flash-lite@europe-central2",
        )
        self.assertFalse(cfg["extract"]["add_current_date"])
        self.assertEqual(
            [next(iter(s)) for s in cfg["prepare"]], ["pdfseparate", "pdftoppm"]
        )
        self.assertEqual(cfg["extract"]["input_file"], "image.png")

    def test_leos(self):
        cfg = load_location("leos").default_variant
        self.assertEqual(cfg["extract"]["type"], "vision")
        self.assertEqual(cfg["publish"]["week_key_from"], "current_week")
        self.assertEqual(cfg["prepare"], [])

    def test_moritzbastei(self):
        cfg = load_location("moritzbastei").default_variant
        self.assertTrue(cfg["extract"]["add_current_weekdays"])
        spider = cfg["scrape"]["spider"]
        self.assertEqual(spider["count"], 1)
        self.assertTrue(spider["clean_html"])

    def test_emilundmoritz(self):
        cfg = load_location("emilundmoritz").default_variant
        spider = cfg["scrape"]["spider"]
        self.assertEqual(spider["count"], 2)
        self.assertEqual(spider["select_index"], 1)
        self.assertTrue(spider["minify"])

    def test_lecasino_default_is_html_follow(self):
        cfg = load_location("lecasino").default_variant
        self.assertTrue(cfg["scrape"]["spider"]["follow"])
        self.assertEqual(
            cfg["extract"]["prompt_prefix"],
            'The input only includes day offers and no week offers! Each day '
            'contains additional side dishes "Sättigungsbeilage" and '
            '"Gemüsebeilage" which you should not ignore and add each single '
            'of to the particular day. The input is:\n',
        )


if __name__ == "__main__":
    unittest.main()
