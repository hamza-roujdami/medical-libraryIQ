from __future__ import annotations

import asyncio
import logging
import sys

from libraryiq.agent import AgentSettings, build_agent


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    settings = AgentSettings()
    agent = build_agent(settings, "librarian" if "librarian" in sys.argv[1:] else "requester")
    async with agent:
        session = agent.create_session()
        print(f"LibraryIQ ({settings.model}). Ctrl+D to quit.")
        while True:
            try:
                text = await asyncio.to_thread(input, "you> ")
            except EOFError:
                break
            if text.strip():
                response = await agent.run(text, session=session)
                print(f"agent> {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
