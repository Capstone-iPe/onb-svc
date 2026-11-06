from onb.intake import ask, empty_snapshot, pending_item
from onb.store import MemoryApplicationStore

ANSWERS = (
    "shop_name",
    "city",
    "business_type",
    "monthly_volume",
    "payment_methods",
    "stores_payer_phones",
    "note",
)
PACK = (
    "business_registration",
    "owner_id",
    "bank_proof",
    "shopfront_photo",
)


def test_first_call_creates_one_application_and_asks_for_the_shop_name() -> None:
    store = MemoryApplicationStore()
    result = ask(store, None)

    assert store.count() == 1
    assert result["application_id"].startswith("app_")
    assert result["pending"] == {"kind": "field", "name": "shop_name"}
    assert set(result["snapshot"]["answers"]) == set(ANSWERS)
    assert all(value is None for value in result["snapshot"]["answers"].values())
    assert set(result["snapshot"]["files"]) == set(PACK)
    assert "dpa_addendum" not in result["snapshot"]["files"]


def test_same_id_does_not_create_a_second_application() -> None:
    store = MemoryApplicationStore()
    first = ask(store, None)
    second = ask(store, first["application_id"])

    assert store.count() == 1
    assert second["application_id"] == first["application_id"]
    assert second["pending"] == {"kind": "field", "name": "shop_name"}


def test_unknown_id_is_an_error_and_does_not_create() -> None:
    store = MemoryApplicationStore()
    result = ask(store, "app_missing")

    assert result == {"error": "unknown_application", "application_id": "app_missing"}
    assert store.count() == 0


def test_blank_id_creates() -> None:
    store = MemoryApplicationStore()
    result = ask(store, "  ")
    assert store.count() == 1
    assert result["pending"]["name"] == "shop_name"


def _ready_for_files(phones: object) -> dict:
    snapshot = empty_snapshot()
    for name in ANSWERS:
        if name == "note":
            continue
        snapshot["answers"][name] = "yes" if name == "stores_payer_phones" else "filled"
    snapshot["answers"]["stores_payer_phones"] = phones
    return snapshot


def test_addendum_is_pending_only_when_phones_are_stored() -> None:
    with_phones = _ready_for_files(True)
    for slot in PACK:
        with_phones["files"][slot] = {"state": "accepted"}
    assert pending_item(with_phones) == {"kind": "upload", "name": "dpa_addendum"}

    without_phones = _ready_for_files(False)
    for slot in PACK:
        without_phones["files"][slot] = {"state": "accepted"}
    assert pending_item(without_phones) == {"kind": "field", "name": "note"}


def test_nothing_pending_after_the_note() -> None:
    snapshot = _ready_for_files(False)
    for slot in PACK:
        snapshot["files"][slot] = {"state": "accepted"}
    snapshot["answers"]["note"] = ""
    assert pending_item(snapshot) is None
