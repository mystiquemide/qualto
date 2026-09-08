from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from qualto.engine.claim import Claim, ClaimValidationError

EXAMPLES_ROOT = Path(__file__).parents[1] / "examples"
VALID_CLAIMS = tuple(
    EXAMPLES_ROOT / "claims" / name
    for name in (
        "limit-buy.json",
        "market-filled.json",
        "partial-fill.json",
        "market-pending.json",
    )
)
RECEIPT_SCENARIOS = tuple(
    EXAMPLES_ROOT / "receipts" / name
    for name in (
        "unproved.jsonl",
        "partial.jsonl",
        "pending.jsonl",
        "orphan-recovery.jsonl",
        "tampered.jsonl",
    )
)
RECEIPT_SCENARIOS += (EXAMPLES_ROOT / "proof-receipts.jsonl",)


@pytest.mark.parametrize("path", VALID_CLAIMS, ids=lambda path: path.name)
def test_public_claim_examples_are_strict_claims(path: Path) -> None:
    claim = Claim.from_mapping(json.loads(path.read_text(encoding="utf-8")))

    assert claim.claim_id.startswith("qualto-claim-")
    assert claim.symbol == "BNBUSDT"


def test_public_tampered_claim_example_is_rejected() -> None:
    path = EXAMPLES_ROOT / "claims" / "tampered.json"

    with pytest.raises(ClaimValidationError, match="unknown"):
        Claim.from_mapping(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", RECEIPT_SCENARIOS, ids=lambda path: path.name)
def test_public_receipt_examples_are_valid_jsonl(path: Path) -> None:
    entries: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        assert isinstance(value, Mapping)
        entries.append(value)

    assert entries
    assert entries[0]["event"] in {"claim_attestation", "order_submitted"}


def test_orphan_example_shows_the_recovery_sequence() -> None:
    path = EXAMPLES_ROOT / "receipts" / "orphan-recovery.jsonl"
    events = [
        json.loads(line)["event"]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]

    assert events == [
        "order_submitted",
        "claim_attestation",
        "order_cleanup",
        "order_cancellation",
    ]
