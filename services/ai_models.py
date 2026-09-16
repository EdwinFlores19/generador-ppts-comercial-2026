# -*- coding: utf-8 -*-
"""
Catálogo de variantes de IA disponibles para el chatbot de preventa.

Por qué existe
--------------
El modelo estaba fijado en una variable de entorno (`GEMINI_MODEL` /
`GROQ_MODEL`): cambiarlo obligaba a editar el `.env` del servidor y reiniciar el
proceso. Un consultor quiere poder elegir en el momento — un modelo rápido para
tantear el alcance de un prospecto, uno más capaz para redactar los dolores de
una propuesta que va a presentar mañana.

Qué NO hace
-----------
No cambia el proveedor en caliente: el cliente (Gemini o Groq) se crea al
arrancar con la clave del `.env`, y sin esa clave no hay nada que elegir. Aquí
solo se escoge **la variante dentro del proveedor ya configurado**, que es un
simple parámetro de cada llamada y no requiere reiniciar nada.
"""

# El catálogo es deliberadamente corto: solo variantes que el proyecto puede
# usar de verdad con el plan gratuito de cada proveedor. Añadir un modelo que
# devuelve 404 por no estar en el plan del consultor es peor que no ofrecerlo.
MODELOS = {
    'gemini': [
        {
            'id': 'gemini-2.0-flash',
            'nombre': 'Gemini 2.0 Flash',
            'descripcion': 'Equilibrado y rápido. Es la opción por defecto y la recomendada para preventa.',
            'perfil': 'equilibrado',
            'por_defecto': True,
        },
        {
            'id': 'gemini-2.0-flash-lite',
            'nombre': 'Gemini 2.0 Flash Lite',
            'descripcion': 'El más rápido y barato. Útil para tantear varios prospectos seguidos.',
            'perfil': 'rapido',
            'por_defecto': False,
        },
        {
            'id': 'gemini-2.5-flash',
            'nombre': 'Gemini 2.5 Flash',
            'descripcion': 'Redacta mejor los dolores y el contexto del cliente. Algo más lento.',
            'perfil': 'calidad',
            'por_defecto': False,
        },
    ],
    'groq': [
        {
            'id': 'llama-3.3-70b-versatile',
            'nombre': 'Llama 3.3 70B',
            'descripcion': 'El más capaz de Groq. Opción por defecto para redactar propuestas.',
            'perfil': 'calidad',
            'por_defecto': True,
        },
        {
            'id': 'llama-3.1-8b-instant',
            'nombre': 'Llama 3.1 8B Instant',
            'descripcion': 'Respuesta casi inmediata. Para recoger datos rápido, no para redactar.',
            'perfil': 'rapido',
            'por_defecto': False,
        },
    ],
}

PERFILES = {
    'rapido': 'Prioriza velocidad',
    'equilibrado': 'Equilibrio entre velocidad y calidad',
    'calidad': 'Prioriza calidad de redacción',
}


class ModeloInvalido(ValueError):
    """El modelo pedido no existe para el proveedor activo."""


def listar_modelos(provider):
    """Variantes disponibles para el proveedor activo, para el selector de la UI."""
    provider = (provider or 'gemini').strip().lower()
    return [dict(m) for m in MODELOS.get(provider, [])]


def modelo_por_defecto(provider):
    """
    Variante por defecto del proveedor.

    Respeta `GEMINI_MODEL` / `GROQ_MODEL` si están definidos: quien ya tenía esa
    variable en su `.env` no debe ver cambiar el comportamiento al actualizar.
    """
    import os
    provider = (provider or 'gemini').strip().lower()
    var = 'GROQ_MODEL' if provider == 'groq' else 'GEMINI_MODEL'
    del_entorno = os.getenv(var, '').strip()
    if del_entorno:
        return del_entorno
    for m in MODELOS.get(provider, []):
        if m['por_defecto']:
            return m['id']
    return 'llama-3.3-70b-versatile' if provider == 'groq' else 'gemini-2.0-flash'


def normalizar_modelo(provider, modelo):
    """
    Valida la variante pedida contra el catálogo del proveedor.

    Un id vacío o None devuelve el modelo por defecto. Un id desconocido se
    rechaza en vez de pasarlo al proveedor: así el consultor recibe un mensaje
    claro en lugar de un 404 críptico de la API a mitad de conversación.
    """
    provider = (provider or 'gemini').strip().lower()
    if modelo is None or str(modelo).strip() == '':
        return modelo_por_defecto(provider)

    modelo = str(modelo).strip()
    validos = {m['id'] for m in MODELOS.get(provider, [])}

    # Se admite también el valor del .env aunque no esté en el catálogo: puede
    # ser un modelo nuevo o uno al que ese consultor sí tiene acceso.
    validos.add(modelo_por_defecto(provider))

    if modelo not in validos:
        raise ModeloInvalido(
            f"La variante '{modelo}' no está disponible para {provider}. "
            f"Opciones: {', '.join(sorted(validos))}."
        )
    return modelo
