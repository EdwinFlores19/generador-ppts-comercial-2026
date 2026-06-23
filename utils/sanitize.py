import re

def sanitize_input_string(s):
    if not s:
        return ""
    sanitized = re.sub(r"['\"\;/\*]|--", "", s)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized
