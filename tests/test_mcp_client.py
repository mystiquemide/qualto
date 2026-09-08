from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from qualto import __version__
from qualto.mcp.client import (
    BinanceMCPClient,
    CodexCredentialProvider,
    CredentialError,
    MCPProtocolError,
    MCPTransportError,
    ToolNotAllowedError,
)


def write_credentials(
    path: Path, *, token: str = "test-token", expires_at: int | None = None
) -> None:
    document = {
        "binance": {
            "server_name": "binance-mcp-server",
            "server_url": "https://agent.binance.com/mcp/agentic",
            "client_id": "codex",
            "access_token": token,
            "expires_at": (
                int(time.time() * 1000) + 60_000 if expires_at is None else expires_at
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


def test_client_defaults_to_package_version(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)

    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))

    assert client.client_version == __version__


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


def test_client_rejects_non_object_gateway_arguments(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)
    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))

    with pytest.raises(TypeError, match="object"):
        client.call_visible_tool("tool_search", ["not-an-object"])  # type: ignore[arg-type]


def test_client_disconnect_blocks_requests_until_reconnect(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)
    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))
    client.disconnect()
    assert not client.connected
    with pytest.raises(MCPTransportError, match="disconnected"):
        client.initialize()
    client.reconnect()
    assert client.connected

    calls: list[str] = []

    def fake_request(method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        del params
        calls.append(method)
        return {"result": {"protocolVersion": "2025-03-26"}}

    client._request = fake_request  # type: ignore[method-assign]
    assert client.initialize()["protocolVersion"] == "2025-03-26"
    assert calls == ["initialize"]


def test_client_decodes_sse_and_nested_tool_result(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    write_credentials(credentials_path)
    client = BinanceMCPClient(CodexCredentialProvider(credentials_path))

    responses: Iterator[Mapping[str, Any]] = iter(
        [
            {
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "serverInfo": {"name": "binance"},
                }
            },
            {"result": {"tools": [{"name": "tool_search"}, {"name": "tool_execute"}]}},
            {
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps({"canTrade": True})}
                    ]
                }
            },
        ]
    )

    def next_response(method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        del method, params
        return next(responses)

    client._request = next_response  # type: ignore[method-assign]

    assert client.initialize()["protocolVersion"] == "2025-03-26"
    assert len(client.list_tools()) == 2
    assert client.account_read() == {"canTrade": True}


def test_jsonrpc_decoder_rejects_a_mismatched_response_id() -> None:
    payload = json.dumps({"jsonrpc": "2.0", "id": 99, "result": {"ok": True}}).encode()

    with pytest.raises(MCPProtocolError, match="ID"):
        BinanceMCPClient._decode_jsonrpc(payload, expected_id=1)


def test_jsonrpc_decoder_selects_the_matching_sse_response_id() -> None:
    payload = (
        b'event: message\ndata: {"jsonrpc":"2.0","id":99,"result":{"ok":false}}\n\n'
        b'event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n'
    )

    response = BinanceMCPClient._decode_jsonrpc(payload, expected_id=7)

    assert response["id"] == 7
    assert response["result"] == {"ok": True}
