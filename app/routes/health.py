from flask import Blueprint, jsonify

bp = Blueprint("health", __name__) #creates blue print with name health

@bp.get("/health") #override notation
def health(): #method for health
    return jsonify({"status": "ok"}) #returns that server is up

#file is here to demonstrate server connectivity 