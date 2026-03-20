import uuid
import time
from datetime import datetime, timezone

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_DEVICE_ID", str(uuid.uuid4()))
    monkeypatch.setenv("DEMO_API_KEY", "demo-test-key")

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


def iso_z(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def test_demo_session_scoping_defaults_to_latest_active(client):
    creds_resp_a = client.get("/api/demo/credentials")
    assert creds_resp_a.status_code == 200
    creds_a = creds_resp_a.get_json()
    session_a = creds_a["session_id"]

    headers = {
        "X-Device-Id": creds_a["device_id"],
        "X-API-Key": creds_a["api_key"],
    }

    now_a = datetime.now(timezone.utc)
    ingest_a = client.post(
        "/api/ingest",
        json={
            "session_id": session_a,
            "readings": [{"sensor": "imu_ax", "ts": iso_z(now_a), "value": 1.0}],
        },
        headers=headers,
    )
    assert ingest_a.status_code == 200
    assert ingest_a.get_json()["accepted"] == 1

    read_a_default = client.get("/api/readings", headers=headers)
    assert read_a_default.status_code == 200
    data_a_default = read_a_default.get_json()
    assert data_a_default["session_id"] == session_a
    assert data_a_default["count"] == 1
    assert all(r["session_id"] == session_a for r in data_a_default["readings"])

    creds_resp_b = client.get("/api/demo/credentials")
    assert creds_resp_b.status_code == 200
    creds_b = creds_resp_b.get_json()
    session_b = creds_b["session_id"]
    assert session_b != session_a

    now_b = datetime.now(timezone.utc)
    ingest_b = client.post(
        "/api/ingest",
        json={
            "session_id": session_b,
            "readings": [{"sensor": "imu_ax", "ts": iso_z(now_b), "value": 2.0}],
        },
        headers=headers,
    )
    assert ingest_b.status_code == 200
    assert ingest_b.get_json()["accepted"] == 1

    read_b_default = client.get("/api/readings", headers=headers)
    assert read_b_default.status_code == 200
    data_b_default = read_b_default.get_json()
    assert data_b_default["session_id"] == session_b
    assert data_b_default["count"] == 1
    assert all(r["session_id"] == session_b for r in data_b_default["readings"])
    assert all(r["value"] == 2.0 for r in data_b_default["readings"])

    read_a_explicit = client.get(f"/api/readings?session_id={session_a}", headers=headers)
    assert read_a_explicit.status_code == 200
    data_a_explicit = read_a_explicit.get_json()
    assert data_a_explicit["session_id"] == session_a
    assert data_a_explicit["count"] == 1
    assert all(r["session_id"] == session_a for r in data_a_explicit["readings"])
    assert all(r["value"] == 1.0 for r in data_a_explicit["readings"])


def test_ingest_uses_request_level_session_id_precedence(client):
    creds_resp = client.get("/api/demo/credentials")
    assert creds_resp.status_code == 200
    creds = creds_resp.get_json()
    session_a = creds["session_id"]
    session_b = str(uuid.uuid4())
    session_c = str(uuid.uuid4())

    headers = {
        "X-Device-Id": creds["device_id"],
        "X-API-Key": creds["api_key"],
    }

    now = datetime.now(timezone.utc)
    ingest_resp = client.post(
        "/api/ingest",
        json={
            "session_id": session_a,
            "demo_session_id": session_b,
            "readings": [
                {"sensor": "imu_ax", "ts": iso_z(now), "value": 1.0, "session_id": session_c},
                {"sensor": "imu_ay", "ts": iso_z(now), "value": 2.0, "session_id": session_c},
            ],
        },
        headers=headers,
    )
    assert ingest_resp.status_code == 200
    assert ingest_resp.get_json()["accepted"] == 2

    read_a = client.get(f"/api/readings?session_id={session_a}", headers=headers).get_json()
    read_b = client.get(f"/api/readings?session_id={session_b}", headers=headers).get_json()
    read_c = client.get(f"/api/readings?session_id={session_c}", headers=headers).get_json()

    assert read_a["count"] == 2
    assert all(r["session_id"] == session_a for r in read_a["readings"])
    assert read_b["count"] == 0
    assert read_c["count"] == 0


def test_demo_credentials_rotate_0_does_not_rotate_and_session_endpoint_matches(client):
    creds_rotate = client.get("/api/demo/credentials")
    assert creds_rotate.status_code == 200
    rotated = creds_rotate.get_json()
    session_a = rotated["session_id"]

    creds_no_rotate = client.get("/api/demo/credentials?rotate=0")
    assert creds_no_rotate.status_code == 200
    not_rotated = creds_no_rotate.get_json()
    assert not_rotated["session_id"] == session_a

    headers = {
        "X-Device-Id": rotated["device_id"],
        "X-API-Key": rotated["api_key"],
    }
    session_resp = client.get("/api/demo/session", headers=headers)
    assert session_resp.status_code == 200
    session_data = session_resp.get_json()
    assert session_data["device_id"] == rotated["device_id"]
    assert session_data["session_id"] == session_a


def test_demo_start_stop_generates_data_without_simulator(client):
    creds_resp = client.get("/api/demo/credentials")
    assert creds_resp.status_code == 200
    creds = creds_resp.get_json()
    headers = {
        "X-Device-Id": creds["device_id"],
        "X-API-Key": creds["api_key"],
    }

    start_resp = client.post("/api/demo/start", json={"interval_ms": 500, "sensor": "imu_ax"}, headers=headers)
    assert start_resp.status_code == 200
    start_data = start_resp.get_json()
    session_id = start_data["session_id"]
    assert start_data["status"] == "started"

    time.sleep(1.3)
    read_1 = client.get(f"/api/readings?session_id={session_id}", headers=headers)
    assert read_1.status_code == 200
    count_1 = read_1.get_json()["count"]
    assert count_1 > 0

    stop_resp = client.post("/api/demo/stop", headers=headers)
    assert stop_resp.status_code == 200
    assert stop_resp.get_json()["status"] == "stopped"

    time.sleep(1.2)
    read_2 = client.get(f"/api/readings?session_id={session_id}", headers=headers)
    assert read_2.status_code == 200
    count_2 = read_2.get_json()["count"]

    time.sleep(1.0)
    read_3 = client.get(f"/api/readings?session_id={session_id}", headers=headers)
    assert read_3.status_code == 200
    count_3 = read_3.get_json()["count"]

    assert count_2 == count_3
