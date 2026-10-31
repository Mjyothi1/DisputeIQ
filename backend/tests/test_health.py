from collections.abc import Iterator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def _client_with_session(session: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_ok() -> None:
    session = MagicMock()
    for client in _client_with_session(session):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


def test_health_degraded_when_db_down() -> None:
    session = MagicMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
    for client in _client_with_session(session):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded", "database": "down"}


def test_openapi_docs_available() -> None:
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 200
