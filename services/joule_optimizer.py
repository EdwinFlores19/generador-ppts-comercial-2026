import re
import logging

log = logging.getLogger("joule_optimizer")

# Definición de Palabras Mágicas Oficiales de SEIDOR Joule
MAGIC_WORDS = ["MOSTRAR", "LISTAR", "BUSCAR", "ABRIR"]

# Mapeo de términos incorrectos / subjetivos a correctos y objetivos
REPLACEMENT_FACTURAS_VENCIDAS = "facturas vencidas"
TERM_REPLACEMENTS = {
    r"\bclientes morosos\b": REPLACEMENT_FACTURAS_VENCIDAS,
    r"\bmorosos\b": REPLACEMENT_FACTURAS_VENCIDAS,
    r"\bclientes con problemas de pago\b": REPLACEMENT_FACTURAS_VENCIDAS,
    r"\bcomportamiento malo\b": "retrasos en entregas",
    r"\bentregas lentas\b": "desviaciones en tiempos de entrega"
}

def clean_and_standardize_prompt(prompt: str) -> str:
    """
    Sanitiza y estandariza un prompt básico de usuario antes de evaluarlo.
    """
    if not prompt:
        return ""
    # Quitar múltiples espacios en blanco y dejarlo limpio
    return re.sub(r"\s+", " ", prompt).strip()

def _apply_term_replacements(query_lower, optimized, reasons):
    """Reemplaza términos subjetivos por su versión objetiva."""
    for pattern, replacement in TERM_REPLACEMENTS.items():
        if re.search(pattern, query_lower, re.IGNORECASE):
            optimized = re.sub(pattern, replacement, optimized, flags=re.IGNORECASE)
            reasons.append(f"Se reemplazó término subjetivo/prohibido por '{replacement}'")
    return optimized


def _handle_transactional(query_lower, optimized, reasons):
    """Convierte acciones de creación directa a comandos ABRIR en Fiori."""
    creation_patterns = [
        (r"\bcrear (una |el |un )?orden de servicio\b", "ABRIR Crear Orden de Servicio (App Fiori)"),
        (r"\bcrear (una |el |un )?solicitud de pedido\b", "ABRIR Crear Solicitud de Pedido (App Fiori)"),
        (r"\bcrear (una |el |un )?orden de compra\b", "ABRIR Crear Orden de Compra (App Fiori)"),
        (r"\bcrear (una |el |un )?pedido de cliente\b", "ABRIR Crear Pedido de Cliente (App Fiori)"),
        (r"\brealizar (el )?picking.*pedido (\d+)\b", r"ABRIR App para Picking de Pedido \2"),
        (r"\bcrear entrega de salida.*pedido (\d+)\b", r"ABRIR App para Entrega de Salida de Pedido \1"),
        (r"\bsimular y ejecutar el último ciclo de distribución\b", "ABRIR Distribución de Costos (App Fiori) - Nota: Joule requiere parámetros específicos para simulación")
    ]
    for pattern, action_replace in creation_patterns:
        if re.search(pattern, query_lower, re.IGNORECASE):
            optimized = re.sub(pattern, action_replace, optimized, flags=re.IGNORECASE)
            reasons.append("Joule no crea datos directamente. Se redirigió al aplicativo Fiori usando ABRIR")
            return optimized, True
    return optimized, False


def _normalize_magic_word(query_lower, optimized, reasons):
    """Normaliza la palabra mágica inicial si existe, y aplica correcciones especiales."""
    magic_map = {
        r"^(mostrar|muéstrame|muestra|lístame|listame|quiero ver|ver)\b": "MOSTRAR",
        r"^(listar|lista)\b": "LISTAR",
        r"^(buscar|busca)\b": "BUSCAR",
        r"^(abrir|abre|ir a)\b": "ABRIR"
    }
    for pattern, magic_word in magic_map.items():
        if re.match(pattern, query_lower, re.IGNORECASE):
            optimized = re.sub(pattern, magic_word, optimized, count=1, flags=re.IGNORECASE)
            break
    else:
        return optimized, False

    # Corrección: "buscar contrato ... mayor valor" -> MOSTRAR
    if "contrato" in query_lower and "mayor valor" in query_lower and "buscar" in query_lower:
        optimized = re.sub(r"^BUSCAR", "MOSTRAR", optimized, flags=re.IGNORECASE)
        reasons.append("Se cambió 'BUSCAR' a 'MOSTRAR' para consultas de agrupaciones/valores máximos")
    # Corrección: "buscar facturas pendientes" -> LISTAR
    if "facturas pendientes" in query_lower and "buscar" in query_lower:
        optimized = re.sub(r"^BUSCAR", "LISTAR", optimized, flags=re.IGNORECASE)
        reasons.append("Se cambió 'BUSCAR' a 'LISTAR' para grupos de facturas pendientes")
    return optimized, True


def _infer_magic_word(query_lower, optimized, reasons):
    """Infierer la palabra mágica más apropiada cuando no se detecta ninguna."""
    if any(w in query_lower for w in ["factura", "pedido", "orden", "lista", "proveedor"]):
        if any(w in query_lower for w in ["lista", "todos", "los"]):
            optimized = "LISTAR " + optimized
            reasons.append("Se antepuso la palabra mágica LISTAR para grupos de elementos")
        else:
            optimized = "BUSCAR " + optimized
            reasons.append("Se antepuso la palabra mágica BUSCAR para elementos específicos")
    else:
        optimized = "MOSTRAR " + optimized
        reasons.append("Se antepuso la palabra mágica general MOSTRAR")
    return optimized


def optimize_prompt(user_query: str) -> dict:
    """
    Analiza una consulta de usuario para SAP Joule y la optimiza según las reglas de SEIDOR:
    1. Reemplazo de términos subjetivos ("morosos" -> "facturas vencidas").
    2. Corrección e inserción de Palabras Mágicas (MOSTRAR, LISTAR, BUSCAR, ABRIR).
    3. Conversión de flujos de creación/acciones transaccionales directas a comandos "ABRIR" (Fiori App).

    Retorna un diccionario con:
    - 'original': Query original
    - 'optimized': Query optimizada
    - 'is_valid': True si la query original ya cumplía con los estándares, False si requirió optimización.
    - 'reason': Explicación de los cambios realizados.
    """
    query = clean_and_standardize_prompt(user_query)
    optimized = query
    reasons = []
    query_lower = query.lower()

    optimized = _apply_term_replacements(query_lower, optimized, reasons)

    optimized, is_transactional = _handle_transactional(query_lower, optimized, reasons)

    if not is_transactional:
        optimized, starts_with_magic = _normalize_magic_word(query_lower, optimized, reasons)
        if not starts_with_magic:
            optimized = _infer_magic_word(query_lower, optimized, reasons)

    optimized = re.sub(r"^(MOSTRAR|LISTAR|BUSCAR|ABRIR)\s+(MOSTRAR|LISTAR|BUSCAR|ABRIR)\s+", r"\1 ", optimized)

    return {
        "original": query,
        "optimized": optimized,
        "is_valid": (query == optimized),
        "reasons": reasons if reasons else ["Cumple con las directrices de SEIDOR"]
    }

if __name__ == "__main__":
    # Test rápido
    test_queries = [
        "Muéstrame el saldo de clientes morosos",
        "crear una orden de servicio",
        "buscar contrato de compras con mayor valor",
        "buscar las facturas pendientes de clientes",
        "realizar el picking de la entrega de salida del pedido 80000009",
        "Mostrar lista de centros de costo existentes"
    ]
    
    print("=== TEST DE OPTIMIZADOR JOULE ===")
    for q in test_queries:
        res = optimize_prompt(q)
        print(f"\nOriginal:  {res['original']}")
        print(f"Optimizado: {res['optimized']}")
        print(f"Válido:     {res['is_valid']}")
        print(f"Razones:    {', '.join(res['reasons'])}")
