from __future__ import annotations

import logging

from agent_framework_foundry_hosting import ResponsesHostServer

from libraryiq.agent import build_agent, build_services, make_chat_client
from libraryiq.config import Settings
from libraryiq.core.lookup import make_http_client


def create_server() -> ResponsesHostServer:
    settings = Settings()
    svc = build_services(settings, make_http_client(settings.contact_email))
    agent = build_agent(make_chat_client(settings), svc)
    return ResponsesHostServer(agent=agent, history_source="agent_server")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    create_server().run()
