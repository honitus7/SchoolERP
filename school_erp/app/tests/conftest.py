from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.services.seed_service import seed_data


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_data()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
