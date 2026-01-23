from flask import Flask #importing flask class to construct app
from .config import Config #pulls in settings
from .extensions import db #imports global SQLalchemy object
from .routes import register_routes #imports register functions for endpoint blueprints
import os
from datetime import datetime, timezone
from .models import Device

def create_app(): 
    app = Flask(__name__) #creating app object
    app.config.from_object(Config) #loads config constraints

    db.init_app(app) #attaches SQLalchemy to Flask instance - connection between app context

    with app.app_context(): #creates table readings 
        db.create_all()

    register_routes(app) #registers all routes blueprints health/ingest/query
    ensure_demo_device(app) 
    return app #returns fully configured app to run.py

def ensure_demo_device(app):
    if os.getenv("DEMO_MODE", "0") != "1":
        return

    demo_device_id = os.getenv("DEMO_DEVICE_ID")
    demo_api_key = os.getenv("DEMO_API_KEY")

    if not demo_device_id or not demo_api_key:
        app.logger.warning("DEMO_MODE=1 but DEMO_DEVICE_ID/DEMO_API_KEY not set. Skipping demo seeding.")
        return

    with app.app_context():
        existing = db.session.get(Device, demo_device_id)
        if existing:
            # Keep the key synced (optional)
            existing.api_key = demo_api_key
            existing.last_seen_at = existing.last_seen_at or datetime.now(timezone.utc)
            db.session.commit()
            app.logger.info(f"Demo device ensured: {demo_device_id}")
            return

        d = Device(id=demo_device_id, name="DemoDevice", api_key_hash="")
        d.set_api_key(demo_api_key)
        db.session.add(d)
        db.session.commit()
        app.logger.info(f"Demo device created: {demo_device_id}")