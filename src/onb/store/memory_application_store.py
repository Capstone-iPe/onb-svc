"""The process remembers applications until it stops."""

from __future__ import annotations

import copy

from onb.store.application_store import ApplicationStore
from onb.store.ids import new_application_id


class MemoryApplicationStore(ApplicationStore):
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._next_review = 2041

    def create(self, snapshot: dict) -> str:
        application_id = new_application_id()
        self._rows[application_id] = copy.deepcopy(snapshot)
        return application_id

    def replace(self, application_id: str, snapshot: dict) -> bool:
        if application_id not in self._rows:
            return False
        self._rows[application_id] = copy.deepcopy(snapshot)
        return True

    def get(self, application_id: str) -> dict | None:
        row = self._rows.get(application_id)
        return copy.deepcopy(row) if row is not None else None

    def allocate_review_id(self) -> str:
        review_id = f"MR-{self._next_review}"
        self._next_review += 1
        return review_id

    def count(self) -> int:
        return len(self._rows)
