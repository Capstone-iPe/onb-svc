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
        _load_fixtures()

    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        if not file:
            return {"accepted": False, "reason_code": "no_bytes"}
        if _format(file) is None:
            return {"accepted": False, "reason_code": "format"}

        text = file.decode("utf-8", errors="ignore").strip()
        lowered = text.lower()
        legal_name = shop_name.strip().lower()

        # Tier 0: Check synthetic fixtures table (by sha256 or filename hint)
        digest = hashlib.sha256(file).hexdigest()
        fix = _FIXTURES_BY_SHA.get(digest) or _FIXTURES_BY_FILE.get(Path(text).name)
        if fix:
            if fix.get("slot") != slot:
                return {"accepted": False, "reason_code": "wrong_document"}
            is_acc = fix.get("accepted") == "True"
            code = fix.get("reason_code", "ACCEPTED" if is_acc else "WRONG_DOCUMENT")
            return {
                "accepted": is_acc,
                "reason_code": _CODE_MAP.get(code, code.lower()),
            }

        # Generic reject test hook
        if "reject" in lowered:
            return {"accepted": False, "reason_code": "rejected"}

        # Slot-kind validation based on keywords
        if slot == "dpa_addendum":
            if any(k in lowered for k in ("reg_pdf", "registration", "bank_letter", "passbook", "id_card", "shopfront")) and not any(k in lowered for k in ("addendum", "dpa")):
                return {"accepted": False, "reason_code": "wrong_document"}
        elif slot == "bank_proof":
            if any(k in lowered for k in ("shopfront", "registration", "addendum", "utility_bill", "fssai", "udyam")) and not any(k in lowered for k in ("bank", "passbook", "cheque")):
                return {"accepted": False, "reason_code": "wrong_document"}
        elif slot == "business_registration":
            if any(k in lowered for k in ("fssai", "udyam", "utility_bill", "passbook", "cheque", "addendum")) and not any(k in lowered for k in ("registration", "reg_")):
                return {"accepted": False, "reason_code": "wrong_document"}
        elif slot == "owner_id":
            if any(k in lowered for k in ("selfie", "stamp", "portrait", "kyc_csv")):
                return {"accepted": False, "reason_code": "wrong_document"}
        elif slot == "shopfront_photo":
            if any(k in lowered for k in ("interior", "render", "website", "menu")):
                return {"accepted": False, "reason_code": "not_shopfront"}

        if slot == "bank_proof" and "personal" in lowered and legal_name not in lowered:
            return {"accepted": False, "reason_code": "not_legal_name"}
        if legal_name and any(k in lowered for k in ("other_shop", "other_company", "different_shop")):
            return {"accepted": False, "reason_code": "not_legal_name"}
        if slot == "shopfront_photo" and _photo_too_old(text, submit_date):
            return {"accepted": False, "reason_code": "too_old"}
        if slot == "dpa_addendum" and "unsigned" in lowered:
            return {"accepted": False, "reason_code": "unsigned"}
        if "reject" in lowered:
            return {"accepted": False, "reason_code": "rejected"}
        return {"accepted": True, "reason_code": "ok"}
