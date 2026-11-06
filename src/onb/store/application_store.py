"""The application row. Memory and Postgres both implement this."""

from __future__ import annotations

from typing import Protocol


class ApplicationStore(Protocol):
    def create(self, snapshot: dict) -> str: ...

    def replace(self, application_id: str, snapshot: dict) -> bool: ...

    def get(self, application_id: str) -> dict | None: ...

    def allocate_review_id(self) -> str: ...

    def count(self) -> int: ...
