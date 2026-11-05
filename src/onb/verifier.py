"""Document Verifier seam. ONB calls this. The copilot never does."""

from typing import Protocol


class DocumentVerifier(Protocol):
    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        """Return whether the file is accepted for this slot."""
