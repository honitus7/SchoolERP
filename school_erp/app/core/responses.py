from __future__ import annotations

from flask import jsonify


def ok(data=None, meta=None, status=200):
    return jsonify({"data": data, "meta": meta or {}, "error": None}), status


def fail(message: str, status=400, code: str = "bad_request", details=None):
    return (
        jsonify(
            {
                "data": None,
                "meta": {},
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                },
            }
        ),
        status,
    )
