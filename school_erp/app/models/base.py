from __future__ import annotations

from datetime import datetime

from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class TenantMixin:
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)


class BaseModel(db.Model, TimestampMixin):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
