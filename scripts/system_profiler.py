import time
import tracemalloc
import cProfile
import pstats
import io
import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import financial_engine, ppt_generator

log = logging.getLogger("system_profiler")

EXCEL_PATH = r"Estimador S0 V2.0.xlsx"


def profile_excel_reading_raw():
    tracemalloc.start()
    start_time = time.perf_counter()

    if hasattr(financial_engine, '_excel_cache'):
        financial_engine._excel_cache = {}
        financial_engine._excel_last_mtime = 0

    results = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])

    end_time = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024

    return elapsed_ms, peak_kb, results


def profile_excel_reading_cached():
    financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])

    tracemalloc.start()
    start_time = time.perf_counter()

    results = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])

    end_time = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024

    return elapsed_ms, peak_kb, results


def profile_pptx_generation():
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
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed_ms = (end_time - start_time) * 1000
    peak_kb = peak / 1024

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            log.warning("No se pudo eliminar el archivo temporal: %s", output_path)

    return elapsed_ms, peak_kb


def run_full_profiling():
    log.info("==================================================")
    log.info("      SISTEMA DE PROFILING DE RENDIMIENTO        ")
    log.info("==================================================")

    log.info("--- Ejecutando Profiling del Motor Financiero ---")

    raw_time, raw_mem, _ = profile_excel_reading_raw()
    log.info("Lectura Física de Excel (Disco):")
    log.info("  > Tiempo Transcurrido: %.2f ms", raw_time)
    log.info("  > Memoria de Pico Usada: %.2f KB", raw_mem)

    cached_time, cached_mem, _ = profile_excel_reading_cached()
    log.info("Lectura Cacheada (Memoria):")
    log.info("  > Tiempo Transcurrido: %.2f ms", cached_time)
    log.info("  > Memoria de Pico Usada: %.2f KB", cached_mem)

    improvement_factor = raw_time / cached_time if cached_time > 0 else 1.0
    log.info("Factor de Mejora en Tiempo: %.1fx más rápido.", improvement_factor)

    log.info("--- Ejecutando Profiling de Compilación PPTX ---")
    ppt_time, ppt_mem = profile_pptx_generation()
    log.info("Generación del Deck (python-pptx + Gráficos Nativo):")
    log.info("  > Tiempo Transcurrido: %.2f ms", ppt_time)
    log.info("  > Memoria de Pico Usada: %.2f KB", ppt_mem)

    log.info("--- Ejecutando Análisis Detallado (cProfile) ---")
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(5):
        financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
    pr.disable()

    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats(15)
    log.info(s.getvalue())


if __name__ == "__main__":
    run_full_profiling()
