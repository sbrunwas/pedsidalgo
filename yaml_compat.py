"""YAML compatibility helpers.

Uses PyYAML when available. If unavailable, falls back to system Ruby YAML parser.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any


try:
    import yaml as _pyyaml  # type: ignore
except Exception:  # pragma: no cover - fallback path
    _pyyaml = None


def safe_load(text: str) -> Any:
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)

    cmd = [
        "ruby",
        "-rjson",
        "-ryaml",
        "-e",
        "obj = YAML.safe_load(ARGF.read, aliases: true); print JSON.generate(obj)",
    ]
    proc = subprocess.run(cmd, input=text, text=True, capture_output=True, check=True)
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def safe_dump(data: Any, sort_keys: bool = False) -> str:
    if _pyyaml is not None:
        return _pyyaml.safe_dump(data, sort_keys=sort_keys)

    payload = json.dumps(data)
    cmd = [
        "ruby",
        "-rjson",
        "-ryaml",
        "-e",
        "obj = JSON.parse(ARGF.read); print obj.to_yaml",
    ]
    proc = subprocess.run(cmd, input=payload, text=True, capture_output=True, check=True)
    return proc.stdout
