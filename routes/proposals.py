import os
import re
import json
import math
import traceback
import logging
from contextlib import closing
from datetime import datetime
from werkzeug.exceptions import HTTPException
from flask import Blueprint, request, jsonify, send_file, current_app
from middleware.auth import require_auth
from middleware.rate_limit import rate_limit
from models.database import get_db_connection
from utils.paging import parse_paging, paging_headers
from utils.sanitize import sanitize_input_string
from utils.validators import validate_inputs, EXCEL_LOCK_INDICATORS, EXCEL_LOCKED_MSG
from services.preview import generate_preview_data
from services.auditoria import consultar as consultar_auditoria, purgar_antiguas, registrar
from services.scope_items import normalize_edition
from services.themes import (
    CLAVES_COLOR, FUENTES_SEGURAS, TemaInvalido, listar_temas, normalizar_tema
)
import services.scraper
import services.financial_engine
import services.ppt_generator

# Las excepciones HTTP del framework (413 petición demasiado grande, 429, …) se
# dejan pasar: un `except Exception` genérico las convertía en un 500 con el
# mensaje equivocado. Werkzeug las lanza al LEER el cuerpo, o sea ya dentro del
# try de la vista, así que hay que re-lanzarlas explícitamente.
log = logging.getLogger("routes.proposals")
proposals_bp = Blueprint('proposals', __name__)


# El historial crecía sin techo: con 405 propuestas el endpoint devolvía el JSON
# completo (preview_json incluido, ~2 MB) y el navegador pintaba 405 filas de
# golpe. Se pagina en servidor y el front pide más bajo demanda.
# @rate_limit va ENCIMA de @require_auth a propósito: los decoradores se
# aplican de abajo arriba, así que el de más arriba se ejecuta primero. Con el
# orden contrario, un 401 salía sin pasar por el limitador y se podían probar
# tokens sin límite (comprobado: 40 intentos fallidos, 0 respuestas 429).
@proposals_bp.route('/api/proposals', methods=['GET'])
@rate_limit
@require_auth
def get_proposals():
    try:
        limit, offset = parse_paging(request.args)
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS n FROM proposals")
            total = cursor.fetchone()['n']
            # created_at puede empatar entre filas generadas en el mismo segundo:
            # el id como segundo criterio evita que la paginación repita o salte filas.
            cursor.execute(
                "SELECT * FROM proposals ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cursor.fetchall()
            proposals = []
            for r in rows:
                preview_data = []
                if r['preview_json']:
                    try:
                        preview_data = json.loads(r['preview_json'])
                    except (json.JSONDecodeError, TypeError):
                        log.warning("preview_json corrupto para propuesta ID=%s", r['id'])

                row_keys = r.keys()
                proposals.append({
                    'id': r['id'],
                    'company_name': r['company_name'],
                    'complexity': r['complexity'],
                    'edition': r['edition'] if 'edition' in row_keys else 'Public',
                    'theme_id': r['theme_id'] if 'theme_id' in row_keys else 'seidor',
                    'sector': r['sector'],
                    'description': r['description'],
                    'active_modules': r['active_modules'],
                    'total_weeks': r['total_weeks'],
                    'total_hours': r['total_hours'],
                    'consulting_cost': r['consulting_cost'],
                    'licensing_cost': r['licensing_cost'],
                    'support_cost': r['support_cost'],
                    'total_investment': r['total_investment'],
                    'savings_annual': r['savings_annual'],
                    'roi_five_years': r['roi_five_years'],
                    'payback_period': r['payback_period'],
                    'ppt_path': r['ppt_path'],
                    'preview_json': preview_data,
                    'created_at': r['created_at']
                })
            return paging_headers(jsonify(proposals), total, limit, offset)
    except HTTPException:
        raise
    except Exception as e:
        # El detalle va al log, no al cliente: str(e) filtraba rutas del
        # servidor y mensajes internos de SQLite en la respuesta HTTP.
        log.error("Error al obtener propuestas: %s", e, exc_info=True)
        return jsonify({'error': 'No se pudo cargar el historial de propuestas.'}), 500


@proposals_bp.route('/api/auditoria', methods=['GET'])
@rate_limit
@require_auth
def get_auditoria():
    """
    Registro de auditoría: qué se hizo con los datos de los prospectos.

    Es de solo lectura a propósito. Un registro que la propia aplicación puede
    borrar no sirve como evidencia; la depuración va por retención (purga por
    antigüedad), no por borrado selectivo.
    """
    try:
        limite, offset = parse_paging(request.args, page_size=100)
        accion = request.args.get('accion') or None
        eventos, total = consultar_auditoria(limite=limite, offset=offset, accion=accion)
        return paging_headers(jsonify(eventos), total, limite, offset)
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al leer el registro de auditoría: %s", e, exc_info=True)
        return jsonify({'error': 'No se pudo leer el registro de auditoría.'}), 500


@proposals_bp.route('/api/retencion', methods=['POST'])
@rate_limit
@require_auth
def ejecutar_retencion():
    """
    Aplica la política de conservación: borra propuestas y conversaciones que
    superen el plazo, con sus PPTX.

    Por defecto **simula**: hay que pedir explícitamente `confirmar: true` para
    que borre. Es una operación irreversible sobre datos comerciales reales.
    """
    try:
        data = request.json or {}
        dias = data.get('dias')
        confirmar = data.get('confirmar') is True
        resumen = purgar_antiguas(
            dias=dias,
            directorio_salida=current_app.config.get('OUTPUT_DIR', 'generated_decks'),
            simular=not confirmar,
        )
        resumen['mensaje'] = (
            'Purga aplicada.' if confirmar
            else 'Simulación: no se ha borrado nada. Envía {"confirmar": true} para ejecutarla.'
        )
        return jsonify(resumen)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al ejecutar la retención: %s", e, exc_info=True)
        return jsonify({'error': 'No se pudo aplicar la política de retención.'}), 500


@proposals_bp.route('/api/themes', methods=['GET'])
@rate_limit
@require_auth
def get_themes():
    """
    Catálogo de temas visuales para el selector de la interfaz.

    Devuelve también la lista de fuentes admitidas y las claves de color, para
    que el formulario de tema a medida se construya solo y no se desincronice
    con services/themes.py.
    """
    return jsonify({
        'temas': listar_temas(),
        'por_defecto': 'seidor',
        'fuentes': list(FUENTES_SEGURAS),
        'claves_color': list(CLAVES_COLOR),
    })


@proposals_bp.route('/api/config', methods=['GET'])
@rate_limit
@require_auth
def get_config():
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT parametro, valor, descripcion FROM configuracion_comercial")
            rows = cursor.fetchall()
            config = {}
            for r in rows:
                config[r['parametro']] = {
                    'valor': r['valor'],
                    'descripcion': r['descripcion']
                }
            return jsonify(config)
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al leer configuración comercial: %s", e, exc_info=True)
        return jsonify({'error': 'No se pudo leer la configuración comercial.'}), 500


CONFIG_PARAMS = (
    'tarifa_hora_consultor', 'porcentaje_ams', 'margen_saas',
    'anos_roi', 'factor_igv', 'tipo_cambio_pen', 'factor_ahorro'
)


@proposals_bp.route('/api/config', methods=['POST'])
@rate_limit
@require_auth
def update_config():
    """
    Guarda los parámetros comerciales. Se valida TODO antes de escribir nada:
    antes se validaba y escribía parámetro a parámetro dentro de la
    transacción, y un `return ... 400` a mitad del bucle salía del bloque
    `with conn:` de forma normal, es decir **haciendo commit** de los
    parámetros ya escritos. Enviar {tarifa: 999, igv: 0.99} dejaba la tarifa
    en 999 mientras el consultor leía "no válido" y creía que no se había
    guardado nada — y todas las propuestas siguientes salían con esa tarifa.
    """
    try:
        data = request.json or {}
        from utils.validators import _validate_and_convert_param

        cambios = []
        for key in CONFIG_PARAMS:
            if key not in data:
                continue
            try:
                valor = float(data[key])
            except (ValueError, TypeError):
                return jsonify({'error': f"El valor para '{key}' no es un número válido."}), 400
            if not math.isfinite(valor):
                return jsonify({'error': f"El valor para '{key}' no es un número válido."}), 400
            try:
                if valor < 0:
                    raise ValueError("El valor no puede ser negativo.")
                valor = _validate_and_convert_param(key, valor)
            except (ValueError, TypeError) as val_err:
                return jsonify({'error': f"El valor para '{key}' no es válido: {val_err}"}), 400
            cambios.append((valor, key))

        if not cambios:
            return jsonify({'error': 'No se recibió ningún parámetro válido para guardar.'}), 400

        with closing(get_db_connection()) as conn:
            with conn:
                conn.executemany(
                    "UPDATE configuracion_comercial SET valor = ? WHERE parametro = ?",
                    cambios
                )
        registrar('config_modificada',
                  detalle=', '.join(f"{k}={v}" for v, k in cambios))

        return jsonify({
            'success': True,
            'message': 'Configuración comercial guardada con éxito en SQLite.',
            'actualizados': [k for _, k in cambios]
        })
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al actualizar configuración comercial: %s", e, exc_info=True)
        return jsonify({'error': 'No se pudo guardar la configuración comercial.'}), 500


# La previsualización expone tarifas, márgenes y el cálculo comercial completo:
# es información interna, no pública.
@proposals_bp.route('/api/preview', methods=['POST'])
@rate_limit
@require_auth
def preview_proposal():
    try:
        data = request.json or {}
        company_name = sanitize_input_string(data.get('company_name', ''))
        sector_input = sanitize_input_string(data.get('sector', ''))

        if not company_name:
            return jsonify({'error': 'El nombre de la empresa es un dato obligatorio.'}), 400

        is_valid, validation_res = validate_inputs(data)
        if not is_valid:
            return jsonify({'error': validation_res}), 400

        revenue = validation_res['revenue']
        consulting_rate = validation_res['consulting_rate']
        support_percentage = validation_res['support_percentage']
        modular_licenses = validation_res['modular_licenses']
        complexity_mode = data.get('complexity_mode', 'auto')
        edition = normalize_edition(data.get('edition'))
        try:
            tema = normalizar_tema(data.get('theme'))
        except TemaInvalido as e:
            # 400 y no 500: el tema lo elige el consultor y el mensaje le dice
            # exactamente qué color arreglar.
            return jsonify({'error': str(e)}), 400

        scraped_profile = services.scraper.get_company_profile(company_name, sector=sector_input)
        complexity = scraped_profile['complexity']
        sector = scraped_profile['sector']
        description = scraped_profile['description']
        active_modules_str = scraped_profile['active_modules']

        if complexity_mode == 'alta':
            complexity = 'Alta'
            active_modules_str = 'FI, CO, MM, SD, PP, PS'
        elif complexity_mode == 'media':
            complexity = 'Media'
            active_modules_str = 'FI, CO, MM, SD'

        active_modules_list = [m.strip() for m in active_modules_str.split(',')]

        config = {
            'consulting_rate': consulting_rate,
            'support_percentage': support_percentage,
            'annual_revenue': revenue,
            'modular_licenses': modular_licenses
        }
        fin_results = services.financial_engine.calculate_financials(active_modules_list, config)
        slides_preview = generate_preview_data(company_name, sector, description, complexity, fin_results,
                                               edition=edition)

        return jsonify({
            'success': True,
            'company_name': company_name,
            'complexity': complexity,
            'edition': edition,
            'sector': sector,
            'total_investment': fin_results['summary']['total_investment'],
            'total_investment_net': fin_results['summary']['total_investment_net'],
            'total_weeks': fin_results['summary']['total_weeks'],
            'roi': fin_results['summary']['roi_five_years'],
            'payback': fin_results['summary']['payback_period'],
            'advertencias': fin_results['summary'].get('advertencias', []),
            'financial_data': fin_results,
            'slides_preview': slides_preview,
            # La web pinta la previsualización con estos colores, así que el
            # consultor ve el tema antes de gastar 20 s en generar el PPTX.
            'theme': tema
        })
    except ValueError as e:
        log.warning("[PREVIEW] Error de validación: %s", e)
        return jsonify({'error': str(e)}), 400
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al previsualizar la propuesta: %s", e)
        traceback.print_exc()
        err_msg = str(e)
        if any(indicator in err_msg.lower() for indicator in EXCEL_LOCK_INDICATORS):
            err_msg = EXCEL_LOCKED_MSG
        return jsonify({'error': err_msg}), 500


@proposals_bp.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'db': os.path.exists(current_app.config.get('DB_NAME', 'proposals.db')),
        'excel': os.path.exists(services.financial_engine.EXCEL_PATH),
    })


@proposals_bp.route('/api/generate', methods=['POST'])
@rate_limit
@require_auth
def generate_proposal():
    try:
        data = request.json or {}
        company_name = sanitize_input_string(data.get('company_name', ''))
        sector_input = sanitize_input_string(data.get('sector', ''))

        if not company_name:
            return jsonify({'error': 'El nombre de la empresa es un dato obligatorio.'}), 400

        is_valid, validation_res = validate_inputs(data)
        if not is_valid:
            return jsonify({'error': validation_res}), 400

        revenue = validation_res['revenue']
        consulting_rate = validation_res['consulting_rate']
        support_percentage = validation_res['support_percentage']
        modular_licenses = validation_res['modular_licenses']
        complexity_mode = data.get('complexity_mode', 'auto')
        edition = normalize_edition(data.get('edition'))
        try:
            tema = normalizar_tema(data.get('theme'))
        except TemaInvalido as e:
            # 400 y no 500: el tema lo elige el consultor y el mensaje le dice
            # exactamente qué color arreglar.
            return jsonify({'error': str(e)}), 400

        scraped_profile = services.scraper.get_company_profile(company_name, sector=sector_input)
        complexity = scraped_profile['complexity']
        sector = scraped_profile['sector']
        description = scraped_profile['description']
        active_modules_str = scraped_profile['active_modules']

        if complexity_mode == 'alta':
            complexity = 'Alta'
            active_modules_str = 'FI, CO, MM, SD, PP, PS'
        elif complexity_mode == 'media':
            complexity = 'Media'
            active_modules_str = 'FI, CO, MM, SD'

        active_modules_list = [m.strip() for m in active_modules_str.split(',')]

        config = {
            'consulting_rate': consulting_rate,
            'support_percentage': support_percentage,
            'annual_revenue': revenue,
            'modular_licenses': modular_licenses
        }
        fin_results = services.financial_engine.calculate_financials(active_modules_list, config)
        summary = fin_results['summary']

        slides_preview = generate_preview_data(company_name, sector, description, complexity, fin_results,
                                               edition=edition)
        preview_json_str = json.dumps(slides_preview)

        output_dir = current_app.config.get('OUTPUT_DIR', 'generated_decks')
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', company_name)
        sello = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = f"Propuesta_{safe_name.replace(' ', '_')}_{complexity}_{sello}.pptx"
        ppt_path = os.path.join(output_dir, filename)

        services.ppt_generator.generate_deck(
            company_name=company_name,
            sector=sector,
            description=description,
            complexity=complexity,
            financial_data=fin_results,
            output_path=ppt_path,
            edition=edition,
            theme=tema
        )

        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO proposals (
                        company_name, complexity, sector, description, active_modules,
                        total_weeks, total_hours, consulting_cost, licensing_cost, support_cost,
                        total_investment, savings_annual, roi_five_years, payback_period, ppt_path, preview_json,
                        edition, theme_id, theme_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_name, complexity, sector, description, active_modules_str,
                    summary['total_weeks'], summary['total_hours'], summary['consulting_cost'],
                    summary['licensing_cost'], summary['support_cost'], summary['total_investment'],
                    summary['savings_annual'], summary['roi_five_years'], summary['payback_period'],
                    ppt_path, preview_json_str, edition, tema['id'], json.dumps(tema)
                ))
                proposal_id = cursor.lastrowid

        registrar('propuesta_generada', recurso=proposal_id,
                  detalle=f"{company_name} · {complexity} · {edition} · tema {tema['id']}")

        return jsonify({
            'success': True,
            'proposal_id': proposal_id,
            'company_name': company_name,
            'complexity': complexity,
            'edition': edition,
            'sector': sector,
            'total_investment': summary['total_investment'],
            'total_weeks': summary['total_weeks'],
            'roi': summary['roi_five_years'],
            'payback': summary['payback_period'],
            'advertencias': summary.get('advertencias', []),
            'theme': tema,
            'slides_preview': slides_preview
        })
    except ValueError as e:
        log.warning("[GENERATE] Error de validación: %s", e)
        return jsonify({'error': str(e)}), 400
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al generar propuesta comercial SAP: %s", e, exc_info=True)
        err_msg = str(e)
        if any(indicator in err_msg.lower() for indicator in EXCEL_LOCK_INDICATORS):
            # Este sí se devuelve tal cual: dice al consultor exactamente qué
            # hacer (cerrar el Excel del estimador).
            return jsonify({'error': EXCEL_LOCKED_MSG}), 500
        return jsonify({
            'error': 'No se pudo generar la propuesta. Revise el log del servidor para el detalle.'
        }), 500


# La descarga entrega el PPTX de un cliente concreto. Sin autenticación, y con
# los ids siendo consecutivos, bastaba recorrer /download/1..N para bajarse
# todas las propuestas comerciales del historial. El front la pide por fetch
# con cabecera Authorization (descargarArchivo en common.js), no con <a href>,
# porque una navegación del navegador no puede enviar cabeceras.
def _nombre_descarga(company_name, complexity):
    """
    Nombre del archivo que ve el cliente al descargar. Se limpian los caracteres
    que rompen el header Content-Disposition o el sistema de archivos; el
    saneo de entrada preserva a propósito comillas y ampersands (razones
    sociales reales), así que aquí hay que quitarlos.
    """
    base = f"Propuesta_{company_name or 'Cliente'}_{complexity or 'Media'}"
    base = re.sub(r'[\\/:*?"<>|\r\n]', '', base)
    base = re.sub(r'\s+', '_', base).strip('_')
    return (base[:120] or 'Propuesta') + '.pptx'


@proposals_bp.route('/download/<int:proposal_id>', methods=['GET'])
@rate_limit
@require_auth
def download_ppt(proposal_id):
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ppt_path, company_name, complexity FROM proposals WHERE id = ?", (proposal_id,))
            row = cursor.fetchone()

        if not row:
            return "Propuesta comercial no localizada.", 404

        ppt_path = row['ppt_path']
        # Misma contención que en el borrado: solo se sirven archivos que estén
        # dentro de OUTPUT_DIR, nunca una ruta arbitraria de la BBDD.
        output_dir = os.path.abspath(current_app.config.get('OUTPUT_DIR', 'generated_decks'))
        abs_path = os.path.abspath(ppt_path or '')
        if not abs_path.startswith(output_dir + os.sep):
            log.error("Ruta de PPTX fuera del directorio de salida para la propuesta %s", proposal_id)
            return "Archivo de presentación no disponible.", 404
        if not os.path.exists(abs_path):
            return "Archivo de presentación no encontrado en el servidor.", 404

        clean_name = _nombre_descarga(row['company_name'], row['complexity'])
        registrar('propuesta_descargada', recurso=proposal_id, detalle=row['company_name'])
        return send_file(abs_path, as_attachment=True, download_name=clean_name)
    except HTTPException:
        raise
    except Exception as e:
        log.error("Error al descargar la presentación: %s", e)
        return "Internal Server Error", 500


@proposals_bp.route('/api/proposals/<int:proposal_id>', methods=['DELETE'])
@rate_limit
@require_auth
def delete_proposal(proposal_id):
    """
    Elimina una propuesta del historial y su archivo PPTX.

    Sin esta ruta, una propuesta generada por error (nombre mal escrito, cifras
    equivocadas) quedaba para siempre en el historial y, al ser la más reciente,
    alimentaba el panel de "Métricas de la Última Propuesta" de forma permanente
    hasta generar otra.
    """
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ppt_path FROM proposals WHERE id = ?", (proposal_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Propuesta no encontrada.'}), 404

                ppt_path = row['ppt_path']
                # Desvincula la propuesta de las sesiones de chat que la
                # referencian (la FK impediría el borrado con foreign_keys=ON).
                cursor.execute("UPDATE chat_sessions SET proposal_id = NULL WHERE proposal_id = ?", (proposal_id,))
                cursor.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))

        # El archivo se borra fuera de la transacción: si falla, la fila ya se
        # eliminó y el usuario no queda bloqueado por un PPTX huérfano.
        if ppt_path:
            try:
                output_dir = os.path.abspath(current_app.config.get('OUTPUT_DIR', 'generated_decks'))
                abs_path = os.path.abspath(ppt_path)
                # Nunca borrar fuera del directorio de salida.
                if abs_path.startswith(output_dir + os.sep) and os.path.exists(abs_path):
                    os.remove(abs_path)
            except OSError as file_err:
                log.warning("Propuesta %s eliminada, pero no se pudo borrar %s: %s",
                            proposal_id, ppt_path, file_err)

        registrar('propuesta_eliminada', recurso=proposal_id)

        return jsonify({'success': True, 'message': 'Propuesta eliminada del historial.'})

    except HTTPException:
        raise
    except Exception as e:
        # Sin exc_info ni mensaje genérico, este manejador devolvía str(e) al
        # cliente: era el último que quedaba filtrando detalle interno.
        log.error("Error al eliminar la propuesta %s: %s", proposal_id, e, exc_info=True)
        return jsonify({'error': 'No se pudo eliminar la propuesta.'}), 500
