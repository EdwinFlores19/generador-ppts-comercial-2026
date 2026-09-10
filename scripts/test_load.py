import os
import sys
import threading
import sqlite3
import time
import random

# Respeta la misma variable de entorno que la aplicación: si DB_NAME apunta a
# otra ruta (p. ej. en PythonAnywhere), el script actúa sobre la BD correcta.
DB_NAME = os.getenv("DB_NAME", "proposals.db")

_errors = []

def run_db_operations(thread_id):
    """
    Simula ejecuciones concurrentes de base de datos para comprobar
    que el pool de conexiones de SQLite es seguro y no se bloquea
    bajo la estructura de 'with sqlite3.connect'.
    """
    print(f"Hilo {thread_id} iniciando transacciones concurrentes...")
    try:
        # Usar timeout largo para evitar bloqueos temporales por concurrencia
        with sqlite3.connect(DB_NAME, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Leer configuración comercial
            cursor.execute("SELECT parametro, valor FROM configuracion_comercial")
            rows = cursor.fetchall()
            print(f"Hilo {thread_id} leyó {len(rows)} parámetros de configuración comercial.")
            
            # Simular un ligero retraso para forzar concurrencia solapada
            time.sleep(random.uniform(0.1, 0.4))
            
            # 2. Insertar una propuesta de simulación masiva
            cursor.execute("""
                INSERT INTO proposals (
                    company_name, complexity, sector, description, active_modules,
                    total_weeks, total_hours, consulting_cost, licensing_cost, support_cost,
                    total_investment, savings_annual, roi_five_years, payback_period, ppt_path, preview_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"Empresa Concurrente {thread_id} (Simulación Carga)", "Alta", "Minería y Recursos",
                "Simulación de carga concurrente empresarial para pruebas de calidad QA en SEIDOR.", "FI, CO, MM, SD",
                22.0, 1500.0, 90000.0, 60000.0, 13500.0, 163500.0, 150000.0, 12.5, 1.1,
                "dummy_path.pptx", "[]"
            ))
            
            # 3. Leer las últimas propuestas
            cursor.execute("SELECT id, company_name FROM proposals ORDER BY id DESC LIMIT 3")
            proposals = cursor.fetchall()
            print(f"Hilo {thread_id} completó escritura. Últimas 3 propuestas:")
            for p in proposals:
                print(f"  [ID: {p['id']}] {p['company_name']}")
                
        print(f"Hilo {thread_id} finalizado de forma SEGURA.")
    except Exception as e:
        print(f"ERROR en Hilo {thread_id}: {e}")
        _errors.append(f"Hilo {thread_id}: {e}")

def run_concurrency_test():
    print("==================================================")
    print("INICIANDO TEST DE CARGA CONCURRENTE EN SQLITE3")
    print("==================================================")
    threads = []
    # Simular tres ejecuciones paralelas
    for i in range(3):
        t = threading.Thread(target=run_db_operations, args=(i+1,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Las excepciones de un hilo no se propagan al join: sin esta comprobación
    # el script imprimía "ÉXITO" incluso si los tres hilos habían fallado.
    if _errors:
        print("\n==================================================")
        print(f"TEST DE CONCURRENCIA FALLIDO: {len(_errors)} error(es)")
        for err in _errors:
            print(f"  - {err}")
        print("==================================================")
        _cleanup_simulation_rows()
        sys.exit(1)

    _cleanup_simulation_rows()
    print("\n==================================================")
    print("¡TEST DE CONCURRENCIA DE SQLITE COMPLETADO CON ÉXITO!")
    print("==================================================")


def _cleanup_simulation_rows():
    """
    Borra las filas de simulación. Sin esto, cada ejecución dejaba propuestas
    basura ('Empresa Concurrente N (Simulación Carga)') visibles en el
    historial real del usuario en la interfaz web.
    """
    try:
        with sqlite3.connect(DB_NAME, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM proposals WHERE company_name LIKE ?", ('%(Simulación Carga)',))
            print(f"\nLimpieza: {cur.rowcount} fila(s) de simulación eliminadas de {DB_NAME}.")
    except Exception as e:
        print(f"\nADVERTENCIA: no se pudieron limpiar las filas de simulación: {e}")

if __name__ == "__main__":
    run_concurrency_test()
