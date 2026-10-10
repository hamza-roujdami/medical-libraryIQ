import sqlite3

from fakes import article
from libraryiq.orders import SqliteRequestStore


def test_create_get_roundtrip(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = store.create("staff@example.org", article(), "note")
    fetched = store.get(created.id)
    assert fetched == created
    assert fetched.article.doi == "10.1000/a.1"


def test_data_survives_reopening(tmp_path):
    first = SqliteRequestStore(tmp_path / "s.db")
    created = first.create("staff@example.org", article(), None)
    assert SqliteRequestStore(tmp_path / "s.db").get(created.id) == created


def test_find_pending_matches_requester_and_article(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = store.create("a@example.org", article(), None)
    assert (store.find_pending("a@example.org", article())).id == created.id
    assert store.find_pending("b@example.org", article()) is None
    assert store.find_pending("a@example.org", article(doi="10.1000/other")) is None


def test_decided_request_is_no_longer_pending(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = store.create("a@example.org", article(), None)
    store.decide(created.id, True, None)
    assert store.find_pending("a@example.org", article()) is None


def test_queries_are_parameterised(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    store.create("a@example.org", article(), None)
    assert store.get("x' OR '1'='1") is None
    with sqlite3.connect(tmp_path / "s.db") as conn:
        assert conn.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
