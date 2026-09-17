# -*- coding: utf-8 -*-
"""
Registro de auditoría y retención de datos.

Por qué existe
--------------
La base guarda datos comerciales sensibles de prospectos reales: razón social,
facturación anual estimada, tarifas, márgenes y el importe de cada propuesta.
Hasta ahora no quedaba constancia de **quién** generaba, descargaba o borraba
esa información, ni había forma de responder a una pregunta tan básica como
"¿quién se llevó la propuesta de este cliente y cuándo?".

Dos obligaciones que esto cubre:

- **Trazabilidad** (ISO/IEC 27001 A.8.15, registro de eventos): toda acción que
  lea o modifique datos de cliente deja rastro con fecha, origen y resultado.
- **Limitación del plazo de conservación** (RGPD art. 5.1.e y Ley 29733 de
  Perú, art. 8): los datos no pueden guardarse indefinidamente "por si acaso".
  `purgar_antiguas()` aplica un plazo configurable.

Qué NO pretende ser
-------------------
No identifica personas: la aplicación usa un único token compartido, así que no
hay usuarios individuales que registrar. Se anota el origen de la petición y la
acción. Si algún día hay login por usuario, el campo `actor` ya está previsto.
"""
import logging
import os
from contextlib import closing
from datetime import datetime, timedelta, timezone

from models.database import get_db_connection

log = logging.getLogger("auditoria")

# Plazo de conservación por defecto. 365 días cubre el ciclo comercial completo
# (una propuesta puede reactivarse meses después) sin acumular indefinidamente.
DIAS_RETENCION_POR_DEFECTO = int(os.getenv("DIAS_RETENCION", "365"))

# Acciones registradas. Lista cerrada para que el registro sea consultable y no
# se llene de cadenas libres.
ACCIONES = (
    'propuesta_generada',
    'propuesta_descargada',
    'propuesta_eliminada',
    'config_modificada',
    'conversacion_eliminada',
    'purga_ejecutada',
)


def registrar(accion, recurso=None, detalle=None, origen=None, actor=None, resultado='ok'):
    """
    Anota un evento. Nunca lanza: un fallo registrando no debe tumbar la acción
    que el consultor estaba haciendo, pero sí queda en el log del servidor.
    """
    if accion not in ACCIONES:
        log.warning("Acción de auditoría desconocida: %r", accion)

    try:
        if origen is None:
            try:
                from flask import request, has_request_context
                origen = request.remote_addr if has_request_context() else None
            except Exception:
                origen = None

        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute(
                    """INSERT INTO auditoria (accion, recurso, detalle, origen, actor,
                                              resultado, ocurrido_en)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (accion, str(recurso) if recurso is not None else None,
                     detalle, origen, actor, resultado,
                     datetime.now(timezone.utc).isoformat())
                )
    except Exception as e:
        log.error("No se pudo registrar el evento de auditoría '%s': %s", accion, e)


def consultar(limite=100, offset=0, accion=None):
    """Lee el registro, del más reciente al más antiguo."""
    limite = max(1, min(int(limite), 500))
    offset = max(0, int(offset))
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        if accion:
            cursor.execute(
                """SELECT id, accion, recurso, detalle, origen, actor, resultado, ocurrido_en
                   FROM auditoria WHERE accion = ?
                   ORDER BY id DESC LIMIT ? OFFSET ?""", (accion, limite, offset))
        else:
            cursor.execute(
                """SELECT id, accion, recurso, detalle, origen, actor, resultado, ocurrido_en
                   FROM auditoria ORDER BY id DESC LIMIT ? OFFSET ?""", (limite, offset))
        filas = [dict(r) for r in cursor.fetchall()]
        total = cursor.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]
    return filas, total


def _borrar_pptx(ruta, directorio_salida):
    """
    Borra el PPTX solo si está dentro del directorio de salida.

    Misma contención que en el borrado manual: la ruta viene de la BBDD y no se
    sirve ni se borra nada fuera de OUTPUT_DIR.
    """
    if not ruta:
        return False
    destino = os.path.abspath(ruta)
    base = os.path.abspath(directorio_salida)
    if not destino.startswith(base + os.sep):
        log.warning("Ruta fuera del directorio de salida, no se borra: %s", ruta)
        return False
    try:
        if os.path.exists(destino):
            os.remove(destino)
            return True
    except OSError as e:
        log.warning("No se pudo borrar %s: %s", destino, e)
    return False


def purgar_antiguas(dias=None, directorio_salida=None, simular=False):
    """
    Elimina las propuestas y conversaciones que superen el plazo de conservación.

    Devuelve un resumen con lo borrado. Con `simular=True` no toca nada: sirve
    para comprobar qué se iría antes de ejecutarlo de verdad, que es lo que uno
    quiere la primera vez que aplica una política de retención sobre datos
    reales de clientes.
    """
    dias = int(dias if dias is not None else DIAS_RETENCION_POR_DEFECTO)
    if dias < 1:
        raise ValueError("El plazo de conservación debe ser de al menos 1 día.")

    directorio_salida = directorio_salida or os.getenv("OUTPUT_DIR", "generated_decks")
    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    resumen = {'dias': dias, 'corte': corte, 'simulado': simular,
               'propuestas': 0, 'archivos': 0, 'conversaciones': 0}

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, ppt_path FROM proposals WHERE created_at < ?", (corte,))
        caducadas = cursor.fetchall()
        resumen['propuestas'] = len(caducadas)

        cursor.execute(
            "SELECT COUNT(*) FROM chat_sessions WHERE updated_at < ?", (corte,))
        resumen['conversaciones'] = cursor.fetchone()[0]

        if simular:
            return resumen

        for fila in caducadas:
            if _borrar_pptx(fila['ppt_path'], directorio_salida):
                resumen['archivos'] += 1

        with conn:
            ids = [f['id'] for f in caducadas]
            if ids:
                marcas = ','.join('?' * len(ids))
                # La FK de chat_sessions apunta a proposals: primero se
                # desvincula, si no el DELETE falla con foreign_keys=ON.
                conn.execute(
                    f"UPDATE chat_sessions SET proposal_id = NULL WHERE proposal_id IN ({marcas})",
                    ids)
                conn.execute(f"DELETE FROM proposals WHERE id IN ({marcas})", ids)
            conn.execute("DELETE FROM chat_sessions WHERE updated_at < ?", (corte,))

    registrar('purga_ejecutada', detalle=(
        f"{resumen['propuestas']} propuestas, {resumen['archivos']} archivos y "
        f"{resumen['conversaciones']} conversaciones anteriores a {corte[:10]}"))
    log.info("Purga de retención: %s", resumen)
    return resumen
