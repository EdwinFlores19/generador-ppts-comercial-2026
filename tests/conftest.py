import os
import shutil
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Los tests no usan mocks: generan PPTX y filas de verdad. Hasta ahora apuntaban
# a proposals.db y generated_decks/ del propio proyecto, así que cada corrida
# dejaba cientos de propuestas basura en el historial del consultor y ~38 MB de
# PPTX por lámina generada (el repo llegó a acumular 913 MB). Se aísla todo en un
# directorio temporal.
#
# Esto tiene que ocurrir ANTES de importar la aplicación: models/database.py y
# services/financial_engine.py leen DB_NAME en tiempo de import, no de llamada.
_TMP_DIR = tempfile.mkdtemp(prefix='seidor-tests-')
os.environ['DB_NAME'] = os.path.join(_TMP_DIR, 'proposals_test.db')
os.environ['OUTPUT_DIR'] = os.path.join(_TMP_DIR, 'decks')
os.makedirs(os.environ['OUTPUT_DIR'], exist_ok=True)


@pytest.fixture(scope='session')
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['RATE_LIMIT_WINDOW'] = 9999
    app.config['RATE_LIMIT_MAX'] = 9999
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True, scope='session')
def setup_db():
    from models.database import init_db
    init_db()
    yield
    # La BBDD y los decks de prueba se van con el directorio temporal. Si el
    # borrado falla (Windows con un handle abierto) no se hace fallar la suite:
    # el sistema operativo limpiará %TEMP% de todos modos.
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
