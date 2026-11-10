"""The verdict. Code over the snapshot. No model."""

from __future__ import annotations

import re

CEILING_INR = 4_000_000

_REFUSED = (
    "hawala",
    "hundi",
    "forex",
    "money service",
    "money transfer",
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


_LAKH = 100_000
_CRORE = 10_000_000
_VOLUME_UNIT = re.compile(r"^(\d+(?:\.\d+)?)\s*(lakh|lakhs|crore|crores)$")
_YES = {"yes", "y", "true", "haan"}
_NO = {"no", "n", "false"}


def parse_volume(value: str) -> int | None:
    """The rupee figure, or None when the words are not that figure.

    Digits, or a number of lakh or crore. A sentence around the figure is not a figure.
    """
    text = value.strip().lower().replace("₹", "").replace(",", "")
    text = re.sub(r"\brs\.?|\binr\b", "", text)
    text = " ".join(text.split())
    if text.isdigit():
        return int(text)
    match = _VOLUME_UNIT.fullmatch(text)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = _LAKH if match.group(2).startswith("lakh") else _CRORE
    figure = amount * unit
    if figure != int(figure):
        return None
    return int(figure)


def phone_stored(value: object) -> bool | None:
    """True or False when the answer starts with yes or no. None otherwise."""
    if value is True:
        return True
    if value is False:
        return False
    if not isinstance(value, str):
        return None
    word = re.match(r"[a-z]+", value.strip().lower())
    if word is None:
        return None
    token = word.group(0)
    if token in _YES:
        return True
    if token in _NO:
        return False
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
    phones = phone_stored(answers.get("stores_payer_phones")) is True
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
