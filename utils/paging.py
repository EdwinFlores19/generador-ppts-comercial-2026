"""
Paginación compartida por los listados de la API.

Vive aquí y no duplicado en cada blueprint porque este proyecto ya se llevó un
susto con helpers copiados: `escapeHtml` y el patrón de `fetch` estaban
duplicados en las dos plantillas y las dos copias habían divergido (de ahí
`static/common.js`). El listado de propuestas y el de conversaciones necesitan
exactamente el mismo saneo de `limit`/`offset`.
"""

# Un consultor no revisa más de un puñado de propuestas por sesión: 50 llena la
# tabla sin traer megabytes de preview_json.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Tope del offset: sin él, un `?offset=999999999999` obliga a SQLite a recorrer
# la tabla entera para no devolver nada.
MAX_OFFSET = 10_000_000


def _entero_acotado(args, nombre, defecto, minimo, maximo):
    """Lee un entero de la query string; ante cualquier basura, usa el defecto."""
    crudo = args.get(nombre)
    if crudo is None or str(crudo).strip() == '':
        return defecto
    try:
        valor = int(str(crudo).strip())
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, valor))


def parse_paging(args, page_size=DEFAULT_PAGE_SIZE, max_page_size=MAX_PAGE_SIZE):
    """
    Devuelve (limit, offset) saneados a partir de `request.args`.

    Los valores fuera de rango se recortan en vez de rechazarse: un listado es
    una lectura idempotente y devolver 400 por un `?limit=0` solo rompe la
    página sin proteger nada.
    """
    limit = _entero_acotado(args, 'limit', page_size, 1, max_page_size)
    offset = _entero_acotado(args, 'offset', 0, 0, MAX_OFFSET)
    return limit, offset


def paging_headers(resp, total, limit, offset):
    """Adjunta la metadata de paginación a la respuesta y la devuelve.

    Va en cabeceras y no en el cuerpo a propósito: los listados devuelven un
    array plano y tanto los tests como el frontend dependen de esa forma.
    """
    resp.headers['X-Total-Count'] = str(total)
    resp.headers['X-Limit'] = str(limit)
    resp.headers['X-Offset'] = str(offset)
    # Necesario si algún día se consume la API desde otro origen: sin esto el
    # navegador oculta las cabeceras personalizadas al JavaScript.
    resp.headers['Access-Control-Expose-Headers'] = 'X-Total-Count, X-Limit, X-Offset'
    return resp
