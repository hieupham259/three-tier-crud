"""CRUD endpoints for items (contract: runbook-k8s-vmware-phase2.md, section 4.2)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pymongo.errors import DuplicateKeyError

from ..db import ItemStore
from ..models import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, Item, ItemCreate, ItemPage, ItemUpdate

router = APIRouter(prefix="/api/items", tags=["items"])


def _store(request: Request) -> ItemStore:
    return request.app.state.db.items


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Item)
async def create_item(payload: ItemCreate, request: Request) -> Any:
    try:
        return await _store(request).insert(payload.model_dump())
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="item with this id already exists"
        ) from None


@router.get("", response_model=ItemPage)
async def list_items(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
) -> Any:
    documents, total = await _store(request).list_page(page, page_size)
    return {"items": documents, "page": page, "page_size": page_size, "total": total}


@router.get("/{item_id}", response_model=Item)
async def get_item(item_id: str, request: Request) -> Any:
    document = await _store(request).get(item_id)
    if document is None:
        raise _not_found()
    return document


@router.put("/{item_id}", response_model=Item)
async def update_item(item_id: str, payload: ItemUpdate, request: Request) -> Any:
    document = await _store(request).update(item_id, payload.model_dump())
    if document is None:
        raise _not_found()
    return document


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_item(item_id: str, request: Request) -> Response:
    if not await _store(request).delete(item_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
