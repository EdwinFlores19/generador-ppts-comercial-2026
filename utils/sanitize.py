import re

MAX_CHAT_MESSAGE_LEN = 4000


def sanitize_input_string(s):
    """Sanitiza campos cortos de formulario (nombre de empresa, sector, títulos)."""
    if not s:
        return ""
    sanitized = re.sub(r"['\"\;\*]|--", "", s)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def sanitize_chat_message(s):
    """
    Sanitiza mensajes de chat sin mutilar el contenido del usuario
    (ej. 'S/4HANA', comillas o montos como S/. 150,000 deben conservarse).
    Solo remueve caracteres de control y limita la longitud.
    """
    if not s:
        return ""
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(s))
    return sanitized.strip()[:MAX_CHAT_MESSAGE_LEN]
