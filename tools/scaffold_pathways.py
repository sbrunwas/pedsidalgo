#!/usr/bin/env python3
"""Generate pathway stub YAML graphs for entries in source/sources.yaml."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yaml_compat import safe_dump, safe_load

SOURCES = ROOT / "source" / "sources.yaml"
PATHWAYS_DIR = ROOT / "pathways"


def scaffold(overwrite: bool = False) -> int:
    data = safe_load(SOURCES.read_text()) or {}
    pathways = data.get("pathways", [])
    PATHWAYS_DIR.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for p in pathways:
        pid = p["id"]
        title = p["title"]
        url = p["url"]
        out = PATHWAYS_DIR / f"{pid}.yaml"
        if out.exists() and not overwrite:
            skipped += 1
            continue

        graph = {
            "id": pid,
            "title": title,
            "source_urls": [url],
            "tags": ["stub", "needs_algorithm_extraction"],
            "nodes": [
                {
                    "id": "start",
                    "type": "info",
                    "label": "Start",
                    "text": "Stub pathway start.",
                    "source_urls": [url],
                },
                {
                    "id": "algorithm_stub",
                    "type": "info",
                    "label": "Algorithm Stub",
                    "text": "Algorithm steps are intentionally not populated yet.",
                    "source_urls": [url],
                },
                {
                    "id": "definitions_stub",
                    "type": "info",
                    "label": "Definitions Stub",
                    "text": "Definitions and criteria pending curation from source pathway.",
                    "source_urls": [url],
                },
                {
                    "id": "end",
                    "type": "end",
                    "label": "End",
                    "text": "Stub pathway end.",
                    "source_urls": [url],
                },
            ],
            "edges": [
                {"from": "start", "to": "algorithm_stub"},
                {"from": "algorithm_stub", "to": "definitions_stub"},
                {"from": "definitions_stub", "to": "end"},
            ],
        }
        out.write_text(safe_dump(graph, sort_keys=False))
        created += 1

    print(f"Scaffold complete. created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(scaffold(overwrite=False))
