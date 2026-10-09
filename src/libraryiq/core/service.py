from __future__ import annotations

from dataclasses import dataclass

from libraryiq.core.access import AccessChecker
from libraryiq.core.identifiers import parse_identifier
from libraryiq.core.lookup import ArticleLookup
from libraryiq.core.models import Article, ArticleRequest, FindResult
from libraryiq.core.notify import Notifier
from libraryiq.core.store import RequestStore


@dataclass
class Services:
    lookup: ArticleLookup
    access: AccessChecker
    store: RequestStore
    notifier: Notifier
    librarian_email: str
    approval_base_url: str
    requester: str


def _describe(article: Article) -> str:
    parts = [article.title]
    if article.journal:
        parts.append(article.journal)
    if article.year:
        parts.append(str(article.year))
    return ", ".join(parts)


def describe_candidate(number: int, article: Article) -> str:
    authors = ", ".join(article.authors[:3]) + (" et al." if len(article.authors) > 3 else "")
    where = ", ".join(
        p for p in (article.journal, str(article.year) if article.year else None) if p
    )
    ref = f"DOI: {article.doi}" if article.doi else f"PMID: {article.pmid}"
    return f"{number}. {article.title} - {authors or 'authors unknown'} ({where or 'no journal'}) {ref}"


async def resolve_article(svc: Services, text: str) -> tuple[Article | None, list[Article]]:
    """Return the matching article, or a list of candidates when the input is a typed citation."""
    ident = parse_identifier(text)
    if ident.kind == "doi":
        return await svc.lookup.by_doi(ident.value), []
    if ident.kind == "pmid":
        return await svc.lookup.by_pmid(ident.value), []
    return None, await svc.lookup.by_citation(ident.value)


async def find_article(svc: Services, text: str) -> FindResult:
    article, candidates = await resolve_article(svc, text)

    if article is None and candidates:
        return FindResult(
            status="confirm_match",
            message="Typed citation: show the numbered options below exactly as written and ask the "
            "user which one they mean. Do not pick one yourself.",
            candidates=candidates,
            options=[describe_candidate(i, c) for i, c in enumerate(candidates, 1)],
        )
    if article is None:
        return FindResult(status="not_found", message="No matching article was found.")

    access = await svc.access.check(article)
    if access.subscribed:
        return FindResult(
            status="has_access",
            message=f"The library has access to: {_describe(article)}.",
            article=article,
            access=access,
        )

    free_copy = await svc.lookup.free_copy(article.doi) if article.doi else None
    if free_copy:
        return FindResult(
            status="free_copy",
            message=f"Not in the library's subscriptions, but a free legal copy exists: {_describe(article)}.",
            article=article,
            access=access,
            free_copy=free_copy,
        )
    return FindResult(
        status="needs_request",
        message=f"Not available through the library or as a free copy: {_describe(article)}. "
        "Offer to send a request to the librarian.",
        article=article,
        access=access,
    )


async def request_article(
    svc: Services, identifier: str, note: str | None
) -> tuple[ArticleRequest | None, bool]:
    """Create a pending request. Returns (request, created); created is False for a duplicate."""
    article, _ = await resolve_article(svc, identifier)
    if article is None:
        return None, False
    existing = await svc.store.find_pending(svc.requester, article)
    if existing:
        return existing, False
    request = await svc.store.create(svc.requester, article, note)
    await svc.notifier.send(
        svc.librarian_email,
        f"Article request {request.id}",
        f"{svc.requester} requests: {_describe(article)}\n"
        f"DOI: {article.doi or '-'}  PMID: {article.pmid or '-'}\n"
        f"Review: {svc.approval_base_url}/requests/{request.id}",
    )
    return request, True


async def decide_request(
    svc: Services, request_id: str, approved: bool, reason: str | None
) -> ArticleRequest | None:
    request = await svc.store.decide(request_id, approved, reason)
    if request is None:
        return None
    outcome = "approved" if approved else "declined"
    await svc.notifier.send(
        request.requester,
        f"Your article request {request.id} was {outcome}",
        f"{_describe(request.article)}\n" + (f"Reason: {reason}" if reason else ""),
    )
    return request
