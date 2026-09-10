# Archivo WSGI de referencia para PythonAnywhere.
# Copiar este contenido en: Web > WSGI configuration file
# (ej. /var/www/consultoredwinflores_pythonanywhere_com_wsgi.py)
#
# Ajustar USERNAME y PROJECT si cambian.

import os
import sys

USERNAME = "ConsultorEdwinFlores"
PROJECT = f"/home/{USERNAME}/generador-ppts-comercial-2026"

# Variables de entorno ANTES de importar la app (financial_engine lee DB_NAME al importar)
os.environ.setdefault("DB_NAME", f"{PROJECT}/proposals.db")
os.environ.setdefault("OUTPUT_DIR", f"{PROJECT}/generated_decks")
# Reducir latencia del scraper: la lista blanca del plan gratuito bloquea DuckDuckGo
os.environ.setdefault("SCRAPER_MAX_RETRIES", "1")

# Cargar .env del proyecto. Variables relevantes:
#   AI_PROVIDER      gemini (default) | groq
#   GEMINI_API_KEY   requerida si AI_PROVIDER=gemini
#   GROQ_API_KEY     requerida si AI_PROVIDER=groq
#   GEMINI_MODEL / GROQ_MODEL  (opcionales, sobreescriben el modelo por defecto)
#   FLASK_SECRET_KEY, API_TOKEN (opcional: si se define, la API exige Bearer token)
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT, ".env"))

if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

os.chdir(PROJECT)

from app import app as application  # noqa: E402
