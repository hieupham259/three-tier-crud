"""MongoDB access built on the official PyMongo Async API (``pymongo.AsyncMongoClient``)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, ReturnDocument

from .config import Settings

# Default name MongoDB assigns to the key pattern {id: 1}. It must match the index created by
# the database init script so that create_index() is a no-op instead of an options conflict.
ID_INDEX_NAME = "id_1"


def utc_now() -> datetime:
    """Current UTC time truncated to milliseconds, the precision of a BSON date."""
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


class ItemStore:
    """Data access for the items collection.

    ``collection`` is a ``pymongo.asynchronous.collection.AsyncCollection`` in production and a
    small in-memory double in the unit tests; only the methods used below are required.
    """

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        # Idempotent: an existing index with identical keys and options is a no-op server-side.
        await self._collection.create_index(
            [("id", ASCENDING)], unique=True, name=ID_INDEX_NAME
        )

    async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        document = {**data, "created_at": now, "updated_at": now}
        await self._collection.insert_one(document)  # DuplicateKeyError on an existing id
        document.pop("_id", None)
        return document

    async def get(self, item_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"id": item_id}, {"_id": 0})

    async def list_page(self, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        total = await self._collection.count_documents({})
        cursor = (
            self._collection.find({}, {"_id": 0})
            .sort([("created_at", DESCENDING), ("id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        documents = await cursor.to_list(length=page_size)
        return documents, total

    async def update(self, item_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        return await self._collection.find_one_and_update(
            {"id": item_id},
            {"$set": {**data, "updated_at": utc_now()}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def delete(self, item_id: str) -> bool:
        result = await self._collection.delete_one({"id": item_id})
        return result.deleted_count == 1


class Database:
    """Owns the client lifecycle, the readiness ping and the index bookkeeping."""

    def __init__(self, client: Any, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._indexes_ready = False
        self._index_lock = asyncio.Lock()
        self.items = ItemStore(client[settings.mongodb_database][settings.mongodb_collection])

    @classmethod
    def from_settings(cls, settings: Settings) -> Database:
        client = AsyncMongoClient(
            settings.mongodb_uri,
            connectTimeoutMS=settings.mongodb_connect_timeout_ms,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
            tz_aware=True,
            appname="three-tier-crud-backend",
        )
        return cls(client, settings)

    @property
    def indexes_ready(self) -> bool:
        return self._indexes_ready

    async def ping(self) -> None:
        """Round-trip to MongoDB bounded by a finite timeout; raises on failure or timeout."""
        timeout = self._settings.mongodb_ping_timeout_ms / 1000
        await asyncio.wait_for(self._client.admin.command("ping"), timeout=timeout)

    async def ensure_indexes(self, timeout_ms: int | None = None) -> None:
        timeout = (timeout_ms or self._settings.startup_index_timeout_ms) / 1000
        async with self._index_lock:
            if self._indexes_ready:
                return
            await asyncio.wait_for(self.items.ensure_indexes(), timeout=timeout)
            self._indexes_ready = True

    async def close(self) -> None:
        await self._client.close()
