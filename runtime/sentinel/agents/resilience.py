"""Shared helpers for agent loop resilience."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_agent_loop_error(agent: str, exc: Exception, *, context: str = "message") -> None:
    """Log full traceback; caller continues the agent loop."""
    logger.exception(
        "%s agent failed processing %s (%s) — continuing loop",
        agent.upper(),
        context,
        type(exc).__name__,
    )
