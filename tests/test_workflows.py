"""Static checks for the generalized GitHub Actions orchestration."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
LOCATION_CRONS = {
    "augustiner": ("augustiner.yaml", "10 10 * * 0"),
    "emilundmoritz": ("emilundmoritz.yaml", "10 5 * * 1"),
    "galeria": ("galeria.yaml", "0 18 * * 0"),
    "lecasino": ("lecasino.yaml", "45 7 * * 1"),
    "leos": ("leos.yaml", "30 7 * * 1"),
    "moritzbastei": ("moritzbastai.yaml", "0 9 * * 2"),
    "ratskeller": ("ratskeller.yaml", "0 14 * * 0"),
}
OLD_WORKFLOW_MARKERS = (
    "scraped_done",
    "scrapy runspider",
    "process_chatgpt.py",
    "pdfseparate",
    "pdftoppm",
    "pdftotext",
    "::set-output",
    "sed -n",
)


class WorkflowTests(unittest.TestCase):
    def test_location_callers_preserve_schedule_without_stage_logic(self):
        for location, (filename, cron) in LOCATION_CRONS.items():
            with self.subTest(location=location):
                content = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertIn(f"cron: '{cron}'", content)
                self.assertIn(f"location: {location}", content)
                self.assertIn("uses: ./.github/workflows/location.yaml", content)
                self.assertIn("secrets: inherit", content)
                for marker in OLD_WORKFLOW_MARKERS:
                    self.assertNotIn(marker, content)

    def test_common_workflow_owns_stages_state_artifacts_and_api_secret(self):
        content = (WORKFLOWS / "location.yaml").read_text(encoding="utf-8")
        for location in ("all", *LOCATION_CRONS):
            self.assertIn(location, content)
        for stage in ("scrape_download", "process", "publish"):
            self.assertIn(f"  {stage}:", content)
        self.assertIn("python -m pipeline", content)
        self.assertIn("--legacy-state", content)
        self.assertIn("--no-state", content)
        self.assertIn("OPENAI_COMPATIBLE_API_KEY", content)
        self.assertIn("actions/upload-artifact@v4", content)
        self.assertIn("actions/download-artifact@v4", content)
        self.assertIn(
            "ghcr.io/holygrolli/whatsupforlunch:sha-087f703-2026-02-09",
            content,
        )
        for marker in OLD_WORKFLOW_MARKERS:
            self.assertNotIn(marker, content)

    def test_all_workflow_yaml_files_parse(self):
        for path in WORKFLOWS.rglob("*.yaml"):
            with self.subTest(path=path):
                yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_act_event_and_secret_template_are_safe_and_documented(self):
        event = json.loads((ROOT / "event_local.json").read_text(encoding="utf-8"))
        self.assertEqual(event["event_name"], "workflow_dispatch")
        self.assertTrue(event["act"])
        self.assertEqual(event["inputs"]["location"], "ratskeller")
        secrets = (ROOT / "act/secrets.example").read_text(encoding="utf-8")
        for line in secrets.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                if key != "AWS_DEFAULT_REGION":
                    self.assertEqual(value, "", key)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(".github/workflows/location.yaml", readme)
        self.assertIn("OPENAI_COMPATIBLE_API_KEY", readme)
        self.assertIn("event_local.json", readme)


if __name__ == "__main__":
    unittest.main()
