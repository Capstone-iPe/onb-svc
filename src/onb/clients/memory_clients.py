"""The process remembers registrations until it stops."""

from __future__ import annotations

from mcp.shared.auth import OAuthClientInformationFull

from onb.clients.client_directory import ClientDirectory


class MemoryClients(ClientDirectory):
    def __init__(self) -> None:
        self._rows: dict[str, OAuthClientInformationFull] = {}

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._rows.get(client_id)

    def put(self, client: OAuthClientInformationFull) -> None:
        self._rows[client.client_id] = client
