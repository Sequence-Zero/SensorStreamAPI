from flask import Blueprint, jsonify, g
from ..auth import require_device_api_key

bp = Blueprint("debug", __name__, url_prefix="/api/debug")


@bp.get("/whoami")
@require_device_api_key
def whoami():
    return jsonify({
        "device_id": g.device.id,
        "active_session_id": g.device.active_session_id,
        "last_seen_at": g.device.last_seen_at.isoformat() if g.device.last_seen_at else None,
    }), 200
