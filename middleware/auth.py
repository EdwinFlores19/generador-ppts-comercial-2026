import functools
import hmac
import logging

from flask import request, jsonify, current_app

log = logging.getLogger("auth")

_PREFIJO = "Bearer "


def _token_de_la_peticion():
    """
    Extrae el token de la cabecera Authorization exigiendo el esquema Bearer.

    Antes se hacía `header.replace("Bearer ", "")`, que además de no validar el
    esquema sustituye la cadena en cualquier posición: un header sin esquema
    ("Authorization: <token>") o con el prefijo repetido ("Bearer Bearer
    <token>") se daban por buenos. No era explotable —había que conocer el
    token igualmente— pero es laxo y cualquier escáner lo marca.
    """
    cabecera = request.headers.get("Authorization", "")
    if not cabecera.startswith(_PREFIJO):
        return None
    return cabecera[len(_PREFIJO):].strip()


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        api_token = current_app.config.get('API_TOKEN')
        if not api_token:
            # Sin API_TOKEN configurado la autenticación está deshabilitada a
            # propósito (uso local de un solo consultor).
            return f(*args, **kwargs)

        token = _token_de_la_peticion()

        # hmac.compare_digest en vez de '!=': la comparación de cadenas de
        # Python corta en el primer byte distinto, así que el tiempo de
        # respuesta filtra cuántos caracteres del token son correctos y permite
        # reconstruirlo byte a byte.
        if token is None or not hmac.compare_digest(token, api_token):
            # Se registra el intento fallido: sin esto no hay forma de detectar
            # un ataque de fuerza bruta ni de responder a una auditoría sobre
            # accesos no autorizados.
            log.warning("Intento de acceso no autorizado a %s desde %s",
                        request.path, request.remote_addr or 'desconocida')
            return jsonify({'error': 'No autorizado.'}), 401

        return f(*args, **kwargs)
    return wrapper
