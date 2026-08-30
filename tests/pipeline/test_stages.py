"""Unit tests for pipeline stages with mocked HTTP/model/DynamoDB."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pipeline.stages.extract import MealChat, extract_json_object, ExtractError
from pipeline.stages.publish import (
    PublishError,
    publish,
    validate_menu_json,
    week_key_for,
)
from pipeline.stages.scrape import ScrapeError, _build_spider_class, scrape
from pipeline.stages.download import download_items, filename_for_link
from pipeline.stages.prepare import prepare_one, PrepareError


class FakeState:
    """In-memory stand-in for the DynamoDB state backend."""

    def __init__(self, existing=()):
        self.links = dict.fromkeys(existing, 8)
        self.added = []

    def link_exists(self, link):
        return link in self.links

    def add_link(self, link, ttl_weeks=8):
        self.links[link] = ttl_weeks
        self.added.append((link, ttl_weeks))
        return True


class TestLegacyState(unittest.TestCase):
    def test_reads_legacy_entries_but_delegates_writes(self):
        from pipeline.__main__ import _LegacyAwareState

        backend = FakeState()
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "scraped_done.txt"
            marker.write_text("https://old.example/menu.pdf\n")
            state = _LegacyAwareState(backend, marker)
            self.assertTrue(state.link_exists("https://old.example/menu.pdf"))
            self.assertFalse(state.link_exists("https://new.example/menu.pdf"))
            state.add_link("https://new.example/menu.pdf", ttl_weeks=8)
        self.assertEqual(backend.added, [("https://new.example/menu.pdf", 8)])


class TestExtractJsonObject(unittest.TestCase):
    def test_carves_object_from_prose(self):
        text = 'Here is the menu.\n  {\n    "2024-01-01": []\n  }\nSome explanation.'
        self.assertEqual(
            json.loads(extract_json_object(text)), {"2024-01-01": []}
        )

    def test_no_json(self):
        with self.assertRaises(ExtractError):
            extract_json_object("no json here")


class TestMealChatTemplating(unittest.TestCase):
    """The {MC_TODAY}/{MC_WEEKSTART} templating and weekend-rolls-to-next-week
    logic must be preserved verbatim (prompt regression tests depend on it)."""

    def _chat(self, **kwargs):
        defaults = dict(
            user_message="hello",
            system_prompt="schema: {MC_JSON_SCHEMA} today: {MC_TODAY} week: {MC_WEEKSTART}",
            json_schema="{}",
        )
        defaults.update(kwargs)
        return MealChat(**defaults)

    def test_weekday_date_override(self):
        # 2024-01-04 is a Thursday -> week starts Monday 2024-01-01
        chat = self._chat(date_override="2024-01-04")
        self.assertEqual(chat.week_start.strftime("%Y-%m-%d"), "2024-01-01")
        self.assertEqual(chat.week_start.strftime("%G-W%V"), "2024-W01")

    def test_weekend_rolls_to_next_week(self):
        # 2023-12-22 is a Friday -> current week; 2023-12-23 Saturday -> next
        fri = self._chat(date_override="2023-12-22")
        sat = self._chat(date_override="2023-12-23")
        self.assertEqual(fri.week_start.strftime("%Y-%m-%d"), "2023-12-18")
        self.assertEqual(sat.week_start.strftime("%Y-%m-%d"), "2023-12-25")

    def test_prefix_templating(self):
        chat = self._chat(
            date_override="2024-01-04",
            user_message_prefix="week {MC_WEEKSTART} / {MC_TODAY}: ",
        )
        self.assertEqual(chat.user_message_prefix, "week 2024-W01 / 2024-01-01: ")

    def test_addon_message_with_weekdays(self):
        chat = self._chat(date_override="2024-01-04")
        msgs = chat.prompt_addon_messages()
        self.assertEqual(len(msgs), 1)
        content = msgs[0]["content"]
        self.assertIn('"Monday" 2024-01-01', content)
        self.assertIn("2024-W01", content)
        self.assertIn("Monday(2024-01-01)", content)
        self.assertIn("Sunday(2024-01-07)", content)

    def test_addon_message_disabled(self):
        chat = self._chat(date_override="2024-01-04", add_current_date=False)
        self.assertEqual(chat.prompt_addon_messages(), [])

    def test_addon_message_without_weekdays(self):
        chat = self._chat(date_override="2024-01-04", add_current_weekdays=False)
        content = chat.prompt_addon_messages()[0]["content"]
        self.assertNotIn("Monday(2024-01-01)", content)

    def test_openai_compatible_provider_configuration_is_shared(self):
        with mock.patch.dict(
            os.environ,
            {"OPENAI_COMPATIBLE_API_KEY": "openai-compatible-key"},
            clear=False,
        ):
            google = self._chat(model_provider="google")
            openai = self._chat(model_provider="openai")
            expected = "https://router.eu.requesty.ai/v1"
            self.assertEqual(google.model_provider_config()["base_url"], expected)
            self.assertEqual(google.model_provider_config()["api_key"], "openai-compatible-key")
            self.assertEqual(openai.model_provider_config()["base_url"], expected)
            self.assertEqual(openai.model_provider_config()["api_key"], "openai-compatible-key")

    def test_openai_compatible_api_key_environment_variable(self):
        with mock.patch.dict(
            os.environ,
            {"OPENAI_COMPATIBLE_API_KEY": "openai-compatible-key"},
            clear=False,
        ):
            chat = self._chat()
            self.assertEqual(chat.model_provider_config()["api_key"], "openai-compatible-key")

    def test_base_url_override(self):
        chat = self._chat(base_url="http://localhost:1234/v1", api_key="k")
        cfg = chat.model_provider_config()
        self.assertEqual(cfg["base_url"], "http://localhost:1234/v1")
        self.assertEqual(cfg["api_key"], "k")


class TestMealChatExtraction(unittest.TestCase):
    """Extraction against a mocked OpenAI-compatible endpoint."""

    def _mock_completion(self, payload):
        usage = mock.Mock()
        usage.model_dump.return_value = {"total_tokens": 10}
        message = mock.Mock()
        message.content = f'Here you go:\n{json.dumps(payload)}\nDone.'
        choice = mock.Mock()
        choice.message = message
        completion = mock.Mock()
        completion.usage = usage
        completion.choices = [choice]
        return completion

    def test_process_text(self):
        payload = {"2024-01-01": [{"desc": "Soup", "price": 5.5}]}
        with TemporaryDirectory() as tmp:
            chat = MealChat(
                user_message="menu text",
                system_prompt="sys {MC_JSON_SCHEMA}",
                json_schema="{}",
                date_override="2024-01-04",
                run_dir=tmp,
            )
            with mock.patch.object(MealChat, "_client") as client:
                client.return_value.chat.completions.create.return_value = (
                    self._mock_completion(payload)
                )
                menu = chat.process_text()
            self.assertEqual(menu, payload)
            self.assertTrue((Path(tmp) / "chatgpt.json").is_file())
            self.assertTrue((Path(tmp) / "chatgpt_usage.json").is_file())
            call = client.return_value.chat.completions.create.call_args
            self.assertEqual(call.kwargs["model"], "azure/gpt-5-mini@francecentral")
            self.assertEqual(call.kwargs["max_completion_tokens"], 5000)
            self.assertNotIn("max_tokens", call.kwargs)
            self.assertNotIn("temperature", call.kwargs)

    def test_process_image(self):
        payload = {"2024-W01": [{"desc": "Pasta", "price": 4.9}]}
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "image.png").write_bytes(b"\x89PNG fake")
            chat = MealChat(
                user_message="describe",
                user_image_file="image.png",
                system_prompt="sys {MC_JSON_SCHEMA}",
                json_schema="{}",
                date_override="2024-01-04",
                run_dir=tmp,
            )
            with mock.patch.object(MealChat, "_client") as client:
                client.return_value.chat.completions.create.return_value = (
                    self._mock_completion(payload)
                )
                menu = chat.process_image()
            self.assertEqual(menu, payload)
            call = client.return_value.chat.completions.create.call_args
            content = call.kwargs["messages"][-1]["content"]
            self.assertEqual(content[1]["type"], "image_url")
            self.assertTrue(
                content[1]["image_url"]["url"].startswith("data:image/png;base64,")
            )


class TestPublish(unittest.TestCase):
    def test_validate_menu_json(self):
        validate_menu_json({"2024-01-01": []})
        validate_menu_json({"2024-W01": [{"desc": "x", "price": 1.0}]})
        with self.assertRaises(PublishError):
            validate_menu_json({})
        with self.assertRaises(PublishError):
            validate_menu_json({"nonsense": []})
        with self.assertRaises(PublishError):
            validate_menu_json({"2024-01-01": [{"no_desc": 1}]})

    def test_week_key_first_date(self):
        menu = {"2024-01-03": [], "2024-01-01": []}
        self.assertEqual(week_key_for(menu, "first_date"), "2024-W01")

    def test_week_key_week_key(self):
        self.assertEqual(
            week_key_for({"2024-W05": []}, "week_key"), "2024-W05"
        )

    def test_week_key_current_week_weekend(self):
        from datetime import datetime

        saturday = datetime(2023, 12, 23)
        self.assertEqual(
            week_key_for({}, "current_week", now=saturday), "2023-W52"
        )

    def test_publish_writes_and_marks(self):
        state = FakeState()
        menu = {"2024-01-01": [{"desc": "Soup", "price": 5.5}]}
        with TemporaryDirectory() as tmp:
            target = publish(menu, tmp, "http://example.com/menu.pdf", state,
                             ttl_weeks=8)
            self.assertEqual(target.name, "2024-W01.json")
            written = json.loads(target.read_text())
            self.assertEqual(written, menu)
        self.assertEqual(state.added, [("http://example.com/menu.pdf", 8)])

    def test_failed_validation_never_marks(self):
        state = FakeState()
        with TemporaryDirectory() as tmp:
            with self.assertRaises(PublishError):
                publish({"bad": []}, tmp, "http://x", state)
        self.assertEqual(state.added, [])


class TestScrapeStage(unittest.TestCase):
    def test_static(self):
        variant = {"scrape": {"type": "static", "url": "https://x/menu.pdf"}}
        result = scrape(variant, "https://x/", state=FakeState())
        self.assertEqual(result["links"], ["https://x/menu.pdf"])
        self.assertEqual(result["new_links"], ["https://x/menu.pdf"])

    def test_static_filters_processed(self):
        variant = {"scrape": {"type": "static", "url": "https://x/menu.pdf"}}
        state = FakeState(existing=["https://x/menu.pdf"])
        result = scrape(variant, "https://x/", state=state)
        self.assertEqual(result["links"], ["https://x/menu.pdf"])
        self.assertEqual(result["new_links"], [])

    def test_meta_refresh(self):
        html = (b'<html><head><meta property="article:modified_time" '
                b'content="2024-01-02T10:00:00+00:00"></head><body></body></html>')
        variant = {"scrape": {"type": "meta_refresh"}}
        with mock.patch("urllib.request.urlopen") as urlopen:
            response = mock.Mock()
            response.read.return_value = html
            response.__enter__ = lambda s: s
            response.__exit__ = mock.Mock(return_value=False)
            urlopen.return_value = response
            result = scrape(variant, "https://mb.example/", state=None)
        self.assertEqual(result["links"], ["https://mb.example/"])

    def test_unknown_type(self):
        with self.assertRaises(ScrapeError):
            scrape({"scrape": {"type": "nope"}}, "https://x/")

    def test_generated_spider_resolves_urls_and_carries_inline_html(self):
        try:
            from scrapy.http import HtmlResponse
        except ModuleNotFoundError:
            self.skipTest("Scrapy is provided by the production image")

        spider_class = _build_spider_class(
            {
                "allowed_domains": ["example.com"],
                "link_xpath": "//div[@class='menu']",
                "item_key": "div",
                "inline": True,
            },
            "https://example.com/",
        )
        items = []
        spider = spider_class(items=items)
        response = HtmlResponse(
            url="https://example.com/",
            body=b'<div class="menu"><p>Soup</p></div>',
            encoding="utf-8",
        )
        yielded = list(spider.parse(response))
        self.assertEqual(len(yielded), 1)
        self.assertEqual(yielded[0]["div"], "https://example.com/")
        self.assertIn("Soup", yielded[0]["html"])


class TestVariantSelection(unittest.TestCase):
    """Plan section 3.5: win / loss / no-new-content / exhausted cases."""

    def _cfg(self):
        from pipeline.config import load_location

        return load_location("lecasino")

    def test_default_wins(self):
        from pipeline import __main__ as main

        cfg = self._cfg()
        with mock.patch.object(main, "scrape") as m:
            m.return_value = {"links": ["a"], "new_links": ["a"], "items": []}
            variant, result = main._select_variant(cfg, None)
        self.assertEqual(variant["name"], "default")

    def test_fallback_on_default_loss(self):
        from pipeline import __main__ as main

        cfg = self._cfg()
        results = {
            "default": ScrapeError("no links"),
            "pdf": {"links": ["p"], "new_links": ["p"], "items": []},
        }
        with mock.patch.object(main, "scrape") as m:
            m.side_effect = [results["default"], results["pdf"]]
            variant, _ = main._select_variant(cfg, None)
        self.assertEqual(variant["name"], "pdf")

    def test_no_new_content_is_a_win(self):
        from pipeline import __main__ as main

        cfg = self._cfg()
        with mock.patch.object(main, "scrape") as m:
            m.return_value = {"links": ["a"], "new_links": [], "items": []}
            variant, result = main._select_variant(cfg, None)
        self.assertEqual(variant["name"], "default")
        self.assertEqual(result["new_links"], [])

    def test_all_variants_lost(self):
        from pipeline import __main__ as main

        cfg = self._cfg()
        with mock.patch.object(main, "scrape") as m:
            m.side_effect = ScrapeError("boom")
            with self.assertRaises(ScrapeError):
                main._select_variant(cfg, None)


class TestDownload(unittest.TestCase):
    def test_filename_for_link(self):
        self.assertEqual(
            filename_for_link("https://x.de/path/Wochenkarte.pdf?x=1"),
            "Wochenkarte.pdf",
        )
        name = filename_for_link("https://x.de/", ".html")
        self.assertTrue(name.endswith(".html"))

    def test_download_items_inline_html(self):
        items = [{"link": "https://x/page", "html": "<html>menu</html>"}]
        with TemporaryDirectory() as tmp:
            records = download_items(items, ["https://x/page"], "link", tmp)
            self.assertEqual(len(records), 1)
            content = (Path(tmp) / records[0]["file"]).read_text()
            self.assertEqual(content, "<html>menu</html>")


class TestPrepare(unittest.TestCase):
    def test_reduce_to_text(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "in.html").write_text("<div>menu</div>")
            out = prepare_one(tmp, "in.html", [{"reduce_to_text": {}}])
            self.assertEqual(out, ["chatgpt_user.txt"])
            self.assertEqual(
                (Path(tmp) / "chatgpt_user.txt").read_text(), "<div>menu</div>"
            )

    def test_unknown_preparer(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "x").write_text("y")
            with self.assertRaises(PrepareError):
                prepare_one(tmp, "x", [{"bogus": {}}])

    def test_missing_input(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(PrepareError):
                prepare_one(tmp, "missing.pdf", [{"pdftotext": {}}])

    def test_html_to_text(self):
        html = """<html><body>
        <div class="group/container"><h2>Speiseplan</h2>
        <p>Montag</p><p>Soup 5,50 €</p>
        <script>var x=1;</script></div>
        </body></html>"""
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "page.html").write_text(html)
            out = prepare_one(tmp, "page.html", [{"html_to_text": {}}])
            self.assertEqual(out, ["chatgpt_user.txt"])
            text = (Path(tmp) / "chatgpt_user.txt").read_text()
            self.assertIn("Speiseplan", text)
            self.assertIn("Montag", text)
            self.assertNotIn("var x=1", text)

    def test_multi_page_render_outputs_unique_images(self):
        def fake_run(command, cwd):
            if command[0] == "pdfseparate":
                for page in (1, 2):
                    (cwd / f"menu_separated_{page}.pdf").write_bytes(b"page")
            else:
                (cwd / f"{command[-1]}.png").write_bytes(b"image")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "menu.pdf").write_bytes(b"pdf")
            with mock.patch("pipeline.stages.prepare._run", side_effect=fake_run):
                out = prepare_one(
                    root,
                    "menu.pdf",
                    [{"pdfseparate": {}}, {"pdftoppm": {}}],
                )
            self.assertEqual(
                out,
                ["menu_separated_1.png", "menu_separated_2.png"],
            )
            self.assertEqual((root / out[0]).read_bytes(), b"image")
            self.assertEqual((root / out[1]).read_bytes(), b"image")


if __name__ == "__main__":
    unittest.main()
