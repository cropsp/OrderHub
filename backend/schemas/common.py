"""
OrderHub CRM — Common Schemas

Shared schemas for pagination, errors, etc.
"""

from pydantic import BaseModel


class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 50


class PaginatedResponse(BaseModel):
    items: list
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
