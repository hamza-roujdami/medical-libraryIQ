from __future__ import annotations

from agent_framework import Agent
from agent_framework_openai import OpenAIChatClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from libraryiq.access import SampleAccessChecker
from libraryiq.audit import AuditMiddleware
from libraryiq.lookup import PublicLookup, make_http_client
from libraryiq.orders import SimulatedNotifier, SqliteRequestStore
from libraryiq.tools import Library, User, library_tools


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRARYIQ_", env_file=".env", extra="ignore")

    # The model is reached only through the AI gateway, never directly.
    gateway_url: str
    gateway_api_key: SecretStr
    model: str

    # Sent to Crossref, PubMed and Unpaywall as their requested contact address.
    contact_email: str
    librarian_email: str = "librarian@example.org"
    database_path: str = "libraryiq.db"

    # The two demo people. In production the user comes from the signed-in identity.
    requester_id: str = "demo.user@example.org"
    librarian_id: str = "demo.librarian@example.org"

    @property
    def requester(self) -> User:
        return User(self.requester_id, "requester")

    @property
    def librarian(self) -> User:
        return User(self.librarian_id, "librarian")


def open_library(settings: AgentSettings) -> Library:
    return Library(
        lookup=PublicLookup(make_http_client(settings.contact_email), settings.contact_email),
        access=SampleAccessChecker(),
        store=SqliteRequestStore(settings.database_path),
        notifier=SimulatedNotifier(),
        librarian_email=settings.librarian_email,
    )


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


def build_agent(settings: AgentSettings, library: Library, user: User) -> Agent:
    """The agent for one user: their role decides the instructions and the tools."""
    # Responses API: gpt-6-sol rejects function tools on /chat/completions.
    client = OpenAIChatClient(
        settings.model,
        api_key="unused",
        base_url=settings.gateway_url,
        default_headers={"api-key": settings.gateway_api_key.get_secret_value()},
    )
    librarian = user.role == "librarian"
    return Agent(
        client,
        LIBRARIAN_INSTRUCTIONS if librarian else REQUESTER_INSTRUCTIONS,
        name=f"LibraryIQ {user.role}",
        tools=library_tools(library, user),
        middleware=[AuditMiddleware()],
    )
