import uuid
import pytest
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import Device


@pytest.fixture()
def app(tmp_path):
    app = create_app()

    db_path = tmp_path / "test.db"
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    with app.app_context():
        db.drop_all()
        db.create_all()

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_device(app, raw_key="test-device-key", name="Test Device"):
    device_id = str(uuid.uuid4())
    with app.app_context():
        d = Device(id=device_id, name=name, api_key_hash="placeholder")
        d.set_api_key(raw_key)
        db.session.add(d)
        db.session.commit()
    return device_id, raw_key


def iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def test_device_auth_missing_headers(client):
    resp = client.post("/api/ingest", json={"readings": [{"sensor": "imu_ax", "ts": iso_z(datetime.now(timezone.utc)), "value": 1.0}]})
    assert resp.status_code in (401, 403)


def test_device_auth_rejects_bad_key(client, app):
    device_id, _real_key = seed_device(app)

    resp = client.post(
        "/api/ingest",
        json={"readings": [{"sensor": "imu_ax", "ts": iso_z(datetime.now(timezone.utc)), "value": 1.0}]},
        headers={"X-Device-Id": device_id, "X-API-Key": "wrong-key"},
    )
    assert resp.status_code in (401, 403)


def test_device_auth_accepts_valid_key(client, app):
    device_id, api_key = seed_device(app)

    resp = client.post(
        "/api/ingest",
        json={"readings": [{"sensor": "imu_ax", "ts": iso_z(datetime.now(timezone.utc)), "value": 1.0}]},
        headers={"X-Device-Id": device_id, "X-API-Key": api_key},
    )
    assert resp.status_code == 200
