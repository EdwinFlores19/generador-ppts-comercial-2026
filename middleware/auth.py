import functools
from flask import request, jsonify, current_app


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        api_token = current_app.config.get('API_TOKEN')
        if api_token:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if token != api_token:
                return jsonify({'error': 'No autorizado.'}), 401
        return f(*args, **kwargs)
    return wrapper
