"""The application row. Memory and Postgres both implement this.

Intake reads and writes applications through these methods. It does not open the database itself.
"""

from __future__ import annotations

from typing import Protocol


class ApplicationStore(Protocol):
    """Where an application snapshot is kept."""

    def create(self, snapshot: dict) -> str:
        """Save a new snapshot and return its application id.

        The id looks like app_ followed by twelve hex characters. This call does not allocate a review id.
        """
        ...

    def replace(self, application_id: str, snapshot: dict) -> bool:
        """Write this snapshot over the row for application_id.

        Return True when that row was updated. Return False when no row has this id.
        """
        ...

    def get(self, application_id: str) -> dict | None:
        """Return the snapshot stored for this id.

        Return None when no row has this id. A change to the returned dict is saved only by replace.
        """
        ...

    def allocate_review_id(self) -> str:
        """Return the next review id.

        The first id is MR-2041. Each later call returns the next number. submit calls this when the verdict is kept. A REFUSED verdict leaves review_id empty and does not call this.
        """
        ...

    def count(self) -> int:
        """Return how many application rows are stored."""
        ...
