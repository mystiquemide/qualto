from __future__ import annotations

import json
from pathlib import Path

from qualto.cli import main


def test_claim_cli_requires_explicit_live_write_confirmation(tmp_path: Path, capsys) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps({"claimId": "qualto-claim-abcdefghijkl"}), encoding="utf-8")

    assert main(["claim", "--claim-file", str(claim_file)]) == 2
    assert "confirmation is required" in capsys.readouterr().err


def test_claim_cli_validation_rejects_malformed_claim_before_network(tmp_path: Path, capsys) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")

    assert main(["claim", "--claim-file", str(claim_file), "--confirm-live-write"]) == 1
    assert "claim=error" in capsys.readouterr().err


def test_claim_cli_cancel_flag_still_requires_confirmation(tmp_path: Path, capsys) -> None:
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(json.dumps({"claimId": "qualto-claim-abcdefghijkl"}), encoding="utf-8")

    assert main(["claim", "--claim-file", str(claim_file), "--cancel-after-attestation"]) == 2
    assert "confirmation is required" in capsys.readouterr().err
