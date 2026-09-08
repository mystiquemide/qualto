from __future__ import annotations

import json
from pathlib import Path

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
