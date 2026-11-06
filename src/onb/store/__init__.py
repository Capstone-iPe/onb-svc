"""The application repository. One class per file."""

from __future__ import annotations

import os

from onb.store.application_store import ApplicationStore
from onb.store.memory_application_store import MemoryApplicationStore
from onb.store.postgres_application_store import PostgresApplicationStore

__all__ = [
    "ApplicationStore",
    "MemoryApplicationStore",
    "PostgresApplicationStore",
    "open_application_store",
]


def open_application_store() -> ApplicationStore:
    url = os.environ.get("DATABASE_URL")
    if url:
        return PostgresApplicationStore(url)
    return MemoryApplicationStore()
