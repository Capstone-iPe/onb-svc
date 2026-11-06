from onb.store import MemoryApplicationStore, PostgresApplicationStore, open_application_store


def test_reads_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://onb:secret@localhost:5432/onb")
    store = open_application_store()
    assert isinstance(store, PostgresApplicationStore)
    assert store.database_url == "postgresql://onb:secret@localhost:5432/onb"


def test_no_database_url_is_memory(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(open_application_store(), MemoryApplicationStore)
