"""ChatGPT keeps the client id. A restart must still know it."""

from __future__ import annotations

from mcp.shared.auth import OAuthClientInformationFull

from onb.clients.client_directory import ClientDirectory
from onb.postgres import connect


class PostgresClients(ClientDirectory):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._ready = False

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        self._ensure()
        with connect(self.database_url) as conn:
            row = conn.execute(
                "SELECT record FROM oauth_clients WHERE client_id = %s",
                (client_id,),
            ).fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row[0])

    def put(self, client: OAuthClientInformationFull) -> None:
        from psycopg.types.json import Jsonb

        self._ensure()
        record = client.model_dump(mode="json")
        with connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO oauth_clients (client_id, record)
                VALUES (%s, %s)
                ON CONFLICT (client_id) DO UPDATE SET record = EXCLUDED.record
                """,
                (client.client_id, Jsonb(record)),
            )

    def _ensure(self) -> None:
        if self._ready:
            return
        with connect(self.database_url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id text PRIMARY KEY,
                    record jsonb NOT NULL
                )
                """
            )
        self._ready = True
