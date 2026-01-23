import uuid
import secrets
from flask import Blueprint, request, jsonify, current_app
from ..extensions import db
from ..models import Device
from ..auth import require_admin

bp = Blueprint("devices", __name__, url_prefix="/api/devices")

@bp.post("")
@require_admin(lambda: current_app.config)
def create_device():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400

    device_id = str(uuid.uuid4())
    raw_api_key = secrets.token_urlsafe(32)

    device = Device(id=device_id, name=name, api_key_hash="temp")
    device.set_api_key(raw_api_key)

    db.session.add(device)
    db.session.commit()

    # Only return the raw key ONCE
    return jsonify({"device_id": device_id, "api_key": raw_api_key}), 201

@bp.get("/<device_id>")
def get_device(device_id: str):
    device = Device.query.get(device_id)
    if not device:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "device_id": device.id,
        "name": device.name,
        "created_at": device.created_at.isoformat(),
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None
    })