"""Kubernetes probe endpoints.

``/api/health/live`` answers from the event loop only and never touches MongoDB, so a database
outage cannot make the kubelet restart a healthy FastAPI process. ``/api/health/ready`` pings
MongoDB with a finite timeout and returns 503 while the database is unreachable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from pymongo.errors import PyMongoError

from ..db import Database
from ..redaction import redact

log = logging.getLogger("app.health")
router = APIRouter(prefix="/api/health", tags=["health"])
_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/live")
async def live(response: Response) -> dict[str, str]:
    response.headers.update(_NO_STORE)
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    response.headers.update(_NO_STORE)
    db: Database = request.app.state.db
    try:
        await db.ping()
        if not db.indexes_ready:
            await db.ensure_indexes()
    except (PyMongoError, TimeoutError, OSError) as exc:
        log.warning("readiness failed: %s: %s", type(exc).__name__, redact(str(exc)))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is not ready",
            headers=_NO_STORE,
        ) from None
    return {"status": "ok", "mongodb": "ready"}
