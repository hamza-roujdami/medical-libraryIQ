from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from agent_framework import FunctionInvocationContext, FunctionMiddleware

logger = logging.getLogger("libraryiq.audit")


class AuditMiddleware(FunctionMiddleware):
    """Logs every tool call with its arguments, outcome and duration."""

    async def process(
        self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
    ) -> None:
        name = context.function.name
        logger.info("tool_call name=%s args=%s", name, dict(context.arguments))
        started = time.perf_counter()
        try:
            await call_next()
        except Exception:
            logger.exception("tool_error name=%s", name)
            raise
        logger.info("tool_done name=%s ms=%d", name, (time.perf_counter() - started) * 1000)
