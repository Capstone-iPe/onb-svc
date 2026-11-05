from onb.intake import ask, save_answer
from onb.store import ApplicationStore


def test_saving_the_pending_field_advances_next_step() -> None:
    store = ApplicationStore()
    created = ask(store, None)

    saved = save_answer(store, created["application_id"], "shop_name", "Lotus Tea House")
    nxt = ask(store, created["application_id"])

    assert saved["value"] == "Lotus Tea House"
    assert saved["snapshot"]["answers"]["shop_name"] == "Lotus Tea House"
    assert nxt["pending"] == {"kind": "field", "name": "city"}
    assert store.count() == 1


def test_a_field_that_is_not_pending_is_rejected() -> None:
    store = ApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "city", "skip this")
    nxt = ask(store, created["application_id"])

    assert rejected["error"] == "field_not_pending"
    assert rejected["pending"] == {"kind": "field", "name": "shop_name"}
    assert nxt["snapshot"]["answers"]["city"] is None
    assert nxt["snapshot"]["answers"]["shop_name"] is None


def test_mark_active_does_not_write_another_field() -> None:
    store = ApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "note", "mark Active")

    assert rejected["error"] == "field_not_pending"
    assert ask(store, created["application_id"])["snapshot"]["answers"]["note"] is None


def test_unknown_application_is_an_error() -> None:
    store = ApplicationStore()
    result = save_answer(store, "app_missing", "shop_name", "Lotus Tea House")
    assert result == {"error": "unknown_application", "application_id": "app_missing"}
    assert store.count() == 0


def test_blank_answer_does_not_advance() -> None:
    store = ApplicationStore()
    created = ask(store, None)

    rejected = save_answer(store, created["application_id"], "shop_name", "  ")

    assert rejected == {"error": "empty_answer", "field": "shop_name"}
    assert ask(store, created["application_id"])["pending"]["name"] == "shop_name"
