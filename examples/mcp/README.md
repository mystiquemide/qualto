# MCP client setup

Qualto uses standard MCP over local stdio. Any coding agent that supports local MCP servers can launch the same `qualto-mcp` command. Copy the `qualto` entry from [`mcp-client.json`](mcp-client.json) into that agent's MCP configuration.

The server exposes policy tools for live context, claim-bound attestation, orphan cleanup, session status, and read-only receipt verification. It never exposes raw Binance operations. Keep `QUALTO_ENABLE_LIVE_WRITES` set to `0` until the operator is ready to arm live writes.

The Binance credential remains deployment-specific. Use a Binance-supported host-managed credential path and do not place a token in this configuration file.
