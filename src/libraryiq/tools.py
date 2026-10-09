from __future__ import annotations

from typing import Annotated, Any

from agent_framework import FunctionTool, tool

from libraryiq.core import service
from libraryiq.core.identifiers import parse_identifier
from libraryiq.core.lookup import LookupFailed
from libraryiq.core.service import Services


def _unavailable(exc: LookupFailed) -> dict[str, Any]:
    return {
        "status": "error",
        "message": f"A lookup service is unavailable ({exc}). Tell the user to try again shortly.",
    }


def make_tools(svc: Services) -> list[FunctionTool]:
    @tool(
        name="find_article",
        description=(
            "Identify an article and check whether the library can provide it. Returns the "
            "article details, the library access result and any free legal copy, each with its "
            "source. For a typed citation it returns candidate articles to confirm."
        ),
        approval_mode="never_require",
    )
    async def find_article(
        query: Annotated[
            str, "A DOI, a PubMed ID, or a typed citation (title, authors, journal, year)"
        ],
    ) -> dict[str, Any]:
        try:
            result = await service.find_article(svc, query)
        except LookupFailed as exc:
            return _unavailable(exc)
        return result.model_dump(mode="json", exclude_none=True, exclude={"candidates"})

    @tool(
        name="request_article",
        description=(
            "Send a request for an article to the librarian, who approves every order. Only call "
            "this after the user has agreed to send a request. Needs the article's DOI or PubMed ID."
        ),
        approval_mode="never_require",
    )
    async def request_article(
        identifier: Annotated[str, "The DOI or PubMed ID of the confirmed article"],
        note: Annotated[str | None, "Optional reason or context from the user"] = None,
    ) -> dict[str, Any]:
        if parse_identifier(identifier).kind == "citation":
            return {
                "status": "error",
                "message": "A DOI or PubMed ID is needed. Use find_article first and pass the "
                "DOI of the confirmed article.",
            }
        try:
            request, created = await service.request_article(svc, identifier, note)
        except LookupFailed as exc:
            return _unavailable(exc)
        if request is None:
            return {"status": "not_found", "message": "No matching article was found."}
        return {
            "status": "created" if created else "already_pending",
            "request_id": request.id,
            "message": "The request is with the librarian for approval; the requester is emailed "
            "the outcome."
            if created
            else "A request for this article is already waiting for the librarian.",
        }

    return [find_article, request_article]
