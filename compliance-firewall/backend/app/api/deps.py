"""FastAPI dependencies. Everything comes from app.state so tests can swap it out."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlmodel import Session

from app.ai.governance import AIPolicy
from app.ai.llm import LLMClient
from app.ai.prompts import PROMPT_VERSION
from app.core.config import Settings
from app.core.db import get_session as _db_session
from app.pipeline.firewall import FirewallContext, Simulate
from app.rules.cache import RulesCache


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    yield from _db_session(request.app.state.engine)


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


def get_rules_cache(request: Request) -> RulesCache:
    return request.app.state.rules_cache


def get_firewall_context(
    request: Request, llm: Annotated[LLMClient, Depends(get_llm)]
) -> FirewallContext:
    return FirewallContext(llm=llm, cache=get_rules_cache(request), ai=get_ai_policy(request),
                           redact_audit=get_settings(request).audit_redact_pii)


def get_ai_policy(request: Request) -> AIPolicy:
    settings = get_settings(request)
    return AIPolicy(
        enabled=settings.ai_enabled,
        budget=request.app.state.ai_budget,
        timeout_s=settings.check_timeout_s,
        model=settings.groq_model,
        prompt_version=PROMPT_VERSION,
    )


def _matches(given: str | None, expected: str) -> bool:
    return bool(given) and bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def require_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header(description="Required when ADMIN_TOKEN is set")] = None,
) -> None:
    """AI security: rule edits, reviews and suite runs need the admin token.

    If ADMIN_TOKEN is not configured these endpoints only work with DEBUG=true (fail closed).
    """
    settings = get_settings(request)
    expected = settings.admin_token.get_secret_value()
    if not expected:
        if settings.debug:
            return
        raise HTTPException(status_code=403, detail="set ADMIN_TOKEN to enable this endpoint")
    if not _matches(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="missing or wrong X-Admin-Token")


def require_client(
    request: Request,
    x_api_key: Annotated[str | None, Header(description="Required when API_TOKEN is set")] = None,
    x_admin_token: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> None:
    """AI security: checks, chat, audit reads and the governance report need the API token
    (the admin token is accepted too). If API_TOKEN is not configured these endpoints only work
    with DEBUG=true (fail closed)."""
    settings = get_settings(request)
    api_token = settings.api_token.get_secret_value()
    if not api_token:
        if settings.debug:
            return
        raise HTTPException(status_code=403, detail="set API_TOKEN to enable this endpoint")
    if not (_matches(x_api_key, api_token)
            or _matches(x_admin_token, settings.admin_token.get_secret_value())):
        raise HTTPException(status_code=401, detail="missing or wrong X-API-Key")


def rate_limit(request: Request) -> None:
    """Per-client (IP) limit on endpoints that can trigger AI calls."""
    client = request.client.host if request.client else "unknown"
    if not request.app.state.rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="too many requests, slow down",
                            headers={"Retry-After": "60"})


def get_simulate(
    request: Request,
    simulate: Simulate | None = Query(default=None, description="Debug only: crash | timeout"),
) -> Simulate | None:
    if simulate is not None and not get_settings(request).debug:
        raise HTTPException(status_code=403, detail="simulate is only available when DEBUG=true")
    return simulate
