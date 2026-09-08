"""Qualto command-line smoke checks."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from .agent.loop import AgentContextError, AgentLoop, AgentOutputError, LLMProviderError
from .engine.attest import (
    AttestationEngine,
    CancellationError,
    CleanupError,
    Verdict,
)
from .engine.claim import Claim, ClaimValidationError
from .engine.flow import NegativePathRunner
from .engine.receipts import ReceiptLog
from .engine.session import Session, SessionState
from .engine.verify import VerificationError, verify_receipts
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
    except (
        AgentContextError,
        AgentOutputError,
        LLMProviderError,
        MCPError,
        ValueError,
    ) as exc:
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
        print(
            "claim=blocked reason=explicit live-write confirmation is required",
            file=sys.stderr,
        )
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
            if result.order_id is None:
                print(
                    "claim=error reason=no known order ID; cancellation skipped",
                    file=sys.stderr,
                )
                return 1
            cancelled = engine.cancel_order(claim, result.order_id)
            output["cancellation"] = {
                "orderId": cancelled.order_id,
                "status": cancelled.status,
                "verdict": Verdict.PROVED.value,
            }
    except (
        OSError,
        json.JSONDecodeError,
        ClaimValidationError,
        CancellationError,
        MCPError,
        ValueError,
    ) as exc:
        print(f"claim=error reason={exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0 if result.verdict is Verdict.PROVED else 1


def run_cleanup(claim_file: str, receipts_file: str, confirm_live_write: bool) -> int:
    """Recover an orphan order by claim ID and cancel its exact exchange ID."""

    if not confirm_live_write:
        print(
            "cleanup=blocked reason=explicit live-write confirmation is required",
            file=sys.stderr,
        )
        return 2
    try:
        with Path(claim_file).open(encoding="utf-8") as handle:
            claim = Claim.from_mapping(json.load(handle))
        session = Session(f"session-{uuid.uuid4().hex[:12]}", ReceiptLog(receipts_file))
        session.connect()
        session.activate()
        engine = AttestationEngine(BinanceMCPClient(), session)
        cancelled = engine.cleanup_by_claim(claim)
    except (
        OSError,
        json.JSONDecodeError,
        ClaimValidationError,
        CleanupError,
        CancellationError,
        MCPError,
        ValueError,
    ) as exc:
        print(f"cleanup=error reason={exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "claim": claim.to_mapping(),
                "cleanup": {
                    "orderId": cancelled.order_id,
                    "status": cancelled.status,
                    "verdict": Verdict.PROVED.value,
                },
            },
            sort_keys=True,
        )
    )
    return 0


def run_verify(receipts_file: str) -> int:
    """Re-verify receipt verdicts against live Binance order readbacks."""

    try:
        results = verify_receipts(receipts_file, BinanceMCPClient())
    except (OSError, MCPError, VerificationError, ValueError) as exc:
        print(f"verify=error reason={exc}", file=sys.stderr)
        return 1

    print("claimId\torderId\trecorded\tlive\tmatch\treason")
    for result in results:
        live_verdict = "-" if result.live_verdict is None else result.live_verdict.value
        print(
            "\t".join(
                [
                    result.claim_id,
                    "-" if result.order_id is None else str(result.order_id),
                    result.recorded_verdict or "-",
                    live_verdict,
                    "yes" if result.matched else "no",
                    result.reason,
                ]
            )
        )
    return 0 if all(result.matched for result in results) else 1


def run_agent(
    mandate: str,
    symbol: str,
    receipts_file: str,
    confirm_live_write: bool,
    cancel_after_attestation: bool,
    disconnect_before_order: bool,
) -> int:
    if not confirm_live_write:
        print(
            "agent=blocked reason=explicit live-write confirmation is required",
            file=sys.stderr,
        )
        return 2
    session: Session | None = None
    try:
        client = BinanceMCPClient()
        session = Session(f"session-{uuid.uuid4().hex[:12]}", ReceiptLog(receipts_file))
        session.connect()
        session.activate()
        claim = AgentLoop(client).generate_claim(mandate, symbol=symbol)
        engine = AttestationEngine(client, session)
        if disconnect_before_order:
            output = NegativePathRunner(client, session, engine).run(claim).to_mapping()
            print(json.dumps(output, sort_keys=True))
            return 0
        result = engine.place_and_attest(claim)
        output = {"claim": claim.to_mapping(), "attestation": result.to_mapping()}
        if cancel_after_attestation:
            if result.order_id is None:
                print(
                    "agent=error reason=no known order ID; cancellation skipped",
                    file=sys.stderr,
                )
                return 1
            cancelled = engine.cancel_order(claim, result.order_id)
            output["cancellation"] = {
                "orderId": cancelled.order_id,
                "status": cancelled.status,
                "verdict": Verdict.PROVED.value,
            }
    except (
        OSError,
        json.JSONDecodeError,
        AgentContextError,
        AgentOutputError,
        ClaimValidationError,
        CancellationError,
        LLMProviderError,
        MCPError,
        ValueError,
    ) as exc:
        if session is not None and session.state in {
            SessionState.CREATED,
            SessionState.CONNECTED,
            SessionState.ACTIVE,
        }:
            session.error(
                "agent execution failed",
                receipt={
                    "event": "session_error",
                    "outcome": "error",
                    "reason": "agent execution failed",
                    "errorType": type(exc).__name__,
                },
            )
        print(f"agent=error reason={exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0 if result.verdict is Verdict.PROVED else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qualto")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke", help="verify the supported Binance MCP gateway")
    propose_parser = subparsers.add_parser(
        "propose", help="generate one claim without placing an order"
    )
    propose_parser.add_argument(
        "--mandate", required=True, help="free-text operator mandate"
    )
    propose_parser.add_argument(
        "--symbol", default="BNBUSDT", help="uppercase Binance spot symbol"
    )
    claim_parser = subparsers.add_parser(
        "claim", help="place and attest one validated claim"
    )
    claim_parser.add_argument(
        "--claim-file", required=True, help="path to a claim JSON object"
    )
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
    cleanup_parser = subparsers.add_parser(
        "cleanup", help="recover an orphan order by claim ID and cancel it"
    )
    cleanup_parser.add_argument(
        "--claim-file", required=True, help="path to the original claim JSON object"
    )
    cleanup_parser.add_argument(
        "--receipts-file",
        default="runtime/receipts.jsonl",
        help="append-only JSONL receipt path",
    )
    cleanup_parser.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="explicitly authorize the live cancellation request",
    )
    verify_parser = subparsers.add_parser(
        "verify", help="re-verify claim receipts with read-only Binance reads"
    )
    verify_parser.add_argument(
        "--receipts-file",
        default="runtime/receipts.jsonl",
        help="append-only JSONL receipt path to verify",
    )
    agent_parser = subparsers.add_parser(
        "agent", help="generate, attest, and optionally cancel one claim"
    )
    agent_parser.add_argument(
        "--mandate", required=True, help="free-text operator mandate"
    )
    agent_parser.add_argument(
        "--symbol", default="BNBUSDT", help="uppercase Binance spot symbol"
    )
    agent_parser.add_argument(
        "--receipts-file",
        default="runtime/receipts.jsonl",
        help="append-only JSONL receipt path",
    )
    agent_parser.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="explicitly authorize the live order request",
    )
    agent_parser.add_argument(
        "--cancel-after-attestation",
        action="store_true",
        help="cancel the known order after attestation, including cleanup after an unproved readback",
    )
    agent_parser.add_argument(
        "--disconnect-before-order",
        action="store_true",
        help="sever the gateway after claim generation to prove the blocked negative path",
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
    if args.command == "cleanup":
        return run_cleanup(
            args.claim_file,
            args.receipts_file,
            args.confirm_live_write,
        )
    if args.command == "verify":
        return run_verify(args.receipts_file)
    if args.command == "agent":
        return run_agent(
            args.mandate,
            args.symbol,
            args.receipts_file,
            args.confirm_live_write,
            args.cancel_after_attestation,
            args.disconnect_before_order,
        )
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
