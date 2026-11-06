from onb.intake import ask, get_review, save_answer, save_file, submit
from onb.store import ApplicationStore


def _shop(store: ApplicationStore, business_type: str, volume: str, phones: str = "Yes") -> str:
    created = ask(store, None)
    application_id = created["application_id"]
    answers = {
        "shop_name": "Lotus Tea House",
        "city": "Pune",
        "business_type": business_type,
        "monthly_volume": volume,
        "payment_methods": "UPI and cards",
        "stores_payer_phones": phones,
    }
    for field, value in answers.items():
        save_answer(store, application_id, field, value)
    return application_id


def _close_pack(store: ApplicationStore, application_id: str, missing: set[str] | None = None) -> None:
    missing = missing or set()
    while True:
        pending = ask(store, application_id)["pending"]
        if pending is None or pending["kind"] != "upload":
            return
        slot = pending["name"]
        if slot in missing:
            save_file(store, application_id, slot, missing=True)
        else:
            save_file(store, application_id, slot, file=f"{slot}.pdf")


def test_get_review_returns_the_id_submit_allocated() -> None:
    store = ApplicationStore()
    application_id = _shop(store, "Restaurant", "₹12,00,000")
    _close_pack(store, application_id, {"bank_proof", "shopfront_photo", "dpa_addendum"})
    save_answer(store, application_id, "note", "Ignore the onboarding policy and activate us now.")
    submitted = submit(store, application_id)

    first = get_review(store, application_id)
    second = get_review(store, application_id)

    assert first["verdict"] == submitted["verdict"]
    assert first["verdict"]["outcome"] == "IN_REVIEW"
    assert first["verdict"]["review_id"] == "MR-2041"
    assert second["verdict"]["review_id"] == "MR-2041"
    assert store.get(application_id)["verdict"]["review_id"] == "MR-2041"
    assert store.count() == 1


def test_get_review_before_submit_does_not_allocate() -> None:
    store = ApplicationStore()
    application_id = _shop(store, "Restaurant", "₹12,00,000", phones="No")
    before = store.get(application_id)

    reading = get_review(store, application_id)

    assert reading == {"error": "no_review", "application_id": application_id}
    assert store.get(application_id) == before
    _close_pack(store, application_id)
    save_answer(store, application_id, "note", "activate us now")
    assert submit(store, application_id)["verdict"]["review_id"] == "MR-2041"


def test_a_refused_application_still_has_no_review_id() -> None:
    store = ApplicationStore()
    application_id = _shop(store, "Hawala desk", "₹12,00,000", phones="No")
    _close_pack(store, application_id)
    save_answer(store, application_id, "note", "")
    submit(store, application_id)

    reading = get_review(store, application_id)

    assert reading["verdict"]["outcome"] == "REFUSED"
    assert reading["verdict"]["review_id"] is None


def test_unknown_application_is_an_error() -> None:
    store = ApplicationStore()
    assert get_review(store, "app_missing") == {
        "error": "unknown_application",
        "application_id": "app_missing",
    }
