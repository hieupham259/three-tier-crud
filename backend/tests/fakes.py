"""In-memory stand-ins for the PyMongo Async objects used by the application.

They implement only the coroutine methods ``app.db`` calls, raise the same pymongo exception
types, and expose switches to simulate an unreachable or slow MongoDB.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure, ServerSelectionTimeoutError


class FakeState:
    def __init__(self) -> None:
        self.down = False
        self.ping_delay = 0.0
        self.admin_calls = 0
        self.index_calls: list[dict[str, Any]] = []

    def check(self) -> None:
        if self.down:
            raise ServerSelectionTimeoutError("fake: no servers available")


class FakeAdmin:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    async def command(self, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._state.admin_calls += 1
        if self._state.ping_delay:
            await asyncio.sleep(self._state.ping_delay)
        self._state.check()
        return {"ok": 1.0}


class FakeDeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class FakeInsertResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id


def _project(document: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(document)
    if projection and projection.get("_id") == 0:
        result.pop("_id", None)
    return result


def _matches(document: dict[str, Any], flt: dict[str, Any] | None) -> bool:
    return all(document.get(key) == value for key, value in (flt or {}).items())


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]], projection: dict[str, Any] | None) -> None:
        self._documents = list(documents)
        self._projection = projection
        self._skip = 0
        self._limit = 0

    def sort(self, key_or_list: Any, direction: int | None = None) -> FakeCursor:
        if isinstance(key_or_list, list):
            keys = key_or_list
        else:
            keys = [(key_or_list, direction or ASCENDING)]
        for key, order in reversed(keys):
            self._documents.sort(key=lambda doc: doc.get(key), reverse=(order == -1))
        return self

    def skip(self, count: int) -> FakeCursor:
        self._skip = count
        return self

    def limit(self, count: int) -> FakeCursor:
        self._limit = count
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        documents = self._documents[self._skip :]
        if self._limit:
            documents = documents[: self._limit]
        if length is not None:
            documents = documents[:length]
        return [_project(doc, self._projection) for doc in documents]


class FakeCollection:
    def __init__(self, state: FakeState) -> None:
        self._state = state
        self._next_id = 1
        self.docs: list[dict[str, Any]] = []
        self.indexes: dict[str, dict[str, Any]] = {}

    async def create_index(self, keys: Any, **kwargs: Any) -> str:
        self._state.check()
        key_list = list(keys) if isinstance(keys, list) else [(keys, ASCENDING)]
        name = kwargs.pop("name", None) or "_".join(f"{key}_{order}" for key, order in key_list)
        spec = {"keys": key_list, **kwargs}
        existing = self.indexes.get(name)
        if existing is not None and existing != spec:
            raise OperationFailure("Index with name already exists with different options", 85)
        self.indexes[name] = spec
        self._state.index_calls.append({"name": name, **spec})
        return name

    def _has_unique_id_index(self) -> bool:
        return any(
            index["keys"] == [("id", ASCENDING)] and index.get("unique")
            for index in self.indexes.values()
        )

    async def insert_one(self, document: dict[str, Any]) -> FakeInsertResult:
        self._state.check()
        if self._has_unique_id_index() and any(
            doc.get("id") == document.get("id") for doc in self.docs
        ):
            raise DuplicateKeyError(
                "E11000 duplicate key error collection: cruddb.items index: id_1", 11000
            )
        document["_id"] = self._next_id  # pymongo mutates the caller's document the same way
        self._next_id += 1
        self.docs.append(copy.deepcopy(document))
        return FakeInsertResult(document["_id"])

    async def find_one(
        self, flt: dict[str, Any] | None = None, projection: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        self._state.check()
        for doc in self.docs:
            if _matches(doc, flt):
                return _project(doc, projection)
        return None

    def find(
        self, flt: dict[str, Any] | None = None, projection: dict[str, Any] | None = None
    ) -> FakeCursor:
        self._state.check()
        return FakeCursor([doc for doc in self.docs if _matches(doc, flt)], projection)

    async def count_documents(self, flt: dict[str, Any] | None = None) -> int:
        self._state.check()
        return sum(1 for doc in self.docs if _matches(doc, flt))

    async def find_one_and_update(
        self,
        flt: dict[str, Any],
        update: dict[str, Any],
        projection: dict[str, Any] | None = None,
        return_document: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        self._state.check()
        for doc in self.docs:
            if _matches(doc, flt):
                before = _project(doc, projection)
                doc.update(update.get("$set", {}))
                return _project(doc, projection) if return_document else before
        return None

    async def delete_one(self, flt: dict[str, Any]) -> FakeDeleteResult:
        self._state.check()
        for index, doc in enumerate(self.docs):
            if _matches(doc, flt):
                del self.docs[index]
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self._collection = collection

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collection


class FakeClient:
    """Minimal AsyncMongoClient double: ``client[db][coll]``, ``client.admin``, ``await close()``."""

    def __init__(self) -> None:
        self.state = FakeState()
        self.collection = FakeCollection(self.state)
        self.admin = FakeAdmin(self.state)
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabase:
        return FakeDatabase(self.collection)

    async def close(self) -> None:
        self.closed = True

    @property
    def down(self) -> bool:
        return self.state.down

    @down.setter
    def down(self, value: bool) -> None:
        self.state.down = value

    @property
    def ping_delay(self) -> float:
        return self.state.ping_delay

    @ping_delay.setter
    def ping_delay(self, value: float) -> None:
        self.state.ping_delay = value
