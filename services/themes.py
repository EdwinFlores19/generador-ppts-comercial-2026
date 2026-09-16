# -*- coding: utf-8 -*-
"""
Temas visuales del deck: colores y tipografía.

Por qué existe
--------------
Los colores vivían como constantes sueltas en `ppt_generator`, así que la única
forma de cambiar el aspecto de una propuesta era editar el código. Un consultor
necesita, como mínimo, poder alinear la propuesta con la marca del cliente o
usar una variante clara para imprimir.

El contraste se valida
----------------------
Este proyecto ya sufrió una vez el fallo de **texto blanco sobre fondo blanco**
(se elegía un layout con foto y el texto desaparecía). Con colores libres ese
fallo vuelve a ser posible, así que un tema personalizado no se acepta si su
texto no contrasta lo suficiente con su fondo: se calcula el ratio WCAG y se
rechaza por debajo de 4.5:1, el mínimo legible para texto normal.
"""
import re

# Ratio de contraste mínimo (WCAG 2.1 AA para texto normal).
CONTRASTE_MINIMO = 4.5

# Los títulos van a 20 pt o más, que es "texto grande" para WCAG: 3:1 basta.
CONTRASTE_MINIMO_TITULO = 3.0

_HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')

# Tipografías admitidas. Se limitan a fuentes presentes en cualquier Windows y
# Office: una fuente que el cliente no tenga instalada hace que PowerPoint
# sustituya por otra y descuadre todas las láminas.
FUENTES_SEGURAS = (
    'Arial',
    'Calibri',
    'Segoe UI',
    'Verdana',
    'Tahoma',
    'Georgia',
    'Times New Roman',
    'Trebuchet MS',
)

# Claves de color que define un tema. Son las mismas que usa ppt_generator.
CLAVES_COLOR = (
    'primary',      # Fondo de cabeceras y barras; azul noche en SEIDOR
    'royal',        # Acento intermedio
    'secondary',    # Acento claro, series de gráficos, iconos
    'background',   # Fondo de tarjetas y zonas claras
    'white',        # Texto sobre primary/royal
    'text',         # Texto sobre background
    'gray',         # Texto secundario
    'card_line',    # Contorno de tarjetas
)


class TemaInvalido(ValueError):
    """El tema recibido no es utilizable (color mal formado o sin contraste)."""


def _normalizar_hex(valor, clave):
    if not isinstance(valor, str):
        raise TemaInvalido(f"El color '{clave}' debe ser una cadena hexadecimal como '#07153A'.")
    m = _HEX.match(valor.strip())
    if not m:
        raise TemaInvalido(
            f"El color '{clave}' ('{valor}') no es un hexadecimal de 6 dígitos. "
            f"Formato esperado: '#RRGGBB'."
        )
    return '#' + m.group(1).upper()


def hex_a_rgb(valor):
    """'#07153A' -> (7, 21, 58)."""
    h = _normalizar_hex(valor, 'color').lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminancia_relativa(rgb):
    """Luminancia relativa WCAG de un color sRGB."""
    def canal(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio_contraste(color_a, color_b):
    """
    Ratio de contraste WCAG entre dos colores (de 1:1 a 21:1).

    Se usa para no dejar pasar combinaciones ilegibles: este proyecto ya tuvo
    texto blanco sobre fondo blanco en producción.
    """
    la = _luminancia_relativa(hex_a_rgb(color_a))
    lb = _luminancia_relativa(hex_a_rgb(color_b))
    claro, oscuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (oscuro + 0.05)


# ---------------------------------------------------------------------------
# Catálogo de temas
# ---------------------------------------------------------------------------
# 'seidor' es el tema por defecto y reproduce exactamente los colores extraídos
# de la plantilla corporativa: cambiarlo altera TODAS las propuestas nuevas.
TEMAS = {
    'seidor': {
        'nombre': 'SEIDOR Corporativo',
        'descripcion': 'Paleta oficial extraída de la plantilla de SEIDOR. Es la opción por defecto.',
        'colores': {
            'primary': '#07153A',
            'royal': '#263C7A',
            'secondary': '#66B6FF',
            'background': '#F6F6F6',
            'white': '#FFFFFF',
            'text': '#242528',
            'gray': '#919191',
            'card_line': '#D9E2F2',
        },
        'fuente_titulos': 'Arial',
        'fuente_cuerpo': 'Arial',
    },
    'seidor-claro': {
        'nombre': 'SEIDOR Claro (impresión)',
        'descripcion': 'Misma marca con fondos claros: gasta menos tinta y se lee mejor impreso.',
        'colores': {
            'primary': '#1B3A6B',
            'royal': '#2F5596',
            'secondary': '#3D8FD1',
            'background': '#FFFFFF',
            'white': '#FFFFFF',
            'text': '#1A1A1A',
            'gray': '#6B6B6B',
            'card_line': '#C9D6E8',
        },
        'fuente_titulos': 'Arial',
        'fuente_cuerpo': 'Arial',
    },
    'grafito': {
        'nombre': 'Grafito Ejecutivo',
        'descripcion': 'Grises neutros con acento azul. Sobrio para comités de dirección.',
        'colores': {
            'primary': '#2B2F36',
            'royal': '#414751',
            'secondary': '#7FB2E5',
            'background': '#F2F3F5',
            'white': '#FFFFFF',
            'text': '#1F2126',
            'gray': '#83888F',
            'card_line': '#D5D8DD',
        },
        'fuente_titulos': 'Calibri',
        'fuente_cuerpo': 'Calibri',
    },
    'esmeralda': {
        'nombre': 'Esmeralda Agroindustrial',
        'descripcion': 'Verdes corporativos, pensado para agroindustria, pesca y sostenibilidad.',
        'colores': {
            'primary': '#0B3D2E',
            'royal': '#15614A',
            'secondary': '#4FBF95',
            'background': '#F3F8F5',
            'white': '#FFFFFF',
            'text': '#1B2420',
            'gray': '#7C8A84',
            'card_line': '#CBE3D8',
        },
        'fuente_titulos': 'Arial',
        'fuente_cuerpo': 'Arial',
    },
    'cobre': {
        'nombre': 'Cobre Minero',
        'descripcion': 'Tierras y cobre sobre azul profundo, para minería e hidrocarburos.',
        'colores': {
            'primary': '#14253D',
            'royal': '#2D4763',
            'secondary': '#D98B4A',
            'background': '#F7F4F0',
            'white': '#FFFFFF',
            'text': '#221D18',
            'gray': '#8A8178',
            'card_line': '#E2D6C8',
        },
        'fuente_titulos': 'Arial',
        'fuente_cuerpo': 'Arial',
    },
}

TEMA_POR_DEFECTO = 'seidor'


def listar_temas():
    """Catálogo para el selector de la interfaz (sin exponer la estructura interna)."""
    return [
        {
            'id': tid,
            'nombre': t['nombre'],
            'descripcion': t['descripcion'],
            'colores': dict(t['colores']),
            'fuente_titulos': t['fuente_titulos'],
            'fuente_cuerpo': t['fuente_cuerpo'],
        }
        for tid, t in TEMAS.items()
    ]


def _validar_contraste(colores):
    """
    Comprueba las combinaciones que de verdad se pintan en el deck.

    Devuelve (errores, advertencias):

    - **errores**: combinaciones ilegibles. Bloquean la generación, porque el
      deck saldría con texto invisible y eso ya pasó en producción.
    - **advertencias**: contraste flojo pero utilizable. No bloquean a
      propósito: el gris oficial de SEIDOR (#919191 sobre #F6F6F6) se queda en
      2.9:1, así que un umbral duro rechazaría la propia paleta corporativa y,
      peor aún, rechazaría un tema a medida por un color que el consultor ni
      siquiera tocó.

    Solo se miran los pares que el generador pinta de verdad; validar todo
    contra todo descartaría temas válidos por combinaciones que nunca ocurren.
    """
    errores = []
    advertencias = []

    pares_texto_normal = [
        ('text', 'background', 'el texto del cuerpo sobre el fondo de las tarjetas'),
        ('white', 'primary', 'el texto blanco sobre la cabecera'),
        ('white', 'royal', 'el texto blanco sobre las barras de acento'),
    ]
    for frente, fondo, donde in pares_texto_normal:
        ratio = ratio_contraste(colores[frente], colores[fondo])
        if ratio < CONTRASTE_MINIMO:
            errores.append(
                f"{donde} queda en {ratio:.1f}:1 y hace falta {CONTRASTE_MINIMO}:1 "
                f"({colores[frente]} sobre {colores[fondo]})"
            )

    ratio_gris = ratio_contraste(colores['gray'], colores['background'])
    if ratio_gris < CONTRASTE_MINIMO_TITULO:
        advertencias.append(
            f"El texto secundario queda en {ratio_gris:.1f}:1 sobre el fondo "
            f"({colores['gray']} sobre {colores['background']}); se lee, pero justo. "
            f"Oscurece el gris si la propuesta se va a imprimir o proyectar."
        )

    ratio_acento = ratio_contraste(colores['secondary'], colores['background'])
    if ratio_acento < 2.0:
        advertencias.append(
            f"El color de acento apenas se distingue del fondo ({ratio_acento:.1f}:1): "
            f"las series de los gráficos quedarán desvaídas."
        )

    return errores, advertencias


def normalizar_tema(entrada):
    """
    Devuelve un tema utilizable a partir de lo que llegue de la API.

    Admite:
      - None o '' -> tema por defecto.
      - 'grafito' (str) -> uno del catálogo.
      - {'id': 'grafito'} -> igual que el anterior.
      - {'colores': {...}, 'fuente_titulos': ..., 'fuente_cuerpo': ...} -> tema
        a medida; los colores que falten se heredan del tema base indicado en
        'base' (o del de SEIDOR).

    Lanza TemaInvalido con un mensaje accionable si algo no cuadra.
    """
    if entrada is None or entrada == '':
        entrada = TEMA_POR_DEFECTO

    if isinstance(entrada, str):
        tid = entrada.strip().lower()
        if tid not in TEMAS:
            disponibles = ', '.join(sorted(TEMAS))
            raise TemaInvalido(f"El tema '{entrada}' no existe. Disponibles: {disponibles}.")
        base = TEMAS[tid]
        colores = dict(base['colores'])
        _, advertencias = _validar_contraste(colores)
        return {
            'id': tid,
            'nombre': base['nombre'],
            'base': tid,
            'colores': colores,
            'fuente_titulos': base['fuente_titulos'],
            'fuente_cuerpo': base['fuente_cuerpo'],
            'advertencias': advertencias,
        }

    if not isinstance(entrada, dict):
        raise TemaInvalido("El tema debe ser el identificador de un tema o un objeto con 'colores'.")

    base_id = str(entrada.get('base') or entrada.get('id') or TEMA_POR_DEFECTO).strip().lower()
    if base_id not in TEMAS:
        disponibles = ', '.join(sorted(TEMAS))
        raise TemaInvalido(f"El tema base '{base_id}' no existe. Disponibles: {disponibles}.")
    base = TEMAS[base_id]

    colores_entrada = entrada.get('colores') or {}
    if not isinstance(colores_entrada, dict):
        raise TemaInvalido("'colores' debe ser un objeto con claves como 'primary' o 'secondary'.")

    desconocidas = set(colores_entrada) - set(CLAVES_COLOR)
    if desconocidas:
        raise TemaInvalido(
            f"Colores no reconocidos: {', '.join(sorted(desconocidas))}. "
            f"Válidos: {', '.join(CLAVES_COLOR)}."
        )

    colores = dict(base['colores'])
    for clave, valor in colores_entrada.items():
        colores[clave] = _normalizar_hex(valor, clave)


    errores, advertencias = _validar_contraste(colores)
    if errores:
        raise TemaInvalido(
            "El tema no es legible: " + "; ".join(errores) +
            ". Ajusta los colores antes de generar la propuesta."
        )

    def _fuente(clave):
        valor = entrada.get(clave)
        if valor is None or valor == '':
            return base[clave]
        valor = str(valor).strip()
        if valor not in FUENTES_SEGURAS:
            raise TemaInvalido(
                f"La tipografía '{valor}' no está en la lista de fuentes seguras "
                f"({', '.join(FUENTES_SEGURAS)}). Una fuente que el cliente no tenga "
                f"instalada descuadra todas las láminas."
            )
        return valor

    fuente_titulos = _fuente('fuente_titulos')
    fuente_cuerpo = _fuente('fuente_cuerpo')

    # "Personalizado" se decide comparando el RESULTADO con el tema base, no por
    # si el llamante mandó claves. Así la función es idempotente: normalizar un
    # tema ya normalizado (algo que pasa cuando la ruta lo valida y luego se lo
    # pasa al generador) devuelve el mismo id en vez de rebautizarlo
    # "personalizado". Y pasar los colores exactos de un tema del catálogo
    # tampoco lo convierte en otra cosa.
    personalizado = (
        colores != base['colores']
        or fuente_titulos != base['fuente_titulos']
        or fuente_cuerpo != base['fuente_cuerpo']
    )

    return {
        'id': 'personalizado' if personalizado else base_id,
        'nombre': entrada.get('nombre') or ('Personalizado' if personalizado else base['nombre']),
        'base': base_id,
        'colores': colores,
        'fuente_titulos': fuente_titulos,
        'fuente_cuerpo': fuente_cuerpo,
        'advertencias': advertencias,
    }
