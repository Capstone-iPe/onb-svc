"""A saved MCP client registration. Memory and Postgres both implement this."""

from __future__ import annotations

from typing import Protocol

from mcp.shared.auth import OAuthClientInformationFull


class ClientDirectory(Protocol):
    def get(self, client_id: str) -> OAuthClientInformationFull | None: ...

    def put(self, client: OAuthClientInformationFull) -> None: ...
