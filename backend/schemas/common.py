"""
OrderHub CRM — Common Schemas

Shared schemas for pagination, errors, etc.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 50


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


class ErrorResponse(BaseModel):
    detail: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[dict]
