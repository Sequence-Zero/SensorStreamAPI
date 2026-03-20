from functools import wraps
from flask import request, jsonify, g 
from .models import Device #imports SQLAlchemy model class, used to query the db for the row
from datetime import datetime, timezone #imports datetime.now() and a timezone constant
from .extensions import db #imports the SQLAlchemy manager object, which owns db.session
#request the current HTTP request object
#jsonify is a helper that returns a Flask response w/ JSON
#g is a special per request storage object

def require_admin(config): #Defines a function that takes config and returns another fn ( a decorator)
    def decorator(fn): #defines the deco that receives a function and returns a wrapped function
        @wraps(fn) #applies wraps to the wrapper function defined next
        def wrapper(*args, **kwargs): #defines a new function which accepts any positiona;/keyword arguments
            resolved_config = config() if callable(config) else config
            token = request.headers.get("X-Admin-Token", "") #reads a header request, if missing - returns empty string
            if token != resolved_config["ADMIN_TOKEN"]: #checking token against admin token in config
                return jsonify({"error": "admin_required"}), 403
            return fn(*args, **kwargs) #returns the original route function which was wrapped
        return wrapper #decorator returns the wrapper function
    return decorator #require_admin(config) returns the decoratror

def require_device_api_key(fn): #defines a normal decorator, not a factory
    @wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "") #reads api key header (device password)
        device_id = request.headers.get("X-Device-Id", "") #device id feeds to

        if not api_key or not device_id:
            return jsonify({"error": "missing_device_auth_headers"}), 401

        device = db.session.get(Device, device_id) #this method which runs a query using device id
        if not device or not device.check_api_key(api_key): #check api key and device match
            return jsonify({"error": "invalid_device_credentials"}), 401

        # update last seen
        device.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()

        g.device = device #Sets an attribute on the Flask g object, g is unique per request
        #lets downstream route handlers access the authenticated device without querying again
        return fn(*args, **kwargs) #calls the original protected endpoint now that auth passed
    return wrapper
