"""HTTP middleware for production hardening."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Request-ID", request.state.request_id)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach request id and log latency for observability."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:12])
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_id=%s method=%s path=%s unhandled",
                request.state.request_id,
                request.method,
                request.url.path,
            )
            raise
        ms = (time.perf_counter() - started) * 1000
        if request.url.path not in ("/health", "/ready"):
            logger.info(
                "request_id=%s method=%s path=%s status=%s latency_ms=%.1f",
                request.state.request_id,
                request.method,
                request.url.path,
                response.status_code,
                ms,
            )
        return response
