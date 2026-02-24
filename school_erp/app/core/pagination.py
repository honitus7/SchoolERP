from __future__ import annotations

from flask import request


def parse_pagination(default_per_page: int = 20, max_per_page: int = 100) -> tuple[int, int]:
    page = max(int(request.args.get("page", 1)), 1)
    per_page = max(int(request.args.get("per_page", default_per_page)), 1)
    per_page = min(per_page, max_per_page)
    return page, per_page
