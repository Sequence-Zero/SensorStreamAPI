import uuid
from datetime import datetime, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import Device, Reading


@pytest.fixture()
def app(tmp_path):
    app = create_app()

    # Override DB to a temporary sqlite file
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


def test_ingest_requires_auth_headers(client):
    resp = client.post("/api/ingest", json={"readings": []})
    assert resp.status_code in (401, 403)


def test_ingest_rejects_invalid_sensor(client, app):
    device_id, api_key = seed_device(app)

    payload = {
        "readings": [
            {"sensor": "not_a_real_sensor", "ts": iso_z(datetime.now(timezone.utc)), "value": 1.0}
        ]
    }
    resp = client.post(
        "/api/ingest",
        json=payload,
        headers={"X-Device-Id": device_id, "X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["accepted"] == 0
    assert data["rejected"] == 1
    assert data["errors"][0]["reason"] == "invalid_sensor"


def test_ingest_accepts_valid_and_persists(client, app):
    device_id, api_key = seed_device(app)

    now = datetime(2026, 1, 21, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "readings": [
            {"sensor": "imu_ax", "ts": iso_z(now), "value": 0.1},
            {"sensor": "imu_ay", "ts": iso_z(now), "value": 0.2},
            {"sensor": "hr_bpm", "ts": iso_z(now), "value": 72},
        ]
    }

    resp = client.post(
        "/api/ingest",
        json=payload,
        headers={"X-Device-Id": device_id, "X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["device_id"] == device_id
    assert data["accepted"] == 3
    assert data["rejected"] == 0

    # Verify DB persistence
    with app.app_context():
        count = Reading.query.filter_by(device_id=device_id).count()
        assert count >= 3


def test_ingest_handles_mixed_batch(client, app):
    device_id, api_key = seed_device(app)

    now = datetime.now(timezone.utc)
    payload = {
        "readings": [
            {"sensor": "imu_ax", "ts": iso_z(now), "value": 0.1},               # valid
            {"sensor": "bad_sensor", "ts": iso_z(now), "value": 0.2},            # invalid sensor
            {"sensor": "imu_ay", "ts": "not-a-timestamp", "value": 0.3},         # invalid ts
            {"sensor": "imu_az", "ts": iso_z(now), "value": "not-a-number"},     # invalid value
        ]
    }

    resp = client.post(
        "/api/ingest",
        json=payload,
        headers={"X-Device-Id": device_id, "X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["accepted"] == 1
    assert data["rejected"] == 3
    assert isinstance(data["errors"], list)
    assert len(data["errors"]) >= 3