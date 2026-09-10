import os
import requests
import re
import urllib.parse
import time
from bs4 import BeautifulSoup
import logging

log = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# CONSTANTES CENTRALIZADAS
# ---------------------------------------------------------------------------
MODULES_HIGH = "FI, CO, MM, SD, PP, PS"
MODULES_MEDIUM = "FI, CO, MM, SD"
MODULES_FERREYROS = "FI, CO, MM, SD, PS"

# Nombres de sector como constantes para evitar duplicación de literales
SECTOR_MINERIA = "Minería y Recursos"
SECTOR_CONSTRUCCION = "Construcción e Infraestructura"
SECTOR_ALIMENTOS = "Alimentos y Agroindustria"
SECTOR_RETAIL = "Retail y Consumo Masivo"
SECTOR_MANUFACTURA = "Manufactura Industrial"
SECTOR_SERVICIOS = "Servicios Comerciales"

COMPANY_PRESETS = {
    "alicorp": {
        "sector": SECTOR_ALIMENTOS,
        "description": "Alicorp es la empresa de bienes de consumo más grande del Perú, con múltiples plantas de producción y centros de distribución a nivel nacional. Líder en aceites, fideos y galletas.",
        "complexity": "Alta",
        "active_modules": MODULES_HIGH
    },
    "aceros arequipa": {
        "sector": SECTOR_MANUFACTURA,
        "description": "Corporación Aceros Arequipa es líder en la producción de acero en el Perú, con plantas en Pisco y Arequipa, y distribución a nivel nacional de fierro corrugado, perfiles y alambrones.",
        "complexity": "Alta",
        "active_modules": MODULES_HIGH
    },
    "gloria": {
        "sector": SECTOR_ALIMENTOS,
        "description": "Leche Gloria S.A. es el mayor productor de lácteos y derivados en el Perú. Posee plantas de acopio y producción en Arequipa, Lima, Cajamarca y distribución en todo el territorio nacional.",
        "complexity": "Alta",
        "active_modules": MODULES_HIGH
    },
    "pacasmayo": {
        "sector": SECTOR_CONSTRUCCION,
        "description": "Cementos Pacasmayo opera plantas de cemento en Pacasmayo, Rioja y Piura, atendiendo al sector construcción e infraestructura en el norte del Perú.",
        "complexity": "Alta",
        "active_modules": MODULES_HIGH
    },
    "ferreyros": {
        "sector": SECTOR_SERVICIOS,
        "description": "Ferreyros es la empresa líder en la comercialización de bienes de capital y servicios en el Perú, representante de Caterpillar, con talleres y sucursales en las principales ciudades y zonas mineras.",
        "complexity": "Alta",
        "active_modules": MODULES_FERREYROS
    }
}

SECTOR_DESCRIPTIONS = {
    SECTOR_MINERIA: "{name} es una empresa del sector de Minería y Recursos con operaciones extractivas y de procesamiento en el Perú, requiriendo control de costos y proyectos.",
    SECTOR_CONSTRUCCION: "{name} participa activamente en el sector de Construcción e Infraestructura en el Perú, gestionando proyectos complejos de obras civiles y presupuestos.",
    SECTOR_ALIMENTOS: "{name} opera en el sector de Alimentos y Agroindustria, requiriendo control logístico, planificación de producción de bienes y aseguramiento de la calidad.",
    SECTOR_RETAIL: "{name} es una corporación en el sector de Retail y Consumo Masivo, con múltiples almacenes, logística capilar y distribución nacional en el mercado peruano.",
    SECTOR_MANUFACTURA: "{name} cuenta con plantas de Manufactura Industrial en el Perú para la transformación de insumos y distribución de bienes terminados.",
    SECTOR_SERVICIOS: "{name} es una organización orientada a la prestación de servicios comerciales y distribución en el mercado peruano."
}

SECTOR_HIGH_KEYWORDS = [
    "minera", "minero", "mina", "cobre", "oro", "zinc", "plata", "compañia minera",
    "hidrocarbur", "petrolera", "gasifera", "gasífera"
]
SECTOR_CONSTRUCTION_KEYWORDS = [
    "construc", "cemento", "obra", "vias", "edif", "concret", "ladrill", "inmobiliar"
]
SECTOR_FOOD_KEYWORDS = [
    # "pesquer" y no "pesca": la razón social real dice "Pesquera Diamante",
    # y "pesca" no es subcadena de "pesquera".
    "alimento", "leche", "bebida", "agro", "pesca", "pesquer", "lacteo", "lácteo",
    "molino", "avicola", "avícola", "azucarer", "conserv"
]
SECTOR_RETAIL_KEYWORDS = [
    "retail", "tienda", "supermercado", "comercio", "mall"
]
SECTOR_MANUFACTURING_KEYWORDS = [
    "planta", "fabrica", "manufact", "acero", "textil"
]

HIGH_COMPLEXITY_KEYWORDS = [
    "planta", "plantas", "fábrica", "fabrica", "fábricas", "produccion", "producción",
    "industrial", "manufactura", "mina", "minas", "minera", "provincias", "sucursales",
    "sedes", "arequipa", "pisco", "trujillo", "chiclayo", "piura", "obras", "infraestructura",
    "pep", "wbs", "project system", "pesquera", "agroindustrial", "construccion", "construcción",
    "concesion", "concesión", "operaciones",
    # "constructora" y "cementos" son la forma en que estas empresas se llaman
    # de verdad, y ninguna de las anteriores las cubría: "construccion" no es
    # subcadena de "constructora".
    "construct", "cemento", "siderurg", "refineria", "refinería", "molino", "azucarer",
    "avicola", "avícola", "logistica integral", "multiplanta"
]

MEDIUM_COMPLEXITY_KEYWORDS = [
    "comercializadora", "distribuidora", "importadora", "retail", "tienda", "tiendas",
    "servicios", "consultora", "tecnología", "digital", "ventas", "asesoría", "finanzas",
    "seguros", "banco", "comercio"
]

HTTP_RETRY_CODES = {429, 500, 502, 503, 504}

SSRF_PROTO_PATTERN = re.compile(
    r'(https?|ftp|file)://',
    re.IGNORECASE
)
SSRF_IP_PATTERN = re.compile(
    r'localhost|127\.0\.0\.1|::1|0\.0\.0\.0|169\.254\.|10\.\d+|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.',
    re.IGNORECASE
)
def _is_ssrf_attempt(url):
    """Check if a URL is a potential SSRF attempt."""
    return bool(SSRF_PROTO_PATTERN.search(url) or SSRF_IP_PATTERN.search(url))

DEFAULT_SECTOR = "Servicios Comerciales"
DEFAULT_COMPLEXITY = "Media"
# ---------------------------------------------------------------------------

def _build_sector_info(company_name):
    """Construye el mapeo de sectores con descripciones interpoladas."""
    return {
        sector: {
            "description": desc.format(name=company_name),
            "complexity": "Alta" if sector != DEFAULT_SECTOR else DEFAULT_COMPLEXITY,
            "active_modules": MODULES_MEDIUM if sector == DEFAULT_SECTOR else MODULES_HIGH
        }
        for sector, desc in SECTOR_DESCRIPTIONS.items()
    }

def fallback_sectorial(company_name, sector):
    """
    Asigna un perfil genérico automatizado según el sector industrial seleccionado
    por el usuario, evitando que la aplicación lance un error 500 si el raspado falla.
    """
    log.info("Aplicando fallback sectorial para '%s' con sector '%s'...", company_name, sector)

    sector_info = _build_sector_info(company_name)
    info = sector_info.get(sector, {
        "description": f"{company_name} es una corporación operando en el sector {sector or 'Comercial'} en el Perú.",
        "complexity": DEFAULT_COMPLEXITY,
        "active_modules": MODULES_MEDIUM
    })

    return {
        "sector": sector or DEFAULT_SECTOR,
        "description": info["description"],
        "complexity": info["complexity"],
        "active_modules": info["active_modules"],
        "is_fallback": True
    }

def _make_request(url, headers, attempt, max_retries, delay):
    """Realiza una petición HTTP con reintento exponencial."""
    log.info("Intento %d de %d para raspado...", attempt + 1, max_retries)
    response = requests.get(url, headers=headers, timeout=SCRAPER_TIMEOUT)

    if response.status_code in HTTP_RETRY_CODES:
        log.warning("Advertencia: Recibido código de estado HTTP %s.", response.status_code)
        if attempt < max_retries - 1:
            time.sleep(delay)
        return None, delay * 2.0

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        snippets = [r.get_text() for r in soup.find_all('a', class_='result__snippet')]
        corpus = " ".join(snippets)
        log.info("Raspado completado con éxito. Se obtuvieron %d fragmentos de DuckDuckGo.", len(snippets))
        return corpus, delay

    log.warning("Código HTTP no exitoso (%s) en el intento %d.", response.status_code, attempt + 1)
    if attempt < max_retries - 1:
        time.sleep(delay)
    return None, delay * 2.0

# El raspado web está DESACTIVADO por defecto, y es una decisión medida:
#
#   - En PythonAnywhere (plan gratuito) html.duckduckgo.com no está en la lista
#     blanca de salida, así que la petición nunca llega.
#   - Fuera de allí, DuckDuckGo responde 202/timeout al User-Agent de un script.
#
# Es decir: el raspado fallaba SIEMPRE, pero antes de rendirse gastaba
# 3 intentos x 10 s de timeout + 3 s de backoff = ~33 segundos por llamada, y
# /api/preview y /api/generate lo llaman por separado. El consultor esperaba
# más de medio minuto por lámina para acabar usando exactamente el mismo
# fallback sectorial que se aplica ahora al instante.
#
# Para reactivarlo (por ejemplo en un plan de pago con salida libre):
#   SCRAPER_ENABLED=1
SCRAPER_TIMEOUT = float(os.getenv("SCRAPER_TIMEOUT", "6"))

# Si el raspado falla una vez, el host se considera inalcanzable para el resto
# de la vida del proceso: sin esto, cada propuesta volvía a pagar el timeout
# completo contra un servidor que ya sabíamos caído.
_scraper_disponible = True


def scraping_habilitado():
    """True si el raspado web está activado por configuración."""
    return os.getenv("SCRAPER_ENABLED", "0").strip().lower() in ("1", "true", "yes", "si", "sí")


def _marcar_scraper_caido(motivo):
    global _scraper_disponible
    if _scraper_disponible:
        log.warning(
            "Raspado web desactivado para el resto del proceso (%s). "
            "Se usará el fallback sectorial, que es instantáneo.", motivo
        )
    _scraper_disponible = False


def search_company_pe(company_name):
    """
    Busca información pública sobre la huella operativa de la empresa en el Perú
    utilizando DuckDuckGo con políticas de reintento exponencial (exponential backoff).

    Devuelve cadena vacía sin tocar la red si el raspado está desactivado o si
    ya falló antes en este proceso.
    """
    if not scraping_habilitado():
        log.debug("Raspado web desactivado (SCRAPER_ENABLED=0). Se usa el fallback sectorial.")
        return ""
    if not _scraper_disponible:
        log.debug("Raspado web omitido: el host ya se marcó como inalcanzable.")
        return ""

    query = f"{company_name} operaciones peru sedes plantas"
    log.info("Iniciando raspado web para la consulta: '%s'...", query)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    max_retries = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))
    delay = float(os.getenv("SCRAPER_BACKOFF_FACTOR", "1.0"))

    for attempt in range(max_retries):
        try:
            result, delay = _make_request(url, headers, attempt, max_retries, delay)
            if result is not None:
                return result
        except Exception as e:
            log.error("Error durante el raspado en el intento %d: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2.0
            else:
                _marcar_scraper_caido(f"agotados {max_retries} intentos: {e}")

    return ""

def _classify_sector(name_lower, corpus_lower):
    """Clasifica el sector industrial basándose en palabras clave."""
    if any(k in corpus_lower or k in name_lower for k in SECTOR_HIGH_KEYWORDS):
        return SECTOR_MINERIA, "empresa del sector minero con operaciones extractivas y de procesamiento en el Perú."
    if any(k in corpus_lower or k in name_lower for k in SECTOR_CONSTRUCTION_KEYWORDS):
        return SECTOR_CONSTRUCCION, "participa activamente en el sector construcción e infraestructura en el Perú, gestionando proyectos a nivel nacional."
    if any(k in corpus_lower or k in name_lower for k in SECTOR_FOOD_KEYWORDS):
        return SECTOR_ALIMENTOS, "es una empresa agroindustrial/alimentaria peruana enfocada en la producción y distribución masiva."
    if any(k in corpus_lower or k in name_lower for k in SECTOR_RETAIL_KEYWORDS):
        return SECTOR_RETAIL, "opera en el sector retail/consumo en el Perú, con canales de distribución y tiendas físicas o virtuales."
    if any(k in corpus_lower or k in name_lower for k in SECTOR_MANUFACTURING_KEYWORDS):
        return SECTOR_MANUFACTURA, "cuenta con plantas industriales de manufactura en el Perú para la transformación de insumos y bienes."
    return None, None

def _compute_complexity(name_lower, corpus_lower):
    """Calcula puntaje de complejidad basado en palabras clave."""
    high_score = sum(
        (3 if kw in name_lower else 0) + corpus_lower.count(kw)
        for kw in HIGH_COMPLEXITY_KEYWORDS
    )
    med_score = sum(
        (3 if kw in name_lower else 0) + corpus_lower.count(kw)
        for kw in MEDIUM_COMPLEXITY_KEYWORDS
    )
    log.debug("Puntaje de Clasificación - Complejidad Alta: %d, Complejidad Media: %d", high_score, med_score)
    return high_score, med_score

def analyze_company_intelligence(company_name, text_corpus=""):
    """
    Analiza de manera inteligente el corpus de texto raspado o usa perfiles
    predefinidos (presets) para determinar el sector, descripción, complejidad y módulos SAP recomendados.
    """
    name_lower = company_name.lower()
    corpus_lower = text_corpus.lower()

    # 1. Calcular complejidad (los presets ya se verificaron en get_company_profile)
    high_score, med_score = _compute_complexity(name_lower, corpus_lower)

    # 2. Determinar complejidad y módulos
    if high_score > 3 or (high_score > med_score and high_score > 0):
        complexity = "Alta"
        active_modules = MODULES_HIGH
    else:
        complexity = DEFAULT_COMPLEXITY
        active_modules = MODULES_MEDIUM

    # 4. Clasificar sector
    sector, desc_suffix = _classify_sector(name_lower, corpus_lower)

    # Si se identifica un sector industrial concreto, la complejidad es Alta
    # aunque las palabras de complejidad no hayan disparado. Es la misma regla
    # que ya aplicaba fallback_sectorial (_build_sector_info: todo sector que no
    # sea "Servicios Comerciales" es Alta), y sin ella las dos rutas se
    # contradecían: "Corporación Petrolera del Norte" salía Minería + Media,
    # es decir sector industrial con alcance de empresa de servicios.
    if sector is not None and sector != DEFAULT_SECTOR:
        complexity = "Alta"
        active_modules = MODULES_HIGH

    if sector is None:
        if complexity == "Alta":
            sector = "Corporación Industrial"
            description = f"{company_name} es una corporación industrial diversificada con operaciones descentralizadas en el territorio peruano."
        else:
            sector = DEFAULT_SECTOR
            description = f"{company_name} es una organización orientada a la prestación de servicios comerciales y distribución en el mercado de Perú."
    else:
        description = f"{company_name} {desc_suffix}"

    return {
        "sector": sector,
        "description": description,
        "complexity": complexity,
        "active_modules": active_modules
    }

def _match_company_preset(name_lower):
    """Busca coincidencia con preset corporativo. Retorna el perfil o None."""
    for key, preset in COMPANY_PRESETS.items():
        if key in name_lower:
            log.info("Coincidencia directa con preset corporativo para la empresa")
            profile = preset.copy()
            profile["is_fallback"] = False
            return profile
    return None

def get_company_profile(company_name, sector=None):
    """
    Punto de entrada principal del scraper: busca en la web y analiza la empresa.
    Si coincide con un preset conocido, se retorna inmediatamente.
    Si la búsqueda falla o no devuelve datos fidedignos, se aplica el fallback sectorial.
    """
    # Mitigación estricta de SSRF y inyección de URLs/IPs locales
    if _is_ssrf_attempt(company_name) or _is_ssrf_attempt(sector or ""):
        log.warning("[SSRF DETECTED] Bloqueo de entrada sospechosa: '%s' / '%s'", company_name, sector)
        return fallback_sectorial("Empresa Protegida", sector or DEFAULT_SECTOR)

    # 1. Verificar coincidencia con presets primero para evitar dependencias de red
    profile = _match_company_preset(company_name.lower())
    if profile:
        return profile

    # 2. Probar raspado web (no-op si está desactivado o el host ya falló)
    text_corpus = ""
    try:
        text_corpus = search_company_pe(company_name)
    except Exception as e:
        log.error("Error crítico en search_company_pe para '%s': %s.", company_name, e)

    if text_corpus and len(text_corpus.strip()) >= 10:
        profile = analyze_company_intelligence(company_name, text_corpus)
        profile["is_fallback"] = False
        return profile

    # 3. Sin corpus, clasificar por el NOMBRE antes de rendirse.
    #
    # analyze_company_intelligence ya sabía leer el nombre ("minera", "cementos",
    # "agroindustrial"...), pero solo se llegaba a él por la rama del raspado,
    # que en la práctica nunca se ejecuta. El resultado era que "Minera Las
    # Bambas S.A." salía como "Servicios Comerciales / Media": el nombre, que es
    # la señal más fiable que tenemos, se estaba tirando a la basura.
    perfil_por_nombre = analyze_company_intelligence(company_name, "")
    # Un sector concreto es señal; una complejidad Alta también lo es aunque el
    # sector salga genérico ("Pesquera Diamante" no casa con ningún sector del
    # catálogo, pero su nombre dice claramente que es una operación industrial).
    nombre_es_informativo = (
        perfil_por_nombre["sector"] != DEFAULT_SECTOR
        or perfil_por_nombre["complexity"] == "Alta"
    )

    if nombre_es_informativo:
        log.info("Perfil deducido del nombre de la empresa: sector '%s', complejidad '%s'.",
                 perfil_por_nombre["sector"], perfil_por_nombre["complexity"])
        # El sector que el consultor haya escrito manda sobre la deducción.
        if sector and sector != perfil_por_nombre["sector"]:
            perfil_por_nombre = _fusionar_sector_indicado(perfil_por_nombre, company_name, sector)
        perfil_por_nombre["is_fallback"] = True
        return perfil_por_nombre

    log.info("El nombre '%s' no aporta señal sectorial. Fallback por sector indicado.", company_name)
    return fallback_sectorial(company_name, sector)


def _fusionar_sector_indicado(perfil, company_name, sector):
    """
    El consultor eligió un sector explícito: manda sobre el deducido del nombre,
    pero se conserva la complejidad deducida (el nombre sigue diciendo si la
    empresa es industrial y multiplanta, cosa que el desplegable no captura).
    """
    descripcion = SECTOR_DESCRIPTIONS.get(sector)
    return {
        "sector": sector,
        "description": descripcion.format(name=company_name) if descripcion else perfil["description"],
        "complexity": perfil["complexity"],
        "active_modules": perfil["active_modules"],
    }

if __name__ == "__main__":
    import sys
    test_company = sys.argv[1] if len(sys.argv) > 1 else "Alicorp"
    profile = get_company_profile(test_company, "Alimentos y Agroindustria")
    print("\n--- Resultado de Prueba de Perfil ---")
    print(profile)
