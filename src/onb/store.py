"""Applications live here. One row is the id plus the snapshot. Verdict columns come later."""

from __future__ import annotations

import copy
import os
import uuid


def new_application_id() -> str:
    return "app_" + uuid.uuid4().hex[:12]


class ApplicationStore:
    """Memory when DATABASE_URL is unset. Postgres when it is set."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url
        self._rows: dict[str, dict] = {}
        self._ready = False

    @classmethod
    def from_env(cls) -> ApplicationStore:
        return cls(os.environ.get("DATABASE_URL"))

    def create(self, snapshot: dict) -> str:
        application_id = new_application_id()
        if self.database_url:
            self._postgres_put(application_id, snapshot)
        else:
            self._rows[application_id] = copy.deepcopy(snapshot)
        return application_id

    def get(self, application_id: str) -> dict | None:
        if self.database_url:
            return self._postgres_get(application_id)
        row = self._rows.get(application_id)
        return copy.deepcopy(row) if row is not None else None

    def count(self) -> int:
        if self.database_url:
            self._ensure_table()
            with self._connect() as conn:
                row = conn.execute("SELECT count(*) FROM applications").fetchone()
            return int(row[0])
        return len(self._rows)

    def _connect(self):
        import psycopg

        url = self.database_url or ""
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        return psycopg.connect(url, autocommit=True)

    def _ensure_table(self) -> None:
        if self._ready:
            return
        with self._connect() as conn:
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

    def _postgres_put(self, application_id: str, snapshot: dict) -> None:
        from psycopg.types.json import Jsonb

        self._ensure_table()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO applications (id, snapshot) VALUES (%s, %s)",
                (application_id, Jsonb(snapshot)),
            )

    def _postgres_get(self, application_id: str) -> dict | None:
        self._ensure_table()
        with self._connect() as conn:
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
