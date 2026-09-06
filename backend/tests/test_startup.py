from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo import ASCENDING

from app.config import Settings
from app.db import ID_INDEX_NAME, Database
from app.main import create_app
from tests.fakes import FakeClient


def _app(settings: Settings, fake_client: FakeClient) -> FastAPI:
    return create_app(settings=settings, database=Database(fake_client, settings))


def test_startup_creates_unique_index_on_id(client: TestClient, fake_client: FakeClient) -> None:
    assert fake_client.collection.indexes == {
        ID_INDEX_NAME: {"keys": [("id", ASCENDING)], "unique": True}
    }


def test_index_creation_is_idempotent_across_restarts(
    settings: Settings, fake_client: FakeClient
) -> None:
    with TestClient(_app(settings, fake_client)) as first:
        first.get("/api/health/ready")  # readiness must not re-create an index already ensured
    with TestClient(_app(settings, fake_client)):
        pass  # second process (restart or second replica) against the same collection

    assert list(fake_client.collection.indexes) == [ID_INDEX_NAME]
    assert len(fake_client.state.index_calls) == 2


def test_startup_survives_mongodb_down_and_recovers(
    settings: Settings, fake_client: FakeClient
) -> None:
    fake_client.down = True
    with TestClient(_app(settings, fake_client)) as client:
        assert client.get("/api/health/live").status_code == 200
        assert client.get("/api/health/ready").status_code == 503
        assert ID_INDEX_NAME not in fake_client.collection.indexes

        fake_client.down = False
        assert client.get("/api/health/ready").status_code == 200
        assert fake_client.collection.indexes[ID_INDEX_NAME]["unique"] is True


def test_shutdown_closes_mongodb_client(settings: Settings, fake_client: FakeClient) -> None:
    with TestClient(_app(settings, fake_client)):
        assert fake_client.closed is False
    assert fake_client.closed is True


def test_startup_log_never_contains_credentials(
    fake_client: FakeClient, caplog: pytest.LogCaptureFixture
) -> None:
    # Built by concatenation so the repository never contains a literal user:password@ URI.
    uri = "mongodb://" + "crudapp:" + "s3cret%40pw" + "@mongodb:27017/cruddb?authSource=cruddb"
    settings = Settings(mongodb_uri=uri, mongodb_ping_timeout_ms=200, startup_index_timeout_ms=200)
    caplog.set_level(logging.INFO, logger="app")

    with TestClient(_app(settings, fake_client)):
        pass

    assert "s3cret" not in caplog.text
    assert "crudapp" not in caplog.text
    assert "mongodb://mongodb:27017/cruddb" in caplog.text
