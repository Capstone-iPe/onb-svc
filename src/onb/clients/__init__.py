"""Saved MCP client registrations."""

from onb.clients.client_directory import ClientDirectory
from onb.clients.memory_clients import MemoryClients
from onb.clients.postgres_clients import PostgresClients

__all__ = ["ClientDirectory", "MemoryClients", "PostgresClients", "client_directory"]


def client_directory() -> ClientDirectory:
    import os

    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return PostgresClients(url)
    return MemoryClients()
