from __future__ import annotations

from typing import Any

from app.extensions import db


class BaseRepository:
    def __init__(self, model):
        self.model = model

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        db.session.add(obj)
        db.session.commit()
        return obj

    def get(self, obj_id: int):
        return self.model.query.get(obj_id)

    def list(self, **filters):
        query = self.model.query
        for key, value in filters.items():
            query = query.filter(getattr(self.model, key) == value)
        return query.all()

    def update(self, obj_id: int, data: dict[str, Any]):
        obj = self.model.query.get(obj_id)
        if not obj:
            return None
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        db.session.commit()
        return obj
