from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, current_app
from ..extensions import db
from ..models import Reading
from ..auth import require_device_api_key

bp = Blueprint("ingest", __name__, url_prefix="/api")

ALLOWED_SENSORS = {
    # IMU-like
    "imu_ax", "imu_ay", "imu_az",
    "imu_gx", "imu_gy", "imu_gz",
    # EMG-like
    "emg_ch1", "emg_ch2", "emg_ch3", "emg_ch4",
    # Optional pressure/heart
    "pressure_kpa", "hr_bpm"
}

def parse_ts(ts_str: str): #formatting timezone data
    # Accept ISO-8601, including Z
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), None
    except Exception:
        return None, "invalid_timestamp"

@bp.post("/ingest")
@require_device_api_key #running device verification and initializing g.device
def ingest(): #defining ingest method
    payload = request.get_json(silent=True) or {}
    readings = payload.get("readings")
    payload_session_id = payload.get("session_id")
    payload_demo_session_id = payload.get("demo_session_id")
    payload_debug_session_id = payload_session_id or payload_demo_session_id
    if payload_session_id is not None and not isinstance(payload_session_id, str):
        return jsonify({"error": "session_id_must_be_string"}), 400
    if payload_demo_session_id is not None and not isinstance(payload_demo_session_id, str):
        return jsonify({"error": "demo_session_id_must_be_string"}), 400

    if not isinstance(readings, list) or len(readings) == 0:
        return jsonify({"error": "readings_list_required"}), 400 #fails to initialize empty data

    # Resolve exactly one session for the full request:
    # A) session_id, B) demo_session_id, C) device.active_session_id, D) None.
    resolved_session_id = payload_session_id or payload_demo_session_id or g.device.active_session_id

    accepted = 0
    rejected = 0
    errors = []

    for i, r in enumerate(readings):
        if not isinstance(r, dict): #if not valid reading
            rejected += 1 #increment rejected count
            errors.append({"index": i, "reason": "reading_must_be_object"})
            continue

        sensor = (r.get("sensor") or "").strip()
        ts_raw = r.get("ts")
        value = r.get("value")

        if sensor not in ALLOWED_SENSORS:
            rejected += 1
            errors.append({"index": i, "reason": "invalid_sensor"})
            continue

        if not isinstance(ts_raw, str):
            rejected += 1
            errors.append({"index": i, "reason": "ts_must_be_string"})
            continue

        ts, err = parse_ts(ts_raw)
        if err:
            rejected += 1
            errors.append({"index": i, "reason": err})
            continue

        try:
            value_f = float(value)
        except Exception:
            rejected += 1
            errors.append({"index": i, "reason": "value_must_be_number"}) #input validation
            continue

        db.session.add(Reading( #if none of the failure conditions have been met
            device_id=g.device.id, #reads device id
            sensor=sensor, #reads sensor type
            ts=ts, #reads local timezone timestamp
            value=value_f, #reads sensor value
            session_id=resolved_session_id,
            created_at=datetime.utcnow()
        ))
        accepted += 1

    db.session.commit()
    if current_app.config.get("DEBUG_DEMO", False):
        print(
            f"[ingest] device={g.device.id} payload_session={payload_debug_session_id} "
            f"active_session={g.device.active_session_id} resolved_session={resolved_session_id} "
            f"accepted={accepted} rejected={rejected}"
        )

    response = {
        "device_id": g.device.id,
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors[:25],  # cap
    }
    if current_app.config.get("DEBUG_DEMO", False):
        response["debug"] = {
            "payload_session_id": payload_debug_session_id,
            "active_session_id": g.device.active_session_id,
            "resolved_session_id": resolved_session_id,
            "device_id": g.device.id,
            "accepted": accepted,
            "rejected": rejected,
        }
    return jsonify(response), 200
