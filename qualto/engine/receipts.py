"""Append-only, JSONL-backed receipt persistence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class ReceiptLog:
    """Write and read append-only JSONL receipts without raw provider data."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            self.path.touch(mode=0o600)
        else:
            os.chmod(self.path, 0o600)

    def append(self, event: Mapping[str, Any]) -> None:
        if not isinstance(event, Mapping):
            raise TypeError("receipt must be an object")
        record = dict(event)
        record.setdefault("timestamp", time.time())
        serialized = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def entries(self) -> list[dict[str, Any]]:
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
