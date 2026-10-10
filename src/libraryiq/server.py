from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from libraryiq.access import SampleAccessChecker
from libraryiq.lookup import PublicLookup, make_http_client
from libraryiq.orders import SimulatedNotifier, SqliteRequestStore
from libraryiq.tools import LibraryTools, User

logger = logging.getLogger("libraryiq.server")


class ToolsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRARYIQ_", env_file=".env", extra="ignore")

    # Sent to Crossref, PubMed and Unpaywall as their requested contact address.
    contact_email: str

    librarian_email: str = "librarian@example.org"
    approval_base_url: str = "http://localhost:8000"
    # The caller when no identity header arrives, for local runs without the gateway.
    requester: str = "demo.user@example.org"
    database_path: str = "libraryiq.db"

    # Calls must carry this key in x-backend-key. The AI gateway adds it, together with the
    # x-user-id and x-user-role headers it derives from the caller's subscription.
    backend_key: SecretStr | None = None
    # Exposes /_test/state and /_test/reset for the eval runner. Keep off outside dev.
    enable_test_endpoints: bool = False


class BackendKeyMiddleware:
    """Rejects any call that does not carry the shared key the gateway adds."""

    def __init__(self, app: ASGIApp, key: str) -> None:
        self.app = app
        self.key = key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            given = Request(scope).headers.get("x-backend-key", "")
            if not secrets.compare_digest(given, self.key):
                response = JSONResponse({"error": "Missing or invalid backend key"}, 401)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


def _caller(ctx: Context, default_id: str) -> User:
    """The identity the gateway set. Without it (local runs) the caller is the default requester."""
    request = ctx.request_context.request
    headers = request.headers if request is not None else {}
    role = "librarian" if headers.get("x-user-role") == "librarian" else "requester"
    return User(headers.get("x-user-id") or default_id, role)


def build_server(tools: LibraryTools, settings: ToolsSettings) -> FastMCP:
    mcp = FastMCP(
        "libraryiq-library-tools",
        stateless_http=True,
        json_response=True,
        # Calls arrive through the gateway with its host name, so the localhost-only check is off.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    default_id = settings.requester

    @mcp.tool(
        description=(
            "Identify an article and check whether the library can provide it. Returns the "
            "article details, the library access result and any free legal copy, each with its "
            "source. For a typed citation it returns candidate articles to confirm."
        )
    )
    async def find_article(
        query: Annotated[
            str,
            Field(
                description="A DOI, a PubMed ID, or a typed citation (title, authors, journal, year)"
            ),
        ],
    ) -> dict[str, Any]:
        return await tools.find_article(query)

    @mcp.tool(
        description=(
            "Send a request for an article to the librarian, who approves every order. Only call "
            "this after the user has agreed to send a request. Needs the article's DOI or PubMed ID."
        )
    )
    async def request_article(
        identifier: Annotated[
            str, Field(description="The DOI or PubMed ID of the confirmed article")
        ],
        ctx: Context,
        note: Annotated[str, Field(description="Optional reason or context from the user")] = "",
    ) -> dict[str, Any]:
        return await tools.request_article(_caller(ctx, default_id), identifier, note)

    @mcp.tool(
        description=(
            "Check the status of an article request: pending, approved or declined, with the "
            "librarian's reason. Requesters can see only their own requests."
        )
    )
    async def get_request_status(
        request_id: Annotated[str, Field(description="The request ID, for example REQ-1A2B3C")],
        ctx: Context,
    ) -> dict[str, Any]:
        return await tools.get_request_status(_caller(ctx, default_id), request_id)

    @mcp.tool(description="List the article requests waiting for a decision. Librarian only.")
    async def list_pending_requests(ctx: Context) -> dict[str, Any]:
        return await tools.list_pending_requests(_caller(ctx, default_id))

    @mcp.tool(
        description=(
            "Approve or decline a pending article request, with an optional reason. Librarian "
            "only. Only call this when the librarian has asked for that decision."
        )
    )
    async def decide_request(
        request_id: Annotated[str, Field(description="The request ID, for example REQ-1A2B3C")],
        approved: Annotated[bool, Field(description="True to approve, false to decline")],
        ctx: Context,
        reason: Annotated[str, Field(description="Optional reason, shown to the requester")] = "",
    ) -> dict[str, Any]:
        return await tools.decide_request(_caller(ctx, default_id), request_id, approved, reason)

    if settings.enable_test_endpoints:

        @mcp.custom_route("/_test/state", methods=["GET"])
        async def state(_: Request) -> JSONResponse:
            return JSONResponse(
                {"pending": tools.store.count_pending(), "emails": len(tools.notifier.outbox)}
            )

        @mcp.custom_route("/_test/reset", methods=["POST"])
        async def reset(_: Request) -> JSONResponse:
            tools.store.clear()
            tools.notifier.outbox.clear()
            return JSONResponse({"status": "reset"})

    return mcp


def create_app() -> Starlette:
    """ASGI app for uvicorn: `uvicorn libraryiq.server:create_app --factory`."""
    settings = ToolsSettings()
    tools = LibraryTools(
        PublicLookup(make_http_client(settings.contact_email), settings.contact_email),
        SampleAccessChecker(),
        SqliteRequestStore(settings.database_path),
        SimulatedNotifier(),
        librarian_email=settings.librarian_email,
        approval_base_url=settings.approval_base_url,
    )
    app = build_server(tools, settings).streamable_http_app()
    if settings.backend_key:
        app.add_middleware(BackendKeyMiddleware, key=settings.backend_key.get_secret_value())
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
