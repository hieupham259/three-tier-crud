from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app
from tests.fakes import FakeClient

# No credentials on purpose: the source gate greps the repository for user:password@ URIs.
TEST_URI = "mongodb://mongodb:27017/cruddb"


@pytest.fixture
def settings() -> Settings:
    return Settings(mongodb_uri=TEST_URI, mongodb_ping_timeout_ms=200, startup_index_timeout_ms=200)


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def client(settings: Settings, fake_client: FakeClient) -> Iterator[TestClient]:
    app = create_app(settings=settings, database=Database(fake_client, settings))
    with TestClient(app) as test_client:  # the context manager runs the lifespan (startup/shutdown)
        yield test_client
