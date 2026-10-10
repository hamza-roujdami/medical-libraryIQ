import httpx
import pytest
from pydantic import SecretStr

from libraryiq.server import BackendKeyMiddleware, ToolsSettings, build_server


def settings(tmp_path, **overrides) -> ToolsSettings:
    # Explicit defaults so a developer's LIBRARYIQ_* environment variables do not leak in.
    values = {"backend_key": None, "enable_test_endpoints": False, **overrides}
    return ToolsSettings(
        _env_file=None,
        contact_email="test@example.org",
        database_path=str(tmp_path / "test.db"),
        **values,
    )


async def test_exposes_exactly_the_five_tools(make_tools, tmp_path):
    server = build_server(make_tools(), settings(tmp_path))
    tools = {t.name: t for t in await server.list_tools()}
    assert set(tools) == {
        "find_article",
        "request_article",
        "get_request_status",
        "list_pending_requests",
        "decide_request",
    }
    assert tools["request_article"].inputSchema["required"] == ["identifier"]
    assert "ctx" not in tools["request_article"].inputSchema["properties"]
    assert set(tools["decide_request"].inputSchema["required"]) == {"request_id", "approved"}
    assert "DOI" in tools["find_article"].inputSchema["properties"]["query"]["description"]


async def test_tool_call_returns_the_result(make_tools, tmp_path):
    server = build_server(make_tools(), settings(tmp_path))
    _, structured = await server.call_tool("find_article", {"query": "10.1000/nope"})
    assert structured["status"] == "not_found"


@pytest.fixture
def make_client(make_tools, tmp_path):
    def _make(**overrides):
        cfg = settings(tmp_path, **overrides)
        app = build_server(make_tools(), cfg).streamable_http_app()
        if cfg.backend_key:
            app.add_middleware(BackendKeyMiddleware, key=cfg.backend_key.get_secret_value())
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tools")
        return app, client

    return _make


async def test_rejects_a_missing_or_wrong_backend_key(make_client):
    app, client = make_client(backend_key=SecretStr("s3cret"))
    async with app.router.lifespan_context(app), client:
        missing = await client.post("/mcp", json={})
        wrong = await client.post("/mcp", json={}, headers={"x-backend-key": "nope"})
        ok = await client.post("/mcp", json={}, headers={"x-backend-key": "s3cret"})
    assert (missing.status_code, wrong.status_code) == (401, 401)
    assert ok.status_code != 401


async def test_test_endpoints_are_off_by_default(make_client):
    _, client = make_client()
    async with client:
        assert (await client.get("/_test/state")).status_code == 404


async def test_test_endpoints_report_and_reset_state(make_client):
    _, client = make_client(enable_test_endpoints=True)
    async with client:
        assert (await client.get("/_test/state")).json() == {"pending": 0, "emails": 0}
        assert (await client.post("/_test/reset")).json() == {"status": "reset"}


async def _call(client, tool, arguments, headers=None):
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        headers={"Accept": "application/json, text/event-stream", **(headers or {})},
    )
    return response.json()["result"]["structuredContent"]


async def test_the_caller_identity_comes_from_the_gateway_headers(make_client):
    app, client = make_client(enable_test_endpoints=True)
    async with app.router.lifespan_context(app), client:
        # With no identity headers the caller is the default requester, who cannot list requests.
        assert (await _call(client, "list_pending_requests", {}))["status"] == "forbidden"
        as_requester = {"x-user-id": "alex@example.org", "x-user-role": "requester"}
        denied = await _call(client, "list_pending_requests", {}, as_requester)
        assert denied["status"] == "forbidden"
        as_librarian = {"x-user-id": "sam@example.org", "x-user-role": "librarian"}
        allowed = await _call(client, "list_pending_requests", {}, as_librarian)
        assert allowed["status"] == "ok"
