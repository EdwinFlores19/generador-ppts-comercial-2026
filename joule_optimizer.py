import re

# Definición de Palabras Mágicas Oficiales de SEIDOR Joule
MAGIC_WORDS = ["MOSTRAR", "LISTAR", "BUSCAR", "ABRIR"]

# Mapeo de términos incorrectos / subjetivos a correctos y objetivos
TERM_REPLACEMENTS = {
    r"\bclientes morosos\b": "facturas vencidas",
    r"\bmorosos\b": "facturas vencidas",
    r"\bclientes con problemas de pago\b": "facturas vencidas",
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
    
    # 1. Aplicar reemplazos de términos subjetivos
    query_lower = query.lower()
    for pattern, replacement in TERM_REPLACEMENTS.items():
        if re.search(pattern, query_lower, re.IGNORECASE):
            optimized = re.sub(pattern, replacement, optimized, flags=re.IGNORECASE)
            reasons.append(f"Se reemplazó término subjetivo/prohibido por '{replacement}'")
            
    # 2. Manejar casos transaccionales (creación directa o ejecución física que Joule no puede hacer directamente)
    # Por ejemplo: "crear una orden de servicio", "realizar el picking"
    creation_patterns = [
        (r"\bcrear (una |el |un )?orden de servicio\b", "ABRIR Crear Orden de Servicio (App Fiori)"),
        (r"\bcrear (una |el |un )?solicitud de pedido\b", "ABRIR Crear Solicitud de Pedido (App Fiori)"),
        (r"\bcrear (una |el |un )?orden de compra\b", "ABRIR Crear Orden de Compra (App Fiori)"),
        (r"\bcrear (una |el |un )?pedido de cliente\b", "ABRIR Crear Pedido de Cliente (App Fiori)"),
        (r"\brealizar (el )?picking.*pedido (\d+)\b", r"ABRIR App para Picking de Pedido \2"),
        (r"\bcrear entrega de salida.*pedido (\d+)\b", r"ABRIR App para Entrega de Salida de Pedido \1"),
        (r"\bsimular y ejecutar el último ciclo de distribución\b", "ABRIR Distribución de Costos (App Fiori) - Nota: Joule requiere parámetros específicos para simulación")
    ]
    
    is_transactional = False
    for pattern, action_replace in creation_patterns:
        if re.search(pattern, query_lower, re.IGNORECASE):
            if r"\3" in action_replace or r"\2" in action_replace:
                optimized = re.sub(pattern, action_replace, optimized, flags=re.IGNORECASE)
            else:
                optimized = action_replace
            reasons.append("Joule no crea datos directamente. Se redirigió al aplicativo Fiori usando ABRIR")
            is_transactional = True
            break
            
    # 3. Validar Palabras Mágicas si no es una acción transaccional ya resuelta
    if not is_transactional:
        # Verificar si comienza con una palabra mágica
        # Mapear variaciones comunes a las oficiales
        magic_map = {
            r"^(mostrar|muéstrame|muestra|lístame|listame|quiero ver|ver)\b": "MOSTRAR",
            r"^(listar|lista)\b": "LISTAR",
            r"^(buscar|busca)\b": "BUSCAR",
            r"^(abrir|abre|ir a)\b": "ABRIR"
        }
        
        starts_with_magic = False
        matched_magic_key = None
        
        for pattern, magic_word in magic_map.items():
            if re.match(pattern, query_lower, re.IGNORECASE):
                starts_with_magic = True
                matched_magic_key = magic_word
                # Normalizar la palabra inicial
                optimized = re.sub(pattern, magic_word, optimized, count=1, flags=re.IGNORECASE)
                break
                
        # Corrección de casos específicos documentados en los fallos
        # "buscar contrato de compras con mayor valor" -> Falla porque buscar es para items individuales.
        # Debe ser "MOSTRAR contratos de compras con mayor valor" o "LISTAR".
        if "contrato" in query_lower and "mayor valor" in query_lower and "buscar" in query_lower:
            optimized = re.sub(r"^BUSCAR", "MOSTRAR", optimized, flags=re.IGNORECASE)
            reasons.append("Se cambió 'BUSCAR' a 'MOSTRAR' para consultas de agrupaciones/valores máximos")
            starts_with_magic = True
            
        # "buscar las facturas pendientes de clientes" -> Debe ser LISTAR
        if "facturas pendientes" in query_lower and "buscar" in query_lower:
            optimized = re.sub(r"^BUSCAR", "LISTAR", optimized, flags=re.IGNORECASE)
            reasons.append("Se cambió 'BUSCAR' a 'LISTAR' para grupos de facturas pendientes")
            starts_with_magic = True
            
        if not starts_with_magic:
            # Si no empieza con palabra mágica, inferir la mejor
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
                
    # Sanitizar dobles palabras mágicas si ocurrieran accidentalmente
    optimized = re.sub(r"^(MOSTRAR|LISTAR|BUSCAR|ABRIR)\s+(MOSTRAR|LISTAR|BUSCAR|ABRIR)\s+", r"\1 ", optimized)
    
    # Determinar validez original
    is_valid = (query == optimized)
    
    return {
        "original": query,
        "optimized": optimized,
        "is_valid": is_valid,
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
