"""Config loading helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore


def load_config(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML configs")
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)  # type: ignore[no-any-return]
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
