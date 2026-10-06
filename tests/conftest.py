import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.seed import ensure_defaults


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        ensure_defaults()
        for username, role in (("admin", "admin"), ("viewer", "viewer")):
            user = User(username=username, email=f"{username}@test.local", role=role)
            user.set_password("password123")
            db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username):
    return client.post("/login", data={"username": username, "password": "password123"}, follow_redirects=True)


@pytest.fixture()
def admin_client(client):
    login(client, "admin")
    return client


@pytest.fixture()
def viewer_client(client):
    login(client, "viewer")
    return client
