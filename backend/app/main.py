"""Application factory.

Run with ``uvicorn app.main:create_app --factory`` (see Dockerfile). The factory form keeps
module import free of side effects, so tests can build an app with injected settings and a
test double for the database without touching the environment.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from . import __version__
from .config import Settings
from .db import ID_INDEX_NAME, Database
from .redaction import describe_uri, redact
from .routers import health, items

log = logging.getLogger("app.main")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("pymongo").setLevel(logging.WARNING)


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            db = database or Database.from_settings(resolved)
        except Exception as exc:  # pymongo raises InvalidURI / ConfigurationError for a bad URI
            log.error(
                "mongodb client configuration failed: %s: %s",
                type(exc).__name__,
                redact(str(exc)),
            )
            raise RuntimeError("mongodb client configuration failed") from None
        app.state.db = db
        app.state.settings = resolved
        log.info(
            "mongodb target=%s database=%s collection=%s",
            describe_uri(resolved.mongodb_uri),
            resolved.mongodb_database,
            resolved.mongodb_collection,
        )
        try:
            await db.ensure_indexes(resolved.startup_index_timeout_ms)
            log.info("unique index %s ensured on startup", ID_INDEX_NAME)
        except (PyMongoError, TimeoutError, OSError) as exc:
            # The process stays up (liveness keeps passing); readiness retries the index and
            # stays 503 until MongoDB is reachable and the unique index exists.
            log.warning(
                "could not ensure indexes on startup (%s: %s); readiness will retry",
                type(exc).__name__,
                redact(str(exc)),
            )
        try:
            yield
        finally:
            # Reached on SIGTERM/SIGINT after uvicorn drained in-flight requests.
            await db.close()
            log.info("mongodb client closed")

    app = FastAPI(
        title="three-tier-crud backend",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.include_router(health.router)
    app.include_router(items.router)

    @app.exception_handler(PyMongoError)
    async def mongodb_unavailable(_: Request, exc: PyMongoError) -> JSONResponse:
        log.error("mongodb operation failed: %s: %s", type(exc).__name__, redact(str(exc)))
        return JSONResponse(status_code=503, content={"detail": "database unavailable"})

    @app.exception_handler(TimeoutError)
    async def mongodb_timeout(_: Request, exc: TimeoutError) -> JSONResponse:
        log.error("mongodb operation timed out: %s", redact(str(exc)))
        return JSONResponse(status_code=503, content={"detail": "database timeout"})

    return app
