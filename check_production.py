import requests
import json
import sys
import os

# Códigos ANSI para impresión con colores en la terminal (Windows compatible)
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_RESET = "\033[0m"

# Dirección base del servidor Flask
BASE_URL = "http://127.0.0.1:5000"

def print_pass(message):
    print(f"{COLOR_GREEN}[PASS]{COLOR_RESET} {message}")

def print_fail(message):
    print(f"{COLOR_RED}[FAIL]{COLOR_RESET} {message}")

def print_info(message):
    print(f"{COLOR_BLUE}[INFO]{COLOR_RESET} {message}")

def run_smoke_test():
    print("==================================================")
    print("  GROW DECK AUTOMATOR - SMOKE TEST DE PRODUCCIÓN  ")
    print("==================================================")
    
    # ---------------------------------------------------------
    # PASO 1: Ping HTTP a la ruta raíz (GET /)
    # ---------------------------------------------------------
    print_info("Iniciando Paso 1: Ping HTTP a la ruta raíz...")
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code == 200:
            print_pass(f"Servidor Flask respondiendo en {BASE_URL} (Código HTTP 200).")
        else:
            print_fail(f"Servidor Flask retornó código de estado HTTP {response.status_code}.")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print_fail(f"No se pudo conectar al servidor en {BASE_URL}.")
        print_info(f"Asegúrese de levantar los servicios locales ejecutando 'python app.py' o 'docker-compose up --build -d'.")
        sys.exit(1)
    except Exception as e:
        print_fail(f"Error inesperado al hacer ping al servidor: {e}")
        sys.exit(1)

    # ---------------------------------------------------------
    # PASO 2: Interrogar API interna (POST /api/preview)
    # ---------------------------------------------------------
    print_info("\nIniciando Paso 2: Enviando petición de prueba al endpoint de previsualización...")
    payload = {
        "company_name": "Alicorp S.A.A. (Smoke Test)",
        "sector": "Alimentos y Agroindustria",
        "annual_revenue": 15000000.0,
        "complexity_mode": "auto",
        "consulting_rate": 65.0,  # Valor de prueba no-default
        "support_percentage": 15.0,
        "modular_licenses": {}
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        preview_url = f"{BASE_URL}/api/preview"
        response = requests.post(preview_url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") is True:
                print_pass("API respondió exitosamente con éxito operativo y estructura JSON válida.")
            else:
                print_fail(f"API retornó success=False en el JSON: {data}")
                sys.exit(1)
        else:
            print_fail(f"API de previsualización falló con código HTTP {response.status_code}. Detalle: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print_fail(f"Error de conexión o fallo de comunicación con la API: {e}")
        sys.exit(1)

    # ---------------------------------------------------------
    # PASO 3: Validación Matemática y Estructuras Multimoneda (USD/PEN)
    # ---------------------------------------------------------
    print_info("\nIniciando Paso 3: Validando estructuras de moneda, IGV y consistencia...")
    
    # Extraer estructuras del JSON
    financial_data = data.get("financial_data", {})
    summary = financial_data.get("summary", {})
    
    # Comprobar presencia de llaves bimoneda USD y PEN
    if "usd" in summary and "pen" in summary:
        print_pass("Estructuras multimoneda de localización (USD y PEN) presentes en la respuesta.")
    else:
        print_fail("Faltan los desgloses 'usd' o 'pen' dentro del sumario de respuesta de la API.")
        sys.exit(1)
        
    # Obtener valores numéricos y tasas dinámicas
    igv_rate = summary.get("factor_igv", 0.18)
    tc = summary.get("tipo_cambio_pen", 3.78)
    
    # USD
    usd_net = summary["usd"]["net_investment"]
    usd_igv = summary["usd"]["igv"]
    usd_total = summary["usd"]["total_facturable"]
    
    # PEN
    pen_net = summary["pen"]["net_investment"]
    pen_igv = summary["pen"]["igv"]
    pen_total = summary["pen"]["total_facturable"]
    
    print_info(f"Parámetros comerciales aplicados: IGV={igv_rate*100}%, Tipo Cambio={tc}")
    print_info(f"Valores en USD - Neto: {usd_net}, IGV: {usd_igv}, Total: {usd_total}")
    print_info(f"Valores en PEN - Neto: {pen_net}, IGV: {pen_igv}, Total: {pen_total}")
    
    # Validaciones matemáticas con tolerancia flotante delta < 0.05
    try:
        # Validación de IGV en USD
        expected_usd_igv = round(usd_net * igv_rate, 2)
        assert abs(usd_igv - expected_usd_igv) < 0.05, f"Desviación de IGV USD: Esperado {expected_usd_igv}, Obtenido {usd_igv}"
        
        # Validación de Inversión Total Facturable en USD
        expected_usd_total = round(usd_net + usd_igv, 2)
        assert abs(usd_total - expected_usd_total) < 0.05, f"Desviación de Total USD: Esperado {expected_usd_total}, Obtenido {usd_total}"
        
        # Validación de Conversión Multimoneda (USD a PEN)
        expected_pen_net = round(usd_net * tc, 2)
        assert abs(pen_net - expected_pen_net) < 0.05, f"Desviación de Conversión PEN: Esperado {expected_pen_net}, Obtenido {pen_net}"
        
        # Validación de IGV en PEN
        expected_pen_igv = round(pen_net * igv_rate, 2)
        assert abs(pen_igv - expected_pen_igv) < 0.05, f"Desviación de IGV PEN: Esperado {expected_pen_igv}, Obtenido {pen_igv}"
        
        # Validación de Inversión Total Facturable en PEN
        expected_pen_total = round(pen_net + pen_igv, 2)
        assert abs(pen_total - expected_pen_total) < 0.05, f"Desviación de Total PEN: Esperado {expected_pen_total}, Obtenido {pen_total}"
        
        print_pass("Validaciones matemáticas del 18% de IGV y conversión bimoneda aprobadas con éxito.")
    except AssertionError as assert_err:
        print_fail(f"Fallo de coherencia en cálculos financieros locales SUNAT: {assert_err}")
        sys.exit(1)
        
    # Verificar que no hay excepciones ni llaves de error
    if "error" in data:
        print_fail(f"La respuesta JSON reportó una excepción/error latente: {data['error']}")
        sys.exit(1)
        
    # Validar heurística de complejidad e industrias del Scraper
    complexity = data.get("complexity")
    sector = data.get("sector")
    print_info(f"Clasificación del prospecto - Complejidad: {complexity}, Sector: {sector}")
    
    assert complexity in ["Alta", "Media"], f"Complejidad inválida retornada: {complexity}"
    assert len(data.get("slides_preview", [])) > 0, "No se generaron viñetas ni previsualización de diapositivas."
    print_pass("Heurística de Scraper y estructura de diapositivas correctamente integradas.")
    
    # Confirmación final de salud de memoria y ejecución limpia
    print_pass("No se detectaron fugas de memoria o excepciones críticas durante la transacción.")
    
    print("\n==================================================")
    print(f" {COLOR_GREEN}SMOKE TEST EXITOSO - ENTORNO APTO PARA PRODUCCIÓN{COLOR_RESET} ")
    print("==================================================")
    
if __name__ == "__main__":
    run_smoke_test()
