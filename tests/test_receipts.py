from __future__ import annotations

import json
from pathlib import Path

from qualto.engine.receipts import ReceiptLog


def test_receipts_are_append_only_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "receipts.jsonl"
    log = ReceiptLog(path)

    log.append({"event": "first", "value": 1})
    log.append({"event": "second", "value": 2})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["first", "second"]
    assert [item["value"] for item in log.entries()] == [1, 2]


def test_receipt_log_uses_restricted_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    ReceiptLog(path)

    assert path.stat().st_mode & 0o077 == 0
