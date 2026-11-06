"""What ONB asks for next. Field order is policy. The copilot does not choose it."""

from __future__ import annotations

import copy
from datetime import date
from typing import TYPE_CHECKING

from onb.rules import parse_volume
from onb.rules import decide
from onb.verifier import MockDocumentVerifier, file_bytes

if TYPE_CHECKING:
    from onb.store import ApplicationStore
    from onb.verifier import DocumentVerifier

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


def save_file(
    store: ApplicationStore,
    application_id: str,
    slot: str,
    file: str | None = None,
    missing: bool = False,
    verifier: DocumentVerifier | None = None,
    submit_date: str | None = None,
) -> dict:
    """Store one upload, or close a slot the merchant does not have.

    The verifier decides accepted. This function does not.
    """
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    pending = pending_item(snapshot)
    if pending is None or pending.get("kind") != "upload" or pending.get("name") != slot:
        return {"error": "slot_not_pending", "slot": slot, "pending": pending}
    payload = file_bytes(file)
    if missing and payload:
        return {"error": "file_and_missing", "slot": slot}
    if missing:
        snapshot["files"][slot] = {"state": "missing"}
        if not store.replace(application_id, snapshot):
            return {"error": "unknown_application", "application_id": application_id}
        return {
            "application_id": application_id,
            "slot": slot,
            "state": "missing",
            "snapshot": shown_snapshot(snapshot),
        }
    if not payload:
        return {"error": "file_missing", "slot": slot}
    checker = verifier or MockDocumentVerifier()
    shop_name = str(snapshot["answers"].get("shop_name") or "")
    result = checker.verify(slot, shop_name, payload, submit_date or date.today().isoformat())
    accepted = bool(result.get("accepted"))
    reason_code = str(result.get("reason_code") or ("ok" if accepted else "rejected"))
    snapshot["files"][slot] = {
        "state": "accepted" if accepted else "pending",
        "reason_code": reason_code,
    }
    if not store.replace(application_id, snapshot):
        return {"error": "unknown_application", "application_id": application_id}
    return {
        "application_id": application_id,
        "slot": slot,
        "state": snapshot["files"][slot]["state"],
        "reason_code": reason_code,
        "snapshot": shown_snapshot(snapshot),
    }


def submit(store: ApplicationStore, application_id: str) -> dict:
    """Run the rules once. A second call returns the same verdict and the same review id."""
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    stored = snapshot.get("verdict")
    if isinstance(stored, dict):
        return {"application_id": application_id, "verdict": stored}
    shown = shown_snapshot(snapshot)
    missing_answers = [name for name in ANSWER_FIELDS if shown["answers"].get(name) is None]
    if missing_answers:
        return {"error": "answers_incomplete", "application_id": application_id, "fields": missing_answers}
    if parse_volume(str(shown["answers"].get("monthly_volume") or "")) is None:
        return {"error": "volume_unreadable", "application_id": application_id}
    open_slots = [
        slot
        for slot, file in shown["files"].items()
        if file.get("state") == "pending" and not file.get("reason_code")
    ]
    if open_slots:
        return {"error": "slots_open", "application_id": application_id, "slots": open_slots}
    verdict = decide(shown["answers"], shown["files"])
    if verdict["outcome"] != "REFUSED":
        verdict["review_id"] = store.allocate_review_id()
    snapshot["verdict"] = verdict
    if not store.replace(application_id, snapshot):
        return {"error": "unknown_application", "application_id": application_id}
    return {"application_id": application_id, "verdict": verdict}
