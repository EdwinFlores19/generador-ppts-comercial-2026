# -*- coding: utf-8 -*-
"""
Adelgazado del PPTX: quita del paquete lo que la propuesta no usa.

El problema
-----------
El deck se construye sobre la plantilla corporativa de 49 MB, que es un curso
de 63 láminas sobre Joule. Al quedarnos solo con nuestras 11-12 láminas, el
archivo seguía pesando **40 MB**, y midiéndolo resultó que el 99,2% era
`ppt/media`: 82 imágenes, de las cuales la propuesta solo necesita 11.

Las otras 71 son material interno (fotos y arte del curso original) que además
viajaba hasta el cliente. Venían arrastradas por los 118 layouts y 5 masters
que la propuesta no usa pero seguían dentro del paquete.

Por qué importa
---------------
- **Una propuesta de 40 MB no se puede enviar por correo.** La mayoría de
  servidores corporativos cortan entre 10 y 25 MB. A 1,4 MB sí se envía.
- En el plan gratuito de PythonAnywhere (512 MB) caben ~12 propuestas de 40 MB;
  a 1,4 MB caben cientos.
- La descarga deja de tardar y el disco deja de ser el cuello de botella.

Cómo se hace
------------
Se calcula qué partes del paquete son alcanzables desde las láminas —sus
layouts, los masters de esos layouts y lo que estos referencian— y se descarta
el resto. La sutileza está en **no seguir** la rama master → layouts no usados:
un master referencia TODOS sus layouts, así que seguirla vuelve a arrastrar el
paquete entero (medido: sin ese corte la reducción baja del 96% al 16%).

Descartar partes obliga a rehacer tres cosas, o PowerPoint da el archivo por
corrupto:
  1. `presentation.xml` y sus relaciones: quitar los masters descartados.
  2. Cada master conservado: quitar de su `sldLayoutIdLst` los layouts que ya
     no están, y sus relaciones.
  3. `[Content_Types].xml`: quitar los Override de todo lo eliminado.

Ante cualquier problema se conserva el archivo original: un deck grande es
molesto, uno corrupto delante de un cliente es otra cosa.
"""
import logging
import os
import posixpath
import re
import tempfile
import zipfile

log = logging.getLogger("pptx_slim")

_RE_LAMINA = re.compile(r'^ppt/slides/slide\d+\.xml$')
_RE_LAYOUT = re.compile(r'^ppt/slideLayouts/slideLayout\d+\.xml$')
_RE_MASTER = re.compile(r'^ppt/slideMasters/slideMaster\d+\.xml$')


def _ruta_rels(parte):
    directorio, fichero = posixpath.split(parte)
    return posixpath.join(directorio, '_rels', fichero + '.rels')


def _relaciones(z, parte, nombres):
    """[(id, destino_absoluto)] de las relaciones internas de `parte`."""
    ruta = _ruta_rels(parte)
    if ruta not in nombres:
        return []
    xml = z.read(ruta).decode('utf-8', 'replace')
    salida = []
    for etiqueta in re.finditer(r'<Relationship\b[^>]*>', xml):
        texto = etiqueta.group(0)
        if 'TargetMode="External"' in texto:
            continue
        destino = re.search(r'Target="([^"]+)"', texto)
        ident = re.search(r'Id="([^"]+)"', texto)
        if not destino or not ident or '://' in destino.group(1):
            continue
        absoluta = posixpath.normpath(
            posixpath.join(posixpath.dirname(parte), destino.group(1))).lstrip('/')
        salida.append((ident.group(1), absoluta))
    return salida


def _calcular_necesarias(z, nombres):
    """
    Devuelve (partes_necesarias, layouts_usados, masters_usados).

    El cierre transitivo NO sigue master -> layout: un master referencia todos
    sus layouts y seguir esa rama arrastra el paquete entero.
    """
    laminas = {n for n in nombres if _RE_LAMINA.match(n)}
    if not laminas:
        raise ValueError("el paquete no tiene láminas")

    layouts = set()
    for lamina in laminas:
        layouts |= {d for _, d in _relaciones(z, lamina, nombres) if _RE_LAYOUT.match(d)}

    masters = set()
    for layout in layouts:
        masters |= {d for _, d in _relaciones(z, layout, nombres) if _RE_MASTER.match(d)}

    if not layouts or not masters:
        raise ValueError("no se pudo resolver la cadena lámina → layout → master")

    vistos = set()
    pila = list(laminas | layouts | masters)
    while pila:
        parte = pila.pop()
        if parte in vistos or parte not in nombres:
            continue
        vistos.add(parte)
        es_master = _RE_MASTER.match(parte)
        for _, destino in _relaciones(z, parte, nombres):
            # Aquí está el corte que hace que esto sirva de algo.
            if es_master and _RE_LAYOUT.match(destino) and destino not in layouts:
                continue
            pila.append(destino)

    return vistos, layouts, masters


def _quitar_relaciones(xml, ids):
    for ident in ids:
        xml = re.sub(r'<Relationship\b[^>]*Id="%s"[^>]*/>' % re.escape(ident), '', xml)
    return xml


def _quitar_referencias(xml, etiqueta, ids):
    """Quita <p:sldMasterId .../> o <p:sldLayoutId .../> por r:id."""
    for ident in ids:
        xml = re.sub(
            r'<p:%s\b[^>]*r:id="%s"[^>]*/>' % (etiqueta, re.escape(ident)), '', xml)
    return xml


def adelgazar(ruta_pptx):
    """
    Quita del .pptx las partes que la propuesta no usa.

    Devuelve un resumen {'antes', 'despues', 'partes_eliminadas'} en bytes.
    Ante cualquier error deja el archivo intacto y lo registra.
    """
    if not os.path.exists(ruta_pptx):
        raise FileNotFoundError(ruta_pptx)

    antes = os.path.getsize(ruta_pptx)
    directorio = os.path.dirname(os.path.abspath(ruta_pptx)) or '.'
    temporal = None

    try:
        with zipfile.ZipFile(ruta_pptx, 'r') as origen:
            nombres = set(origen.namelist())
            necesarias, layouts, masters = _calcular_necesarias(origen, nombres)

            def se_conserva(nombre):
                # Las partes estructurales (presentation, docProps, theme…) se
                # conservan siempre; solo se poda lo que cuelga de la plantilla.
                if _RE_LAYOUT.match(nombre) or _RE_MASTER.match(nombre):
                    return nombre in necesarias
                if nombre.startswith('ppt/media/'):
                    return nombre in necesarias
                # El .rels de un layout/master descartado se va con él.
                if nombre.endswith('.rels'):
                    duenyo = nombre.replace('_rels/', '').replace('.rels', '')
                    if _RE_LAYOUT.match(duenyo) or _RE_MASTER.match(duenyo):
                        return duenyo in necesarias
                return True

            eliminadas = {n for n in nombres if not se_conserva(n)}
            if not eliminadas:
                log.info("El paquete ya está ajustado: no hay nada que quitar.")
                return {'antes': antes, 'despues': antes, 'partes_eliminadas': 0}

            # Relaciones a eliminar en presentation.xml (masters descartados)
            ids_master = [i for i, d in _relaciones(origen, 'ppt/presentation.xml', nombres)
                          if _RE_MASTER.match(d) and d not in masters]

            # Y en cada master conservado (layouts descartados)
            ids_layout_por_master = {}
            for master in masters:
                ids_layout_por_master[master] = [
                    i for i, d in _relaciones(origen, master, nombres)
                    if _RE_LAYOUT.match(d) and d not in layouts]

            fd, temporal = tempfile.mkstemp(suffix='.pptx', dir=directorio)
            os.close(fd)

            with zipfile.ZipFile(temporal, 'w', zipfile.ZIP_DEFLATED) as destino:
                for info in origen.infolist():
                    nombre = info.filename
                    if nombre in eliminadas:
                        continue
                    datos = origen.read(nombre)

                    if nombre == 'ppt/presentation.xml' and ids_master:
                        datos = _quitar_referencias(
                            datos.decode('utf-8'), 'sldMasterId', ids_master).encode('utf-8')

                    elif nombre == 'ppt/_rels/presentation.xml.rels' and ids_master:
                        datos = _quitar_relaciones(
                            datos.decode('utf-8'), ids_master).encode('utf-8')

                    elif _RE_MASTER.match(nombre):
                        ids = ids_layout_por_master.get(nombre, [])
                        if ids:
                            datos = _quitar_referencias(
                                datos.decode('utf-8'), 'sldLayoutId', ids).encode('utf-8')

                    elif nombre.endswith('.rels'):
                        duenyo = nombre.replace('_rels/', '').replace('.rels', '')
                        ids = ids_layout_por_master.get(duenyo, [])
                        if ids:
                            datos = _quitar_relaciones(datos.decode('utf-8'), ids).encode('utf-8')

                    elif nombre == '[Content_Types].xml':
                        xml = datos.decode('utf-8')
                        for parte in eliminadas:
                            if parte.endswith('.rels'):
                                continue
                            xml = re.sub(
                                r'<Override\s+PartName="/%s"[^>]*/>' % re.escape(parte), '', xml)
                        datos = xml.encode('utf-8')

                    destino.writestr(info, datos)

        os.replace(temporal, ruta_pptx)
        temporal = None
        despues = os.path.getsize(ruta_pptx)
        log.info("Deck ajustado: %.1f MB -> %.1f MB (%d partes sobrantes eliminadas, -%.0f%%)",
                 antes / 1048576, despues / 1048576, len(eliminadas),
                 100 - despues / antes * 100 if antes else 0)
        return {'antes': antes, 'despues': despues, 'partes_eliminadas': len(eliminadas)}

    except Exception as e:
        log.error("No se pudo adelgazar %s: %s. Se conserva el archivo original.",
                  ruta_pptx, e, exc_info=True)
        if temporal and os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass
        return {'antes': antes, 'despues': antes, 'partes_eliminadas': 0}


def validar_paquete(ruta_pptx):
    """
    Comprueba que el .pptx sigue siendo coherente tras podarlo.

    Devuelve (ok, [problemas]). Se usa en los tests y sirve para revisar a mano
    un deck: un archivo que PowerPoint rechaza delante de un cliente es peor
    que uno grande.
    """
    problemas = []
    with zipfile.ZipFile(ruta_pptx) as z:
        nombres = set(z.namelist())

        for nombre in nombres:
            if not nombre.endswith('.rels'):
                continue
            base = nombre.rsplit('_rels/', 1)[0]
            xml = z.read(nombre).decode('utf-8', 'replace')
            for etiqueta in re.finditer(r'<Relationship\b[^>]*>', xml):
                texto = etiqueta.group(0)
                if 'TargetMode="External"' in texto:
                    continue
                destino = re.search(r'Target="([^"]+)"', texto)
                if not destino or '://' in destino.group(1):
                    continue
                absoluta = posixpath.normpath(
                    posixpath.join(base, destino.group(1))).lstrip('/')
                if absoluta not in nombres:
                    problemas.append(f"relación rota en {nombre}: {destino.group(1)}")

        ct = z.read('[Content_Types].xml').decode('utf-8', 'replace')
        defaults = {e.lower() for e in re.findall(r'Default Extension="([^"]+)"', ct)}
        overrides = set(re.findall(r'Override PartName="/([^"]+)"', ct))
        for nombre in nombres:
            if nombre == '[Content_Types].xml':
                continue
            if nombre not in overrides and nombre.rsplit('.', 1)[-1].lower() not in defaults:
                problemas.append(f"sin content type: {nombre}")
        for override in overrides:
            if override not in nombres:
                problemas.append(f"Override a parte inexistente: {override}")

        # Cada lámina necesita su layout, y cada layout su master.
        for nombre in (n for n in nombres if _RE_LAMINA.match(n)):
            destinos = [d for _, d in _relaciones(z, nombre, nombres)]
            if not any(_RE_LAYOUT.match(d) for d in destinos):
                problemas.append(f"{nombre} se quedó sin layout")

    return not problemas, problemas
