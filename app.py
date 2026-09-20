import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("app")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


# Política de contenido.
#
#   - script-src es 'self' SIN 'unsafe-inline': todo el JavaScript vive en
#     static/*.js. Esto es lo que convierte la CSP en una defensa real contra
#     XSS — con 'unsafe-inline' un script inyectado se ejecutaría igual. Si
#     alguien vuelve a meter un <script> dentro de una plantilla, el navegador
#     lo bloqueará y la página dejará de funcionar: es intencionado.
#   - style-src sí conserva 'unsafe-inline': quedan estilos en línea y varios
#     puntos del JS fijan `element.style`. Un estilo inyectado es un vector
#     mucho más débil que un script, y quitarlo exigiría reescribir el frontend
#     entero sin aportar una defensa comparable.
#   - Font Awesome y Google Fonts se sirven desde CDN, por eso están permitidos.
#   - frame-ancestors 'none' es la defensa contra clickjacking que de verdad
#     respetan los navegadores modernos (X-Frame-Options queda como respaldo).
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def _registrar_cabeceras_seguridad(app):
    """
    Cabeceras de seguridad en todas las respuestas.

    La auditoría encontró que producción no enviaba NINGUNA: sin
    X-Frame-Options la aplicación se podía embeber en un iframe ajeno
    (clickjacking sobre el botón de borrar o el panel de tarifas), y sin
    X-Content-Type-Options el navegador adivinaba el tipo de contenido.
    """
    @app.after_request
    def aplicar_cabeceras(respuesta):
        respuesta.headers.setdefault('Content-Security-Policy', CSP)
        respuesta.headers.setdefault('X-Content-Type-Options', 'nosniff')
        respuesta.headers.setdefault('X-Frame-Options', 'DENY')
        respuesta.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        respuesta.headers.setdefault('Permissions-Policy',
                                     'geolocation=(), microphone=(), camera=(), payment=()')
        respuesta.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        # HSTS solo tiene sentido sobre HTTPS; enviarlo en el servidor de
        # desarrollo (http://127.0.0.1) fijaría el navegador del consultor a
        # HTTPS en localhost y le rompería el entorno local.
        if request.is_secure:
            respuesta.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        # El historial y las propuestas no deben quedar en cachés intermedias.
        if request.path.startswith('/api/') or request.path.startswith('/download/'):
            respuesta.headers.setdefault('Cache-Control', 'no-store')
        return respuesta


def _registrar_manejadores_error(app):
    """
    Respuestas de error coherentes.

    Las rutas de API devolvían la página HTML por defecto de Flask ante un 404
    o un 500, así que un cliente que espera JSON recibía markup. Y el 413 nuevo
    (petición demasiado grande) necesita un mensaje que explique el límite.
    """
    def _es_api():
        return request.path.startswith('/api/') or request.path.startswith('/download/')

    @app.errorhandler(404)
    def no_encontrado(e):
        if _es_api():
            return jsonify({'error': 'Recurso no encontrado.'}), 404
        return e

    @app.errorhandler(413)
    def demasiado_grande(e):
        limite = app.config['MAX_CONTENT_LENGTH'] // 1024
        return jsonify({
            'error': f'La petición supera el tamaño máximo permitido ({limite} KB).'
        }), 413

    @app.errorhandler(429)
    def demasiadas(e):
        return jsonify({'error': 'Demasiadas solicitudes. Intente de nuevo en unos segundos.'}), 429

    @app.errorhandler(500)
    def error_interno(e):
        log.error("Error no controlado en %s", request.path, exc_info=True)
        if _es_api():
            return jsonify({'error': 'Error interno del servidor.'}), 500
        return e


def create_app():
    app = Flask(__name__,
                template_folder=os.path.join(PROJECT_ROOT, 'templates'),
                static_folder=os.path.join(PROJECT_ROOT, 'static'))

    app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
    app.config['API_TOKEN'] = os.getenv("API_TOKEN")
    app.config['RATE_LIMIT_WINDOW'] = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    app.config['RATE_LIMIT_MAX'] = int(os.getenv("RATE_LIMIT_MAX", "30"))
    app.config['DB_NAME'] = os.getenv("DB_NAME", "proposals.db")
    app.config['OUTPUT_DIR'] = os.getenv("OUTPUT_DIR", "generated_decks")

    # Tope del cuerpo de la petición. Sin él, un POST de 12 MB se leía entero en
    # memoria antes de validar nada (comprobado): con 512 MB de RAM en el plan
    # gratuito, unas pocas peticiones así tumban el proceso.
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024)))

    # Endurecido de cookies. Hoy la aplicación no usa sesión, pero dejarlo
    # configurado evita que una sesión añadida mañana nazca insegura.
    app.config['SESSION_COOKIE_SECURE'] = os.getenv("COOKIE_SECURE", "1") == "1"
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Detrás del balanceador de PythonAnywhere, request.remote_addr es su IP
    # interna (comprobado: 10.0.4.129 para todos los clientes), así que el
    # limitador de peticiones metía a TODOS los consultores en el mismo cupo y
    # una sola persona podía dejar fuera al resto.
    #
    # Se corrige con ProxyFix, pero SOLO si se declara cuántos proxies hay
    # delante: confiar en X-Forwarded-For sin saberlo permite falsificar la
    # cabecera y saltarse el límite. En PythonAnywhere el valor es 1.
    proxies = int(os.getenv("TRUST_PROXY_COUNT", "0"))
    if proxies > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies,
                                x_host=proxies, x_prefix=0)
        log.info("  - ProxyFix activo para %d proxy(s): se usa X-Forwarded-For", proxies)
    else:
        log.info("  - ProxyFix desactivado: el límite de peticiones usa la IP directa")

    os.makedirs(app.config['OUTPUT_DIR'], exist_ok=True)

    # Garantiza que el esquema SQLite exista en arranques sobre entornos limpios
    from models.database import init_db
    init_db()

    # CORS(app) a secas abría la API a CUALQUIER origen. Con API_TOKEN vacío
    # —que es el caso por defecto— eso significa que cualquier web que el
    # consultor visite podía leer /api/proposals y llevarse el historial
    # completo de clientes, tarifas y montos. La UI se sirve desde este mismo
    # Flask, así que no necesita CORS: solo se habilita si se declaran orígenes
    # explícitos en CORS_ORIGINS (separados por comas).
    origenes = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if origenes:
        CORS(app, origins=origenes)
        log.info("  - CORS habilitado para: %s", ", ".join(origenes))
    else:
        log.info("  - CORS deshabilitado (solo mismo origen)")

    from routes.main import main_bp
    from routes.proposals import proposals_bp
    from routes.chat import chat_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(chat_bp)

    _registrar_cabeceras_seguridad(app)
    _registrar_manejadores_error(app)

    log.info("Aplicación GROW Deck inicializada correctamente.")
    log.info("  - DB: %s", app.config['DB_NAME'])
    log.info("  - OUTPUT_DIR: %s", app.config['OUTPUT_DIR'])
    log.info("  - Templates: %s", app.template_folder)

    return app


app = create_app()

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, port=5000)
