"""One way to open the Render Postgres connection."""

from __future__ import annotations


def connect(database_url: str):
    import psycopg

    url = database_url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return psycopg.connect(url, autocommit=True)
