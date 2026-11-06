"""The application row survives a restart."""

from __future__ import annotations

from onb.postgres import connect
from onb.store.application_store import ApplicationStore
from onb.store.ids import new_application_id


class PostgresApplicationStore(ApplicationStore):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._ready = False

    def create(self, snapshot: dict) -> str:
        application_id = new_application_id()
        self._put(application_id, snapshot)
        return application_id

    def replace(self, application_id: str, snapshot: dict) -> bool:
        from psycopg.types.json import Jsonb

        self._ensure_table()
        with connect(self.database_url) as conn:
            cursor = conn.execute(
                "UPDATE applications SET snapshot = %s WHERE id = %s",
                (Jsonb(snapshot), application_id),
            )
        return cursor.rowcount == 1

    def get(self, application_id: str) -> dict | None:
        self._ensure_table()
        with connect(self.database_url) as conn:
            row = conn.execute(
                "SELECT snapshot FROM applications WHERE id = %s",
                (application_id,),
            ).fetchone()
        if row is None:
            return None
        snapshot = row[0]
        if isinstance(snapshot, str):
            import json

            snapshot = json.loads(snapshot)
        return snapshot

    def allocate_review_id(self) -> str:
        self._ensure_table()
        with connect(self.database_url) as conn:
            conn.execute("CREATE SEQUENCE IF NOT EXISTS review_ids START 2041")
            row = conn.execute("SELECT nextval('review_ids')").fetchone()
        return f"MR-{int(row[0])}"

    def count(self) -> int:
        self._ensure_table()
        with connect(self.database_url) as conn:
            row = conn.execute("SELECT count(*) FROM applications").fetchone()
        return int(row[0])

    def _ensure_table(self) -> None:
        if self._ready:
            return
        with connect(self.database_url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id text PRIMARY KEY,
                    snapshot jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        self._ready = True

    def _put(self, application_id: str, snapshot: dict) -> None:
        from psycopg.types.json import Jsonb

        self._ensure_table()
        with connect(self.database_url) as conn:
            conn.execute(
                "INSERT INTO applications (id, snapshot) VALUES (%s, %s)",
                (application_id, Jsonb(snapshot)),
            )
