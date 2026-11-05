from onb.intake import ask, save_answer, save_file
from onb.store import ApplicationStore
from onb.verifier import MockDocumentVerifier


def _at_registration(store: ApplicationStore) -> str:
    created = ask(store, None)
    application_id = created["application_id"]
    answers = {
        "shop_name": "Lotus Tea House",
        "city": "Pune",
        "business_type": "restaurant",
        "monthly_volume": "1200000",
        "payment_methods": "UPI",
        "stores_payer_phones": "no",
    }
    for field, value in answers.items():
        save_answer(store, application_id, field, value)
    return application_id


def test_an_accepted_file_closes_the_slot() -> None:
    store = ApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "registration.pdf")
    nxt = ask(store, application_id)

    assert saved["state"] == "accepted"
    assert saved["reason_code"] == "ok"
    assert nxt["pending"] == {"kind": "upload", "name": "owner_id"}
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "accepted"


def test_a_rejected_file_leaves_the_slot_pending() -> None:
    store = ApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "registration.docx")
    nxt = ask(store, application_id)

    assert saved["state"] == "pending"
    assert saved["reason_code"] == "format"
    assert nxt["pending"] == {"kind": "upload", "name": "business_registration"}


def test_missing_closes_the_slot_as_a_gap() -> None:
    store = ApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", missing=True)
    nxt = ask(store, application_id)

    assert saved["state"] == "missing"
    assert nxt["pending"]["name"] == "owner_id"
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "missing"


def test_attached_with_no_file_does_not_count() -> None:
    store = ApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "attached")
    nxt = ask(store, application_id)

    assert saved == {"error": "file_missing", "slot": "business_registration"}
    assert nxt["pending"]["name"] == "business_registration"
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "pending"


def test_a_slot_that_is_not_pending_is_rejected() -> None:
    store = ApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "owner_id", "owner.pdf")

    assert saved["error"] == "slot_not_pending"
    assert ask(store, application_id)["snapshot"]["files"]["owner_id"]["state"] == "pending"


def test_bank_proof_in_a_personal_name_is_rejected() -> None:
    verifier = MockDocumentVerifier()
    result = verifier.verify(
        "bank_proof",
        "Lotus Tea House",
        b"personal-passbook.pdf",
        "2026-11-06",
    )
    assert result == {"accepted": False, "reason_code": "not_legal_name"}


def test_shopfront_older_than_90_days_is_rejected() -> None:
    verifier = MockDocumentVerifier()
    result = verifier.verify(
        "shopfront_photo",
        "Lotus Tea House",
        b"shopfront-2026-01-01.jpg",
        "2026-11-06",
    )
    assert result["accepted"] is False
    assert result["reason_code"] == "too_old"


def test_unknown_application_is_an_error() -> None:
    store = ApplicationStore()
    result = save_file(store, "app_missing", "business_registration", "registration.pdf")
    assert result == {"error": "unknown_application", "application_id": "app_missing"}
