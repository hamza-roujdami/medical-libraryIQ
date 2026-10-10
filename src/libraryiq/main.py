from __future__ import annotations

import logging

from agent_framework_foundry_hosting import ResponsesHostServer

from libraryiq.agent import AgentSettings, build_agent


def create_server() -> ResponsesHostServer:
    return ResponsesHostServer(agent=build_agent(AgentSettings()), history_source="agent_server")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    create_server().run()
