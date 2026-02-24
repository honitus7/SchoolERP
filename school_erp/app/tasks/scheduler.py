from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask


scheduler = BackgroundScheduler(daemon=True)


def _backup_sqlite(app: Flask) -> None:
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        return

    db_path = Path(db_uri.replace("sqlite:///", ""))
    if not db_path.exists():
        return

    backup_dir = Path(app.root_path).parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"erp_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)


def init_scheduler(app: Flask) -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        func=lambda: _backup_sqlite(app),
        trigger="cron",
        hour=2,
        minute=0,
        id="nightly_sqlite_backup",
        replace_existing=True,
    )
    scheduler.start()
