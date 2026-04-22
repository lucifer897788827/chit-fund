from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    pageSize: int
    totalCount: int
    totalPages: int


@dataclass(frozen=True, slots=True)
class PaginationWindow:
    page: int
    page_size: int


def resolve_pagination(
    page: int | None,
    page_size: int | None,
    *,
    default_page_size: int = 50,
    max_page_size: int = 200,
) -> PaginationWindow | None:
    if page is None and page_size is None:
        return None

    normalized_page = 1 if page is None else max(1, page)
    normalized_page_size = default_page_size if page_size is None else max(1, min(page_size, max_page_size))
    return PaginationWindow(page=normalized_page, page_size=normalized_page_size)


def build_paginated_response(
    items: Sequence[T],
    pagination: PaginationWindow,
    total_count: int,
) -> PaginatedResponse[T]:
    total_pages = math.ceil(total_count / pagination.page_size) if total_count else 0
    return PaginatedResponse[T](
        items=list(items),
        page=pagination.page,
        pageSize=pagination.page_size,
        totalCount=total_count,
        totalPages=total_pages,
    )


def count_statement(db: Session, statement) -> int:
    return int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)


def apply_pagination(statement, pagination: PaginationWindow):
    return statement.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
