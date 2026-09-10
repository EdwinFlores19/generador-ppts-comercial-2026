import functools
import time
import logging
import threading
from flask import request, jsonify, current_app

log = logging.getLogger("rate_limit")

_rate_limit_store: dict[str, list] = {}
_store_lock = threading.Lock()

# Cada cuántos segundos se barre el diccionario completo para expulsar IPs
# inactivas. Sin este barrido el store crece indefinidamente: solo se limpiaban
# las marcas de la IP que hacía la petición, nunca las de visitantes que no
# regresan (fuga de memoria en un proceso de larga vida como el de producción).
_SWEEP_INTERVAL = 300
_last_sweep = 0.0


def _sweep_stale_entries(now, window):
    """Expulsa las IPs sin peticiones dentro de la ventana vigente."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    window_start = now - window
    stale = [ip for ip, hits in _rate_limit_store.items()
             if not any(t > window_start for t in hits)]
    for ip in stale:
        del _rate_limit_store[ip]
    if stale:
        log.debug("Rate limiter: %d IPs inactivas expulsadas del store", len(stale))


def rate_limit(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        window = current_app.config.get('RATE_LIMIT_WINDOW', 60)
        max_requests = current_app.config.get('RATE_LIMIT_MAX', 30)
        client_ip = request.remote_addr or "unknown"
        now = time.time()
        window_start = now - window

        with _store_lock:
            _sweep_stale_entries(now, window)
            recent = [t for t in _rate_limit_store.get(client_ip, []) if t > window_start]
            if len(recent) >= max_requests:
                _rate_limit_store[client_ip] = recent
                log.warning("Rate limit excedido para %s", client_ip)
                return jsonify({'error': 'Demasiadas solicitudes. Intente de nuevo en unos segundos.'}), 429
            recent.append(now)
            _rate_limit_store[client_ip] = recent

        return f(*args, **kwargs)
    return wrapper
