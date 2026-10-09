from __future__ import annotations

import asyncio
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from libraryiq.core.models import Article, ArticleRequest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    requester TEXT NOT NULL,
    doi TEXT,
    pmid TEXT,
    article TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decision_reason TEXT
)
"""


class RequestStore(Protocol):
    async def create(
        self, requester: str, article: Article, note: str | None
    ) -> ArticleRequest: ...

    async def get(self, request_id: str) -> ArticleRequest | None: ...

    async def find_pending(self, requester: str, article: Article) -> ArticleRequest | None: ...

    async def decide(
        self, request_id: str, approved: bool, reason: str | None
    ) -> ArticleRequest | None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_request(row: sqlite3.Row) -> ArticleRequest:
    return ArticleRequest(
        id=row["id"],
        requester=row["requester"],
        article=Article.model_validate_json(row["article"]),
        note=row["note"],
        status=row["status"],
        created_at=row["created_at"],
        decided_at=row["decided_at"],
        decision_reason=row["decision_reason"],
    )


class SqliteRequestStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create(self, requester: str, article: Article, note: str | None) -> ArticleRequest:
        request = ArticleRequest(
            id=f"REQ-{secrets.token_hex(3).upper()}",
            requester=requester,
            article=article,
            note=note,
            created_at=_now(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO requests (id, requester, doi, pmid, article, note, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request.id,
                    requester,
                    article.doi,
                    article.pmid,
                    article.model_dump_json(),
                    note,
                    request.status,
                    request.created_at,
                ),
            )
        return request

    def _get(self, request_id: str) -> ArticleRequest | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return _row_to_request(row) if row else None

    def _find_pending(self, requester: str, article: Article) -> ArticleRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE requester = ? AND status = 'pending'"
                " AND ((doi IS NOT NULL AND doi = ?) OR (pmid IS NOT NULL AND pmid = ?))",
                (requester, article.doi, article.pmid),
            ).fetchone()
        return _row_to_request(row) if row else None

    def _decide(self, request_id: str, approved: bool, reason: str | None) -> ArticleRequest | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE requests SET status = ?, decided_at = ?, decision_reason = ?"
                " WHERE id = ? AND status = 'pending'",
                ("approved" if approved else "declined", _now(), reason, request_id),
            )
            if cursor.rowcount == 0:
                return None
        return self._get(request_id)

    async def create(self, requester: str, article: Article, note: str | None) -> ArticleRequest:
        return await asyncio.to_thread(self._create, requester, article, note)

    async def get(self, request_id: str) -> ArticleRequest | None:
        return await asyncio.to_thread(self._get, request_id)

    async def find_pending(self, requester: str, article: Article) -> ArticleRequest | None:
        return await asyncio.to_thread(self._find_pending, requester, article)

    async def decide(
        self, request_id: str, approved: bool, reason: str | None
    ) -> ArticleRequest | None:
        return await asyncio.to_thread(self._decide, request_id, approved, reason)
