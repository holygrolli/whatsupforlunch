"""Run manifest read/write.

Each run writes a manifest JSON (run id, location, links discovered, links new,
files downloaded, files prepared, extraction results, links marked) into the
run directory. CI uploads it as an artifact; it is never committed and never
written to DynamoDB (decision 3).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

MANIFEST_NAME = "manifest.json"


class Manifest:
    def __init__(self, location: str, run_dir: str | Path, run_id: str | None = None):
        self.location = location
        self.run_dir = Path(run_dir)
        self.run_id = run_id or os.environ.get(
            "PIPELINE_RUN_ID", f"{location}-{int(time.time())}"
        )
        self.data = {
            "run_id": self.run_id,
            "location": location,
            "variant": None,
            "links_discovered": [],
            "links_new": [],
            "files_downloaded": [],
            "files_prepared": [],
            "extraction_results": [],
            "links_marked": [],
            "stages_completed": [],
        }

    @property
    def path(self) -> Path:
        return self.run_dir / MANIFEST_NAME

    def write(self) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)
        return self.path

    def stage_done(self, stage: str) -> None:
        if stage not in self.data["stages_completed"]:
            self.data["stages_completed"].append(stage)

    @classmethod
    def load(cls, run_dir: str | Path) -> "Manifest":
        path = Path(run_dir) / MANIFEST_NAME
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        manifest = cls(data["location"], run_dir, run_id=data["run_id"])
        manifest.data = data
        return manifest

    @classmethod
    def exists(cls, run_dir: str | Path) -> bool:
        return (Path(run_dir) / MANIFEST_NAME).is_file()
