import os
import logging
from flask import Flask
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

    os.makedirs(app.config['OUTPUT_DIR'], exist_ok=True)

    CORS(app)

    from routes.main import main_bp
    from routes.proposals import proposals_bp
    from routes.chat import chat_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(chat_bp)

    log.info("Aplicación GROW Deck inicializada correctamente.")
    log.info("  - DB: %s", app.config['DB_NAME'])
    log.info("  - OUTPUT_DIR: %s", app.config['OUTPUT_DIR'])
    log.info("  - Templates: %s", app.template_folder)

    return app


app = create_app()

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, port=5000)
