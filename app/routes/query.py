from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, current_app
from ..models import Reading
from ..auth import require_device_api_key
from sqlalchemy import func
from ..extensions import db

bp = Blueprint("query", __name__, url_prefix="/api")


def parse_ts_param(v: str):
    # Accept ISO-8601, including Z
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clamp_limit(raw: str, default: int = 500, min_v: int = 1, max_v: int = 2000) -> int:
    try:
        n = int(raw)
    except Exception:
        n = default
    return max(min_v, min(n, max_v))
def clamp_offset(raw: str, default: int = 0, min_v: int = 0, max_v: int = 50000) -> int:
    try:
        n = int(raw)
    except Exception:
        n = default
    return max(min_v, min(n, max_v))

@bp.get("/readings")  # GET /api/readings
@require_device_api_key
def get_readings():
    # Authenticated device from g (set by require_device_api_key)
    device_id = g.device.id

    sensor = (request.args.get("sensor") or "").strip()
    requested_session_id = (request.args.get("session_id") or "").strip()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    limit = clamp_limit(request.args.get("limit", "200"), default=200)
    offset = clamp_offset(request.args.get("offset", "0"))
    order = (request.args.get("order") or "desc").strip().lower()
    if order not in ("asc", "desc"):
        return jsonify({"error": "invalid_order"}), 400

    # Parse optional start/end
    start_dt = end_dt = None
    if start:
        try:
            start_dt = parse_ts_param(start)
        except Exception:
            return jsonify({"error": "invalid_start"}), 400

    if end:
        try:
            end_dt = parse_ts_param(end)
        except Exception:
            return jsonify({"error": "invalid_end"}), 400
    if start_dt is not None and end_dt is not None and start_dt > end_dt:
        return jsonify({"error": "start_after_end"}), 400
    # Build query
    q = Reading.query.filter(Reading.device_id == device_id)
    effective_session_id = requested_session_id or g.device.active_session_id
    if requested_session_id:
        q = q.filter(Reading.session_id == requested_session_id)
    elif g.device.active_session_id:
        q = q.filter(Reading.session_id == g.device.active_session_id)

    if sensor:
        q = q.filter(Reading.sensor == sensor)

    if start_dt is not None:
        q = q.filter(Reading.ts >= start_dt)

    if end_dt is not None:
        q = q.filter(Reading.ts <= end_dt)

    # Order + limit
    q = q.order_by(
    Reading.ts.asc() if order == "asc" else Reading.ts.desc()).offset(offset).limit(limit)

    rows = [
        {
            "ts": r.ts.isoformat(),
            "created_at": r.created_at.isoformat(),
            "sensor": r.sensor,
            "value": r.value,
            "session_id": r.session_id,
        }
        for r in q.all()
    ]
    if current_app.config.get("DEBUG_DEMO", False):
        print(
            f"[readings] device={device_id} requested_session={requested_session_id or None} "
            f"active_session={g.device.active_session_id} effective_session={effective_session_id} "
            f"returned={len(rows)}"
        )

    response = {
        "device_id": device_id,
        "sensor": sensor or None,
        "start": start_dt.isoformat() if start_dt else None,
        "end": end_dt.isoformat() if end_dt else None,
        "session_id": effective_session_id,
        "order": order,
        "limit": limit,
        "count": len(rows),
        "readings": rows,
    }
    if current_app.config.get("DEBUG_DEMO", False):
        response["debug"] = {
            "requested_session_id": requested_session_id or None,
            "active_session_id": g.device.active_session_id,
            "effective_session_id": effective_session_id,
            "device_id": g.device.id,
            "returned_count": len(rows),
        }
    return jsonify(response), 200

@bp.get("/sensors")  # GET /api/sensors
@require_device_api_key
def list_sensors():
    device_id = g.device.id

    rows = (
        db.session.query(
            Reading.sensor.label("sensor"),
            func.count(Reading.id).label("count"),
            func.max(Reading.ts).label("last_ts"),
        )
        .filter(Reading.device_id == device_id)
        .group_by(Reading.sensor)
        .order_by(func.count(Reading.id).desc())
        .all()
    )

    sensors = [
        {"sensor": r.sensor, "count": int(r.count), "last_ts": r.last_ts.isoformat() if r.last_ts else None}
        for r in rows
    ]

    return jsonify({"device_id": device_id, "count": len(sensors), "sensors": sensors}), 200
