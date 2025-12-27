from __future__ import annotations

import os
import json
from typing import List

from .models import ExecutionRecord


class ExecutionStore:
    def save(self, record: ExecutionRecord) -> str:
        raise NotImplementedError

    def load(self, execution_id: str) -> ExecutionRecord:
        raise NotImplementedError

    def list_ids(self) -> List[str]:
        raise NotImplementedError


class FileExecutionStore(ExecutionStore):
    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)

    def _path(self, execution_id: str) -> str:
        return os.path.join(self.root_dir, f"{execution_id}.json")

    def save(self, record: ExecutionRecord) -> str:
        path = self._path(record.header.executionId)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, execution_id: str) -> ExecutionRecord:
        path = self._path(execution_id)
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return ExecutionRecord.from_dict(d)

    def list_ids(self) -> List[str]:
        ids: List[str] = []
        for name in os.listdir(self.root_dir):
            if name.endswith(".json"):
                ids.append(name[:-5])
        ids.sort()
        return ids