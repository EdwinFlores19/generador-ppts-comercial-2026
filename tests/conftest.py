import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


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
