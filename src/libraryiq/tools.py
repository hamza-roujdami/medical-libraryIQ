from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from agent_framework import FunctionTool, tool

from libraryiq.access import SampleAccessChecker
from libraryiq.identifiers import parse_identifier
from libraryiq.lookup import Article, LookupFailed, PublicLookup
from libraryiq.orders import ArticleRequest, SimulatedNotifier, SqliteRequestStore


@dataclass(frozen=True)
class User:
    """Who is asking. Set by the application from the signed-in user, never by the model."""

    id: str
    role: Literal["requester", "librarian"] = "requester"


@dataclass
class Library:
    """The systems behind the tools. `access` and `notifier` are stand-ins for now."""

    lookup: PublicLookup
    access: SampleAccessChecker
    store: SqliteRequestStore
    notifier: SimulatedNotifier
    librarian_email: str


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


def library_tools(library: Library, user: User) -> list[FunctionTool]:
    """The tools this user may use. A role never sees the tools it cannot use.

    The rules live here, not in the prompt, and `user` is fixed here, not chosen by the model.
    """

    async def resolve(text: str) -> tuple[Article | None, list[Article]]:
        ident = parse_identifier(text)
        if ident.kind == "doi":
            return await library.lookup.by_doi(ident.value), []
        if ident.kind == "pmid":
            return await library.lookup.by_pmid(ident.value), []
        return None, await library.lookup.by_citation(ident.value)

    @tool(
        description=(
            "Identify an article and check whether the library can provide it. Returns the "
            "article details, the library access result and any free legal copy, each with its "
            "source. For a typed citation it returns candidate articles to confirm."
        )
    )
    async def find_article(
        query: Annotated[
            str, "A DOI, a PubMed ID, or a typed citation (title, authors, journal, year)"
        ],
    ) -> dict[str, Any]:
        try:
            article, candidates = await resolve(query)
            if article is None and candidates:
                return {
                    "status": "confirm_match",
                    "message": "Typed citation: show the numbered options below exactly as "
                    "written and ask the user which one they mean. Do not pick one yourself.",
                    "options": [_option(i, c) for i, c in enumerate(candidates, 1)],
                }
            if article is None:
                return {"status": "not_found", "message": "No matching article was found."}

            access = await library.access.check(article)
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

            free_copy = await library.lookup.free_copy(article.doi) if article.doi else None
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

    @tool(
        description=(
            "Send a request for an article to the librarian, who approves every order. Only call "
            "this after the user has agreed to send a request. Needs the article's DOI or PubMed ID."
        )
    )
    async def request_article(
        identifier: Annotated[str, "The DOI or PubMed ID of the confirmed article"],
        note: Annotated[str, "Optional reason or context from the user"] = "",
    ) -> dict[str, Any]:
        if parse_identifier(identifier).kind == "citation":
            return {
                "status": "error",
                "message": "A DOI or PubMed ID is needed. Use find_article first and pass the "
                "DOI of the confirmed article.",
            }
        try:
            article, _ = await resolve(identifier)
        except LookupFailed as exc:
            return _unavailable(exc)
        if article is None:
            return {"status": "not_found", "message": "No matching article was found."}

        existing = library.store.find_pending(user.id, article)
        if existing:
            return {
                "status": "already_pending",
                "request_id": existing.id,
                "message": "A request for this article is already waiting for the librarian.",
            }
        request = library.store.create(user.id, article, note or None)
        await library.notifier.send(
            library.librarian_email,
            f"Article request {request.id}",
            f"{user.id} requests: {_describe(article)}\n"
            f"DOI: {article.doi or '-'}  PMID: {article.pmid or '-'}",
        )
        return {
            "status": "created",
            "request_id": request.id,
            "message": "The request is with the librarian for approval; the requester is "
            "emailed the outcome.",
        }

    @tool(
        description=(
            "Check the status of an article request: pending, approved or declined, with the "
            "librarian's reason. Requesters can see only their own requests."
        )
    )
    async def get_request_status(
        request_id: Annotated[str, "The request ID, for example REQ-1A2B3C"],
    ) -> dict[str, Any]:
        request = library.store.get(request_id.strip().upper())
        # Requesters see only their own requests, and cannot tell that others exist.
        if request is None or (user.role != "librarian" and request.requester != user.id):
            return {"status": "not_found", "message": "No request with that ID."}
        return _summary(request)

    @tool(description="List the article requests waiting for a decision.")
    async def list_pending_requests() -> dict[str, Any]:
        pending = library.store.list_pending()
        return {"status": "ok", "count": len(pending), "requests": [_summary(r) for r in pending]}

    @tool(
        description=(
            "Approve or decline a pending article request, with an optional reason. Only call "
            "this when the librarian has asked for that decision."
        ),
        # The framework pauses for the librarian's confirmation before this runs.
        approval_mode="always_require",
    )
    async def decide_request(
        request_id: Annotated[str, "The request ID, for example REQ-1A2B3C"],
        approved: Annotated[bool, "True to approve, false to decline"],
        reason: Annotated[str, "Optional reason, shown to the requester"] = "",
    ) -> dict[str, Any]:
        request = library.store.decide(request_id.strip().upper(), approved, reason or None)
        if request is None:
            return {
                "status": "not_found",
                "message": "No pending request with that ID. It may be unknown or already decided.",
            }
        outcome = "approved" if approved else "declined"
        await library.notifier.send(
            request.requester,
            f"Your article request {request.id} was {outcome}",
            f"{_describe(request.article)}\n" + (f"Reason: {reason}" if reason else ""),
        )
        return _summary(request)

    if user.role == "librarian":
        return [find_article, list_pending_requests, get_request_status, decide_request]
    return [find_article, request_article, get_request_status]
