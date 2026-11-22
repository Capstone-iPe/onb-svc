"""Format check plus fixture hints. There is no OCR.

PDF, JPG, and PNG are the allowed formats. A file is rejected when the text contains
"reject", a bank proof says "personal" and not the shop's legal name, a shopfront
date is more than 90 days before submit_date, or an addendum says "unsigned".
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from datetime import date
from pathlib import Path

from onb.verifier.document_verifier import DocumentVerifier
from onb.verifier.rules_document_verifier import RulesDocumentVerifier

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_FIXTURES_BY_SHA: dict[str, dict] = {}
_FIXTURES_BY_FILE: dict[str, dict] = {}
_FIXTURES_LOADED = False


def _load_fixtures() -> None:
    global _FIXTURES_LOADED
    if _FIXTURES_LOADED:
        return
    _FIXTURES_LOADED = True
    candidates = []
    if env := os.environ.get("FIXTURES_CSV"):
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    # ../../../../../analysis/synth/out/fixtures.csv
    candidates.append(here.parents[4] / "analysis" / "synth" / "out" / "fixtures.csv")
    for cand in candidates:
        if cand.is_file():
            try:
                with open(cand, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        sha = row.get("sha256")
                        fn = row.get("file", "")
                        if sha:
                            _FIXTURES_BY_SHA[sha] = row
                        if fn:
                            base = Path(fn).name
                            _FIXTURES_BY_FILE[base] = row
                            _FIXTURES_BY_FILE[fn] = row
            except Exception:
                pass
            break


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


_CODE_MAP = {
    "ACCEPTED": "ok",
    "FORMAT_UNSUPPORTED": "format",
    "PHOTO_TOO_OLD": "too_old",
    "NAME_MISMATCH": "not_legal_name",
    "UNSIGNED": "unsigned",
    "WRONG_DOCUMENT": "wrong_document",
    "NOT_SHOPFRONT": "not_shopfront",
    "FILE_UNREADABLE": "format",
}


class MockDocumentVerifier(DocumentVerifier):
    def __init__(self) -> None:
        self._rules = RulesDocumentVerifier()

    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        if not file:
            return {"accepted": False, "reason_code": "no_bytes"}
        res = self._rules.verify(slot, shop_name, file, submit_date)
        code = res.get("reason_code", "ok")
        return {
            "accepted": res["accepted"],
            "reason_code": _CODE_MAP.get(code, code.lower()),
        }
