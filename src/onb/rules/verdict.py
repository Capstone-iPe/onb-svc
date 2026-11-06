"""The verdict. Code over the snapshot. No model."""

from __future__ import annotations

import re

CEILING_INR = 4_000_000

_REFUSED = (
    "hawala",
    "hundi",
    "forex",
    "money service",
    "remittance",
    "crypto",
    "bitcoin",
    "nft",
    "gambling",
    "betting",
    "satta",
    "matka",
    "casino",
)

_PERMITTED = {
    "restaurant": "restaurant",
    "cafe": "restaurant",
    "coffee shop": "restaurant",
    "dhaba": "restaurant",
    "grocery": "grocery",
    "kirana": "grocery",
    "retail": "retail",
}


def parse_volume(value: str) -> int | None:
    text = value.strip().lower().replace("₹", "").replace(",", "")
    text = text.replace("rs.", "").replace("rs", "").strip()
    if text.isdigit():
        return int(text)
    return None


def classify(business_type: str) -> str:
    """permitted, refused, or unlisted. A refused word wins over a kinder word."""
    text = business_type.strip().lower()
    if any(re.search(rf"\b{re.escape(word)}\b", text) for word in _REFUSED):
        return "refused"
    for phrase, _canonical in sorted(_PERMITTED.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            return "permitted"
    return "unlisted"


def injection_flagged(note: str | None) -> bool:
    text = (note or "").lower()
    if "ignore" in text and "policy" in text:
        return True
    return re.search(r"\bactive\b|\bactivate\b", text) is not None


def decide(answers: dict, files: dict) -> dict:
    """One verdict. The caller allocates the review id, except when the type is refused."""
    kind = classify(str(answers.get("business_type") or ""))
    volume = parse_volume(str(answers.get("monthly_volume") or ""))
    gaps = [
        slot
        for slot, file in files.items()
        if file.get("state") != "accepted"
    ]
    phones = str(answers.get("stores_payer_phones") or "").strip().lower() in {"yes", "y", "true"}
    addendum_required = phones
    flagged = injection_flagged(answers.get("note"))
    above = volume is not None and volume > CEILING_INR
    citations: list[str] = ["ONB-POL-001 §3"]
    if gaps:
        citations.append("ONB-POL-001 §2")
    if addendum_required or flagged:
        citations.append("ONB-POL-003 §2")
    if kind == "refused":
        return {
            "outcome": "REFUSED",
            "business_type_allowed": False,
            "missing_items": gaps,
            "addendum_required": addendum_required,
            "volume_inr": volume,
            "assignee": None,
            "review_id": None,
            "citations": citations,
            "injection_flagged": flagged,
            "policy_conflict_noted": False,
        }
    if above:
        citations.extend(["ONB-POL-001 §4", "ONB-POL-002"])
    elif volume is not None:
        citations.append("ONB-POL-002")
    complete = not gaps
    outcome = "RECOMMEND_GO_LIVE" if kind == "permitted" and complete else "IN_REVIEW"
    assignee = "HEAD_OF_PAYMENTS" if above else "MERCHANT_RISK_LEAD"
    return {
        "outcome": outcome,
        "business_type_allowed": kind == "permitted",
        "missing_items": gaps,
        "addendum_required": addendum_required,
        "volume_inr": volume,
        "assignee": assignee,
        "review_id": None,
        "citations": citations,
        "injection_flagged": flagged,
        "policy_conflict_noted": above,
    }
