"""Qualto command-line smoke checks."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qualto")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke", help="verify the supported Binance MCP gateway")
    args = parser.parse_args(argv)
    if args.command == "smoke":
        return smoke()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
