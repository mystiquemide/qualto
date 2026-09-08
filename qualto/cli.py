"""Qualto command-line smoke checks."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Sequence

from .agent.loop import AgentContextError, AgentLoop, AgentOutputError, LLMProviderError
from .engine.attest import AttestationEngine, CancellationError, Verdict
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


def propose_claim(mandate: str, symbol: str) -> int:
    try:
        claim = AgentLoop(BinanceMCPClient()).generate_claim(mandate, symbol=symbol)
    except (AgentContextError, AgentOutputError, LLMProviderError, MCPError, ValueError) as exc:
        print(f"proposal=error reason={exc}", file=sys.stderr)
        return 1
    print(json.dumps(claim.to_mapping(), sort_keys=True))
    return 0


def run_claim(
    claim_file: str,
    receipts_file: str,
    confirm_live_write: bool,
    cancel_after_attestation: bool,
) -> int:
    if not confirm_live_write:
        print("claim=blocked reason=explicit live-write confirmation is required", file=sys.stderr)
        return 2
    try:
        with Path(claim_file).open(encoding="utf-8") as handle:
            claim = Claim.from_mapping(json.load(handle))
        session = Session(f"session-{uuid.uuid4().hex[:12]}", ReceiptLog(receipts_file))
        session.connect()
        session.activate()
        engine = AttestationEngine(BinanceMCPClient(), session)
        result = engine.place_and_attest(claim)
        output = result.to_mapping()
        if cancel_after_attestation:
            if result.verdict is not Verdict.PROVED or result.order_id is None:
                print("claim=error reason=attestation was not proved; cancellation skipped", file=sys.stderr)
                return 1
            cancelled = engine.cancel_order(claim, result.order_id)
            output["cancellation"] = {
                "orderId": cancelled.order_id,
                "status": cancelled.status,
                "verdict": Verdict.PROVED.value,
            }
    except (OSError, json.JSONDecodeError, ClaimValidationError, CancellationError, MCPError, ValueError) as exc:
        print(f"claim=error reason={exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0 if result.verdict is Verdict.PROVED else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qualto")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke", help="verify the supported Binance MCP gateway")
    propose_parser = subparsers.add_parser("propose", help="generate one claim without placing an order")
    propose_parser.add_argument("--mandate", required=True, help="free-text operator mandate")
    propose_parser.add_argument("--symbol", default="BNBUSDT", help="uppercase Binance spot symbol")
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
    claim_parser.add_argument(
        "--cancel-after-attestation",
        action="store_true",
        help="cancel the proved order immediately after dual readback",
    )
    args = parser.parse_args(argv)
    if args.command == "smoke":
        return smoke()
    if args.command == "propose":
        return propose_claim(args.mandate, args.symbol)
    if args.command == "claim":
        return run_claim(
            args.claim_file,
            args.receipts_file,
            args.confirm_live_write,
            args.cancel_after_attestation,
        )
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
