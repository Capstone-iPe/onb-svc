"""The document check. A real checker and the mock both implement this."""

from __future__ import annotations

from typing import Protocol


class DocumentVerifier(Protocol):
    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        """Return whether the file is accepted for this slot."""
