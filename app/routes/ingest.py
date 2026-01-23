from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
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

    if not isinstance(readings, list) or len(readings) == 0:
        return jsonify({"error": "readings_list_required"}), 400 #fails to initialize empty data

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
            value=value_f #reads sensor value
        ))
        accepted += 1

    db.session.commit()
    return jsonify({
        "device_id": g.device.id,
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors[:25]  # cap
    }), 200