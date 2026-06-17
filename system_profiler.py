import time
import tracemalloc
import cProfile
import pstats
import io
import os
import sys

# Asegurar que el path del proyecto esté en el path de búsqueda
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import financial_engine
import ppt_generator

EXCEL_PATH = r"Estimador S0 V2.0.xlsx"

def profile_excel_reading_raw():
    """
    Mide el rendimiento de la lectura del Excel de estimaciones directamente desde el disco.
    """
    tracemalloc.start()
    start_time = time.perf_counter()
    
    # Forzar la carga física sin caché (limpiando variables si existieran)
    if hasattr(financial_engine, '_excel_cache'):
        financial_engine._excel_cache = {}
        financial_engine._excel_last_mtime = 0
        
    results = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    
    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024
    
    return elapsed_ms, peak_kb, results

def profile_excel_reading_cached():
    """
    Mide el rendimiento de la lectura usando la caché en memoria.
    """
    # Primero cargamos una vez para llenar la caché
    financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    
    tracemalloc.start()
    start_time = time.perf_counter()
    
    results = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    
    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024
    
    return elapsed_ms, peak_kb, results

def profile_pptx_generation():
    """
    Mide el tiempo y memoria utilizados al compilar la presentación PPTX
    e inyectar los gráficos nativos de Office.
    """
    # Obtener datos de prueba
    financial_data = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    
    output_path = "generated_decks/profiling_test.pptx"
    os.makedirs("generated_decks", exist_ok=True)
    
    tracemalloc.start()
    start_time = time.perf_counter()
    
    ppt_generator.generate_deck(
        company_name="Empresa Profiling S.A.",
        sector="Manufactura Industrial",
        description="Empresa de prueba para profiling de rendimiento.",
        complexity="Alta",
        financial_data=financial_data,
        output_path=output_path
    )
    
    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024
    
    # Eliminar archivo temporal si existe
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
            
    return elapsed_ms, peak_kb

def run_full_profiling():
    print("==================================================")
    print("      SISTEMA DE PROFILING DE RENDIMIENTO        ")
    print("==================================================")
    
    print("\n--- Ejecutando Profiling del Motor Financiero ---")
    
    # 1. Medición de lectura física
    raw_time, raw_mem, _ = profile_excel_reading_raw()
    print(f"Lectura Física de Excel (Disco):")
    print(f"  > Tiempo Transcurrido: {raw_time:.2f} ms")
    print(f"  > Memoria de Pico Usada: {raw_mem:.2f} KB")
    
    # 2. Medición de lectura en caché
    cached_time, cached_mem, _ = profile_excel_reading_cached()
    print(f"Lectura Cacheada (Memoria):")
    print(f"  > Tiempo Transcurrido: {cached_time:.2f} ms")
    print(f"  > Memoria de Pico Usada: {cached_mem:.2f} KB")
    
    improvement_factor = raw_time / cached_time if cached_time > 0 else 1.0
    print(f"Factor de Mejora en Tiempo: {improvement_factor:.1f}x más rápido.")
    
    # 3. Profiling de PowerPoint
    print("\n--- Ejecutando Profiling de Compilación PPTX ---")
    ppt_time, ppt_mem = profile_pptx_generation()
    print(f"Generación del Deck (python-pptx + Gráficos Nativo):")
    print(f"  > Tiempo Transcurrido: {ppt_time:.2f} ms")
    print(f"  > Memoria de Pico Usada: {ppt_mem:.2f} KB")
    
    # 4. cProfile en Motor Financiero para cuellos de botella finos
    print("\n--- Ejecutando Análisis Detallado (cProfile) ---")
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(5):
        financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    pr.disable()
    
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats(15)  # Mostrar las 15 funciones con mayor acumulado
    print(s.getvalue())
    
if __name__ == "__main__":
    run_full_profiling()
