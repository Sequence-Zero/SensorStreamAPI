import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g, current_app
from ..extensions import db
from ..models import Device
from ..auth import require_device_api_key
from ..demo_stream import start_stream, stop_stream, clamp_interval_ms, ALLOWED_SENSORS

bp = Blueprint("demo", __name__, url_prefix="/api/demo")


@bp.get("/credentials")
def demo_credentials():
    if os.getenv("DEMO_MODE", "0") != "1":
        return jsonify({"error": "demo_disabled"}), 404

    demo_device_id = os.getenv("DEMO_DEVICE_ID")
    demo_api_key = os.getenv("DEMO_API_KEY")
    if not demo_device_id or not demo_api_key:
        return jsonify({"error": "demo_credentials_missing"}), 500

    rotate = (request.args.get("rotate") or "1").strip().lower() not in ("0", "false", "no")

    device = db.session.get(Device, demo_device_id)
    if not device:
        device = Device(id=demo_device_id, name="DemoDevice", api_key_hash="")
        device.set_api_key(demo_api_key)
        db.session.add(device)

    if rotate or not device.active_session_id:
        session_id = str(uuid.uuid4())
        device.active_session_id = session_id
        device.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()
    else:
        session_id = device.active_session_id

    return jsonify({
        "device_id": demo_device_id,
        "api_key": demo_api_key,
        "session_id": session_id,
    }), 200


@bp.get("/session")
@require_device_api_key
def demo_session():
    return jsonify({
        "device_id": g.device.id,
        "session_id": g.device.active_session_id,
    }), 200


@bp.post("/start")
@require_device_api_key
def demo_start():
    payload = request.get_json(silent=True) or {}
    sensor = payload.get("sensor")
    if sensor is not None:
        sensor = str(sensor).strip()
        if sensor not in ALLOWED_SENSORS:
            return jsonify({"error": "invalid_sensor"}), 400

    interval_ms = clamp_interval_ms(payload.get("interval_ms", 1000))

    if not g.device.active_session_id:
        g.device.active_session_id = str(uuid.uuid4())
        db.session.commit()

    state = start_stream(
        current_app._get_current_object(),
        g.device.id,
        g.device.active_session_id,
        interval_ms,
        sensor=sensor,
    )

    return jsonify({
        "status": "started",
        "device_id": g.device.id,
        "session_id": state["session_id"],
        "interval_ms": state["interval_ms"],
    }), 200


@bp.post("/stop")
@require_device_api_key
def demo_stop():
    stop_stream(g.device.id)
    return jsonify({"status": "stopped"}), 200
