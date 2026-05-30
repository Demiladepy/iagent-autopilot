"""API authentication and production security helpers."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, WebSocket, status

from sentinel.config import Settings, auth_required as config_auth_required

API_KEY_HEADER = "x-sentinel-api-key"


def auth_required(settings: Settings) -> bool:
    """True when protected routes must present a valid API key."""
    return config_auth_required(settings)


def extract_api_key(
    *,
    header_key: str | None = None,
    authorization: str | None = None,
    query_key: str | None = None,
) -> str | None:
    if header_key and header_key.strip():
        return header_key.strip()
    if authorization:
        lower = authorization.lower()
        if lower.startswith("bearer "):
            token = authorization[7:].strip()
            if token:
                return token
    if query_key and query_key.strip():
        return query_key.strip()
    return None


def key_is_valid(settings: Settings, candidate: str | None) -> bool:
    expected = settings.sentinel_api_key
    if not expected or not candidate:
        return False
    return secrets.compare_digest(candidate, expected)


def validate_api_key(settings: Settings, candidate: str | None) -> None:
    """Raise HTTPException if auth is required and the key is missing or wrong."""
    if not auth_required(settings):
        return
    if not settings.sentinel_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key required but SENTINEL_API_KEY is not configured on the server",
        )
    if not key_is_valid(settings, candidate):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_api_key(
    request: Request,
    x_sentinel_api_key: Annotated[str | None, Header(alias="X-Sentinel-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """FastAPI dependency for protected HTTP routes."""
    settings: Settings = request.app.state.settings
    candidate = extract_api_key(
        header_key=x_sentinel_api_key,
        authorization=authorization,
        query_key=request.query_params.get("api_key"),
    )
    validate_api_key(settings, candidate)


def ws_auth_ok(settings: Settings, websocket: WebSocket) -> bool:
    if not auth_required(settings):
        return True
    if not settings.sentinel_api_key:
        return False
    candidate = extract_api_key(
        header_key=websocket.headers.get(API_KEY_HEADER),
        authorization=websocket.headers.get("authorization"),
        query_key=websocket.query_params.get("api_key"),
    )
    return key_is_valid(settings, candidate)


def assert_production_config(settings: Settings) -> None:
    """Deprecated — use sentinel.config.validate_settings instead."""
    from sentinel.config import validate_settings

    validate_settings(settings)
