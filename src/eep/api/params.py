"""Shared request-parameter helpers.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException


def parse_uuid(value: str, what: str = "identifier") -> uuid.UUID:
    """Parse a path parameter into a UUID; 404 on invalid input."""
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Invalid {what}") from exc
