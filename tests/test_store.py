import sqlite3

from fakes import article
from libraryiq.core.store import SqliteRequestStore


async def test_create_get_roundtrip(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = await store.create("staff@example.org", article(), "note")
    fetched = await store.get(created.id)
    assert fetched == created
    assert fetched.article.doi == "10.1000/a.1"


async def test_data_survives_reopening(tmp_path):
    first = SqliteRequestStore(tmp_path / "s.db")
    created = await first.create("staff@example.org", article(), None)
    assert await SqliteRequestStore(tmp_path / "s.db").get(created.id) == created


async def test_find_pending_matches_requester_and_article(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = await store.create("a@example.org", article(), None)
    assert (await store.find_pending("a@example.org", article())).id == created.id
    assert await store.find_pending("b@example.org", article()) is None
    assert await store.find_pending("a@example.org", article(doi="10.1000/other")) is None


async def test_decided_request_is_no_longer_pending(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    created = await store.create("a@example.org", article(), None)
    await store.decide(created.id, True, None)
    assert await store.find_pending("a@example.org", article()) is None


async def test_queries_are_parameterised(tmp_path):
    store = SqliteRequestStore(tmp_path / "s.db")
    await store.create("a@example.org", article(), None)
    assert await store.get("x' OR '1'='1") is None
    with sqlite3.connect(tmp_path / "s.db") as conn:
        assert conn.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
