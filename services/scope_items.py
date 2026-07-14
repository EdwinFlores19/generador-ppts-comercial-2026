"""
Catálogo de Scope Items de SAP Best Practices para SAP S/4HANA Cloud.

Los IDs corresponden a los scope items estándar de SAP Best Practices
(SAP Best Practices Explorer / SAP Signavio Process Navigator) usados
habitualmente en propuestas GROW with SAP (Public Edition).

NOTA PARA CONSULTORES SEIDOR: estos IDs son referenciales y deben
validarse contra el release vigente de SAP Best Practices antes de
comprometer el alcance contractual. Editar este catálogo es seguro:
la lámina de alcance del PPT se genera automáticamente desde aquí.
"""

# Ediciones soportadas de SAP S/4HANA Cloud
EDITION_PUBLIC = "Public"
EDITION_PRIVATE = "Private"
VALID_EDITIONS = (EDITION_PUBLIC, EDITION_PRIVATE)

EDITION_LABELS = {
    EDITION_PUBLIC: {
        "nombre": "SAP S/4HANA Cloud, Public Edition",
        "programa": "GROW with SAP",
        "descripcion": "Nube pública multi-tenant con mejores prácticas preconfiguradas, "
                       "actualizaciones automáticas semestrales y time-to-value acelerado.",
    },
    EDITION_PRIVATE: {
        "nombre": "SAP S/4HANA Cloud, Private Edition",
        "programa": "RISE with SAP",
        "descripcion": "Instancia dedicada en la nube con máxima flexibilidad de extensión, "
                       "ideal para migraciones desde SAP ECC con desarrollos a medida.",
    },
}

# Scope Items por módulo: lista de (id, nombre en español)
SCOPE_ITEMS_CATALOG = {
    "FI": [
        ("J58", "Contabilidad General y Cierre Financiero"),
        ("J59", "Gestión de Cuentas por Cobrar"),
        ("J60", "Gestión de Cuentas por Pagar"),
        ("J62", "Contabilidad de Activos Fijos"),
        ("BFB", "Gestión Básica de Cuentas Bancarias"),
    ],
    "CO": [
        ("J54", "Contabilidad de Costos Indirectos (Overhead)"),
        ("J55", "Análisis de Márgenes y Rentabilidad"),
    ],
    "MM": [
        ("J45", "Aprovisionamiento de Materiales Directos"),
        ("BNX", "Compras de Consumibles"),
        ("22Z", "Aprovisionamiento de Servicios"),
        ("18J", "Gestión de Solicitudes de Compra (Requisitioning)"),
    ],
    "SD": [
        ("BD9", "Venta desde Stock"),
        ("BDG", "Ofertas y Cotizaciones de Venta"),
        ("BD3", "Ventas con Despacho Directo de Terceros"),
    ],
    "PP": [
        ("BJ5", "Fabricación contra Stock – Manufactura Discreta"),
        ("BJ8", "Fabricación contra Pedido – Planificación y Ensamblaje"),
    ],
    "PS": [
        ("J11", "Gestión Financiera de Proyectos de Cliente"),
        ("1YF", "Control Financiero de Proyectos (CAPEX/OPEX)"),
    ],
}


def normalize_edition(value):
    """
    Normaliza cualquier variante ('private', 'Privada', 'RISE', etc.) a
    'Public' o 'Private'. Ante valor desconocido retorna 'Public' (default GROW).
    """
    if isinstance(value, str):
        v = value.strip().lower()
        if v.startswith("priv") or "rise" in v:
            return EDITION_PRIVATE
    return EDITION_PUBLIC


def get_scope_items(active_modules):
    """
    Retorna el subconjunto ordenado del catálogo para los módulos activos.

    Parámetros:
    - active_modules (iterable): módulos SAP activos, ej. ['FI', 'CO', 'MM'].

    Retorna:
    - list[tuple]: lista de (módulo, [(id, nombre), ...]) en orden canónico.
    """
    result = []
    for mod in ("FI", "CO", "MM", "SD", "PP", "PS"):
        if mod in active_modules and mod in SCOPE_ITEMS_CATALOG:
            result.append((mod, SCOPE_ITEMS_CATALOG[mod]))
    return result
