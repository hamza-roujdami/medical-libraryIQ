from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Article(BaseModel):
    title: str
    journal: str | None = None
    issn: list[str] = Field(default_factory=list)
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None
    source: str


class AccessLink(BaseModel):
    category: str
    text: str
    url: str


class AccessResult(BaseModel):
    subscribed: bool
    links: list[AccessLink] = Field(default_factory=list)
    source: str


class FreeCopy(BaseModel):
    url: str
    version: str | None = None
    license: str | None = None
    source: str = "Unpaywall"


FindStatus = Literal["has_access", "free_copy", "needs_request", "confirm_match", "not_found"]


class FindResult(BaseModel):
    status: FindStatus
    message: str
    article: Article | None = None
    candidates: list[Article] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    access: AccessResult | None = None
    free_copy: FreeCopy | None = None


RequestStatus = Literal["pending", "approved", "declined"]


class ArticleRequest(BaseModel):
    id: str
    requester: str
    article: Article
    note: str | None = None
    status: RequestStatus = "pending"
    created_at: str
    decided_at: str | None = None
    decision_reason: str | None = None
