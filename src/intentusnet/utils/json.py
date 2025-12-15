from __future__ import annotations
import json
from typing import Any


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_loads(s: str) -> Any:
    return json.loads(s)
