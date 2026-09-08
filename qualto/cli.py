"""Qualto command-line smoke checks."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Sequence

from .engine.attest import AttestationEngine, Verdict
from .engine.claim import Claim, ClaimValidationError
from .engine.receipts import ReceiptLog
from .engine.session import Session
from .mcp.client import BinanceMCPClient, MCPError


def smoke() -> int:
    client = BinanceMCPClient()
    try:
        initialize = client.initialize()
        tools = client.list_tools()
        account = client.account_read()
    except MCPError as exc:
        print(f"gateway=error reason={exc}", file=sys.stderr)
        return 1

    balance_count = len(account.get("balances", [])) if isinstance(account, dict) else 0
    print("gateway=ready")
    print(f"client_id={client.credential_provider.client_id}")
    print(f"protocol_version={initialize.get('protocolVersion')}")
    print(f"visible_tools={len(tools)}")
    print("account_read=ok")
    print(f"nonzero_balance_records={balance_count}")
    return 0


def run_claim(claim_file: str, receipts_file: str, confirm_live_write: bool) -> int:
    if not confirm_live_write:
        print("claim=blocked reason=explicit live-write confirmation is required", file=sys.stderr)
        return 2
    try:
        with Path(claim_file).open(encoding="utf-8") as handle:
            claim = Claim.from_mapping(json.load(handle))
        session = Session(f"session-{uuid.uuid4().hex[:12]}", ReceiptLog(receipts_file))
        session.connect()
        session.activate()
        result = AttestationEngine(BinanceMCPClient(), session).place_and_attest(claim)
    except (OSError, json.JSONDecodeError, ClaimValidationError, MCPError, ValueError) as exc:
        print(f"claim=error reason={exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_mapping(), sort_keys=True))
    return 0 if result.verdict is Verdict.PROVED else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qualto")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke", help="verify the supported Binance MCP gateway")
    claim_parser = subparsers.add_parser("claim", help="place and attest one validated claim")
    claim_parser.add_argument("--claim-file", required=True, help="path to a claim JSON object")
    claim_parser.add_argument(
        "--receipts-file",
        default="runtime/receipts.jsonl",
        help="append-only JSONL receipt path",
    )
    claim_parser.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="explicitly authorize the live order request",
    )
    args = parser.parse_args(argv)
    if args.command == "smoke":
        return smoke()
    if args.command == "claim":
        return run_claim(args.claim_file, args.receipts_file, args.confirm_live_write)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
