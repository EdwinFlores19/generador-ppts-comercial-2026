import sqlite3
import os

DB_NAME = "proposals.db"

def init_db():
    """
    Inicializa la base de datos relacional SQLite de la suite 'Grow Deck Automator'.
    Crea las tablas 'proposals' para almacenar el histórico de propuestas generadas
    y 'configuracion_comercial' para los parámetros financieros de preventa.
    Realiza migraciones si es necesario.
    """
    print(f"Inicializando la base de datos: {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Crear tabla de propuestas conteniendo todos los datos comerciales e históricos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        complexity TEXT NOT NULL,
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
        preview_json TEXT,  -- Columna para previsualización estructurada en JSON
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Ejecutar migración para bases de datos existentes sin la columna 'preview_json'
    try:
        cursor.execute("PRAGMA table_info(proposals)")
        columns = [col[1] for col in cursor.fetchall()]
        if columns and "preview_json" not in columns:
            print("Migrando tabla 'proposals' para agregar columna 'preview_json'...")
            cursor.execute("ALTER TABLE proposals ADD COLUMN preview_json TEXT")
    except Exception as migration_err:
        print(f"Advertencia durante migración de columnas: {migration_err}")
    
    # Crear tabla de configuración comercial para ajustes de tarifas en tiempo real
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_comercial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parametro TEXT UNIQUE NOT NULL,
        valor REAL NOT NULL,
        descripcion TEXT
    )
    """)
    
    # Insertar parámetros de preventa por defecto
    parametros_defecto = [
        ("tarifa_hora_consultor", 60.00, "Tarifa horaria promedio en USD de consultores SAP en Perú"),
        ("porcentaje_ams", 0.15, "Porcentaje anual (como fracción) para soporte post go-live (AMS)"),
        ("margen_saas", 0.20, "Porcentaje de margen / recargo (como fracción) aplicado a licencias de nube"),
        ("anos_roi", 5.0, "Número de años proyectados para estimar TCO, ahorros y ROI de la propuesta"),
        ("factor_igv", 0.18, "Factor del Impuesto General a las Ventas (IGV) en el Perú (ej: 0.18)"),
        ("tipo_cambio_pen", 3.78, "Tipo de cambio oficial de Dólar a Soles Peruanos (USD a PEN) (ej: 3.78)")
    ]
    
    for parametro, valor, descripcion in parametros_defecto:
        try:
            cursor.execute("""
            INSERT OR IGNORE INTO configuracion_comercial (parametro, valor, descripcion)
            VALUES (?, ?, ?)
            """, (parametro, valor, descripcion))
        except Exception as e:
            print(f"Error al insertar parámetro {parametro}: {e}")
            
    conn.commit()
    conn.close()
    print("¡Base de datos e inicialización comercial completadas con éxito!")

if __name__ == "__main__":
    init_db()
