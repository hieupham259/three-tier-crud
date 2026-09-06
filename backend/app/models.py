"""Request/response schemas and validation limits for the items API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

ID_MAX_LENGTH = 64
NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 500
# URL-safe identifiers only: letters, digits, dot, underscore, tilde, hyphen; no leading punctuation.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._~-]*$"
PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100

ItemId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=ID_MAX_LENGTH, pattern=ID_PATTERN
    ),
]
ItemName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
]
ItemDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH)
]


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ItemId
    name: ItemName
    description: ItemDescription = ""


class ItemUpdate(BaseModel):
    """PUT payload. ``id`` is deliberately absent: the identifier is immutable."""

    model_config = ConfigDict(extra="forbid")

    name: ItemName
    description: ItemDescription = ""


class Item(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class ItemPage(BaseModel):
    items: list[Item]
    page: int
    page_size: int
    total: int
