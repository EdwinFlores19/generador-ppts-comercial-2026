import re

MAX_CHAT_MESSAGE_LEN = 4000
MAX_FIELD_LEN = 200

# Caracteres de control ASCII (excepto tab/LF/CR que se normalizan como espacio)
_CONTROL_CHARS = r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"


def sanitize_input_string(s):
    """
    Sanitiza campos cortos de formulario (nombre de empresa, sector, títulos).

    Preserva la puntuación legítima de razones sociales peruanas —apóstrofos
    ("D'Onofrio"), ampersands ("Backus & Johnston"), puntos ("S.A.C."), guiones
    y barras— porque el nombre se imprime tal cual en la propuesta del cliente.

    La seguridad no depende de esta función: SQLite usa consultas
    parametrizadas, los nombres de archivo se saneen aparte en las rutas, el
    HTML se escapa en el frontend (escapeHtml) y python-pptx escapa el XML.
    Aquí solo se eliminan caracteres de control y corchetes angulares (defensa
    en profundidad contra HTML) y se limita la longitud para no romper el diseño
    de las láminas.
    """
    if not s:
        return ""
    sanitized = re.sub(_CONTROL_CHARS, "", str(s))
    sanitized = re.sub(r"[<>]", "", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:MAX_FIELD_LEN]


def sanitize_chat_message(s):
    """
    Sanitiza mensajes de chat sin mutilar el contenido del usuario
    (ej. 'S/4HANA', comillas o montos como S/. 150,000 deben conservarse).
    Solo remueve caracteres de control y limita la longitud.
    """
    if not s:
        return ""
    sanitized = re.sub(_CONTROL_CHARS, "", str(s))
    return sanitized.strip()[:MAX_CHAT_MESSAGE_LEN]
