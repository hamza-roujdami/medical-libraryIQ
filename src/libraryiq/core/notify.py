from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("libraryiq.notify")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


class Notifier(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class SimulatedNotifier:
    """Records messages instead of sending them. Replace with a real sender behind the same interface."""

    def __init__(self) -> None:
        self.outbox: list[Message] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append(Message(to, subject, body))
        logger.info("simulated email to=%s subject=%s", to, subject)
