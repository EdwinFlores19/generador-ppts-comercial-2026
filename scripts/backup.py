# -*- coding: utf-8 -*-
"""
Copia de seguridad de la base de datos.

Por qué existe
--------------
`proposals.db` guarda el histórico comercial completo: prospectos, facturación
estimada, tarifas aplicadas, importes de cada propuesta y el registro de
auditoría. No había ninguna copia: un borrado accidental, una purga de
retención mal lanzada o un fallo del disco se lo llevaban todo, y `generated_decks/`
está en `.gitignore`, así que tampoco hay una copia indirecta en el repositorio.

Cómo copia
----------
Con la API de backup de SQLite, **no** copiando el fichero. Copiar un `.db` a
pelo mientras el servidor escribe produce una copia corrupta o a medias; con
WAL activado, además, el `.db` por sí solo puede no contener los últimos
commits (están en el `-wal`). `sqlite3.Connection.backup()` hace una copia
consistente aunque haya escrituras en curso.

Uso
---
    python scripts/backup.py                 # copia en ./backups
    python scripts/backup.py --dir /otra/ruta --conservar 14
    python scripts/backup.py --verificar     # solo comprueba la última copia
"""
import argparse
import gzip
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("backup")

DB_NAME = os.getenv("DB_NAME", "proposals.db")
DIR_POR_DEFECTO = os.getenv("BACKUP_DIR", "backups")

# Cuántas copias se conservan. En el plan gratuito el disco son 512 MB y la
# BBDD comprimida ocupa poco, pero acumular sin límite acabaría llenándolo.
COPIAS_POR_DEFECTO = int(os.getenv("BACKUP_CONSERVAR", "7"))


def crear_copia(destino_dir=DIR_POR_DEFECTO, comprimir=True):
    """Copia consistente de la BBDD. Devuelve la ruta del archivo creado."""
    if not os.path.exists(DB_NAME):
        raise FileNotFoundError(f"No existe la base de datos: {DB_NAME}")

    os.makedirs(destino_dir, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    temporal = os.path.join(destino_dir, f"proposals-{marca}.db")

    origen = sqlite3.connect(DB_NAME)
    try:
        copia = sqlite3.connect(temporal)
        try:
            # La API de backup respeta las escrituras en curso: una copia byte a
            # byte del fichero podría quedar a medias o sin los datos del -wal.
            origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()

    destino = temporal
    if comprimir:
        destino = temporal + '.gz'
        with open(temporal, 'rb') as f_in, gzip.open(destino, 'wb', compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(temporal)

    tam = os.path.getsize(destino)
    log.info("Copia creada: %s (%.1f KB)", destino, tam / 1024)
    return destino


def verificar(ruta):
    """
    Comprueba que la copia se abre y tiene las tablas esperadas.

    Una copia que nadie ha verificado no es una copia: es una suposición.
    """
    temporal = None
    try:
        if not os.path.exists(ruta):
            return False, "el archivo no existe"
        if ruta.endswith('.gz'):
            temporal = ruta[:-3] + '.verificando'
            with gzip.open(ruta, 'rb') as f_in, open(temporal, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            objetivo = temporal
        else:
            objetivo = ruta

        conn = sqlite3.connect(objetivo)
        try:
            integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integridad != 'ok':
                return False, f"integrity_check devolvió: {integridad}"

            tablas = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            esperadas = {'proposals', 'configuracion_comercial', 'chat_sessions', 'auditoria'}
            faltan = esperadas - tablas
            if faltan:
                return False, f"faltan tablas: {', '.join(sorted(faltan))}"

            propuestas = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
            eventos = conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]
            return True, f"{propuestas} propuestas, {eventos} eventos de auditoría"
        finally:
            conn.close()
    except (sqlite3.DatabaseError, gzip.BadGzipFile, OSError, EOFError) as e:
        # verificar() NUNCA debe lanzar: si lo hiciera, una copia corrupta
        # tumbaría la tarea programada en vez de avisar de que está corrupta,
        # que es justo lo que se quiere detectar.
        return False, f"no se pudo leer la copia: {type(e).__name__}: {e}"
    finally:
        if temporal and os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass


def rotar(destino_dir=DIR_POR_DEFECTO, conservar=COPIAS_POR_DEFECTO):
    """Deja solo las N copias más recientes."""
    if not os.path.isdir(destino_dir):
        return []
    copias = sorted(
        (f for f in os.listdir(destino_dir) if f.startswith('proposals-')),
        reverse=True)
    borradas = []
    for antigua in copias[conservar:]:
        ruta = os.path.join(destino_dir, antigua)
        try:
            os.remove(ruta)
            borradas.append(antigua)
        except OSError as e:
            log.warning("No se pudo borrar %s: %s", ruta, e)
    if borradas:
        log.info("Rotación: %d copia(s) antigua(s) eliminada(s)", len(borradas))
    return borradas


def ultima_copia(destino_dir=DIR_POR_DEFECTO):
    if not os.path.isdir(destino_dir):
        return None
    copias = sorted((f for f in os.listdir(destino_dir) if f.startswith('proposals-')),
                    reverse=True)
    return os.path.join(destino_dir, copias[0]) if copias else None


def main():
    p = argparse.ArgumentParser(description="Copia de seguridad de la BBDD del generador.")
    p.add_argument('--dir', default=DIR_POR_DEFECTO, help="Directorio de destino")
    p.add_argument('--conservar', type=int, default=COPIAS_POR_DEFECTO,
                   help="Número de copias a conservar")
    p.add_argument('--sin-comprimir', action='store_true')
    p.add_argument('--verificar', action='store_true',
                   help="Solo verifica la última copia, sin crear una nueva")
    args = p.parse_args()

    if args.verificar:
        ruta = ultima_copia(args.dir)
        if not ruta:
            log.error("No hay ninguna copia en %s", args.dir)
            return 1
        ok, detalle = verificar(ruta)
        log.info("%s: %s (%s)", os.path.basename(ruta), "VÁLIDA" if ok else "CORRUPTA", detalle)
        return 0 if ok else 1

    ruta = crear_copia(args.dir, comprimir=not args.sin_comprimir)
    ok, detalle = verificar(ruta)
    if not ok:
        log.error("La copia recién creada NO es válida: %s", detalle)
        return 1
    log.info("Verificada: %s", detalle)
    rotar(args.dir, args.conservar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
