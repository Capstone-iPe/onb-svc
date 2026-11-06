"""A saved MCP client registration. Memory and Postgres both implement this.

Google sign-in looks up the caller here. Postgres keeps the registration across a restart.
"""

from __future__ import annotations

from typing import Protocol

from mcp.shared.auth import OAuthClientInformationFull


class ClientDirectory(Protocol):
    """The registration an MCP client sends when it connects.

    The copilot is that client. Claude and ChatGPT are stored here the same way while they talk to this server directly.
    """

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        """Return the registration stored for this client id.

        Return None when this id has not been stored.
        """
        ...

    def put(self, client: OAuthClientInformationFull) -> None:
        """Save this registration under client.client_id.

        A later get with that id returns it. Saving the same client id again replaces the stored registration.
        """
        ...
