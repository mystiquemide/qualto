from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from qualto.mcp.client import (
    BinanceMCPClient,
    CodexCredentialProvider,
    CredentialError,
    ToolNotAllowedError,
)


def write_credentials(path: Path, *, token: str = "test-token", expires_at: int | None = None) -> None:
    document = {
        "binance": {
            "server_name": "binance-mcp-server",
            "server_url": "https://agent.binance.com/mcp/agentic",
            "client_id": "codex",
            "access_token": token,
            "expires_at": (
                int(time.time() * 1000) + 60_000
                if expires_at is None
                else expires_at
            ),
        }
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def test_provider_selects_registered_codex_credential(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)

    credential = CodexCredentialProvider(credentials_path).load()

    assert credential.client_id == "codex"
    assert credential.access_token == "test-token"
    assert not credential.is_expired()


def test_provider_fails_closed_for_expired_credential(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path, expires_at=int(time.time() * 1000) - 1)

    with pytest.raises(CredentialError, match="expired"):
        CodexCredentialProvider(credentials_path).load()


def test_provider_error_does_not_include_token(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path, token="do-not-leak", expires_at=0)

    with pytest.raises(CredentialError) as error:
        CodexCredentialProvider(credentials_path).load()

    assert "do-not-leak" not in str(error.value)


def test_client_rejects_operations_outside_allowlist(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)
    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))

    with pytest.raises(ToolNotAllowedError):
        client.execute("wallet.withdraw", {})


def test_client_decodes_sse_and_nested_tool_result(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)
    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))

    responses = iter(
        [
            {
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "serverInfo": {"name": "binance"},
                }
            },
            {"result": {"tools": [{"name": "tool_search"}, {"name": "tool_execute"}]}},
            {"result": {"content": [{"type": "text", "text": json.dumps({"canTrade": True})}]}},
        ]
    )
    client._request = lambda method, params: next(responses)  # type: ignore[method-assign]

    assert client.initialize()["protocolVersion"] == "2025-03-26"
    assert len(client.list_tools()) == 2
    assert client.account_read() == {"canTrade": True}
