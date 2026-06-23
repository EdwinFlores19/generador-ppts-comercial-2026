import threading
import sqlite3
import time
import random
from models.database import DB_NAME


class TestDatabaseConcurrency:
    def test_concurrent_reads(self):
        errors = []
        def reader():
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM proposals")
                cursor.fetchone()
                conn.close()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errores en lectura concurrente: {errors}"

    def test_concurrent_writes(self):
        errors = []
        def writer():
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO proposals (company_name, complexity)
                    VALUES (?, ?)
                """, (f"Test Concurrency {time.time()}", "Media"))
                conn.commit()
                conn.close()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errores en escritura concurrente: {errors}"

    def test_concurrent_read_write(self):
        errors = []
        lock = threading.Lock()

        def mixed_operation():
            try:
                for _ in range(3):
                    with lock:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM configuracion_comercial")
                        cursor.fetchone()
                        cursor.execute("""
                            INSERT INTO proposals (company_name, complexity)
                            VALUES (?, ?)
                        """, (f"Mixed {time.time()}", "Alta"))
                        conn.commit()
                        conn.close()
                    time.sleep(random.uniform(0.05, 0.15))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=mixed_operation) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errores en operación mixta: {errors}"
