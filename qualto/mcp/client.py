"""Small, fail-closed client for the supported Binance MCP host gateway.

The Binance OAuth session belongs to the registered Codex host. Qualto reads
the host-managed credential only when a request is made, keeps it in memory for
that request, and never includes it in errors, receipts, or logs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "https://agent.binance.com/mcp/agentic"
DEFAULT_CREDENTIALS_PATH = "/root/.codex/.credentials.json"
DEFAULT_SERVER_NAME = "binance-mcp-server"
DEFAULT_CLIENT_ID = "codex"
MCP_PROTOCOL_VERSION = "2025-03-26"

# These are the only Binance operations the claim engine may request. The
# remote server exposes tool_search/tool_execute as the visible MCP surface,
# so the underlying operation names are enforced here as a second boundary.
ALLOWED_TOOL_NAMES = frozenset(
    {
        "spot.getAccount",
        "spot.tickerPrice",
        "spot.newOrder",
        "spot.getOrder",
        "spot.myTrades",
        "spot.deleteOrder",
    }
)


class MCPError(RuntimeError):
    """Base error for bounded MCP failures."""


class CredentialError(MCPError):
    """The host-managed credential cannot be used."""


class MCPTransportError(MCPError):
    """The MCP endpoint could not be reached or returned an HTTP failure."""


class MCPProtocolError(MCPError):
    """The endpoint returned an invalid or failed JSON-RPC response."""


class ToolNotAllowedError(MCPError):
    """The requested underlying Binance operation is outside the gateway allowlist."""


@dataclass(frozen=True)
class HostCredential:
    """An in-memory view of the registered host credential."""

    access_token: str
    client_id: str
    expires_at_ms: int

    def is_expired(self, now_ms: int | None = None) -> bool:
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        return self.expires_at_ms <= current_ms


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MCPProtocolError("Binance MCP returned an invalid object")
    return value


class CodexCredentialProvider:
    """Load the registered Codex credential without copying or logging it."""

    def __init__(
        self,
        credentials_path: str | Path | None = None,
        *,
        server_name: str = DEFAULT_SERVER_NAME,
        server_url: str = DEFAULT_ENDPOINT,
        client_id: str = DEFAULT_CLIENT_ID,
    ) -> None:
        if credentials_path is not None:
            configured_path = credentials_path
        else:
            configured_path = (
                os.getenv("QUALTO_CODEX_CREDENTIALS_FILE") or DEFAULT_CREDENTIALS_PATH
            )
        self.credentials_path = Path(configured_path)
        self.server_name = server_name
        self.server_url = server_url
        self.client_id = client_id

    def load(self) -> HostCredential:
        try:
            with self.credentials_path.open(encoding="utf-8") as handle:
                document = json.load(handle)
        except (
            FileNotFoundError,
            PermissionError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            raise CredentialError(
                "host-managed Binance credential is unavailable"
            ) from exc

        if not isinstance(document, Mapping):
            raise CredentialError("host-managed Binance credential is malformed")

        candidates = [
            entry
            for entry in document.values()
            if isinstance(entry, Mapping)
            and entry.get("server_name") == self.server_name
            and entry.get("server_url") == self.server_url
        ]
        if len(candidates) != 1:
            raise CredentialError("registered Binance host credential is unavailable")

        entry = candidates[0]
        token = entry.get("access_token")
        entry_client_id = entry.get("client_id")
        expires_at_ms = entry.get("expires_at")
        if (
            not isinstance(token, str)
            or not token
            or entry_client_id != self.client_id
            or not isinstance(expires_at_ms, (int, float))
        ):
            raise CredentialError("registered Binance host credential is malformed")

        credential = HostCredential(
            access_token=token,
            client_id=str(entry_client_id),
            expires_at_ms=int(expires_at_ms),
        )
        if credential.is_expired():
            raise CredentialError("registered Binance host credential is expired")
        return credential


class BinanceMCPClient:
    """JSON-RPC client for the supported Binance Agent OS MCP endpoint."""

    def __init__(
        self,
        credential_provider: CodexCredentialProvider | None = None,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 20.0,
        client_name: str = "qualto",
        client_version: str = "0.1.0",
    ) -> None:
        self.credential_provider = credential_provider or CodexCredentialProvider()
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.client_name = client_name
        self.client_version = client_version
        self._next_request_id = 1
        self._initialized = False
        self._protocol_version: str | None = None
        self._connected = True

    @property
    def protocol_version(self) -> str | None:
        return self._protocol_version

    @property
    def connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        """Disable all MCP calls until an explicit reconnect."""

        self._connected = False
        self._initialized = False

    def reconnect(self) -> None:
        """Restore MCP calls and require a fresh initialize handshake."""

        self._connected = True
        self._initialized = False
        self._protocol_version = None

    def _request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self._connected:
            raise MCPTransportError("Binance MCP gateway is disconnected")
        credential = self.credential_provider.load()
        request_id = self._next_request_id
        self._next_request_id += 1
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {credential.access_token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise MCPTransportError(f"Binance MCP HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MCPTransportError("Binance MCP endpoint is unavailable") from exc

        return self._decode_jsonrpc(raw)

    @staticmethod
    def _decode_jsonrpc(raw: bytes) -> Mapping[str, Any]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MCPProtocolError("Binance MCP returned non-UTF-8 data") from exc

        candidates = [
            line[6:] for line in text.splitlines() if line.startswith("data: ")
        ]
        encoded = candidates[-1] if candidates else text.strip()
        if not encoded:
            raise MCPProtocolError("Binance MCP returned an empty response")
        try:
            response = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise MCPProtocolError("Binance MCP returned invalid JSON") from exc
        response_mapping = _as_mapping(response)
        if "error" in response_mapping:
            raise MCPProtocolError("Binance MCP returned an error")
        return response_mapping

    def initialize(self) -> Mapping[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": self.client_name,
                    "version": self.client_version,
                },
            },
        )
        result = _as_mapping(response.get("result"))
        protocol_version = result.get("protocolVersion")
        if not isinstance(protocol_version, str) or not protocol_version:
            raise MCPProtocolError("Binance MCP initialize response is incomplete")
        self._protocol_version = protocol_version
        self._initialized = True
        return result

    def list_tools(self) -> list[Mapping[str, Any]]:
        if not self._initialized:
            self.initialize()
        response = self._request("tools/list", {})
        result = _as_mapping(response.get("result"))
        tools = result.get("tools")
        if not isinstance(tools, list) or not all(
            isinstance(tool, Mapping) for tool in tools
        ):
            raise MCPProtocolError("Binance MCP tools/list response is invalid")
        return tools

    def call_visible_tool(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        if tool_name not in {"tool_search", "tool_execute"}:
            raise ToolNotAllowedError("MCP gateway tool is not allowed")
        if arguments is not None and not isinstance(arguments, Mapping):
            raise TypeError("MCP gateway arguments must be an object")
        if not self._initialized:
            self.initialize()
        response = self._request(
            "tools/call",
            {"name": tool_name, "arguments": dict(arguments or {})},
        )
        return _as_mapping(response.get("result"))

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        if tool_name not in ALLOWED_TOOL_NAMES:
            raise ToolNotAllowedError(
                "Binance operation is outside the Qualto allowlist"
            )
        result = self.call_visible_tool(
            "tool_execute",
            {"toolName": tool_name, "arguments": dict(arguments or {})},
        )
        return self._decode_tool_result(result)

    def search(self, category: str, cursor: str | None = None) -> Any:
        if not category:
            raise ValueError("tool search category is required")
        arguments: dict[str, Any] = {"category": category}
        if cursor:
            arguments["cursor"] = cursor
        result = self.call_visible_tool("tool_search", arguments)
        return self._decode_tool_result(result)

    @staticmethod
    def _decode_tool_result(result: Mapping[str, Any]) -> Any:
        content = result.get("content")
        if not isinstance(content, list):
            raise MCPProtocolError("Binance MCP tool response is invalid")
        for item in content:
            if isinstance(item, Mapping) and item.get("type") == "text":
                text = item.get("text")
                if not isinstance(text, str):
                    raise MCPProtocolError("Binance MCP tool response text is invalid")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        raise MCPProtocolError("Binance MCP tool response has no readable content")

    def account_read(self) -> Any:
        return self.execute("spot.getAccount", {"omitZeroBalances": True})
