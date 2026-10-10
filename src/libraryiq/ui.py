from __future__ import annotations

import logging

from agent_framework.devui import serve

from libraryiq.agent import AgentSettings, build_agent

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    settings = AgentSettings()
    # Local chat UI. Open it in two browser windows: one on the requester agent, one on the
    # librarian agent. Each agent uses its own gateway key, which is how the gateway tells them apart.
    entities = [build_agent(settings, "requester")]
    if settings.librarian_api_key:
        entities.append(build_agent(settings, "librarian"))
    serve(
        entities=entities,
        port=8080,
        auto_open=True,
        auth_enabled=False,  # bound to localhost only
    )
