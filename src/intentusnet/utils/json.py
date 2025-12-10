import json
from typing import Any


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def json_loads(s: str) -> Any:
    return json.loads(s)
