import requests
import re
import urllib.parse
import time
from bs4 import BeautifulSoup

def fallback_sectorial(company_name, sector):
    """
    Asigna un perfil genérico automatizado según el sector industrial seleccionado
    por el usuario, evitando que la aplicación lance un error 500 si el raspado falla.
    
    Parámetros:
    - company_name (str): Nombre de la empresa a analizar.
    - sector (str): Sector industrial proporcionado como fallback.
    
    Retorna:
    - dict: Perfil comercial con sector, descripción, complejidad y módulos activos.
    """
    print(f"Aplicando fallback sectorial para '{company_name}' con sector '{sector}'...")
    
    # Mapeo de sectores y perfiles predefinidos corporativos
    sector_info = {
        "Minería y Recursos": {
            "description": f"{company_name} es una empresa del sector de Minería y Recursos con operaciones extractivas y de procesamiento en el Perú, requiriendo control de costos y proyectos.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "Construcción e Infraestructura": {
            "description": f"{company_name} participa activamente en el sector de Construcción e Infraestructura en el Perú, gestionando proyectos complejos de obras civiles y presupuestos.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "Alimentos y Agroindustria": {
            "description": f"{company_name} opera en el sector de Alimentos y Agroindustria, requiriendo control logístico, planificación de producción de bienes y aseguramiento de la calidad.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "Retail y Consumo Masivo": {
            "description": f"{company_name} es una corporación en el sector de Retail y Consumo Masivo, con múltiples almacenes, logística capilar y distribución nacional en el mercado peruano.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "Manufactura Industrial": {
            "description": f"{company_name} cuenta con plantas de Manufactura Industrial en el Perú para la transformación de insumos y distribución de bienes terminados.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "Servicios Comerciales": {
            "description": f"{company_name} es una organización orientada a la prestación de servicios comerciales y distribución en el mercado peruano.",
            "complexity": "Media",
            "active_modules": "FI, CO, MM, SD"
        }
    }
    
    info = sector_info.get(sector, {
        "description": f"{company_name} es una corporación operando en el sector {sector or 'Comercial'} en el Perú.",
        "complexity": "Media",
        "active_modules": "FI, CO, MM, SD"
    })
    
    return {
        "sector": sector or "Servicios Comerciales",
        "description": info["description"],
        "complexity": info["complexity"],
        "active_modules": info["active_modules"],
        "is_fallback": True
    }

def search_company_pe(company_name):
    """
    Busca información pública sobre la huella operativa de la empresa en el Perú
    utilizando DuckDuckGo con políticas de reintento exponencial (exponential backoff).
    
    Parámetros:
    - company_name (str): Nombre de la empresa a buscar.
    
    Retorna:
    - str: Corpus de texto extraído de los resultados de búsqueda.
    """
    query = f"{company_name} operaciones peru sedes plantas"
    print(f"Iniciando raspado web para la consulta: '{query}'...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    text_corpus = ""
    max_retries = 3
    delay = 1.0  # Retraso inicial de 1 segundo
    
    for attempt in range(max_retries):
        try:
            print(f"Intento {attempt + 1} de {max_retries} para raspado de '{company_name}'...")
            response = requests.get(url, headers=headers, timeout=10)
            
            # Manejar errores HTTP comunes que requieren reintento (ej. 429, 500, 502, 503, 504)
            if response.status_code in [429, 500, 502, 503, 504]:
                print(f"Advertencia: Recibido código de estado HTTP {response.status_code}.")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2.0
                    continue
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                snippets = []
                for result in soup.find_all('a', class_='result__snippet'):
                    snippets.append(result.get_text())
                text_corpus = " ".join(snippets)
                print(f"Raspado completado con éxito. Se obtuvieron {len(snippets)} fragmentos de DuckDuckGo.")
                break
            else:
                print(f"Código HTTP no exitoso ({response.status_code}) en el intento {attempt + 1}.")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2.0
                    
        except Exception as e:
            print(f"Error durante el raspado en el intento {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2.0
                
    return text_corpus

def analyze_company_intelligence(company_name, text_corpus=""):
    """
    Analiza de manera inteligente el corpus de texto raspado o usa perfiles
    predefinidos (presets) para determinar el sector, descripción, complejidad y módulos SAP recomendados.
    
    Parámetros:
    - company_name (str): Nombre de la empresa a analizar.
    - text_corpus (str, opcional): Corpus de texto de la búsqueda web.
    
    Retorna:
    - dict: Perfil determinado con sector, descripción, complejidad y módulos activos.
    """
    name_lower = company_name.lower()
    corpus_lower = text_corpus.lower()
    
    # 1. Presets de las empresas peruanas más conocidas (Alicorp, Aceros Arequipa, Gloria, Pacasmayo, Ferreyros)
    presets = {
        "alicorp": {
            "sector": "Alimentos y Agroindustria",
            "description": "Alicorp es la empresa de bienes de consumo más grande del Perú, con múltiples plantas de producción y centros de distribución a nivel nacional. Líder en aceites, fideos y galletas.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "aceros arequipa": {
            "sector": "Manufactura Industrial",
            "description": "Corporación Aceros Arequipa es líder en la producción de acero en el Perú, con plantas en Pisco y Arequipa, y distribución a nivel nacional de fierro corrugado, perfiles y alambrones.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "gloria": {
            "sector": "Alimentos y Agroindustria",
            "description": "Leche Gloria S.A. es el mayor productor de lácteos y derivados en el Perú. Posee plantas de acopio y producción en Arequipa, Lima, Cajamarca y distribución en todo el territorio nacional.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "pacasmayo": {
            "sector": "Construcción e Infraestructura",
            "description": "Cementos Pacasmayo opera plantas de cemento en Pacasmayo, Rioja y Piura, atendiendo al sector construcción e infraestructura en el norte del Perú.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "ferreyros": {
            "sector": "Servicios Comerciales",
            "description": "Ferreyros es la empresa líder en la comercialización de bienes de capital y servicios en el Perú, representante de Caterpillar, con talleres y sucursales en las principales ciudades y zonas mineras.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PS"
        }
    }
    
    for key, preset in presets.items():
        if key in name_lower:
            print(f"Coincidencia con preset corporativo para '{company_name}': Complejidad {preset['complexity']}")
            return preset.copy()
            
    # 2. Análisis heurístico basado en palabras clave (Procesamiento de Lenguaje Natural simplificado)
    high_complexity_keywords = [
        "planta", "plantas", "fábrica", "fabrica", "fábricas", "produccion", "producción",
        "industrial", "manufactura", "mina", "minas", "minera", "provincias", "sucursales",
        "sedes", "arequipa", "pisco", "trujillo", "chiclayo", "piura", "obras", "infraestructura",
        "pep", "wbs", "project system", "pesquera", "agroindustrial", "construccion", "construcción",
        "concesion", "concesión", "operaciones"
    ]
    
    medium_complexity_keywords = [
        "comercializadora", "distribuidora", "importadora", "retail", "tienda", "tiendas",
        "servicios", "consultora", "tecnología", "digital", "ventas", "asesoría", "finanzas",
        "seguros", "banco", "comercio"
    ]
    
    high_score = 0
    med_score = 0
    
    # Evaluar palabras clave en el nombre de la empresa
    for kw in high_complexity_keywords:
        if kw in name_lower:
            high_score += 3
    for kw in medium_complexity_keywords:
        if kw in name_lower:
            med_score += 3
            
    # Evaluar palabras clave en el corpus raspado
    for kw in high_complexity_keywords:
        high_score += corpus_lower.count(kw)
    for kw in medium_complexity_keywords:
        med_score += corpus_lower.count(kw)
        
    print(f"Puntaje de Clasificación - Complejidad Alta: {high_score}, Complejidad Media: {med_score}")
    
    # 3. Establecer defaults
    complexity = "Media"
    sector = "Servicios Comerciales"
    description = f"Empresa operando en el mercado peruano en el sector de {company_name}."
    active_modules = "FI, CO, MM, SD"
    
    if high_score > 3 or (high_score > med_score and high_score > 0):
        complexity = "Alta"
        active_modules = "FI, CO, MM, SD, PP, PS"
        
    # Clasificación por sector
    if any(k in corpus_lower or k in name_lower for k in ["minera", "mina", "cobre", "oro"]):
        sector = "Minería y Recursos"
        description = f"{company_name} es una empresa del sector minero con operaciones extractivas y de procesamiento en el Perú."
    elif any(k in corpus_lower or k in name_lower for k in ["construc", "cemento", "obra", "vias", "edif"]):
        sector = "Construcción e Infraestructura"
        description = f"{company_name} participa activamente en el sector construcción e infraestructura en el Perú, gestionando proyectos a nivel nacional."
    elif any(k in corpus_lower or k in name_lower for k in ["alimento", "leche", "bebida", "agro", "pesca"]):
        sector = "Alimentos y Agroindustria"
        description = f"{company_name} es una empresa agroindustrial/alimentaria peruana enfocada en la producción y distribución masiva."
    elif any(k in corpus_lower or k in name_lower for k in ["retail", "tienda", "supermercado", "comercio", "mall"]):
        sector = "Retail y Consumo Masivo"
        description = f"{company_name} opera en el sector retail/consumo en el Perú, con canales de distribución y tiendas físicas o virtuales."
    elif any(k in corpus_lower or k in name_lower for k in ["planta", "fabrica", "manufact", "acero", "textil"]):
        sector = "Manufactura Industrial"
        description = f"{company_name} cuenta con plantas industriales de manufactura en el Perú para la transformación de insumos y bienes."
    else:
        # Clasificación genérica según complejidad
        if complexity == "Alta":
            sector = "Corporación Industrial"
            description = f"{company_name} es una corporación industrial diversificada con operaciones descentralizadas en el territorio peruano."
        else:
            sector = "Servicios Comerciales"
            description = f"{company_name} es una organización orientada a la prestación de servicios comerciales y distribución en el mercado de Perú."

    return {
        "sector": sector,
        "description": description,
        "complexity": complexity,
        "active_modules": active_modules
    }

def get_company_profile(company_name, sector=None):
    """
    Punto de entrada principal del scraper: busca en la web y analiza la empresa.
    Si coincide con un preset conocido, se retorna inmediatamente.
    Si la búsqueda falla o no devuelve datos fidedignos, se aplica el fallback sectorial.
    
    Parámetros:
    - company_name (str): Nombre de la empresa.
    - sector (str, opcional): Sector industrial por defecto de la interfaz gráfica.
    
    Retorna:
    - dict: Perfil comercial validado para la preventa SAP.
    """
    # Mitigación estricta de SSRF y inyección de URLs/IPs locales
    import re
    ssrf_pattern = re.compile(
        r'(https?|ftp|file)://|localhost|127\.0\.0\.1|::1|0\.0\.0\.0|169\.254\.|10\.\d+|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.',
        re.IGNORECASE
    )
    if ssrf_pattern.search(company_name) or ssrf_pattern.search(sector or ""):
        print(f"[SSRF DETECTED] Bloqueo de entrada sospechosa: '{company_name}' / '{sector}'")
        # Forzar un fallback sectorial genérico sin realizar ninguna petición de red
        return fallback_sectorial("Empresa Protegida", sector or "Servicios Comerciales")

    # 1. Verificar coincidencia con presets primero para evitar dependencias de red
    name_lower = company_name.lower()
    presets = {
        "alicorp": {
            "sector": "Alimentos y Agroindustria",
            "description": "Alicorp es la empresa de bienes de consumo más grande del Perú, con múltiples plantas de producción y centros de distribución a nivel nacional. Líder en aceites, fideos y galletas.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "aceros arequipa": {
            "sector": "Manufactura Industrial",
            "description": "Corporación Aceros Arequipa es líder en la producción de acero en el Perú, con plantas en Pisco y Arequipa, y distribución a nivel nacional de fierro corrugado, perfiles y alambrones.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "gloria": {
            "sector": "Alimentos y Agroindustria",
            "description": "Leche Gloria S.A. es el mayor productor de lácteos y derivados en el Perú. Posee plantas de acopio y producción en Arequipa, Lima, Cajamarca y distribución en todo el territorio nacional.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "pacasmayo": {
            "sector": "Construcción e Infraestructura",
            "description": "Cementos Pacasmayo opera plantas de cemento en Pacasmayo, Rioja y Piura, atendiendo al sector construcción e infraestructura en el norte del Perú.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PP, PS"
        },
        "ferreyros": {
            "sector": "Servicios Comerciales",
            "description": "Ferreyros es la empresa líder en la comercialización de bienes de capital y servicios en el Perú, representante de Caterpillar, con talleres y sucursales en las principales ciudades y zonas mineras.",
            "complexity": "Alta",
            "active_modules": "FI, CO, MM, SD, PS"
        }
    }
    
    for key, preset in presets.items():
        if key in name_lower:
            print(f"Coincidencia directa con preset corporativo para '{company_name}'")
            profile = preset.copy()
            profile["is_fallback"] = False
            return profile

    # 2. Probar raspado web con reintentos
    text_corpus = ""
    try:
        text_corpus = search_company_pe(company_name)
    except Exception as e:
        print(f"Error crítico en search_company_pe para '{company_name}': {e}.")
        
    # Verificar si el corpus obtenido es válido o está vacío
    if not text_corpus or len(text_corpus.strip()) < 10:
        print(f"No se pudo recolectar información en la web para '{company_name}'. Activando fallback...")
        profile = fallback_sectorial(company_name, sector)
    else:
        profile = analyze_company_intelligence(company_name, text_corpus)
        profile["is_fallback"] = False
        
    return profile

if __name__ == "__main__":
    import sys
    test_company = sys.argv[1] if len(sys.argv) > 1 else "Alicorp"
    profile = get_company_profile(test_company, "Alimentos y Agroindustria")
    print("\n--- Resultado de Prueba de Perfil ---")
    print(profile)
