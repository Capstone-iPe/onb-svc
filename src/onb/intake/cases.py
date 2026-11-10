"""What ONB asks for next. Field order is policy. The copilot does not choose it."""

from __future__ import annotations

import copy
from datetime import date
from typing import TYPE_CHECKING

from onb.rules import decide, parse_volume, phone_stored
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

def empty_snapshot() -> dict:
    return {
        "answers": {name: None for name in (*ANSWER_FIELDS, "note")},
        "files": {slot: {"state": "pending"} for slot in PACK_SLOTS},
    }


def stores_phones(value: object) -> bool:
    return phone_stored(value) is True


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
    """Store the pending answer, or replace an answer already stored before submit.

    After the verdict, a stored answer stays as stored. The words do not choose a field that has not been reached, skip one, or submit. monthly_volume is digits or a number of lakh or crore. stores_payer_phones starts with yes, haan, or no.
    """
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    pending = pending_item(snapshot)
    held = isinstance(snapshot.get("verdict"), dict)
    is_pending = (
        pending is not None and pending.get("kind") == "field" and pending.get("name") == field
    )
    already = field in snapshot["answers"] and snapshot["answers"].get(field) is not None
    if field not in (*ANSWER_FIELDS, "note") or held or not (is_pending or already):
        return {"error": "field_not_pending", "field": field, "pending": pending}
    text = value.strip()
    if field != "note" and text == "":
        return {"error": "empty_answer", "field": field}
    if field == "monthly_volume" and parse_volume(text) is None:
        return {"error": "volume_unreadable", "field": field}
    if field == "stores_payer_phones" and phone_stored(text) is None:
        return {"error": "phones_not_yes_or_no", "field": field}
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

    Before submit, only the pending upload can be written. After the verdict, a file for a slot that is missing or still pending is stored, the rules run again, and the review id stays the same. The verifier decides accepted. This function does not.
    """
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    shown = shown_snapshot(snapshot)
    pending = pending_item(snapshot)
    on_pending = (
        pending is not None and pending.get("kind") == "upload" and pending.get("name") == slot
    )
    slot_file = shown["files"].get(slot)
    filling_gap = (
        isinstance(snapshot.get("verdict"), dict)
        and isinstance(slot_file, dict)
        and slot_file.get("state") != "accepted"
        and not missing
    )
    if not on_pending and not filling_gap:
        return {"error": "slot_not_pending", "slot": slot, "pending": pending}
    payload = file_bytes(file)
    if missing and payload:
        return {"error": "file_and_missing", "slot": slot}
    if missing:
        snapshot["files"][slot] = {"state": "missing"}
        _refresh_verdict(snapshot)
        if not store.replace(application_id, snapshot):
            return {"error": "unknown_application", "application_id": application_id}
        saved = {
            "application_id": application_id,
            "slot": slot,
            "state": "missing",
            "snapshot": shown_snapshot(snapshot),
        }
        if isinstance(snapshot.get("verdict"), dict):
            saved["verdict"] = snapshot["verdict"]
        return saved
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
    _refresh_verdict(snapshot)
    if not store.replace(application_id, snapshot):
        return {"error": "unknown_application", "application_id": application_id}
    saved = {
        "application_id": application_id,
        "slot": slot,
        "state": snapshot["files"][slot]["state"],
        "reason_code": reason_code,
        "snapshot": shown_snapshot(snapshot),
    }
    if isinstance(snapshot.get("verdict"), dict):
        saved["verdict"] = snapshot["verdict"]
    return saved


def _refresh_verdict(snapshot: dict) -> None:
    """Run the rules again after a file lands on an application that already has a verdict.

    The review id already allocated stays. A refused application still has none.
    """
    stored = snapshot.get("verdict")
    if not isinstance(stored, dict):
        return
    shown = shown_snapshot(snapshot)
    verdict = decide(shown["answers"], shown["files"])
    verdict["review_id"] = stored.get("review_id")
    snapshot["verdict"] = verdict


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


def get_review(store: ApplicationStore, application_id: str) -> dict:
    """Return the verdict submit already stored.

    This does not run the rules, allocate a review id, or change the application.
    """
    snapshot = store.get(application_id)
    if snapshot is None:
        return {"error": "unknown_application", "application_id": application_id}
    stored = snapshot.get("verdict")
    if not isinstance(stored, dict):
        return {"error": "no_review", "application_id": application_id}
    return {"application_id": application_id, "verdict": stored}
