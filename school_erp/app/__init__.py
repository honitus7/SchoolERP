from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from flask import Flask
from sqlalchemy import event

from app.config import config_by_name
from app.extensions import csrf, db, jwt, limiter, migrate


def _resolve_database_uri(uri: str, testing: bool = False) -> str:
    if testing:
        return uri

    if uri.startswith("sqlitecloud://"):
        parsed = urlparse(uri)
        if parsed.path in ("", "/"):
            db_name = (os.getenv("SQLITECLOUD_DB") or "").strip()
            if not db_name:
                raise RuntimeError(
                    "SQLite Cloud URL is missing database name. "
                    "Set DATABASE_URL like sqlitecloud://host:port/yourdb.sqlite?apikey=... "
                    "or set SQLITECLOUD_DB."
                )
            parsed = parsed._replace(path=f"/{db_name.lstrip('/')}")
            return urlunparse(parsed)

    return uri


def _apply_sqlite_pragmas(app: Flask) -> None:
    @event.listens_for(db.engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    env_name = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(config_by_name.get(env_name, config_by_name["development"]))
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri(
        app.config["SQLALCHEMY_DATABASE_URI"],
        testing=bool(app.config.get("TESTING")),
    )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401
        from app.blueprints import register_blueprints
        from app.core.auth import current_user
        from app.tasks.scheduler import init_scheduler

        Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

        _apply_sqlite_pragmas(app)
        db.create_all()
        register_blueprints(app)
        if not app.config.get("TESTING"):
            init_scheduler(app)
        _register_cli(app)

        @app.context_processor
        def inject_user_context():
            user = current_user()
            role = user.roles[0].name.lower() if user and user.roles else "admin"
            return {"current_user": user, "current_role": role}

    return app


def _register_cli(app: Flask) -> None:
    from app.services.seed_service import seed_data

    @app.cli.command("seed")
    def seed_command() -> None:
        """Seed base tenant, roles, users, and sample data."""
        seed_data()
        print("Seed complete.")
