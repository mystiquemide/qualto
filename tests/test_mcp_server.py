from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from qualto.engine.receipts import ReceiptLog
from qualto.engine.session import Session, SessionState
from qualto.mcp.server import QualtoMCPService, build_server


def claim_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy a bounded BNB limit order",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.006",
        "price": "700",
        "status": "NEW",
        "reason": "MCP server contract fixture.",
    }
    payload.update(overrides)
    return payload


def order_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "orderId": 1001,
        "symbol": "BNBUSDT",
        "side": "BUY",
        "origClientOrderId": "qualto-claim-abcdefghijkl",
        "status": "NEW",
        "origQty": "0.006",
        "executedQty": "0",
        "price": "700",
        "type": "LIMIT",
    }
    payload.update(overrides)
    return payload


class FakeBinanceGateway:
    connected = True

    def __init__(self, *, orphan: bool = False, fail: bool = False) -> None:
        self.orphan = orphan
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        args = dict(arguments or {})
        self.calls.append((tool_name, args))
        if self.fail:
            raise RuntimeError("gateway unavailable")
        if tool_name == "spot.tickerPrice":
            return {"symbol": "BNBUSDT", "price": "751.86"}
        if tool_name == "spot.getAccount":
            return {"balances": [{"asset": "USDT", "free": "7.00000000"}]}
        if tool_name == "spot.newOrder":
            return {} if self.orphan else {"orderId": 1001}
        if tool_name == "spot.getOrder":
            return order_payload()
        if tool_name == "spot.deleteOrder":
            response = order_payload(status="CANCELED")
            return response
        raise AssertionError(tool_name)


def make_service(
    tmp_path: Path,
    gateway: FakeBinanceGateway,
    *,
    live_writes_enabled: bool = False,
) -> QualtoMCPService:
    receipts_file = tmp_path / "receipts.jsonl"
    session = Session("mcp-test", ReceiptLog(receipts_file))
    session.connect()
    session.activate()
    return QualtoMCPService(
        gateway,
        session,
        receipts_file,
        live_writes_enabled=live_writes_enabled,
    )


def test_service_exposes_safe_status_and_live_context(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway)

    status = service.session_status()
    context = service.read_context()

    assert status["state"] == SessionState.ACTIVE.value
    assert status["liveWritesEnabled"] is False
    assert context == {
        "ok": True,
        "symbol": "BNBUSDT",
        "price": "751.86",
        "quoteAsset": "USDT",
        "quoteAvailable": "7.00000000",
    }
    assert [call[0] for call in gateway.calls] == [
        "spot.tickerPrice",
        "spot.getAccount",
    ]


def test_service_rejects_invalid_context_symbol_before_gateway_call(
    tmp_path: Path,
) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway)

    result = service.read_context("bnb-usdt")

    assert result == {
        "ok": False,
        "error": "symbol must be uppercase alphanumeric text",
    }
    assert gateway.calls == []


def test_service_redacts_gateway_error_details(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway(fail=True)
    service = make_service(tmp_path, gateway, live_writes_enabled=True)

    result = service.attest_claim(claim_payload(), confirm_live_write=True)

    assert result["attestation"]["verdict"] == "UNPROVED"
    assert "gateway unavailable" not in str(result)


def test_service_blocks_writes_when_server_is_not_armed(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway)

    result = service.attest_claim(
        claim_payload(), confirm_live_write=True, cancel_after_attestation=True
    )

    assert result["ok"] is False
    assert result["requires"] == "QUALTO_ENABLE_LIVE_WRITES=1"
    assert gateway.calls == []


def test_service_requires_per_call_confirmation(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway, live_writes_enabled=True)

    result = service.attest_claim(claim_payload())

    assert result["ok"] is False
    assert result["requires"] == "confirm_live_write=true"
    assert gateway.calls == []


def test_service_attests_and_cancels_a_claim_bound_order(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway, live_writes_enabled=True)

    result = service.attest_claim(
        claim_payload(), confirm_live_write=True, cancel_after_attestation=True
    )

    assert result["ok"] is True
    assert result["attestation"]["verdict"] == "PROVED"
    assert result["cancellation"] == {
        "ok": True,
        "orderId": 1001,
        "status": "CANCELED",
        "verdict": "PROVED",
    }
    assert [call[0] for call in gateway.calls] == [
        "spot.newOrder",
        "spot.getOrder",
        "spot.getOrder",
        "spot.deleteOrder",
    ]


def test_service_blocks_after_unproved_attestation(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway(orphan=True)
    service = make_service(tmp_path, gateway, live_writes_enabled=True)

    result = service.attest_claim(claim_payload(), confirm_live_write=True)

    assert result["ok"] is False
    assert result["attestation"]["verdict"] == "UNPROVED"
    assert result["session"]["state"] == SessionState.BLOCKED.value


def test_service_recovers_an_orphan_by_claim_id(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway(orphan=True)
    service = make_service(tmp_path, gateway, live_writes_enabled=True)
    claim = claim_payload()
    service.attest_claim(claim, confirm_live_write=True)

    result = service.cleanup_claim(claim, confirm_live_write=True)

    assert result["ok"] is True
    assert result["orderId"] == 1001
    assert result["status"] == "CANCELED"
    assert gateway.calls[-2:] == [
        (
            "spot.getOrder",
            {"symbol": "BNBUSDT", "origClientOrderId": "qualto-claim-abcdefghijkl"},
        ),
        ("spot.deleteOrder", {"symbol": "BNBUSDT", "orderId": 1001}),
    ]


def test_service_verifies_receipts_without_write_tools(tmp_path: Path) -> None:
    gateway = FakeBinanceGateway()
    service = make_service(tmp_path, gateway)
    service.session.record(
        {
            "event": "claim_attestation",
            "claim": claim_payload(),
            "attestation": {"orderId": 1001, "verdict": "PROVED"},
        }
    )

    result = service.verify_receipts()

    assert result["ok"] is True
    assert result["results"][0]["matched"] is True
    assert [call[0] for call in gateway.calls] == ["spot.getOrder"]


def test_fastmcp_surface_contains_only_policy_tools(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeBinanceGateway())

    async def list_names() -> list[str]:
        return sorted(tool.name for tool in await build_server(service).list_tools())

    names = asyncio.run(list_names())

    assert names == [
        "qualto_attest_claim",
        "qualto_cleanup_claim",
        "qualto_read_context",
        "qualto_session_status",
        "qualto_verify_receipts",
    ]


def test_stdio_mcp_handshake_and_status_tool() -> None:
    async def run_client() -> tuple[list[str], dict[str, Any]]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "qualto.mcp.server"],
            env={
                **os.environ,
                "QUALTO_RECEIPTS_FILE": "/tmp/qualto-mcp-protocol-test.jsonl",
            },
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = await client.list_tools()
            response = await client.call_tool("qualto_session_status", {})
            structured = response.structuredContent or {}
            return [tool.name for tool in tools.tools], structured

    names, status = asyncio.run(run_client())

    assert sorted(names) == [
        "qualto_attest_claim",
        "qualto_cleanup_claim",
        "qualto_read_context",
        "qualto_session_status",
        "qualto_verify_receipts",
    ]
    assert status["state"] == "ACTIVE"


def test_claude_configuration_is_safe_by_default() -> None:
    path = Path(__file__).parents[1] / "examples" / "mcp" / "claude-desktop.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    config = document["mcpServers"]["qualto"]
    assert config["env"]["QUALTO_ENABLE_LIVE_WRITES"] == "0"
    assert "access_token" not in path.read_text(encoding="utf-8")
    assert "Bearer " not in path.read_text(encoding="utf-8")
