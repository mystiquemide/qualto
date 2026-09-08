"""Read-only re-verification of persisted claim attestations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..mcp.client import MCPError
from .attest import ExchangeOrder, Verdict, compare_claim_to_order
from .claim import Claim, ClaimValidationError


class ReadOnlyGateway(Protocol):
    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        """Execute a read-only allowlisted operation."""


class VerificationError(RuntimeError):
    """The receipt file cannot be safely re-verified."""


@dataclass(frozen=True, slots=True)
class ReceiptVerification:
    claim_id: str
    order_id: int | None
    recorded_verdict: str | None
    live_verdict: Verdict | None
    matched: bool
    reason: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "orderId": self.order_id,
            "recordedVerdict": self.recorded_verdict,
            "liveVerdict": (
                None if self.live_verdict is None else self.live_verdict.value
            ),
            "matched": self.matched,
            "reason": self.reason,
        }


def _load_receipts(path: Path) -> list[Mapping[str, Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            entries: list[Mapping[str, Any]] = []
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise VerificationError(
                        f"receipt file contains invalid JSON on line {line_number}"
                    ) from exc
                if not isinstance(value, Mapping):
                    raise VerificationError(
                        f"receipt file contains a non-object on line {line_number}"
                    )
                entries.append(value)
    except OSError as exc:
        raise VerificationError("receipt file is unavailable") from exc
    return entries


def _positive_order_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        order_id = int(value)
    except (TypeError, ValueError):
        return None
    return order_id if order_id > 0 else None


def _claim_id(entry: Mapping[str, Any]) -> str:
    claim_payload = entry.get("claim")
    if isinstance(claim_payload, Mapping) and isinstance(
        claim_payload.get("claimId"), str
    ):
        return claim_payload["claimId"]
    return "<invalid>"


def _verify_entry(
    entry: Mapping[str, Any], gateway: ReadOnlyGateway
) -> ReceiptVerification:
    claim_id = _claim_id(entry)
    claim_payload = entry.get("claim")
    attestation_payload = entry.get("attestation")
    if not isinstance(claim_payload, Mapping) or not isinstance(
        attestation_payload, Mapping
    ):
        return ReceiptVerification(
            claim_id,
            None,
            None,
            None,
            False,
            "receipt is missing a claim or attestation",
        )

    recorded_verdict = attestation_payload.get("verdict")
    recorded_text = recorded_verdict if isinstance(recorded_verdict, str) else None
    order_id = _positive_order_id(attestation_payload.get("orderId"))
    if order_id is None:
        return ReceiptVerification(
            claim_id,
            None,
            recorded_text,
            None,
            False,
            "receipt has no order ID to read back",
        )

    try:
        claim = Claim.from_mapping(claim_payload)
        response = gateway.execute(
            "spot.getOrder", {"symbol": claim.symbol, "orderId": order_id}
        )
        order = ExchangeOrder.from_mapping(response)
        if order.order_id != order_id:
            raise ValueError("readback order ID does not match the receipt")
        live_attestation = compare_claim_to_order(claim, order)
    except (
        ClaimValidationError,
        MCPError,
        TypeError,
        ValueError,
        RuntimeError,
        OSError,
    ):
        return ReceiptVerification(
            claim_id,
            order_id,
            recorded_text,
            None,
            False,
            "live order readback could not be verified",
        )

    matched = recorded_text == live_attestation.verdict.value
    reason = (
        "recorded verdict matches live readback"
        if matched
        else "recorded verdict differs from live readback"
    )
    return ReceiptVerification(
        claim.claim_id,
        order_id,
        recorded_text,
        live_attestation.verdict,
        matched,
        reason,
    )


def verify_receipts(
    path: str | Path, gateway: ReadOnlyGateway
) -> list[ReceiptVerification]:
    """Re-run every claim attestation using Binance order readbacks only."""

    entries = _load_receipts(Path(path))
    attestation_entries = [
        entry for entry in entries if entry.get("event") == "claim_attestation"
    ]
    if not attestation_entries:
        raise VerificationError("receipt file contains no claim attestations")
    return [_verify_entry(entry, gateway) for entry in attestation_entries]
