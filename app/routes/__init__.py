from .devices import bp as devices_bp
from .ingest import bp as ingest_bp
from .query import bp as query_bp
from .health import bp as health_bp
from .demo import bp as demo_bp

def register_routes(app): #method to route blue prints to app
    app.register_blueprint(devices_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(query_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(demo_bp)
    if app.config.get("DEBUG_DEMO", False):
        from .debug import bp as debug_bp
        app.register_blueprint(debug_bp)

    #file purpose: gather route blueprints and attach them to the app
