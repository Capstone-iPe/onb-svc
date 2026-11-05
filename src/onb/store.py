"""Applications and verdicts will live in Render Postgres. The tables are not designed yet."""

import os


class ApplicationStore:
    """Holds the database URL. Rows are not written until the schema exists."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url

    @classmethod
    def from_env(cls) -> "ApplicationStore":
        return cls(os.environ.get("DATABASE_URL"))
