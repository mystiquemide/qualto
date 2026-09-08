"""Standalone MCP server for claim-bound Binance trading."""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..engine.attest import AttestationEngine, Verdict
from ..engine.claim import Claim, ClaimValidationError
from ..engine.receipts import ReceiptLog
from ..engine.session import Session
from ..engine.verify import VerificationError, verify_receipts
from .client import BinanceMCPClient, MCPError


def _live_writes_enabled() -> bool:
    return os.getenv("QUALTO_ENABLE_LIVE_WRITES", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _receipts_path() -> Path:
    return Path(os.getenv("QUALTO_RECEIPTS_FILE", "runtime/mcp-receipts.jsonl"))


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ClaimValidationError):
        return str(exc)
    return "Qualto operation failed; inspect session status for the safe state"


@dataclass
class QualtoMCPService:
    """Policy boundary exposed to any MCP-compatible agent client."""

    gateway: Any
    session: Session
    receipts_file: Path
    live_writes_enabled: bool = False

    @classmethod
    def from_environment(cls) -> QualtoMCPService:
        receipts_file = _receipts_path()
        receipts = ReceiptLog(receipts_file)
        session = Session(f"mcp-{uuid.uuid4().hex[:12]}", receipts)
        session.connect()
        session.activate()
        return cls(BinanceMCPClient(), session, receipts_file, _live_writes_enabled())

    def session_status(self) -> dict[str, Any]:
        return {
            "sessionId": self.session.session_id,
            "state": self.session.state.value,
            "blockReason": self.session.block_reason,
            "errorReason": self.session.error_reason,
            "liveWritesEnabled": self.live_writes_enabled,
        }

    def read_context(self, symbol: str = "BNBUSDT") -> dict[str, Any]:
        if (
            not isinstance(symbol, str)
            or not symbol.isalnum()
            or symbol.upper() != symbol
        ):
            return {"ok": False, "error": "symbol must be uppercase alphanumeric text"}
        try:
            price = self.gateway.execute("spot.tickerPrice", {"symbol": symbol})
            account = self.gateway.execute(
                "spot.getAccount", {"omitZeroBalances": True}
            )
            balances = (
                account.get("balances", []) if isinstance(account, Mapping) else []
            )
            quote = next(
                (
                    item
                    for item in balances
                    if isinstance(item, Mapping) and item.get("asset") == "USDT"
                ),
                {},
            )
            return {
                "ok": True,
                "symbol": symbol,
                "price": price.get("price") if isinstance(price, Mapping) else None,
                "quoteAsset": "USDT",
                "quoteAvailable": quote.get("free")
                if isinstance(quote, Mapping)
                else None,
            }
        except (MCPError, TypeError, ValueError, RuntimeError, OSError):
            return {
                "ok": False,
                "error": "live context could not be read",
                "session": self.session_status(),
            }

    def attest_claim(
        self,
        claim_payload: Mapping[str, Any],
        *,
        confirm_live_write: bool = False,
        cancel_after_attestation: bool = False,
    ) -> dict[str, Any]:
        gate_error = self._write_gate(confirm_live_write)
        if gate_error is not None:
            return gate_error
        try:
            claim = Claim.from_mapping(claim_payload)
            result = AttestationEngine(self.gateway, self.session).place_and_attest(
                claim
            )
            output: dict[str, Any] = {
                "ok": result.verdict is Verdict.PROVED,
                "attestation": result.to_mapping(),
                "session": self.session_status(),
            }
            if cancel_after_attestation:
                if result.order_id is None:
                    output["cancellation"] = {
                        "ok": False,
                        "error": "no known order ID; use qualto_cleanup_claim",
                    }
                else:
                    cancelled = AttestationEngine(
                        self.gateway, self.session
                    ).cancel_order(claim, result.order_id)
                    output["cancellation"] = {
                        "ok": True,
                        "orderId": cancelled.order_id,
                        "status": cancelled.status,
                        "verdict": Verdict.PROVED.value,
                    }
            output["session"] = self.session_status()
            return output
        except (ClaimValidationError, RuntimeError, ValueError) as exc:
            return {
                "ok": False,
                "error": _safe_error(exc),
                "session": self.session_status(),
            }

    def cleanup_claim(
        self,
        claim_payload: Mapping[str, Any],
        *,
        confirm_live_write: bool = False,
    ) -> dict[str, Any]:
        gate_error = self._write_gate(confirm_live_write)
        if gate_error is not None:
            return gate_error
        try:
            claim = Claim.from_mapping(claim_payload)
            order = AttestationEngine(self.gateway, self.session).cleanup_by_claim(
                claim
            )
            return {
                "ok": True,
                "orderId": order.order_id,
                "status": order.status,
                "verdict": Verdict.PROVED.value,
                "session": self.session_status(),
            }
        except (ClaimValidationError, RuntimeError, ValueError) as exc:
            return {
                "ok": False,
                "error": _safe_error(exc),
                "session": self.session_status(),
            }

    def verify_receipts(self) -> dict[str, Any]:
        try:
            results = verify_receipts(self.receipts_file, self.gateway)
            return {
                "ok": all(result.matched for result in results),
                "results": [result.to_mapping() for result in results],
            }
        except (VerificationError, MCPError, OSError, ValueError):
            return {
                "ok": False,
                "error": "receipt verification failed",
                "results": [],
            }

    def _write_gate(self, confirm_live_write: bool) -> dict[str, Any] | None:
        if not self.live_writes_enabled:
            return {
                "ok": False,
                "error": "live writes are disabled for this MCP server",
                "requires": "QUALTO_ENABLE_LIVE_WRITES=1",
                "session": self.session_status(),
            }
        if not confirm_live_write:
            return {
                "ok": False,
                "error": "explicit live-write confirmation is required",
                "requires": "confirm_live_write=true",
                "session": self.session_status(),
            }
        return None


def build_server(service: QualtoMCPService) -> FastMCP:
    """Build the MCP tool surface around an injected policy service."""

    server = FastMCP(
        "qualto-claim-bound-trading",
        instructions=(
            "Qualto is the claim-bound trading policy server. Submit strict claims "
            "to Qualto; never call raw exchange tools. A PROVED result requires "
            "live Binance readback. UNPROVED blocks the session."
        ),
    )

    @server.tool(
        name="qualto_session_status",
        description="Read the current Qualto session state and write policy.",
    )
    def qualto_session_status() -> dict[str, Any]:
        return service.session_status()

    @server.tool(
        name="qualto_read_context",
        description="Read live price and quote balance context without placing an order.",
    )
    def qualto_read_context(symbol: str = "BNBUSDT") -> dict[str, Any]:
        return service.read_context(symbol)

    @server.tool(
        name="qualto_attest_claim",
        description=(
            "Validate and place one claim-bound order, read it back by both IDs, "
            "and return PROVED, UNPROVED, PARTIAL, or PENDING."
        ),
    )
    def qualto_attest_claim(
        claim: dict[str, Any],
        confirm_live_write: bool = False,
        cancel_after_attestation: bool = False,
    ) -> dict[str, Any]:
        return service.attest_claim(
            claim,
            confirm_live_write=confirm_live_write,
            cancel_after_attestation=cancel_after_attestation,
        )

    @server.tool(
        name="qualto_cleanup_claim",
        description="Resolve an orphan order by claim ID and cancel that exact order.",
    )
    def qualto_cleanup_claim(
        claim: dict[str, Any], confirm_live_write: bool = False
    ) -> dict[str, Any]:
        return service.cleanup_claim(claim, confirm_live_write=confirm_live_write)

    @server.tool(
        name="qualto_verify_receipts",
        description="Re-read persisted claim attestations using read-only Binance calls.",
    )
    def qualto_verify_receipts() -> dict[str, Any]:
        return service.verify_receipts()

    return server


def main() -> None:
    """Run the standalone stdio MCP server for Claude and other MCP clients."""

    build_server(QualtoMCPService.from_environment()).run(transport="stdio")


if __name__ == "__main__":
    main()
