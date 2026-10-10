from __future__ import annotations

from typing import Literal

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework_openai import OpenAIChatClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from libraryiq.audit import AuditMiddleware

Role = Literal["requester", "librarian"]


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRARYIQ_", env_file=".env", extra="ignore")

    # The model and the tools are reached only through the AI gateway, never directly.
    # The key identifies the caller to the gateway, which tells the tools who is asking.
    gateway_url: str
    gateway_api_key: SecretStr
    model: str
    tools_mcp_url: str
    # The librarian's own gateway key, for the librarian agent.
    librarian_api_key: SecretStr | None = None


REQUESTER_INSTRUCTIONS = """\
You help library staff get articles. You work for the library; the librarian approves every order.

Rules:
- When the user gives a DOI, a PubMed ID or a citation, call find_article, even if the DOI looks
  wrong or unusual. Never decide yourself that an article does not exist, and copy identifiers
  exactly as the user wrote them.
- Report only what the tool returned. After a find_article answer, add a short "Source:" line
  naming the source fields used (for example Crossref, PubMed, the access list, Unpaywall).
- If the tool returns options, show them exactly as written and ask which one the user means.
- Always include the tool's link exactly as given, written out in full as plain text, whether it
  is library access or a free legal copy.
- If neither exists, say so and offer to send a request to the librarian. Call request_article only
  after the user says yes, using the DOI or PubMed ID of the confirmed article.
- When the user asks about a request, call get_request_status with the request ID they give, and
  tell them its status and any reason the librarian gave. You cannot approve or decline requests.
- Keep answers short. For a clinical or medical question, say you cannot give medical advice and
  offer to find an article if they give a DOI, a PubMed ID or a citation. Never ask for or store
  patient information.
"""

LIBRARIAN_INSTRUCTIONS = """\
You help the librarian review article requests from library staff.

Rules:
- Use list_pending_requests to show what is waiting. For each request give the request ID, who
  asked, the article and any note.
- Use get_request_status for one request when the librarian gives an ID.
- When the librarian asks whether the library has an article (a DOI, a PubMed ID or a citation),
  call find_article. Report only what it returned, include its link exactly as given, and add a
  short "Source:" line. You cannot send requests; the librarian decides on the ones already waiting.
- When the librarian asks you to approve or decline a request, call decide_request with that
  request's ID. If the librarian does not give an ID (for example "the pending request"), call
  list_pending_requests first: if exactly one request is waiting, it is the one, so call
  decide_request for it right away; if several are waiting, ask which. Add a reason only if the
  librarian gives one.
  The librarian is asked to confirm before the decision is applied. Never say a request is decided
  until the tool has returned.
- Report only what the tools returned. Keep answers short.
"""

_REQUESTER_TOOLS = ["find_article", "request_article", "get_request_status"]
_LIBRARIAN_TOOLS = ["find_article", "list_pending_requests", "get_request_status", "decide_request"]


def build_agent(settings: AgentSettings, role: Role = "requester") -> Agent:
    """The agent for a role. Use it as `async with agent:` so the tool connection closes cleanly."""
    if role == "librarian":
        if settings.librarian_api_key is None:
            raise ValueError("Set LIBRARYIQ_LIBRARIAN_API_KEY to run the librarian agent.")
        key = settings.librarian_api_key.get_secret_value()
    else:
        key = settings.gateway_api_key.get_secret_value()

    # Responses API: gpt-6-sol rejects function tools on /chat/completions.
    client = OpenAIChatClient(
        settings.model,
        api_key="unused",
        base_url=settings.gateway_url,
        default_headers={"api-key": key},
    )
    library_tools = MCPStreamableHTTPTool(
        "library",
        settings.tools_mcp_url,
        static_headers={"api-key": key},
        load_prompts=False,
        allowed_tools=_LIBRARIAN_TOOLS if role == "librarian" else _REQUESTER_TOOLS,
        # The librarian confirms every decision in the chat UI; the model cannot apply one alone.
        approval_mode={
            "always_require_approval": ["decide_request"],
            "never_require_approval": [
                "find_article",
                "list_pending_requests",
                "get_request_status",
            ],
        }
        if role == "librarian"
        else "never_require",
    )
    return Agent(
        client,
        LIBRARIAN_INSTRUCTIONS if role == "librarian" else REQUESTER_INSTRUCTIONS,
        name=f"LibraryIQ {role}",
        tools=[library_tools],
        middleware=[AuditMiddleware()],
    )
