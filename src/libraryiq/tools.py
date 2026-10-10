from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from libraryiq.access import SampleAccessChecker
from libraryiq.identifiers import parse_identifier
from libraryiq.lookup import Article, LookupFailed, PublicLookup
from libraryiq.orders import ArticleRequest, SimulatedNotifier, SqliteRequestStore


@dataclass(frozen=True)
class User:
    """The caller, as established by the gateway. Tools never trust what the model says about it."""

    id: str
    role: Literal["requester", "librarian"] = "requester"


def _describe(article: Article) -> str:
    parts = [article.title]
    if article.journal:
        parts.append(article.journal)
    if article.year:
        parts.append(str(article.year))
    return ", ".join(parts)


def _option(number: int, article: Article) -> str:
    authors = ", ".join(article.authors[:3]) + (" et al." if len(article.authors) > 3 else "")
    where = ", ".join(
        p for p in (article.journal, str(article.year) if article.year else None) if p
    )
    ref = f"DOI: {article.doi}" if article.doi else f"PMID: {article.pmid}"
    return f"{number}. {article.title} - {authors or 'authors unknown'} ({where or 'no journal'}) {ref}"


def _unavailable(exc: LookupFailed) -> dict[str, Any]:
    return {
        "status": "error",
        "message": f"A lookup service is unavailable ({exc}). Tell the user to try again shortly.",
    }


def _forbidden(action: str) -> dict[str, Any]:
    return {"status": "forbidden", "message": f"Only the librarian can {action}."}


def _summary(request: ArticleRequest) -> dict[str, Any]:
    return {
        "request_id": request.id,
        "requester": request.requester,
        "article": request.article.title,
        "doi": request.article.doi,
        "pmid": request.article.pmid,
        "note": request.note,
        "status": request.status,
        "created_at": request.created_at,
        "decided_at": request.decided_at,
        "decision_reason": request.decision_reason,
    }


class LibraryTools:
    """The library tools. Each public method is one tool; the rules live here, not in the prompt.

    `access` and `notifier` are stand-ins until the library's real systems are connected.
    """

    def __init__(
        self,
        lookup: PublicLookup,
        access: SampleAccessChecker,
        store: SqliteRequestStore,
        notifier: SimulatedNotifier,
        *,
        librarian_email: str,
        approval_base_url: str,
    ) -> None:
        self.lookup = lookup
        self.access = access
        self.store = store
        self.notifier = notifier
        self.librarian_email = librarian_email
        self.approval_base_url = approval_base_url

    async def _resolve(self, text: str) -> tuple[Article | None, list[Article]]:
        ident = parse_identifier(text)
        if ident.kind == "doi":
            return await self.lookup.by_doi(ident.value), []
        if ident.kind == "pmid":
            return await self.lookup.by_pmid(ident.value), []
        return None, await self.lookup.by_citation(ident.value)

    async def find_article(self, query: str) -> dict[str, Any]:
        try:
            article, candidates = await self._resolve(query)
            if article is None and candidates:
                return {
                    "status": "confirm_match",
                    "message": "Typed citation: show the numbered options below exactly as "
                    "written and ask the user which one they mean. Do not pick one yourself.",
                    "options": [_option(i, c) for i, c in enumerate(candidates, 1)],
                }
            if article is None:
                return {"status": "not_found", "message": "No matching article was found."}

            access = await self.access.check(article)
            found = {
                "article": article.model_dump(mode="json", exclude_none=True),
                "access": access.model_dump(mode="json"),
            }
            if access.subscribed:
                link = access.links[0].url if access.links else None
                return {
                    "status": "has_access",
                    "message": f"The library has access to: {_describe(article)}. "
                    f"Give the user this link: {link}",
                    **found,
                    "link": link,
                }

            free_copy = await self.lookup.free_copy(article.doi) if article.doi else None
            if free_copy:
                return {
                    "status": "free_copy",
                    "message": "Not in the library's subscriptions, but a free legal copy exists: "
                    f"{_describe(article)}. Give the user this link: {free_copy.url}",
                    **found,
                    "free_copy": free_copy.model_dump(mode="json", exclude_none=True),
                    "link": free_copy.url,
                }
            return {
                "status": "needs_request",
                "message": "Not available through the library or as a free copy: "
                f"{_describe(article)}. Offer to send a request to the librarian.",
                **found,
            }
        except LookupFailed as exc:
            return _unavailable(exc)

    async def request_article(self, user: User, identifier: str, note: str = "") -> dict[str, Any]:
        if parse_identifier(identifier).kind == "citation":
            return {
                "status": "error",
                "message": "A DOI or PubMed ID is needed. Use find_article first and pass the "
                "DOI of the confirmed article.",
            }
        try:
            article, _ = await self._resolve(identifier)
        except LookupFailed as exc:
            return _unavailable(exc)
        if article is None:
            return {"status": "not_found", "message": "No matching article was found."}

        existing = self.store.find_pending(user.id, article)
        if existing:
            return {
                "status": "already_pending",
                "request_id": existing.id,
                "message": "A request for this article is already waiting for the librarian.",
            }
        request = self.store.create(user.id, article, note or None)
        await self.notifier.send(
            self.librarian_email,
            f"Article request {request.id}",
            f"{user.id} requests: {_describe(article)}\n"
            f"DOI: {article.doi or '-'}  PMID: {article.pmid or '-'}\n"
            f"Review: {self.approval_base_url}/requests/{request.id}",
        )
        return {
            "status": "created",
            "request_id": request.id,
            "message": "The request is with the librarian for approval; the requester is "
            "emailed the outcome.",
        }

    async def get_request_status(self, user: User, request_id: str) -> dict[str, Any]:
        request = self.store.get(request_id.strip().upper())
        # Requesters see only their own requests, and cannot tell that others exist.
        if request is None or (user.role != "librarian" and request.requester != user.id):
            return {"status": "not_found", "message": "No request with that ID."}
        return _summary(request)

    async def list_pending_requests(self, user: User) -> dict[str, Any]:
        if user.role != "librarian":
            return _forbidden("list pending requests")
        pending = self.store.list_pending()
        return {"status": "ok", "count": len(pending), "requests": [_summary(r) for r in pending]}

    async def decide_request(
        self, user: User, request_id: str, approved: bool, reason: str = ""
    ) -> dict[str, Any]:
        if user.role != "librarian":
            return _forbidden("approve or decline requests")
        request = self.store.decide(request_id.strip().upper(), approved, reason or None)
        if request is None:
            return {
                "status": "not_found",
                "message": "No pending request with that ID. It may be unknown or already decided.",
            }
        outcome = "approved" if approved else "declined"
        await self.notifier.send(
            request.requester,
            f"Your article request {request.id} was {outcome}",
            f"{_describe(request.article)}\n" + (f"Reason: {reason}" if reason else ""),
        )
        return _summary(request)
