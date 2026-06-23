import os
import re
import json
import traceback
import logging
from contextlib import closing
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app
from middleware.auth import require_auth
from middleware.rate_limit import rate_limit
from models.database import get_db_connection
from utils.sanitize import sanitize_input_string
from utils.validators import validate_inputs, EXCEL_LOCK_INDICATORS, EXCEL_LOCKED_MSG
from services.preview import generate_preview_data
import services.scraper
import services.financial_engine
import services.ppt_generator

log = logging.getLogger("routes.proposals")
proposals_bp = Blueprint('proposals', __name__)


@proposals_bp.route('/api/proposals', methods=['GET'])
@require_auth
def get_proposals():
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM proposals ORDER BY created_at DESC")
            rows = cursor.fetchall()
            proposals = []
            for r in rows:
                preview_data = []
                if r['preview_json']:
                    try:
                        preview_data = json.loads(r['preview_json'])
                    except (json.JSONDecodeError, TypeError):
                        log.warning("preview_json corrupto para propuesta ID=%s", r['id'])

                proposals.append({
                    'id': r['id'],
                    'company_name': r['company_name'],
                    'complexity': r['complexity'],
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
            return jsonify(proposals)
    except Exception as e:
        log.error("Error al obtener propuestas: %s", e)
        return jsonify({'error': str(e)}), 500


@proposals_bp.route('/api/config', methods=['GET'])
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
    except Exception as e:
        log.error("Error al leer configuración comercial: %s", e)
        return jsonify({'error': str(e)}), 500


@proposals_bp.route('/api/config', methods=['POST'])
@require_auth
def update_config():
    try:
        data = request.json or {}
        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                valid_params = [
                    'tarifa_hora_consultor', 'porcentaje_ams', 'margen_saas',
                    'anos_roi', 'factor_igv', 'tipo_cambio_pen'
                ]

                for key in valid_params:
                    if key in data:
                        try:
                            valor = float(data[key])
                            if valor < 0:
                                raise ValueError("El valor no puede ser negativo.")
                            from utils.validators import _validate_and_convert_param
                            valor = _validate_and_convert_param(key, valor)
                            cursor.execute("""
                                UPDATE configuracion_comercial
                                SET valor = ?
                                WHERE parametro = ?
                            """, (valor, key))
                        except (ValueError, TypeError) as val_err:
                            return jsonify({'error': f"El valor para '{key}' no es válido: {val_err}"}), 400
        return jsonify({'success': True, 'message': 'Configuración comercial guardada con éxito en SQLite.'})
    except Exception as e:
        log.error("Error al actualizar configuración comercial: %s", e)
        return jsonify({'error': str(e)}), 500


@proposals_bp.route('/api/preview', methods=['POST'])
@rate_limit
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
        slides_preview = generate_preview_data(company_name, sector, description, complexity, fin_results)

        return jsonify({
            'success': True,
            'company_name': company_name,
            'complexity': complexity,
            'sector': sector,
            'total_investment': fin_results['summary']['total_investment'],
            'total_investment_net': fin_results['summary']['total_investment_net'],
            'total_weeks': fin_results['summary']['total_weeks'],
            'roi': fin_results['summary']['roi_five_years'],
            'payback': fin_results['summary']['payback_period'],
            'financial_data': fin_results,
            'slides_preview': slides_preview
        })
    except ValueError as e:
        log.warning("[PREVIEW] Error de validación: %s", e)
        return jsonify({'error': str(e)}), 400
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
@require_auth
@rate_limit
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

        slides_preview = generate_preview_data(company_name, sector, description, complexity, fin_results)
        preview_json_str = json.dumps(slides_preview)

        output_dir = current_app.config.get('OUTPUT_DIR', 'generated_decks')
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', company_name)
        filename = f"Propuesta_{safe_name.replace(' ', '_')}_{complexity}.pptx"
        ppt_path = os.path.join(output_dir, filename)

        services.ppt_generator.generate_deck(
            company_name=company_name,
            sector=sector,
            description=description,
            complexity=complexity,
            financial_data=fin_results,
            output_path=ppt_path
        )

        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO proposals (
                        company_name, complexity, sector, description, active_modules,
                        total_weeks, total_hours, consulting_cost, licensing_cost, support_cost,
                        total_investment, savings_annual, roi_five_years, payback_period, ppt_path, preview_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_name, complexity, sector, description, active_modules_str,
                    summary['total_weeks'], summary['total_hours'], summary['consulting_cost'],
                    summary['licensing_cost'], summary['support_cost'], summary['total_investment'],
                    summary['savings_annual'], summary['roi_five_years'], summary['payback_period'],
                    ppt_path, preview_json_str
                ))
                proposal_id = cursor.lastrowid

        return jsonify({
            'success': True,
            'proposal_id': proposal_id,
            'company_name': company_name,
            'complexity': complexity,
            'sector': sector,
            'total_investment': summary['total_investment'],
            'total_weeks': summary['total_weeks'],
            'roi': summary['roi_five_years'],
            'payback': summary['payback_period'],
            'slides_preview': slides_preview
        })
    except ValueError as e:
        log.warning("[GENERATE] Error de validación: %s", e)
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        log.error("Error al generar propuesta comercial SAP: %s", e)
        traceback.print_exc()
        err_msg = str(e)
        if any(indicator in err_msg.lower() for indicator in EXCEL_LOCK_INDICATORS):
            err_msg = EXCEL_LOCKED_MSG
        return jsonify({'error': err_msg}), 500


@proposals_bp.route('/download/<int:proposal_id>', methods=['GET'])
def download_ppt(proposal_id):
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ppt_path, company_name, complexity FROM proposals WHERE id = ?", (proposal_id,))
            row = cursor.fetchone()

        if not row:
            return "Propuesta comercial no localizada.", 404

        ppt_path = row['ppt_path']
        if not os.path.exists(ppt_path):
            return "Archivo de presentación no encontrado en el servidor.", 404

        clean_name = f"Propuesta_{row['company_name'].replace(' ', '_')}_{row['complexity']}.pptx"
        return send_file(ppt_path, as_attachment=True, download_name=clean_name)
    except Exception as e:
        log.error("Error al descargar la presentación: %s", e)
        return "Internal Server Error", 500
