from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qualto import cli
from qualto.agent.loop import AgentOutputError
from qualto.cli import main
from qualto.engine.claim import Claim


def test_claim_cli_requires_explicit_live_write_confirmation(
    tmp_path: Path, capsys
) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(
        json.dumps({"claimId": "qualto-claim-abcdefghijkl"}), encoding="utf-8"
    )

    assert main(["claim", "--claim-file", str(claim_file)]) == 2
    assert "confirmation is required" in capsys.readouterr().err


def test_claim_cli_validation_rejects_malformed_claim_before_network(
    tmp_path: Path, capsys
) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")

    assert main(["claim", "--claim-file", str(claim_file), "--confirm-live-write"]) == 1
    assert "claim=error" in capsys.readouterr().err


def test_claim_cli_cancel_flag_still_requires_confirmation(
    tmp_path: Path, capsys
) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(
        json.dumps({"claimId": "qualto-claim-abcdefghijkl"}), encoding="utf-8"
    )

    assert (
        main(["claim", "--claim-file", str(claim_file), "--cancel-after-attestation"])
        == 2
    )
    assert "confirmation is required" in capsys.readouterr().err


def test_propose_cli_prints_claim_without_order(monkeypatch, capsys) -> None:
    payload = {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy 5 USDT of BNB",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.006",
        "price": "700",
        "status": "NEW",
        "reason": "small bounded claim",
    }

    class FakeLoop:
        def __init__(self, gateway) -> None:
            self.gateway = gateway

        def generate_claim(self, mandate: str, *, symbol: str) -> Claim:
            assert mandate == "buy 5 USDT of BNB"
            assert symbol == "BNBUSDT"
            return Claim.from_mapping(payload)

    monkeypatch.setattr("qualto.cli.AgentLoop", FakeLoop)

    assert main(["propose", "--mandate", "buy 5 USDT of BNB"]) == 0
    assert '"claimId": "qualto-claim-abcdefghijkl"' in capsys.readouterr().out


def test_agent_cli_requires_explicit_live_write_confirmation(capsys) -> None:
    assert main(["agent", "--mandate", "buy 5 USDT of BNB"]) == 2
    assert "confirmation is required" in capsys.readouterr().err


def valid_claim() -> Claim:
    return Claim.from_mapping(
        {
            "claimId": "qualto-claim-abcdefghijkl",
            "mandate": "buy 5 USDT of BNB",
            "symbol": "BNBUSDT",
            "side": "BUY",
            "orderType": "LIMIT",
            "quantity": "0.006",
            "price": "700",
            "status": "NEW",
            "reason": "Small bounded CLI test claim.",
        }
    )


class FakeCredentialProvider:
    client_id = "codex"


class FakeGateway:
    connected = True

    def __init__(self, *, orphan: bool = False) -> None:
        self.orphan = orphan
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.credential_provider = FakeCredentialProvider()

    def initialize(self) -> Mapping[str, Any]:
        return {"protocolVersion": "2025-03-26"}

    def list_tools(self) -> list[Mapping[str, Any]]:
        return [{"name": "tool_search"}, {"name": "tool_execute"}]

    def account_read(self) -> Mapping[str, Any]:
        return {"balances": [{"asset": "USDT", "free": "7"}]}

    def disconnect(self) -> None:
        self.connected = False

    def reconnect(self) -> None:
        self.connected = True

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        args = dict(arguments or {})
        self.calls.append((tool_name, args))
        if not self.connected:
            raise RuntimeError("gateway disconnected")
        if tool_name == "spot.newOrder":
            return {} if self.orphan else {"orderId": 1001}
        if tool_name == "spot.getOrder":
            return {
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
        if tool_name == "spot.deleteOrder":
            response = self.execute("spot.getOrder", arguments)
            response["status"] = "CANCELED"
            return response
        raise AssertionError(tool_name)


class FakeAgentLoop:
    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway

    def generate_claim(self, mandate: str, *, symbol: str) -> Claim:
        assert mandate == "buy 5 USDT of BNB"
        assert symbol == "BNBUSDT"
        return valid_claim()


class FailingAgentLoop:
    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway

    def generate_claim(self, mandate: str, *, symbol: str) -> Claim:
        del mandate, symbol
        raise AgentOutputError("bounded test failure")


def test_smoke_cli_runs_all_gateway_checks(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)

    assert main(["smoke"]) == 0

    output = capsys.readouterr().out
    assert "gateway=ready" in output
    assert "visible_tools=2" in output
    assert "account_read=ok" in output


def test_claim_cli_proves_and_cancels_a_confirmed_order(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)
    claim_file = tmp_path / "claim.json"
    receipts_file = tmp_path / "receipts.jsonl"
    claim_file.write_text(json.dumps(valid_claim().to_mapping()), encoding="utf-8")

    assert (
        main(
            [
                "claim",
                "--claim-file",
                str(claim_file),
                "--receipts-file",
                str(receipts_file),
                "--confirm-live-write",
                "--cancel-after-attestation",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "PROVED"
    assert output["cancellation"]["status"] == "CANCELED"
    assert [
        json.loads(line)["event"] for line in receipts_file.read_text().splitlines()
    ] == [
        "order_submitted",
        "claim_attestation",
        "order_cancellation",
    ]


def test_claim_cli_uses_consistent_error_for_unknown_order_id(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", lambda: FakeGateway(orphan=True))
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps(valid_claim().to_mapping()), encoding="utf-8")

    assert (
        main(
            [
                "claim",
                "--claim-file",
                str(claim_file),
                "--receipts-file",
                str(tmp_path / "claim-receipts.jsonl"),
                "--confirm-live-write",
                "--cancel-after-attestation",
            ]
        )
        == 1
    )

    assert "no known order ID; cancellation skipped" in capsys.readouterr().err


def test_agent_cli_proves_and_cancels_a_confirmed_order(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)
    monkeypatch.setattr(cli, "AgentLoop", FakeAgentLoop)

    assert (
        main(
            [
                "agent",
                "--mandate",
                "buy 5 USDT of BNB",
                "--receipts-file",
                str(tmp_path / "receipts.jsonl"),
                "--confirm-live-write",
                "--cancel-after-attestation",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["attestation"]["verdict"] == "PROVED"
    assert output["cancellation"]["status"] == "CANCELED"


def test_agent_cli_negative_path_reports_disconnect_recovery(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)
    monkeypatch.setattr(cli, "AgentLoop", FakeAgentLoop)

    assert (
        main(
            [
                "agent",
                "--mandate",
                "buy 5 USDT of BNB",
                "--receipts-file",
                str(tmp_path / "receipts.jsonl"),
                "--confirm-live-write",
                "--disconnect-before-order",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["attestation"]["verdict"] == "UNPROVED"
    assert output["negativePath"]["recovered"] is True


def test_agent_cli_uses_consistent_error_for_unknown_order_id(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", lambda: FakeGateway(orphan=True))
    monkeypatch.setattr(cli, "AgentLoop", FakeAgentLoop)

    assert (
        main(
            [
                "agent",
                "--mandate",
                "buy 5 USDT of BNB",
                "--receipts-file",
                str(tmp_path / "receipts.jsonl"),
                "--confirm-live-write",
                "--cancel-after-attestation",
            ]
        )
        == 1
    )

    assert "no known order ID; cancellation skipped" in capsys.readouterr().err


def test_agent_cli_records_error_session_when_claim_generation_fails(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)
    monkeypatch.setattr(cli, "AgentLoop", FailingAgentLoop)
    receipts_file = tmp_path / "receipts.jsonl"

    assert (
        main(
            [
                "agent",
                "--mandate",
                "buy 5 USDT of BNB",
                "--receipts-file",
                str(receipts_file),
                "--confirm-live-write",
            ]
        )
        == 1
    )

    assert "agent=error" in capsys.readouterr().err
    receipt = json.loads(receipts_file.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["event"] == "session_error"
    assert receipt["errorType"] == "AgentOutputError"
    assert "verdict" not in receipt


def test_cleanup_cli_recovers_by_claim_id_and_cancels(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "BinanceMCPClient", FakeGateway)
    claim_file = tmp_path / "claim.json"
    receipts_file = tmp_path / "receipts.jsonl"
    claim_file.write_text(json.dumps(valid_claim().to_mapping()), encoding="utf-8")

    assert (
        main(
            [
                "cleanup",
                "--claim-file",
                str(claim_file),
                "--receipts-file",
                str(receipts_file),
                "--confirm-live-write",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["cleanup"] == {
        "orderId": 1001,
        "status": "CANCELED",
        "verdict": "PROVED",
    }


def test_cleanup_cli_requires_explicit_confirmation(tmp_path: Path, capsys) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps(valid_claim().to_mapping()), encoding="utf-8")

    assert main(["cleanup", "--claim-file", str(claim_file)]) == 2
    assert "confirmation is required" in capsys.readouterr().err
