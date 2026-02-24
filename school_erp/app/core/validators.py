from __future__ import annotations

from typing import Iterable


def require_fields(payload: dict, fields: Iterable[str]) -> tuple[bool, list[str]]:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    return len(missing) == 0, missing
