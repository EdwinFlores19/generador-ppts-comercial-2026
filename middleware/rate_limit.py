import functools
import time
import logging
from flask import request, jsonify, current_app

log = logging.getLogger("rate_limit")

_rate_limit_store: dict[str, list] = {}


def rate_limit(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        window = current_app.config.get('RATE_LIMIT_WINDOW', 60)
        max_requests = current_app.config.get('RATE_LIMIT_MAX', 30)
        client_ip = request.remote_addr or "unknown"
        now = time.time()
        window_start = now - window
        _rate_limit_store[client_ip] = [
            t for t in _rate_limit_store.get(client_ip, []) if t > window_start
        ]
        if len(_rate_limit_store[client_ip]) >= max_requests:
            log.warning("Rate limit excedido para %s", client_ip)
            return jsonify({'error': 'Demasiadas solicitudes. Intente de nuevo en unos segundos.'}), 429
        _rate_limit_store[client_ip].append(now)
        return f(*args, **kwargs)
    return wrapper
