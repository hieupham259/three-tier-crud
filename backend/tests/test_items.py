from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models import DESCRIPTION_MAX_LENGTH, ID_MAX_LENGTH, NAME_MAX_LENGTH

ITEM = {"id": "phase2-smoke-001", "name": "Keyboard", "description": "Mechanical keyboard"}


def _create(client: TestClient, **overrides: object):
    return client.post("/api/items", json={**ITEM, **overrides})


# --- create -----------------------------------------------------------------------------------


def test_create_returns_201_with_timestamps(client: TestClient) -> None:
    response = _create(client)
    assert response.status_code == 201
    body = response.json()
    assert {key: body[key] for key in ("id", "name", "description")} == ITEM
    assert body["created_at"] == body["updated_at"]
    assert body["created_at"].endswith(("Z", "+00:00"))  # ISO-8601, UTC
    datetime.fromisoformat(body["created_at"])
    assert "_id" not in body


def test_create_duplicate_returns_409(client: TestClient) -> None:
    assert _create(client).status_code == 201
    duplicate = _create(client, name="Other name")
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "item with this id already exists"}


def test_create_strips_whitespace_and_defaults_description(client: TestClient) -> None:
    response = client.post("/api/items", json={"id": "  spaced-1  ", "name": "  Padded  "})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "spaced-1"
    assert body["name"] == "Padded"
    assert body["description"] == ""


def test_create_accepts_maximum_lengths(client: TestClient) -> None:
    response = _create(
        client,
        id="a" * ID_MAX_LENGTH,
        name="n" * NAME_MAX_LENGTH,
        description="d" * DESCRIPTION_MAX_LENGTH,
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"name": "no id"}, id="missing-id"),
        pytest.param({"id": "", "name": "empty id"}, id="empty-id"),
        pytest.param({"id": "   ", "name": "blank id"}, id="blank-id"),
        pytest.param({"id": "a" * (ID_MAX_LENGTH + 1), "name": "too long"}, id="id-too-long"),
        pytest.param({"id": "bad id", "name": "space"}, id="id-with-space"),
        pytest.param({"id": "../etc", "name": "traversal"}, id="id-with-slash"),
        pytest.param({"id": "-leading", "name": "punct"}, id="id-leading-punctuation"),
        pytest.param({"id": "ok-1"}, id="missing-name"),
        pytest.param({"id": "ok-1", "name": ""}, id="empty-name"),
        pytest.param({"id": "ok-1", "name": "   "}, id="blank-name"),
        pytest.param({"id": "ok-1", "name": "n" * (NAME_MAX_LENGTH + 1)}, id="name-too-long"),
        pytest.param(
            {"id": "ok-1", "name": "ok", "description": "d" * (DESCRIPTION_MAX_LENGTH + 1)},
            id="description-too-long",
        ),
        pytest.param({"id": "ok-1", "name": "ok", "extra": "field"}, id="unknown-field"),
        pytest.param({"id": 123, "name": "ok"}, id="id-not-string"),
    ],
)
def test_create_rejects_invalid_payload_with_422(client: TestClient, payload: dict) -> None:
    response = client.post("/api/items", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get("/api/items").json()["total"] == 0


# --- read -------------------------------------------------------------------------------------


def test_get_returns_item_or_404(client: TestClient) -> None:
    assert client.get("/api/items/phase2-smoke-001").status_code == 404
    _create(client)
    response = client.get("/api/items/phase2-smoke-001")
    assert response.status_code == 200
    assert response.json()["name"] == "Keyboard"


def test_get_unknown_returns_404_detail(client: TestClient) -> None:
    response = client.get("/api/items/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "item not found"}


def test_list_paginates(client: TestClient) -> None:
    for suffix in ("a", "b", "c"):
        assert _create(client, id=f"item-{suffix}").status_code == 201

    first = client.get("/api/items", params={"page": 1, "page_size": 2})
    second = client.get("/api/items", params={"page": 2, "page_size": 2})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["total"] == 3 and second.json()["total"] == 3
    assert first.json()["page"] == 1 and first.json()["page_size"] == 2
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1
    seen = {item["id"] for item in first.json()["items"] + second.json()["items"]}
    assert seen == {"item-a", "item-b", "item-c"}


def test_list_defaults(client: TestClient) -> None:
    response = client.get("/api/items")
    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}]
)
def test_list_rejects_invalid_pagination(client: TestClient, params: dict) -> None:
    assert client.get("/api/items", params=params).status_code == 422


# --- update -----------------------------------------------------------------------------------


def test_update_changes_name_and_description_but_not_id(client: TestClient) -> None:
    created = _create(client).json()
    response = client.put(
        "/api/items/phase2-smoke-001", json={"name": "Keyboard v2", "description": "Updated"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "phase2-smoke-001"
    assert body["name"] == "Keyboard v2"
    assert body["description"] == "Updated"
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] >= created["updated_at"]
    assert client.get("/api/items/phase2-smoke-001").json()["name"] == "Keyboard v2"


def test_update_unknown_returns_404(client: TestClient) -> None:
    response = client.put("/api/items/missing", json={"name": "x", "description": ""})
    assert response.status_code == 404


def test_update_rejects_id_in_body(client: TestClient) -> None:
    _create(client)
    response = client.put(
        "/api/items/phase2-smoke-001", json={"id": "other", "name": "x", "description": ""}
    )
    assert response.status_code == 422
    assert client.get("/api/items/phase2-smoke-001").json()["name"] == "Keyboard"


def test_update_validates_fields(client: TestClient) -> None:
    _create(client)
    assert client.put("/api/items/phase2-smoke-001", json={"name": ""}).status_code == 422
    too_long = {"name": "n" * (NAME_MAX_LENGTH + 1)}
    assert client.put("/api/items/phase2-smoke-001", json=too_long).status_code == 422


# --- delete -----------------------------------------------------------------------------------


def test_delete_returns_204_then_404(client: TestClient) -> None:
    _create(client)
    response = client.delete("/api/items/phase2-smoke-001")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/items/phase2-smoke-001").status_code == 404
    assert client.delete("/api/items/phase2-smoke-001").status_code == 404
    assert client.get("/api/items").json()["total"] == 0


def test_id_can_be_reused_after_delete(client: TestClient) -> None:
    _create(client)
    client.delete("/api/items/phase2-smoke-001")
    assert _create(client).status_code == 201
