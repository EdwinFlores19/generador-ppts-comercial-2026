import sqlite3
import os
from contextlib import closing
import logging

log = logging.getLogger("database")

DB_NAME = os.getenv("DB_NAME", "proposals.db")


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT,
                    complexity TEXT,
                    sector TEXT,
                    description TEXT,
                    active_modules TEXT,
                    total_weeks REAL,
                    total_hours REAL,
                    consulting_cost REAL,
                    licensing_cost REAL,
                    support_cost REAL,
                    total_investment REAL,
                    savings_annual REAL,
                    roi_five_years REAL,
                    payback_period REAL,
                    ppt_path TEXT,
                    preview_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracion_comercial (
                    parametro TEXT PRIMARY KEY,
                    valor REAL,
                    descripcion TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT DEFAULT 'Nueva Conversación',
                    messages TEXT DEFAULT '[]',
                    proposal_data TEXT,
                    proposal_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
                )
            """)

            cursor.execute("PRAGMA table_info(chat_sessions)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            migration_cols = {
                'proposal_data': "ALTER TABLE chat_sessions ADD COLUMN proposal_data TEXT",
                'proposal_id': "ALTER TABLE chat_sessions ADD COLUMN proposal_id INTEGER REFERENCES proposals(id)",
            }
            for col, alter_sql in migration_cols.items():
                if col not in existing_cols:
                    cursor.execute(alter_sql)

            default_params = [
                ('tarifa_hora_consultor', 60.0, 'Tarifa por hora del consultor SAP en USD'),
                ('porcentaje_ams', 0.15, 'Porcentaje de soporte AMS anual'),
                ('margen_saas', 0.20, 'Margen de recargo sobre licencias SaaS'),
                ('anos_roi', 5, 'Número de años para proyección de ROI'),
                ('factor_igv', 0.18, 'Factor de IGV peruano (0.18 = 18%)'),
                ('tipo_cambio_pen', 3.78, 'Tipo de cambio USD a PEN'),
            ]
            for param, valor, desc in default_params:
                cursor.execute("""
                    INSERT OR IGNORE INTO configuracion_comercial (parametro, valor, descripcion)
                    VALUES (?, ?, ?)
                """, (param, valor, desc))

    log.info("Base de datos inicializada correctamente: %s", DB_NAME)
