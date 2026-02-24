from __future__ import annotations

from passlib.hash import argon2

from app.extensions import db
from app.models.base import BaseModel, TimestampMixin


class Tenant(BaseModel):
    __tablename__ = "tenants"

    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(64), unique=True, nullable=False)


class Role(BaseModel):
    __tablename__ = "roles"

    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)


class Permission(BaseModel):
    __tablename__ = "permissions"

    key = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)


class UserRole(TimestampMixin, db.Model):
    __tablename__ = "user_roles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "role_id", name="uq_user_role"),)


class User(BaseModel):
    __tablename__ = "users"

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship("Tenant", backref="users")
    roles = db.relationship("Role", secondary="user_roles", backref="users", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "username", name="uq_user_username_per_tenant"),
        db.UniqueConstraint("tenant_id", "email", name="uq_user_email_per_tenant"),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = argon2.hash(password)

    def check_password(self, password: str) -> bool:
        return argon2.verify(password, self.password_hash)

    def has_role(self, role: str) -> bool:
        return any(r.name.lower() == role.lower() for r in self.roles)


class SessionModel(BaseModel):
    __tablename__ = "sessions"

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)

    user = db.relationship("User", backref="sessions")
