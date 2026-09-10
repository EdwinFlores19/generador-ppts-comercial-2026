import sqlite3
import os
from contextlib import closing
import logging

log = logging.getLogger("database")

DB_NAME = os.getenv("DB_NAME", "proposals.db")


DB_TIMEOUT = float(os.getenv("DB_TIMEOUT", "15"))


def get_db_connection():
    """
    Abre una conexión SQLite endurecida para uso concurrente:
    - timeout: espera a que se libere el lock en vez de fallar de inmediato.
    - journal_mode=WAL: los lectores no bloquean al escritor ni viceversa,
      clave porque la generación del PPTX mantiene la petición viva varios
      segundos antes de escribir en la tabla proposals.
    - busy_timeout: reintento a nivel de motor ante lock contention.
    - foreign_keys=ON: SQLite las ignora por defecto y chat_sessions declara
      una FK hacia proposals(id).
    """
    conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=%d" % int(DB_TIMEOUT * 1000))
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as e:
        log.warning("No se pudieron aplicar los PRAGMA de robustez SQLite: %s", e)
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

            cursor.execute("PRAGMA table_info(proposals)")
            proposal_cols = {row[1] for row in cursor.fetchall()}
            if 'edition' not in proposal_cols:
                cursor.execute("ALTER TABLE proposals ADD COLUMN edition TEXT DEFAULT 'Public'")

            default_params = [
                ('tarifa_hora_consultor', 60.0, 'Tarifa por hora del consultor SAP en USD'),
                ('porcentaje_ams', 0.15, 'Porcentaje de soporte AMS anual'),
                ('margen_saas', 0.20, 'Margen de recargo sobre licencias SaaS'),
                ('anos_roi', 5, 'Número de años para proyección de ROI'),
                ('factor_igv', 0.18, 'Factor de IGV peruano (0.18 = 18%)'),
                ('tipo_cambio_pen', 3.78, 'Tipo de cambio USD a PEN'),
                ('factor_ahorro', 0.015, 'Ahorro anual estimado como % de la facturación (0.015 = 1.5%)'),
            ]
            for param, valor, desc in default_params:
                cursor.execute("""
                    INSERT OR IGNORE INTO configuracion_comercial (parametro, valor, descripcion)
                    VALUES (?, ?, ?)
                """, (param, valor, desc))

            # Índices para el ORDER BY de los listados paginados. Sin ellos
            # SQLite recorre y ordena la tabla entera en cada página, aunque
            # solo se devuelvan 50 filas.
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposals_creadas
                ON proposals (created_at DESC, id DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_actualizadas
                ON chat_sessions (updated_at DESC, id DESC)
            """)

    log.info("Base de datos inicializada correctamente: %s", DB_NAME)
