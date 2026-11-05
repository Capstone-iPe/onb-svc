from onb.store import ApplicationStore


def test_reads_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://onb:secret@localhost:5432/onb")
    store = ApplicationStore.from_env()
    assert store.database_url == "postgresql://onb:secret@localhost:5432/onb"


def test_no_database_url_is_empty(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert ApplicationStore.from_env().database_url is None
