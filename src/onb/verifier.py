"""Document Verifier seam. ONB calls this. The copilot never writes accepted.

The mock checks the format and a few fixture hints. It does not read a real document.
PDF, JPG, and PNG are the allowed formats. A file is rejected when the text contains
"reject", a bank proof says "personal" and not the shop's legal name, a shopfront
date is more than 90 days before submit_date, or an addendum says "unsigned".
"""

from __future__ import annotations

import base64
import re
from datetime import date
from typing import Protocol

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class DocumentVerifier(Protocol):
    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        """Return whether the file is accepted for this slot."""


def file_bytes(file: str | None) -> bytes:
    """Turn the copilot's file string into bytes. "Attached" with no file is empty."""
    if file is None:
        return b""
    text = file.strip()
    if text == "" or text.lower() == "attached":
        return b""
    payload = text
    if payload.startswith("data:") and "base64," in payload:
        payload = payload.split("base64,", 1)[1]
    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:
        decoded = b""
    if decoded:
        return decoded
    return text.encode("utf-8")


def _format(file: bytes) -> str | None:
    if file.startswith(b"%PDF"):
        return "pdf"
    if file.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if file.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    text = file.decode("utf-8", errors="ignore").strip().lower()
    for ext, name in ((".pdf", "pdf"), (".jpeg", "jpeg"), (".jpg", "jpeg"), (".png", "png")):
        if text.endswith(ext):
            return name
    return None


def _photo_too_old(text: str, submit_date: str) -> bool:
    try:
        submitted = date.fromisoformat(submit_date[:10])
    except ValueError:
        return False
    for raw in _ISO_DATE.findall(text):
        taken = date.fromisoformat(raw)
        if (submitted - taken).days > 90:
            return True
    return False


class MockDocumentVerifier:
    """Format check plus fixture hints. There is no OCR."""

    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        if not file:
            return {"accepted": False, "reason_code": "no_bytes"}
        if _format(file) is None:
            return {"accepted": False, "reason_code": "format"}
        text = file.decode("utf-8", errors="ignore")
        lowered = text.lower()
        legal_name = shop_name.strip().lower()
        if slot == "bank_proof" and "personal" in lowered and legal_name not in lowered:
            return {"accepted": False, "reason_code": "not_legal_name"}
        if slot == "shopfront_photo" and _photo_too_old(text, submit_date):
            return {"accepted": False, "reason_code": "too_old"}
        if slot == "dpa_addendum" and "unsigned" in lowered:
            return {"accepted": False, "reason_code": "unsigned"}
        if "reject" in lowered:
            return {"accepted": False, "reason_code": "rejected"}
        return {"accepted": True, "reason_code": "ok"}
