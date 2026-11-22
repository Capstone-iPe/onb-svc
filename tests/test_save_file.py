from onb.intake import ask, save_answer, save_file
from onb.store import ApplicationStore, MemoryApplicationStore
from onb.verifier import RulesDocumentVerifier


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
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "registration.pdf")
    nxt = ask(store, application_id)

    assert saved["state"] == "accepted"
    assert saved["reason_code"] == "ok"
    assert nxt["pending"] == {"kind": "upload", "name": "owner_id"}
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "accepted"


def test_a_rejected_file_leaves_the_slot_pending() -> None:
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "registration.docx")
    nxt = ask(store, application_id)

    assert saved["state"] == "pending"
    assert saved["reason_code"] == "format"
    assert nxt["pending"] == {"kind": "upload", "name": "business_registration"}


def test_missing_closes_the_slot_as_a_gap() -> None:
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", missing=True)
    nxt = ask(store, application_id)

    assert saved["state"] == "missing"
    assert nxt["pending"]["name"] == "owner_id"
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "missing"


def test_attached_with_no_file_does_not_count() -> None:
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "business_registration", "attached")
    nxt = ask(store, application_id)

    assert saved == {"error": "file_missing", "slot": "business_registration"}
    assert nxt["pending"]["name"] == "business_registration"
    assert nxt["snapshot"]["files"]["business_registration"]["state"] == "pending"


def test_a_slot_that_is_not_pending_is_rejected() -> None:
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    saved = save_file(store, application_id, "owner_id", "owner.pdf")

    assert saved["error"] == "slot_not_pending"
    assert ask(store, application_id)["snapshot"]["files"]["owner_id"]["state"] == "pending"


def test_bank_proof_in_a_personal_name_is_rejected() -> None:
    verifier = RulesDocumentVerifier()
    result = verifier.verify(
        "bank_proof",
        "Lotus Tea House",
        b"personal-passbook.pdf",
        "2026-11-06",
    )
    assert result["accepted"] is False
    assert result["reason_code"] in {"NAME_MISMATCH", "not_legal_name"}


def test_shopfront_older_than_90_days_is_rejected() -> None:
    verifier = RulesDocumentVerifier()
    result = verifier.verify(
        "shopfront_photo",
        "Lotus Tea House",
        b"shopfront-2026-01-01.jpg",
        "2026-11-06",
    )
    assert result["accepted"] is False
    assert result["reason_code"] in {"PHOTO_TOO_OLD", "too_old"}


def test_unknown_application_is_an_error() -> None:
    store = MemoryApplicationStore()
    result = save_file(store, "app_missing", "business_registration", "registration.pdf")
    assert result == {"error": "unknown_application", "application_id": "app_missing"}


def test_one_file_cannot_fill_two_slots() -> None:
    """Replay: the registration file was re-uploaded as the signed addendum and accepted."""
    store = MemoryApplicationStore()
    created = ask(store, None)
    application_id = created["application_id"]
    for field, value in {
        "shop_name": "theobromine restaurant",
        "city": "Adoni",
        "business_type": "restaurant",
        "monthly_volume": "5 lakhs",
        "payment_methods": "UPI, cards, cash, wallet",
        "stores_payer_phones": "yes we keep payers phone number",
    }.items():
        save_answer(store, application_id, field, value)
    for slot, name in (
        ("business_registration", "business_registration_1_reg_pdf.pdf"),
        ("owner_id", "owner_id_1_id_card_jpg.jpg"),
        ("bank_proof", "bank_proof_1_bank_letter.pdf"),
        ("shopfront_photo", "shopfront_photo_1_front_dark.jpg"),
    ):
        assert save_file(store, application_id, slot, name)["state"] == "accepted"

    reused = save_file(store, application_id, "dpa_addendum", "business_registration_1_reg_pdf.pdf")

    assert reused["state"] == "pending"
    assert reused["reason_code"] == "duplicate_file"
    assert ask(store, application_id)["pending"] == {"kind": "upload", "name": "dpa_addendum"}
    own = save_file(store, application_id, "dpa_addendum", "signed_dpa.pdf")
    assert own["state"] == "accepted"


def test_slot_mismatch_document_rejected() -> None:
    verifier = RulesDocumentVerifier()
    # A registration PDF uploaded to dpa_addendum
    res = verifier.verify("dpa_addendum", "theobromine restaurant", b"business_registration_1_reg_pdf.pdf", "2026-11-21")
    assert res["accepted"] is False
    assert res["reason_code"] in {"WRONG_DOCUMENT", "wrong_document"}

    # A utility bill uploaded to bank_proof
    res2 = verifier.verify("bank_proof", "theobromine restaurant", b"utility_bill.pdf", "2026-11-21")
    assert res2["accepted"] is False
    assert res2["reason_code"] in {"WRONG_DOCUMENT", "wrong_document"}

    # An interior photo uploaded to shopfront_photo
    res3 = verifier.verify("shopfront_photo", "theobromine restaurant", b"interior_view.jpg", "2026-11-21")
    assert res3["accepted"] is False
    assert res3["reason_code"] in {"NOT_SHOPFRONT", "not_shopfront"}


def test_replace_already_accepted_file_before_submit() -> None:
    store = MemoryApplicationStore()
    application_id = _at_registration(store)

    first = save_file(store, application_id, "business_registration", "registration.pdf")
    assert first["state"] == "accepted"

    # Now replace the business registration before submit
    replaced = save_file(store, application_id, "business_registration", "new_registration.pdf")
    assert replaced["state"] == "accepted"

