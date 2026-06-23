import threading
import sqlite3
import time
import random

DB_NAME = "proposals.db"

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
        raise e

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
        
    print("\n==================================================")
    print("¡TEST DE CONCURRENCIA DE SQLITE COMPLETADO CON ÉXITO!")
    print("==================================================")

if __name__ == "__main__":
    run_concurrency_test()
