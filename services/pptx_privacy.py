# -*- coding: utf-8 -*-
"""
Saneado de metadatos del PPTX antes de entregarlo al cliente.

Por qué existe
--------------
El deck se construye **sobre la plantilla corporativa**, y un .pptx es un ZIP
que arrastra mucho más que las láminas. Auditando un deck descargado de
producción aparecía todo esto dentro del archivo que se envía a un cliente:

- `author: "Pepe"` y `last_modified_by: "Andrea Chavez"` — nombres de personas
  de SEIDOR, es decir datos personales de empleados entregados a un tercero.
- `created: 2022-02-01`, `revision: 249` — delata que la propuesta es una
  plantilla reciclada.
- Los **74 títulos de lámina** de la plantilla interna, con su nomenclatura de
  trabajo ("Negativas", "Plantillas Interiores con Patron para clientes",
  "Separador KickOff").
- `customXml/item3.xml` (14,7 KB): el **esquema de content types de SharePoint**
  de SEIDOR, con IDs y nombres de campos internos.
- `docProps/custom.xml`: el `ContentTypeId` de esa biblioteca de SharePoint.
- `docProps/thumbnail.jpeg`: una **miniatura de la primera lámina del deck
  interno original**, incrustada en cada propuesta.

Cualquiera que reciba el archivo lo ve abriendo Propiedades en PowerPoint, o
descomprimiendo el .pptx. Es una fuga de confidencialidad y, por los nombres
de empleados, también de datos personales.

Cómo se limpia
--------------
`python-pptx` cubre las propiedades básicas (core.xml), pero no sabe eliminar
partes del paquete OPC. El resto se hace reescribiendo el ZIP: se descartan las
partes sobrantes y se parchean los tres ficheros que las referencian
(`[Content_Types].xml`, `_rels/.rels` y `docProps/app.xml`). Si algo sale mal,
**se conserva el archivo original**: es preferible un deck con metadatos de más
que ningún deck delante de un cliente.
"""
import logging
import os
import re
import shutil
import tempfile
import zipfile

log = logging.getLogger("pptx_privacy")

# Partes que se eliminan por completo del paquete.
#
# customXml/* y docProps/custom.xml vienen de la biblioteca de SharePoint donde
# vive la plantilla; thumbnail.jpeg es la vista previa del deck original.
# Ninguna es necesaria para que PowerPoint abra el archivo.
PARTES_A_ELIMINAR = (
    'docProps/thumbnail.jpeg',
    'docProps/thumbnail.jpg',
    'docProps/custom.xml',
)
PREFIJOS_A_ELIMINAR = ('customXml/',)

# Identidad que se publica en el archivo entregado.
AUTOR_PUBLICO = 'SEIDOR Consulting SAC'
EMPRESA_PUBLICA = 'SEIDOR Consulting SAC'


def _debe_eliminarse(nombre):
    return nombre in PARTES_A_ELIMINAR or nombre.startswith(PREFIJOS_A_ELIMINAR)


def _limpiar_content_types(xml, eliminadas):
    """
    Quita los <Override> de las partes eliminadas.

    Los <Default Extension="jpeg"> NO se tocan: las láminas llevan imágenes JPEG
    de la propia plantilla y sin ese Default PowerPoint da el archivo por
    corrupto.
    """
    for parte in eliminadas:
        xml = re.sub(
            r'<Override\s+PartName="/%s"[^>]*/>' % re.escape(parte),
            '', xml
        )
    return xml


def _limpiar_rels(xml, eliminadas):
    """Quita las relaciones que apuntan a partes que ya no existen."""
    basenames = {p.rsplit('/', 1)[-1] for p in eliminadas}
    for parte in eliminadas:
        xml = re.sub(
            r'<Relationship\b[^>]*Target="[^"]*%s"[^>]*/>' % re.escape(parte.rsplit('/', 1)[-1]),
            '', xml
        )
    # Relaciones a customXml declaradas con ruta relativa.
    xml = re.sub(r'<Relationship\b[^>]*Target="[^"]*customXml/[^"]*"[^>]*/>', '', xml)
    del basenames
    return xml


def _limpiar_app_xml(xml):
    """
    Borra el inventario de láminas de la plantilla interna y fija la empresa.

    `TitlesOfParts` y `HeadingPairs` van juntos: son el índice de títulos del
    documento. Quitar uno y dejar el otro descuadra el recuento, así que se
    eliminan los dos.
    """
    xml = re.sub(r'<TitlesOfParts>.*?</TitlesOfParts>', '', xml, flags=re.S)
    xml = re.sub(r'<HeadingPairs>.*?</HeadingPairs>', '', xml, flags=re.S)

    if '<Company>' in xml:
        xml = re.sub(r'<Company>.*?</Company>', f'<Company>{EMPRESA_PUBLICA}</Company>',
                     xml, flags=re.S)
    if '<Manager>' in xml:
        xml = re.sub(r'<Manager>.*?</Manager>', '<Manager></Manager>', xml, flags=re.S)
    return xml


def limpiar_metadatos(ruta_pptx, titulo=None, asunto=None):
    """
    Elimina del .pptx todo rastro interno heredado de la plantilla.

    Reescribe el archivo en el sitio. Devuelve la lista de partes eliminadas.
    Ante cualquier error deja el archivo original intacto y lo registra: un deck
    con metadatos de más es mejor que un deck corrupto en una reunión.
    """
    if not os.path.exists(ruta_pptx):
        raise FileNotFoundError(ruta_pptx)

    directorio = os.path.dirname(os.path.abspath(ruta_pptx)) or '.'
    temporal = None
    try:
        with zipfile.ZipFile(ruta_pptx, 'r') as origen:
            nombres = origen.namelist()
            eliminadas = [n for n in nombres if _debe_eliminarse(n)]

            fd, temporal = tempfile.mkstemp(suffix='.pptx', dir=directorio)
            os.close(fd)

            # Se conserva la compresión del original para no inflar el archivo.
            with zipfile.ZipFile(temporal, 'w', zipfile.ZIP_DEFLATED) as destino:
                for info in origen.infolist():
                    nombre = info.filename
                    if _debe_eliminarse(nombre):
                        continue
                    datos = origen.read(nombre)

                    if nombre == '[Content_Types].xml':
                        datos = _limpiar_content_types(
                            datos.decode('utf-8'), eliminadas).encode('utf-8')
                    elif nombre.endswith('.rels'):
                        datos = _limpiar_rels(
                            datos.decode('utf-8'), eliminadas).encode('utf-8')
                    elif nombre == 'docProps/app.xml':
                        datos = _limpiar_app_xml(datos.decode('utf-8')).encode('utf-8')

                    destino.writestr(info, datos)

        os.replace(temporal, ruta_pptx)
        temporal = None
        log.info("Metadatos saneados en %s (%d partes internas eliminadas)",
                 os.path.basename(ruta_pptx), len(eliminadas))
        return eliminadas

    except Exception as e:
        log.error("No se pudieron sanear los metadatos de %s: %s. "
                  "Se conserva el archivo original.", ruta_pptx, e, exc_info=True)
        if temporal and os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass
        return []


def fijar_propiedades(prs, company_name, edition_label=None):
    """
    Sustituye las propiedades del documento por las de la propuesta.

    Se llama ANTES de guardar. Sin esto el deck sale con el autor y la fecha de
    creación de la plantilla de 2022, más el nombre de la última persona que la
    editó.
    """
    from datetime import datetime, timezone

    cp = prs.core_properties
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)

    cp.author = AUTOR_PUBLICO
    cp.last_modified_by = AUTOR_PUBLICO
    cp.title = f"Propuesta Comercial SAP S/4HANA Cloud — {company_name}"
    cp.subject = edition_label or 'Propuesta comercial'
    cp.comments = ''
    cp.keywords = ''
    cp.category = 'Propuesta comercial'
    cp.created = ahora
    cp.modified = ahora
    # revision venía en 249: delata una plantilla reutilizada 249 veces.
    cp.revision = 1
    try:
        cp.content_status = ''
        cp.identifier = ''
        cp.language = 'es-PE'
    except (AttributeError, ValueError):
        # Propiedades opcionales: si esta versión de python-pptx no las expone,
        # no es motivo para abortar la generación.
        pass


def inspeccionar(ruta_pptx):
    """
    Devuelve qué rastro interno queda en un .pptx. Se usa en los tests y sirve
    para auditar a mano un deck ya entregado.
    """
    resultado = {'partes_internas': [], 'titulos_de_plantilla': 0, 'propiedades': {}}
    with zipfile.ZipFile(ruta_pptx) as z:
        resultado['partes_internas'] = [n for n in z.namelist() if _debe_eliminarse(n)]
        if 'docProps/app.xml' in z.namelist():
            xml = z.read('docProps/app.xml').decode('utf-8', 'replace')
            resultado['titulos_de_plantilla'] = len(re.findall(r'<vt:lpstr>', xml))
        if 'docProps/core.xml' in z.namelist():
            xml = z.read('docProps/core.xml').decode('utf-8', 'replace')
            for etiqueta in ('dc:creator', 'cp:lastModifiedBy', 'dc:title', 'cp:revision'):
                m = re.search(rf'<{etiqueta}>(.*?)</{etiqueta}>', xml, re.S)
                if m:
                    resultado['propiedades'][etiqueta] = m.group(1)
    return resultado


def copiar_sin_metadatos(origen, destino):
    """Copia un .pptx y lo sanea, sin tocar el original. Para auditorías."""
    shutil.copy2(origen, destino)
    return limpiar_metadatos(destino)
