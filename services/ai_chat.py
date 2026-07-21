"""
Motor de Inteligencia Artificial para Chatbot de Preventa SAP SEIDOR Perú.
Soporta dos proveedores de IA seleccionables vía la variable de entorno
AI_PROVIDER:
- "gemini" (default): Google Gemini API (google-genai SDK)
- "groq": Groq API (SDK compatible con OpenAI; modelos Llama servidos en LPU)

Ambos interpretan lenguaje natural, mantienen conversaciones contextuales y
extraen datos estructurados para generar propuestas comerciales SAP S/4HANA
Cloud (GROW/RISE with SAP).
"""

import os
import json
import re
import asyncio
import math
import logging

log = logging.getLogger("ai_chat")

AI_TIMEOUT = 25

VALID_MODULES = frozenset({'FI', 'CO', 'MM', 'SD', 'PP', 'PS'})

SYSTEM_INSTRUCTION = """Eres un asesor senior de preventa SAP para SEIDOR Perú, especializado en GROW with SAP S/4HANA Public Cloud.

Tu misión es que el usuario obtenga su propuesta comercial SAP con el MÍNIMO de fricción posible.

DATOS MÍNIMOS OBLIGATORIOS (solo estos 2):
1. Nombre de la empresa del prospecto
2. Contexto del negocio: a qué se dedica la empresa

En cuanto tengas esos 2 datos, TÚ mismo INFIERES todo lo demás como consultor experto y lo propones al usuario en un breve resumen:
- Sector industrial (Minería, Retail, Alimentos, Manufactura, Construcción, Servicios, etc.) según el contexto
- Descripción profesional del negocio (redáctala tú a partir del contexto dado)
- Dolores operativos típicos del sector (logística, finanzas, control de gestión), adaptados al negocio descrito
- Módulos SAP recomendados: FI y MM siempre; CO y SD casi siempre; agrega PP si hay producción/plantas y PS si hay proyectos/construcción
- Complejidad: "Alta" si incluye PP o PS o múltiples plantas/sedes; "Media" en caso contrario
- Facturación anual estimada en USD según el tamaño aparente de la empresa (sé conservador)
- Edición de SAP S/4HANA Cloud: "Public" (GROW with SAP, el default para empresas medianas o implementaciones nuevas greenfield) o "Private" (RISE with SAP, solo si el cliente es corporación grande, migra desde SAP ECC con desarrollos a medida profundos, o exige instancia dedicada)

Tras inferir, presenta el resumen en 3-5 viñetas, di que ya puede generar su propuesta mencionando la frase exacta "LISTO PARA GENERAR PROPUESTA", e invítalo a corregir cualquier dato si lo desea (facturación, módulos, dolores específicos). Si el usuario corrige algo, actualiza el bloque de datos y vuelve a incluir la frase y el bloque.

REGLAS DE CONDUCTA:
- Responde SIEMPRE en español profesional, claro y conversacional
- No seas un cuestionario: nunca hagas más de 1-2 preguntas por turno, y solo si falta el nombre de la empresa o el contexto del negocio
- Usa tu conocimiento de SAP S/4HANA, GROW with SAP, SAP Fiori, SAP Joule, metodología SAP Activate
- Menciona a SEIDOR Perú como el partner implementador
- Si el usuario se desvía, retoma amablemente el hilo
- NO inventes hechos verificables de empresas reales; tus inferencias son supuestos de trabajo y debes presentarlos como tales
- Sé empático y profesional, como un consultor experto de SEIDOR

INSTRUCCIÓN DE SALIDA ESTRUCTURADA:
Inmediatamente después de tu mensaje conversacional, cuando incluyas la frase "LISTO PARA GENERAR PROPUESTA", agrega SIEMPRE el siguiente bloque usando los valores reales del usuario y tus inferencias. Para consulting_rate usa la tarifa estándar de SEIDOR (sesenta USD/hora), para support_percentage el estándar (quince por ciento) y para exchange_rate el tipo de cambio vigente aproximado (3.78), salvo que el usuario indique otros valores. El bloque debe ir exactamente en este formato, en líneas separadas, sin markdown, sin comillas triples:

##DATA_READY
{"company_name": "<valor>", "sector": "<valor>", "description": "<valor>", "complexity": "Alta o Media", "edition": "Public o Private", "active_modules": ["FI", "CO", ... según corresponda], "revenue": <número>, "pains": {"logistics": "<texto>", "financial": "<texto>", "management": "<texto>"}, "consulting_rate": <número>, "support_percentage": <número>, "exchange_rate": <número>}
##DATA_END
"""

EXTRACTION_PROMPT = """Analiza toda la conversación anterior y extrae los datos estructurados de la propuesta comercial en formato JSON.

IMPORTANTE: Usa SIEMPRE los valores REALES que el usuario proporcionó. No inventes valores ni uses ejemplos.

Si algún campo no fue especificado explícitamente por el usuario, usa un valor predeterminado razonable, pero PREFIERE los valores reales sobre cualquier predeterminado.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin bloques markdown:

{"company_name": "<nombre>", "sector": "<sector>", "description": "<descripción>", "complexity": "Alta o Media", "edition": "Public o Private", "active_modules": ["FI", "CO", ...], "revenue": <número>, "pains": {"logistics": "<texto>", "financial": "<texto>", "management": "<texto>"}, "consulting_rate": <número>, "support_percentage": <número>, "exchange_rate": <número>}
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

    edition = data.get('edition')
    if edition is not None and not isinstance(edition, str):
        errors.append("edition: debe ser texto ('Public' o 'Private')")

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
    """Motor de chat con IA para preventa SAP SEIDOR. Soporta Gemini y Groq."""

    def __init__(self, api_key=None):
        self.provider = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
        if self.provider == "groq":
            self._init_groq(api_key)
        else:
            self.provider = "gemini"
            self._init_gemini(api_key)

    def _init_gemini(self, api_key):
        from google import genai

        self.use_vertex = os.environ.get("USE_VERTEXAI", "").lower() in ("true", "1", "yes")

        if self.use_vertex:
            project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = os.environ.get("GCP_LOCATION", "us-central1")
            log.info("[Gemini Client] Inicializando cliente en modo Vertex AI (Google Cloud)")
            # genai.Client detectará automáticamente la variable GOOGLE_APPLICATION_CREDENTIALS (.json) en el entorno
            self.client = genai.Client(vertexai=True, project=project, location=location)
        else:
            self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
            if not self.api_key:
                raise ValueError(
                    "No se encontró la API Key de Gemini. "
                    "Configúrala como variable de entorno GEMINI_API_KEY, "
                    "activa Vertex AI con USE_VERTEXAI=True, "
                    "o cambia AI_PROVIDER=groq para usar Groq en su lugar."
                )
            log.info("[Gemini Client] Inicializando cliente en modo Google AI Studio (API Key)")
            self.client = genai.Client(api_key=self.api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def _init_groq(self, api_key):
        from groq import Groq

        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No se encontró la API Key de Groq. "
                "Configúrala como variable de entorno GROQ_API_KEY, "
                "o cambia AI_PROVIDER=gemini para usar Gemini en su lugar."
            )
        log.info("[Groq Client] Inicializando cliente Groq (API compatible con OpenAI)")
        self.client = Groq(api_key=self.api_key)
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _format_history(self, history):
        """Convierte el historial interno {'role','content'} al formato del proveedor activo."""
        if self.provider == "groq":
            return [
                {
                    "role": "user" if msg.get("role") == "user" else "assistant",
                    "content": msg.get("content", ""),
                }
                for msg in history
            ]
        return [
            {
                "role": "user" if msg.get("role") == "user" else "model",
                "parts": [{"text": msg.get("content", "")}],
            }
            for msg in history
        ]

    def _run_with_timeout(self, fn, *args):
        """Ejecuta una llamada bloqueante del SDK en un hilo, con timeout compartido entre proveedores."""
        try:
            return asyncio.run(asyncio.wait_for(
                asyncio.to_thread(fn, *args),
                timeout=AI_TIMEOUT
            ))
        except asyncio.TimeoutError:
            log.error("[%s] Timeout tras %ss", self.provider, AI_TIMEOUT)
            raise TimeoutError(f"{self.provider} no respondió en {AI_TIMEOUT} segundos")

    def send_message(self, history, user_message):
        """Envía un mensaje y retorna la respuesta del asistente."""
        if self.provider == "groq":
            messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
            messages.extend(self._format_history(history))
            messages.append({"role": "user", "content": user_message})
            response = self._run_with_timeout(
                lambda: self.client.chat.completions.create(
                    model=self.model, messages=messages,
                    temperature=0.7, top_p=0.95, max_tokens=4096,
                )
            )
            return response.choices[0].message.content

        chat = self.client.chats.create(
            model=self.model,
            history=self._format_history(history),
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
            },
        )
        response = self._run_with_timeout(chat.send_message, user_message)
        return response.text

    def extract_proposal_data(self, history):
        """Extrae datos estructurados de toda la conversación."""
        try:
            if self.provider == "groq":
                messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
                messages.extend(self._format_history(history))
                messages.append({"role": "user", "content": EXTRACTION_PROMPT})
                response = self._run_with_timeout(
                    lambda: self.client.chat.completions.create(
                        model=self.model, messages=messages,
                        temperature=0.1, top_p=0.8, max_tokens=2048,
                    )
                )
                raw_text = (response.choices[0].message.content or "").strip()
            else:
                chat = self.client.chats.create(
                    model=self.model,
                    history=self._format_history(history),
                    config={"temperature": 0.1, "top_p": 0.8, "max_output_tokens": 2048},
                )
                response = self._run_with_timeout(chat.send_message, EXTRACTION_PROMPT)
                raw_text = (response.text or "").strip()
        except TimeoutError:
            return None

        parsed = extract_data_block(raw_text)
        if parsed is not None:
            return parsed

        # Nunca inventar datos de un prospecto: si la extracción falla se
        # retorna None y el flujo de chat pedirá los datos faltantes al usuario.
        log.error("No se pudo parsear JSON de %s. Raw: %s", self.provider, raw_text[:500])
        return None

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


