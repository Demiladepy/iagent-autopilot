"""Consistent API error envelopes — no stack traces to clients."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request as StarletteRequest


def error_body(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    details: Any = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
    }
    if request_id:
        body["request_id"] = request_id
    if details is not None:
        body["error"]["details"] = details
    return body


def request_id_from(request: StarletteRequest) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def json_error(
    *,
    status_code: int,
    code: str,
    message: str,
    request: StarletteRequest | None = None,
    details: Any = None,
) -> JSONResponse:
    rid = request_id_from(request) if request else None
    return JSONResponse(
        status_code=status_code,
        content=error_body(code=code, message=message, request_id=rid, details=details),
    )


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "not_ready" if exc.status_code == 503 else "http_error"
    if exc.status_code == 401:
        code = "unauthorized"
    elif exc.status_code == 404:
        code = "not_found"
    elif exc.status_code == 400:
        code = "bad_request"
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
        details = None
    elif isinstance(detail, dict):
        message = str(detail.get("message", detail))
        details = detail.get("checks", detail)
    else:
        message = str(detail)
        details = detail
    return json_error(
        status_code=exc.status_code,
        code=code,
        message=message,
        request=request,
        details=details,
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return json_error(
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        request=request,
        details=exc.errors(),
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return json_error(
        status_code=500,
        code="internal_error",
        message="Internal server error",
        request=request,
    )
