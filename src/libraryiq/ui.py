from __future__ import annotations

import logging

from agent_framework.devui import serve

from libraryiq.agent import AgentSettings, build_agent, open_library

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    settings = AgentSettings()
    # One library shared by both agents, so a request raised by the requester shows up for the librarian.
    library = open_library(settings)
    serve(
        entities=[
            build_agent(settings, library, settings.requester),
            build_agent(settings, library, settings.librarian),
        ],
        port=8080,
        auto_open=True,
        auth_enabled=False,  # bound to localhost only
    )
