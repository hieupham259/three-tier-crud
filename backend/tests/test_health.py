from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.fakes import FakeClient


def test_live_returns_200(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_ready_returns_200_when_mongodb_answers(client: TestClient) -> None:
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mongodb": "ready"}


def test_live_never_calls_mongodb(client: TestClient, fake_client: FakeClient) -> None:
    assert fake_client.state.admin_calls == 0
    client.get("/api/health/live")
    assert fake_client.state.admin_calls == 0
    client.get("/api/health/ready")
    assert fake_client.state.admin_calls == 1


def test_mongodb_down_live_stays_200_but_ready_is_503(
    client: TestClient, fake_client: FakeClient
) -> None:
    fake_client.down = True

    assert client.get("/api/health/live").status_code == 200
    ready = client.get("/api/health/ready")
    assert ready.status_code == 503
    assert ready.json() == {"detail": "MongoDB is not ready"}
    assert client.get("/api/health/live").status_code == 200


def test_ready_fails_fast_when_ping_hangs(client: TestClient, fake_client: FakeClient) -> None:
    fake_client.ping_delay = 5.0  # ping timeout in the test settings is 200 ms

    started = time.monotonic()
    response = client.get("/api/health/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert elapsed < 3.0


def test_crud_returns_503_when_mongodb_down(client: TestClient, fake_client: FakeClient) -> None:
    fake_client.down = True
    assert client.get("/api/items").status_code == 503
    created = client.post("/api/items", json={"id": "x1", "name": "X"})
    assert created.status_code == 503
    assert created.json() == {"detail": "database unavailable"}
