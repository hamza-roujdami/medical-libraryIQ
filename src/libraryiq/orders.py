from __future__ import annotations

import logging
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from libraryiq.lookup import Article

logger = logging.getLogger("libraryiq.orders")

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


class ArticleRequest(BaseModel):
    id: str
    requester: str
    article: Article
    note: str | None = None
    status: Literal["pending", "approved", "declined"] = "pending"
    created_at: str
    decided_at: str | None = None
    decision_reason: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _to_request(row: sqlite3.Row) -> ArticleRequest:
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
    """Request records. SQLite calls are synchronous: the volume is a few requests a day."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, requester: str, article: Article, note: str | None) -> ArticleRequest:
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

    def get(self, request_id: str) -> ArticleRequest | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return _to_request(row) if row else None

    def find_pending(self, requester: str, article: Article) -> ArticleRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE requester = ? AND status = 'pending'"
                " AND ((doi IS NOT NULL AND doi = ?) OR (pmid IS NOT NULL AND pmid = ?))",
                (requester, article.doi, article.pmid),
            ).fetchone()
        return _to_request(row) if row else None

    def decide(self, request_id: str, approved: bool, reason: str | None) -> ArticleRequest | None:
        """Decide a pending request. Returns None if it is unknown or already decided."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE requests SET status = ?, decided_at = ?, decision_reason = ?"
                " WHERE id = ? AND status = 'pending'",
                ("approved" if approved else "declined", _now(), reason, request_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(request_id)

    def list_pending(self) -> list[ArticleRequest]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM requests WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [_to_request(row) for row in rows]

    def count_pending(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT count(*) FROM requests WHERE status = 'pending'"
            ).fetchone()[0]


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


@dataclass
class SimulatedNotifier:
    """Records messages instead of sending them. Replace with a real sender with the same `send`."""

    outbox: list[Message] = field(default_factory=list)

    async def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append(Message(to, subject, body))
        logger.info("simulated email to=%s subject=%s", to, subject)
