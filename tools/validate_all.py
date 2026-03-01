#!/usr/bin/env python3
"""Validate source catalog, pathway graphs, and master router references."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yaml_compat import safe_load

SOURCES_PATH = ROOT / "source" / "sources.yaml"
PATHWAYS_DIR = ROOT / "pathways"
MASTER_ROUTER_PATH = PATHWAYS_DIR / "master_router.yaml"


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return safe_load(path.read_text()) or {}
    except Exception as exc:
        raise RuntimeError(f"failed to parse {path}: {exc}") from exc


def validate() -> List[str]:
    errors: List[str] = []

    sources = load_yaml(SOURCES_PATH).get("pathways", [])
    source_ids: Set[str] = {p["id"] for p in sources}

    for pid in source_ids:
        p = PATHWAYS_DIR / f"{pid}.yaml"
        if not p.exists():
            errors.append(f"missing pathway graph: {p}")
            continue

        graph = load_yaml(p)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        node_ids = {n.get("id") for n in nodes}

        if "start" not in node_ids:
            errors.append(f"{p}: missing start node")
        if "end" not in node_ids:
            errors.append(f"{p}: missing end node")

        for node in nodes:
            srcs = node.get("source_urls", [])
            if not srcs:
                errors.append(f"{p}: node '{node.get('id')}' missing source_urls")

            if node.get("type") == "link":
                target = node.get("target_pathway_id")
                if not target or target not in source_ids:
                    errors.append(f"{p}: link node '{node.get('id')}' has unknown target_pathway_id '{target}'")

        for edge in edges:
            fr = edge.get("from")
            to = edge.get("to")
            if fr not in node_ids or to not in node_ids:
                errors.append(f"{p}: broken edge {fr} -> {to}")

    router = load_yaml(MASTER_ROUTER_PATH)
    router_refs: Set[str] = set()

    router_refs.update(router.get("infant_split", {}).get("targets", {}).values())
    for rule in router.get("activation_rules", []):
        for pid in rule.get("pathways", []):
            router_refs.add(pid)
    for pid in router.get("critical_overrides", {}).get("forced_critical_pathways", []):
        router_refs.add(pid)

    unknown = sorted(pid for pid in router_refs if pid not in source_ids)
    for pid in unknown:
        errors.append(f"master_router.yaml references unknown pathway id: {pid}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("VALIDATION FAILED")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Validation passed: sources, pathways, and master router are internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
