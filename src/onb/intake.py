"""What ONB asks for next. Field order is policy. The copilot does not choose it."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from onb.store import ApplicationStore

ANSWER_FIELDS = (
    "shop_name",
    "city",
    "business_type",
    "monthly_volume",
    "payment_methods",
    "stores_payer_phones",
)

PACK_SLOTS = (
    "business_registration",
    "owner_id",
    "bank_proof",
    "shopfront_photo",
)

ADDENDUM = "dpa_addendum"

_YES = {"yes", "y", "true"}


def empty_snapshot() -> dict:
    return {
        "answers": {name: None for name in (*ANSWER_FIELDS, "note")},
        "files": {slot: {"state": "pending"} for slot in PACK_SLOTS},
    }


def stores_phones(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _YES
    return False


def shown_snapshot(snapshot: dict) -> dict:
    """The review draft. The addendum slot appears only when payer phones are stored."""
    shown = copy.deepcopy(snapshot)
    if stores_phones(shown["answers"].get("stores_payer_phones")):
        shown["files"].setdefault(ADDENDUM, {"state": "pending"})
    else:
        shown["files"].pop(ADDENDUM, None)
    return shown


def pending_item(snapshot: dict) -> dict | None:
    shown = shown_snapshot(snapshot)
    for name in ANSWER_FIELDS:
        if shown["answers"].get(name) is None:
            return {"kind": "field", "name": name}
    for slot, file in shown["files"].items():
        if file.get("state") == "pending":
            return {"kind": "upload", "name": slot}
    if shown["answers"].get("note") is None:
        return {"kind": "field", "name": "note"}
    return None


def ask(store: ApplicationStore, application_id: str | None) -> dict:
    """Create the application on the first call. Later calls use the same id."""
    if application_id is None or application_id.strip() == "":
        application_id = store.create(empty_snapshot())
        snapshot = store.get(application_id)
    else:
        snapshot = store.get(application_id)
        if snapshot is None:
            return {"error": "unknown_application", "application_id": application_id}
    assert snapshot is not None
    shown = shown_snapshot(snapshot)
    return {
        "application_id": application_id,
        "pending": pending_item(snapshot),
        "snapshot": shown,
    }


def save_answer(store: ApplicationStore, application_id: str, field: str, value: str) -> dict:
    """Store the merchant's words for the one field that is pending.

    The words are data. They do not choose a different field, skip one, or submit.
    """
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    pending = pending_item(snapshot)
    if pending is None or pending.get("kind") != "field" or pending.get("name") != field:
        return {"error": "field_not_pending", "field": field, "pending": pending}
    text = value.strip()
    if field != "note" and text == "":
        return {"error": "empty_answer", "field": field}
    snapshot["answers"][field] = text
    if not store.replace(application_id, snapshot):
        return {"error": "unknown_application", "application_id": application_id}
    return {
        "application_id": application_id,
        "field": field,
        "value": text,
        "snapshot": shown_snapshot(snapshot),
    }
