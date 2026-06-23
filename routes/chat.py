import os
import re
import json
import traceback
import logging
from contextlib import closing
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from middleware.auth import require_auth
from middleware.rate_limit import rate_limit
from models.database import get_db_connection
from utils.sanitize import sanitize_input_string
from utils.validators import EXCEL_LOCK_INDICATORS, EXCEL_LOCKED_MSG
from services.preview import generate_preview_data
from services.ai_chat import extract_data_block, validate_proposal_data
import services.scraper
import services.financial_engine
import services.ppt_generator
import services.ai_chat

log = logging.getLogger("routes.chat")
chat_bp = Blueprint('chat', __name__)

# ---------------------------------------------------------------------------
# Inicialización del motor de IA (falla silenciosamente si no hay API Key)
# ---------------------------------------------------------------------------
try:
    ai_engine = services.ai_chat.AIChatEngine()
    log.info("[CHATBOT IA] Motor Gemini inicializado correctamente.")
except Exception as e:
    log.warning("[CHATBOT IA] No se pudo inicializar Gemini: %s", e)
    log.warning("[CHATBOT IA] El chatbot funcionará en modo offline limitado.")
    ai_engine = None


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _extract_proposal(updated_history):
    if ai_engine is None:
        return None
    try:
        data = ai_engine.extract_proposal_data(updated_history)
        if data and data.get('company_name') and data.get('active_modules'):
            return data
    except Exception:
        log.warning("[CHATBOT] Error en extracción silenciosa")
    return None


def _save_proposal_data(session_id, extracted_data, title):
    with closing(get_db_connection()) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions
                SET proposal_data = ?, title = ?, updated_at = ?
                WHERE id = ?
            """, (
                json.dumps(extracted_data, ensure_ascii=False),
                title,
                datetime.now().isoformat(),
                session_id
            ))


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@chat_bp.route('/api/chat/create', methods=['POST'])
@rate_limit
def chat_create_session():
    try:
        data = request.json or {}
        first_message = sanitize_input_string(data.get('first_message', ''))
        title = first_message[:60] if first_message else "Nueva Conversación"

        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chat_sessions (title, messages, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    title,
                    json.dumps([]),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                session_id = cursor.lastrowid

        return jsonify({'session_id': session_id, 'title': title})

    except Exception as e:
        log.error("[CHATBOT] Error al crear sesión: %s", e)
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/chat/message', methods=['POST'])
@rate_limit
def chat_send_message():
    try:
        data = request.json or {}
        session_id = data.get('session_id')
        user_message = sanitize_input_string(data.get('message', ''))
        history = data.get('history', [])

        if not session_id:
            return jsonify({'error': 'ID de sesión requerido.'}), 400
        if not user_message:
            return jsonify({'error': 'El mensaje no puede estar vacío.'}), 400

        if ai_engine is None:
            return jsonify({
                'response': '⚠️ El motor de IA no está disponible en este momento. '
                           'Verifica que la variable de entorno GEMINI_API_KEY esté configurada correctamente.',
                'proposal_ready': False,
                'extracted_data': None
            })

        ai_response = ai_engine.send_message(history, user_message)

        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": ai_response}
        ]

        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE chat_sessions
                    SET messages = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    json.dumps(updated_history, ensure_ascii=False),
                    datetime.now().isoformat(),
                    session_id
                ))

        extracted_data = extract_data_block(ai_response)
        if extracted_data:
            valid, err = validate_proposal_data(extracted_data)
            if not valid:
                log.warning("Datos extraídos inválidos: %s", err)
                extracted_data = None

        proposal_ready = bool(extracted_data and extracted_data.get('company_name') and extracted_data.get('active_modules'))

        if not proposal_ready and "LISTO PARA GENERAR PROPUESTA" in ai_response:
            extracted_data = _extract_proposal(updated_history)
            if extracted_data:
                valid, err = validate_proposal_data(extracted_data)
                if valid:
                    proposal_ready = True
                    _save_proposal_data(session_id, extracted_data, f"Propuesta: {extracted_data.get('company_name', 'Nueva')}")
                else:
                    log.warning("Fallback extraction también inválido: %s", err)
                    extracted_data = None

        if proposal_ready and extracted_data:
            title = f"Propuesta: {extracted_data.get('company_name', 'Nueva')}"
            _save_proposal_data(session_id, extracted_data, title)

        return jsonify({
            'response': ai_response,
            'proposal_ready': proposal_ready,
            'extracted_data': extracted_data
        })

    except Exception as e:
        log.error("[CHATBOT] Error al enviar mensaje: %s", e)
        traceback.print_exc()
        err_msg = str(e)
        if any(indicator in err_msg.lower() for indicator in EXCEL_LOCK_INDICATORS):
            err_msg = EXCEL_LOCKED_MSG
        return jsonify({'error': err_msg}), 500


@chat_bp.route('/api/chat/sessions', methods=['GET'])
def chat_list_sessions():
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, messages, proposal_data, proposal_id, created_at, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()

        sessions = []
        for r in rows:
            sessions.append({
                'id': r['id'],
                'title': r['title'],
                'messages': r['messages'],
                'proposal_data': r['proposal_data'],
                'proposal_id': r['proposal_id'],
                'created_at': r['created_at'],
                'updated_at': r['updated_at']
            })

        return jsonify(sessions)

    except Exception as e:
        log.error("[CHATBOT] Error al listar sesiones: %s", e)
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/chat/delete/<int:session_id>', methods=['DELETE'])
def chat_delete_session(session_id):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
                deleted = cursor.rowcount

        if deleted == 0:
            return jsonify({'error': 'Sesión no encontrada.'}), 404

        return jsonify({'success': True, 'message': 'Sesión eliminada correctamente.'})

    except Exception as e:
        log.error("[CHATBOT] Error al eliminar sesión: %s", e)
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/chat/generate/<int:session_id>', methods=['POST'])
@require_auth
@rate_limit
def chat_generate_proposal(session_id):
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, messages, proposal_data
                FROM chat_sessions WHERE id = ?
            """, (session_id,))
            session = cursor.fetchone()

        if not session:
            return jsonify({'error': 'Sesión de chat no encontrada.'}), 404

        if not session['proposal_data']:
            return jsonify({'error': 'No hay datos de propuesta extraídos. Completa la conversación primero.'}), 400

        proposal_data = json.loads(session['proposal_data'])

        company_name = proposal_data.get('company_name', 'Empresa Peruana S.A.C.')
        sector = proposal_data.get('sector', 'Servicios Comerciales')
        description = proposal_data.get('description', '')
        complexity = proposal_data.get('complexity', 'Media')
        active_modules = proposal_data.get('active_modules', ['FI', 'CO', 'MM', 'SD'])
        revenue = float(proposal_data.get('revenue', 15000000))
        consulting_rate = float(proposal_data.get('consulting_rate', 60))
        support_percentage = float(proposal_data.get('support_percentage', 15))
        exchange_rate = float(proposal_data.get('exchange_rate', 3.78))

        if complexity not in ['Alta', 'Media']:
            complexity = 'Media' if len(active_modules) <= 4 else 'Alta'

        scraped_profile = services.scraper.get_company_profile(company_name, sector=sector)

        if description:
            scraped_profile['description'] = description
        scraped_profile['complexity'] = complexity
        scraped_profile['active_modules'] = ', '.join(active_modules)

        config = {
            'consulting_rate': consulting_rate,
            'support_percentage': support_percentage,
            'annual_revenue': revenue,
            'exchange_rate': exchange_rate,
            'igv_factor': 0.18,
            'modular_licenses': {
                'FI': proposal_data.get('lic_fi', 20000),
                'CO': proposal_data.get('lic_co', 15000),
                'MM': proposal_data.get('lic_mm', 15000),
                'SD': proposal_data.get('lic_sd', 15000),
                'PP': proposal_data.get('lic_pp', 20000),
                'PS': proposal_data.get('lic_ps', 15000)
            }
        }
        budget = proposal_data.get('budget')
        if budget and revenue > 0:
            config['consulting_rate'] = consulting_rate

        fin_results = services.financial_engine.calculate_financials(active_modules, config)
        summary = fin_results['summary']

        output_dir = current_app.config.get('OUTPUT_DIR', 'generated_decks')
        filename = f"Propuesta_{company_name.replace(' ', '_')}_{complexity}_Chatbot.pptx"
        ppt_path = os.path.join(output_dir, filename)

        services.ppt_generator.generate_deck(
            company_name=company_name,
            sector=sector,
            description=description or scraped_profile['description'],
            complexity=complexity,
            financial_data=fin_results,
            output_path=ppt_path
        )

        slides_preview = generate_preview_data(
            company_name, sector,
            description or scraped_profile['description'],
            complexity, fin_results
        )
        preview_json_str = json.dumps(slides_preview)

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
                    company_name, complexity, sector, description or scraped_profile['description'],
                    ', '.join(active_modules),
                    summary['total_weeks'], summary['total_hours'], summary['consulting_cost'],
                    summary['licensing_cost'], summary['support_cost'], summary['total_investment'],
                    summary['savings_annual'], summary['roi_five_years'], summary['payback_period'],
                    ppt_path, preview_json_str
                ))
                proposal_id = cursor.lastrowid

                cursor.execute("""
                    UPDATE chat_sessions
                    SET proposal_id = ?, updated_at = ?
                    WHERE id = ?
                """, (proposal_id, datetime.now().isoformat(), session_id))

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
            'download_url': f'/download/{proposal_id}'
        })

    except ValueError as e:
        log.warning("[CHAT GENERATE] Error de validación: %s", e)
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        log.error("[CHATBOT] Error al generar propuesta desde chat: %s", e)
        traceback.print_exc()
        err_msg = str(e)
        if any(indicator in err_msg.lower() for indicator in EXCEL_LOCK_INDICATORS):
            err_msg = EXCEL_LOCKED_MSG
        return jsonify({'error': err_msg}), 500
