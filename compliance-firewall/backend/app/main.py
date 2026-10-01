"""App factory: security middleware, CORS, routers, and startup (create/migrate tables + seed)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.ai.governance import AIBudget
from app.ai.llm import GroqClient
from app.api.routes import audit, chat, governance, health, rules, suite
from app.core.config import Settings, get_settings
from app.core.db import create_tables, make_engine, migrate_missing_columns
from app.core.logging import configure_logging, get_logger
from app.core.security import ClientRateLimiter, SecurityHeadersMiddleware
from app.rules.cache import RulesCache
from app.rules.seed import seed_if_empty

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        create_tables(app.state.engine)
        for column in migrate_missing_columns(app.state.engine):
            log.warning("migrated database: added column %s", column)
        with Session(app.state.engine) as session:
            if seed_if_empty(session):
                log.info("seeded rules v1")
        yield
        app.state.engine.dispose()

    app = FastAPI(title="Compliance Firewall for AI Answers", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.llm = GroqClient(settings.groq_api_key.get_secret_value(), settings.groq_model)
    app.state.rules_cache = RulesCache()
    app.state.ai_budget = AIBudget(settings.ai_max_calls_per_minute)
    app.state.rate_limiter = ClientRateLimiter(settings.rate_limit_per_minute)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,  # "*" only honoured when DEBUG=true
        allow_credentials=False,  # auth is by header token, never cookies
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-API-Key", "X-Admin-Token"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    if not settings.debug and not settings.api_token.get_secret_value():
        log.warning("API_TOKEN is not set: check, chat and audit endpoints are closed (403)")
    for module in (health, chat, rules, audit, suite, governance):
        app.include_router(module.router)
    return app


app = create_app()
