from __future__ import annotations

import asyncio
import logging

from libraryiq.agent import build_agent, build_services, make_chat_client
from libraryiq.config import Settings
from libraryiq.core.lookup import make_http_client


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("libraryiq").setLevel(logging.INFO)
    settings = Settings()
    async with make_http_client(settings.contact_email) as http:
        svc = build_services(settings, http)
        agent = build_agent(make_chat_client(settings), svc)
        session = agent.create_session()
        print(f"LibraryIQ ({settings.ollama_model}). Ctrl+D to quit.")
        while True:
            try:
                text = await asyncio.to_thread(input, "you> ")
            except EOFError:
                break
            if not text.strip():
                continue
            response = await agent.run(text, session=session)
            print(f"agent> {response.text}\n")
            for message in getattr(svc.notifier, "outbox", []):
                print(f"[simulated email to {message.to}] {message.subject}")
            getattr(svc.notifier, "outbox", []).clear()


if __name__ == "__main__":
    asyncio.run(main())
