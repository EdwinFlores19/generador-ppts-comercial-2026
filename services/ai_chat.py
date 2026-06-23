"""
Motor de Inteligencia Artificial para Chatbot de Preventa SAP SEIDOR Perú.
Utiliza Google Gemini API (google-genai SDK) para interpretar lenguaje natural,
mantener conversaciones contextuales y extraer datos estructurados para generar
propuestas comerciales SAP S/4HANA Cloud (GROW with SAP).
"""

import os
import json
import re
import asyncio
import math
from google import genai
from google.genai import errors as genai_errors
import logging

log = logging.getLogger("ai_chat")

GEMINI_TIMEOUT = 25

VALID_MODULES = frozenset({'FI', 'CO', 'MM', 'SD', 'PP', 'PS'})

SYSTEM_INSTRUCTION = """Eres un asesor senior de preventa SAP para SEIDOR Perú, especializado en GROW with SAP S/4HANA Public Cloud.

Tu misión es mantener una conversación profesional y cálida para ayudar al usuario a definir una propuesta comercial SAP. Guía la conversación para recopilar TODOS los siguientes datos de forma natural, sin hacer todas las preguntas a la vez:

1. Nombre de la empresa del prospecto
2. Sector industrial (Minería, Retail, Alimentos, Manufactura, Construcción, Servicios, etc.)
3. Descripción del negocio: qué hace la empresa, dónde opera en Perú, tamaño
4. Principales dolores operativos: problemas actuales en logística, finanzas, control de gestión, reportabilidad
5. Módulos SAP que necesita: FI (Finanzas), CO (Controlling), MM (Materiales/Compras), SD (Ventas), PP (Producción), PS (Proyectos)
6. Facturación anual aproximada en USD
7. Complejidad del proyecto: ALTA (necesita PP, PS, múltiples plantas) o MEDIA (solo FI, CO, MM, SD)
8. Presupuesto estimado o expectativa de inversión

REGLAS DE CONDUCTA:
- Responde SIEMPRE en español profesional, claro y conversacional
- No seas un cuestionario: haz 1-2 preguntas por turno
- Usa tu conocimiento de SAP S/4HANA, GROW with SAP, SAP Fiori, SAP Joule, metodología SAP Activate
- Menciona a SEIDOR Perú como el partner implementador
- Si el usuario se desvía, retoma amablemente el hilo
- NO inventes datos de empresas reales que no haya proporcionado el usuario
- Sé empático y profesional, como un consultor experto de SEIDOR

Cuando tengas TODOS los datos necesarios, informa al usuario amablemente que ya puede generar su propuesta y menciona la frase exacta "LISTO PARA GENERAR PROPUESTA". No incluyas esta frase hasta estar seguro de tener todos los datos.

INSTRUCCIÓN DE SALIDA ESTRUCTURADA:
Inmediatamente después de tu mensaje conversacional, cuando tengas TODOS los datos, agrega el siguiente bloque usando SIEMPRE los VALORES REALES que el usuario proporcionó. No uses valores de ejemplo ni predeterminados. El bloque debe ir exactamente en este formato, en líneas separadas, sin markdown, sin comillas triples:

##DATA_READY
{"company_name": "<valor real>", "sector": "<valor real>", "description": "<valor real>", "complexity": "Alta o Media", "active_modules": ["FI", "CO", ... según corresponda], "revenue": <número real>, "pains": {"logistics": "<texto real>", "financial": "<texto real>", "management": "<texto real>"}, "consulting_rate": <número real>, "support_percentage": <número real>, "exchange_rate": <número real>}
##DATA_END
"""

EXTRACTION_PROMPT = """Analiza toda la conversación anterior y extrae los datos estructurados de la propuesta comercial en formato JSON.

IMPORTANTE: Usa SIEMPRE los valores REALES que el usuario proporcionó. No inventes valores ni uses ejemplos.

Si algún campo no fue especificado explícitamente por el usuario, usa un valor predeterminado razonable, pero PREFIERE los valores reales sobre cualquier predeterminado.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin bloques markdown:

{"company_name": "<nombre>", "sector": "<sector>", "description": "<descripción>", "complexity": "Alta o Media", "active_modules": ["FI", "CO", ...], "revenue": <número>, "pains": {"logistics": "<texto>", "financial": "<texto>", "management": "<texto>"}, "consulting_rate": <número>, "support_percentage": <número>, "exchange_rate": <número>}
"""


# ---------------------------------------------------------------------------
# Funciones de utilidad para extracción y validación de datos estructurados
# ---------------------------------------------------------------------------

def extract_data_block(text):
    """
    Extrae el bloque de datos estructurados entre ##DATA_READY y ##DATA_END.
    Fallback: busca cualquier bloque JSON {...} válido en el texto.
    Retorna el dict parseado o None si no se encuentra JSON válido.
    """
    if not text or not text.strip():
        return None

    # Primary: buscar entre delimitadores
    m = re.search(
        r'##DATA_READY\s*\n?(.*?)##DATA_END',
        text, re.DOTALL
    )
    if m:
        raw = m.group(1).strip()
        # Intentar parse directo
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Intentar limpiando markdown fences
        clean = raw.replace('```json', '').replace('```', '').strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

    # Fallback: buscar cualquier {...} que parezca JSON
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        raw = m.group(0).strip()
        for candidate in [raw, raw.replace('```json', '').replace('```', '').strip()]:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    return None


def validate_proposal_data(data):
    """
    Valida que los datos extraídos tengan la estructura y tipos correctos.
    Retorna (True, None) si es válido, (False, mensaje_error) si no.
    """
    if not isinstance(data, dict):
        return False, "Los datos extraídos no son un diccionario"

    errors = []

    if not isinstance(data.get('company_name'), str) or not data['company_name'].strip():
        errors.append("company_name: debe ser un texto no vacío")

    if not isinstance(data.get('sector'), str) or not data['sector'].strip():
        errors.append("sector: debe ser un texto no vacío")

    modules = data.get('active_modules', [])
    if not isinstance(modules, list):
        errors.append("active_modules: debe ser una lista")
    elif not modules:
        errors.append("active_modules: la lista no debe estar vacía")
    else:
        invalid = [m for m in modules if m not in VALID_MODULES]
        if invalid:
            errors.append(f"active_modules: módulos inválidos ({', '.join(invalid)})")

    revenue = data.get('revenue')
    if revenue is not None:
        if not isinstance(revenue, (int, float)) or not math.isfinite(revenue) or revenue <= 0:
            errors.append("revenue: debe ser un número positivo finito")

    complexity = data.get('complexity')
    if complexity is not None and complexity not in ('Alta', 'Media'):
        errors.append("complexity: debe ser 'Alta' o 'Media'")

    pains = data.get('pains')
    if pains is not None:
        if not isinstance(pains, dict):
            errors.append("pains: debe ser un objeto")
        else:
            for key in ('logistics', 'financial', 'management'):
                val = pains.get(key)
                if val is not None and (not isinstance(val, str)):
                    errors.append(f"pains.{key}: debe ser texto")

    consulting_rate = data.get('consulting_rate')
    if consulting_rate is not None:
        if not isinstance(consulting_rate, (int, float)) or consulting_rate <= 0:
            errors.append("consulting_rate: debe ser un número positivo")

    support_pct = data.get('support_percentage')
    if support_pct is not None:
        if not isinstance(support_pct, (int, float)) or support_pct < 0 or support_pct > 100:
            errors.append("support_percentage: debe ser un número entre 0 y 100")

    exchange_rate = data.get('exchange_rate')
    if exchange_rate is not None:
        if not isinstance(exchange_rate, (int, float)) or exchange_rate <= 0:
            errors.append("exchange_rate: debe ser un número positivo")

    if errors:
        return False, "; ".join(errors)
    return True, None


class AIChatEngine:
    """Motor de chat con IA usando Google Gemini para preventa SAP SEIDOR."""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No se encontró la API Key de Gemini. "
                "Configúrala como variable de entorno GEMINI_API_KEY "
                "o pásala como argumento."
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def _format_history(self, history):
        """Convierte historial al formato de google-genai."""
        formatted = []
        for msg in history:
            role = "user" if msg.get("role") == "user" else "model"
            formatted.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })
        return formatted

    def send_message(self, history, user_message):
        """Envía un mensaje y retorna la respuesta del asistente."""
        gemini_history = self._format_history(history)

        chat = self.client.chats.create(
            model=self.model,
            history=gemini_history,
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
            },
        )
        try:
            response = asyncio.run(asyncio.wait_for(
                asyncio.to_thread(chat.send_message, user_message),
                timeout=GEMINI_TIMEOUT
            ))
        except asyncio.TimeoutError:
            log.error("[Gemini] Timeout al enviar mensaje (%ss)", GEMINI_TIMEOUT)
            raise TimeoutError(f"Gemini no respondió en {GEMINI_TIMEOUT} segundos")
        return response.text

    def extract_proposal_data(self, history):
        """Extrae datos estructurados de toda la conversación."""
        gemini_history = self._format_history(history)

        chat = self.client.chats.create(
            model=self.model,
            history=gemini_history,
            config={
                "temperature": 0.1,
                "top_p": 0.8,
                "max_output_tokens": 2048,
            },
        )
        try:
            response = asyncio.run(asyncio.wait_for(
                asyncio.to_thread(chat.send_message, EXTRACTION_PROMPT),
                timeout=GEMINI_TIMEOUT
            ))
        except asyncio.TimeoutError:
            log.error("[Gemini] Timeout en extracción (%ss)", GEMINI_TIMEOUT)
            return self._default_proposal_data()
        raw_text = response.text.strip()

        parsed = extract_data_block(raw_text)
        if parsed is not None:
            return parsed

        log.error("No se pudo parsear JSON de Gemini. Raw: %s", raw_text[:500])
        return self._default_proposal_data()

    def _default_proposal_data(self):
        """Valores predeterminados seguros por si falla la extracción."""
        return {
            "company_name": "Empresa Peruana S.A.C.",
            "sector": "Servicios Comerciales",
            "description": "Empresa con operaciones en el mercado peruano que busca transformación digital con SAP S/4HANA Cloud.",
            "complexity": "Media",
            "active_modules": ["FI", "CO", "MM", "SD"],
            "revenue": 15000000,
            "pains": {
                "logistics": "Falta de trazabilidad en tiempo real del stock y procesos de compra manuales.",
                "financial": "Cierres contables mensuales lentos y conciliaciones multibancos complejas.",
                "management": "Silos de información desarticulados sin control presupuestal en tiempo real."
            },
            "consulting_rate": 60,
            "support_percentage": 15,
            "exchange_rate": 3.78
        }


