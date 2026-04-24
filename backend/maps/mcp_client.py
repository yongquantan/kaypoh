"""
MCP JSON-RPC client for maps.grab.com/api/v1/mcp.

Used for exactly ONE call per audit — the address geocode — so the terminal
shows a real MCP round-trip. Falls back to HTTP gracefully when:

  * `MCP_BEARER` env var is missing
  * The endpoint returns 503 (intermittent)
  * The server responds with non-JSON or an SSE frame we can't parse

Transport: streamable-HTTP. Accept both `application/json` and
`text/event-stream`. `initialize` once, reuse the `mcp-session-id` header.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

MCP_URL = os.environ.get("MCP_URL", "https://maps.grab.com/api/v1/mcp")


class MCPUnavailable(RuntimeError):
    """Raised when MCP cannot be used (no bearer, 503, bad payload)."""


class GrabMapsMCP:
    def __init__(
        self,
        bearer: str | None = None,
        url: str = MCP_URL,
        timeout: float = 10.0,
    ):
        self.bearer = bearer or os.environ.get("MCP_BEARER") or ""
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._req_id = 0
        self.available = bool(self.bearer)

    async def __aenter__(self) -> "GrabMapsMCP":
        if not self.available:
            return self
        headers = {
            "Authorization": f"Bearer {self.bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available or self._client is None:
            raise MCPUnavailable("MCP bearer missing or client not entered")
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        headers = {}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        try:
            resp = await self._client.post(self.url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise MCPUnavailable(f"MCP transport error: {e}") from e
        if resp.status_code >= 500:
            raise MCPUnavailable(f"MCP {resp.status_code}")
        if resp.status_code >= 400:
            raise MCPUnavailable(f"MCP client error {resp.status_code}: {resp.text[:200]}")

        # Capture session id on first success
        sid = resp.headers.get("mcp-session-id")
        if sid and not self.session_id:
            self.session_id = sid

        body = resp.text.strip()
        parsed = self._parse_body(body, resp.headers.get("content-type", ""))
        if "error" in parsed:
            raise MCPUnavailable(f"MCP error: {parsed['error']}")
        return parsed.get("result", parsed)

    @staticmethod
    def _parse_body(body: str, content_type: str) -> dict[str, Any]:
        if "text/event-stream" in content_type or body.startswith("event:") or "\ndata:" in body:
            # Extract last `data: ...` line
            data_line = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    data_line = line[len("data:"):].strip()
            if not data_line:
                raise MCPUnavailable("SSE frame had no data payload")
            return json.loads(data_line)
        if not body:
            return {}
        return json.loads(body)

    async def initialize(self) -> dict[str, Any]:
        return await self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "kaypoh-backend", "version": "0.1.0"},
            },
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke an MCP tool. Returns the JSON-decoded content[0].text when
        the tool wraps its payload as text; otherwise returns the raw result.
        """
        result = await self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        # Unwrap content array
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                text = first["text"]
                try:
                    return json.loads(text)
                except (TypeError, json.JSONDecodeError):
                    return text
        return result
