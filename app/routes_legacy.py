from flask import jsonify, request

def register_routes(app):

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.route("/ingest", methods=["POST"])
    def ingest():
        data = request.json
        return jsonify(
            message="Data received",
            payload=data
        ), 201