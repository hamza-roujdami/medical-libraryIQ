from __future__ import annotations

import httpx
from agent_framework import Agent, SupportsChatGetResponse
from agent_framework_ollama import OllamaChatClient

from libraryiq.audit import AuditMiddleware
from libraryiq.config import Settings
from libraryiq.core.access import SampleAccessChecker
from libraryiq.core.lookup import PublicLookup
from libraryiq.core.notify import SimulatedNotifier
from libraryiq.core.service import Services
from libraryiq.core.store import SqliteRequestStore
from libraryiq.tools import make_tools

INSTRUCTIONS = """\
You help library staff get articles. You work for the library; the librarian approves every order.

Rules:
- When the user gives a DOI, a PubMed ID or a citation, call find_article. Never guess article details.
- Report only what the tool returned. After a find_article answer, add a short "Source:" line
  naming the source fields used (for example Crossref, PubMed, the access list, Unpaywall).
- If the tool returns options, show them exactly as written and ask which one the user means.
- If the library has access, give the link. If there is a free legal copy, give that link.
- If neither exists, say so and offer to send a request to the librarian. Call request_article only
  after the user says yes, using the DOI or PubMed ID of the confirmed article.
- Keep answers short. Do not give clinical advice and do not ask for or store patient information.
"""


def make_chat_client(settings: Settings) -> SupportsChatGetResponse:
    return OllamaChatClient(host=settings.ollama_host, model=settings.ollama_model)


def build_services(settings: Settings, http: httpx.AsyncClient) -> Services:
    return Services(
        lookup=PublicLookup(http, settings.contact_email),
        access=SampleAccessChecker(),
        store=SqliteRequestStore(settings.database_path),
        notifier=SimulatedNotifier(),
        librarian_email=settings.librarian_email,
        approval_base_url=settings.approval_base_url,
        requester=settings.requester,
    )


def build_agent(client: SupportsChatGetResponse, svc: Services) -> Agent:
    return Agent(
        client,
        INSTRUCTIONS,
        name="LibraryIQ",
        tools=make_tools(svc),
        middleware=[AuditMiddleware()],
    )
