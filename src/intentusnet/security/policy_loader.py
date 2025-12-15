from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .policy_engine import PolicyEngine


def _load_config(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("PyYAML is required to load YAML policy files")

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    else:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)


def load_policy_engine_from_file(
    filepath: Optional[str],
    default_mode: str = "allow",
) -> PolicyEngine:
    """
    Load a PolicyEngine from a JSON or YAML file.

    - If filepath is None or empty → return default allow/deny engine
    - If file missing:
        - default_mode="deny" → deny-all
        - default_mode="allow" → allow-all
    """
    if not filepath:
        return PolicyEngine.empty_allow_all() if default_mode == "allow" else PolicyEngine.empty_deny_all()

    path = Path(filepath)
    if not path.is_file():
        if default_mode == "deny":
            return PolicyEngine.empty_deny_all()
        return PolicyEngine.empty_allow_all()

    data = _load_config(path)
    return PolicyEngine.from_dict(data)
