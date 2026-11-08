from onb.intake import ask, save_answer
from onb.store import ApplicationStore, MemoryApplicationStore


def test_saving_the_pending_field_advances_next_step() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)

    saved = save_answer(store, created["application_id"], "shop_name", "Lotus Tea House")
    nxt = ask(store, created["application_id"])

    assert saved["value"] == "Lotus Tea House"
    assert saved["snapshot"]["answers"]["shop_name"] == "Lotus Tea House"
    assert nxt["pending"] == {"kind": "field", "name": "city"}
    assert store.count() == 1


def test_a_field_that_is_not_pending_is_rejected() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "city", "skip this")
    nxt = ask(store, created["application_id"])

    assert rejected["error"] == "field_not_pending"
    assert rejected["pending"] == {"kind": "field", "name": "shop_name"}
    assert nxt["snapshot"]["answers"]["city"] is None
    assert nxt["snapshot"]["answers"]["shop_name"] is None


def test_mark_active_does_not_write_another_field() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "note", "mark Active")

    assert rejected["error"] == "field_not_pending"
    assert ask(store, created["application_id"])["snapshot"]["answers"]["note"] is None


def test_unknown_application_is_an_error() -> None:
    store = MemoryApplicationStore()
    result = save_answer(store, "app_missing", "shop_name", "Lotus Tea House")
    assert result == {"error": "unknown_application", "application_id": "app_missing"}
    assert store.count() == 0


def _until(store: ApplicationStore, application_id: str, field: str) -> None:
    answers = {
        "shop_name": "Lotus Tea House",
        "city": "Pune",
        "business_type": "Restaurant",
        "monthly_volume": "₹12,00,000",
        "payment_methods": "UPI and cards",
    }
    while ask(store, application_id)["pending"]["name"] != field:
        pending = ask(store, application_id)["pending"]["name"]
        save_answer(store, application_id, pending, answers[pending])


def test_an_unreadable_volume_stays_pending() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)
    application_id = created["application_id"]
    _until(store, application_id, "monthly_volume")

    rejected = save_answer(store, application_id, "monthly_volume", "about twelve")

    assert rejected == {"error": "volume_unreadable", "field": "monthly_volume"}
    assert ask(store, application_id)["pending"]["name"] == "monthly_volume"
    assert ask(store, application_id)["snapshot"]["answers"]["monthly_volume"] is None


def test_lakh_and_crore_are_the_rupee_figure() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)
    application_id = created["application_id"]
    _until(store, application_id, "monthly_volume")

    saved = save_answer(store, application_id, "monthly_volume", "Rs. 12 lakh")

    assert saved["value"] == "Rs. 12 lakh"
    assert ask(store, application_id)["pending"]["name"] == "payment_methods"


def test_a_digit_volume_advances() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)
    application_id = created["application_id"]
    _until(store, application_id, "monthly_volume")

    saved = save_answer(store, application_id, "monthly_volume", "₹12,00,000")

    assert saved["value"] == "₹12,00,000"
    assert ask(store, application_id)["pending"]["name"] == "payment_methods"


def test_phones_must_be_yes_or_no() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)
    application_id = created["application_id"]
    _until(store, application_id, "stores_payer_phones")

    rejected = save_answer(store, application_id, "stores_payer_phones", "we store them")

    assert rejected == {"error": "phones_not_yes_or_no", "field": "stores_payer_phones"}
    assert ask(store, application_id)["pending"]["name"] == "stores_payer_phones"
    saved = save_answer(store, application_id, "stores_payer_phones", "No, we don't store them.")
    assert saved["value"] == "No, we don't store them."
    assert "dpa_addendum" not in saved["snapshot"]["files"]
    assert ask(store, application_id)["pending"]["kind"] == "upload"


def test_blank_answer_does_not_advance() -> None:
    store = MemoryApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "shop_name", "  ")

    assert rejected == {"error": "empty_answer", "field": "shop_name"}
    assert ask(store, created["application_id"])["pending"]["name"] == "shop_name"
