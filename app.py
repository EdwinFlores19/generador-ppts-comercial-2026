from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
import traceback
import json
import re
from contextlib import closing
import scraper
import financial_engine
import ppt_generator

app = Flask(__name__)
DB_NAME = "proposals.db"
OUTPUT_DIR = "generated_decks"

# Asegurar que el directorio de propuestas generadas existe
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_db_connection():
    """
    Establece una conexión con la base de datos local SQLite y retorna el objeto de conexión.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_input_string(s):
    """
    Sanitiza cadenas de entrada de usuario para prevenir vulnerabilidades de inyección SQL
    y asegurar que no se introduzcan caracteres no deseados en la base de datos o archivos.
    
    Parámetros:
    - s (str): Cadena de texto de entrada.
    
    Retorna:
    - str: Cadena sanitizada.
    """
    if not s:
        return ""
    # Mitiga inyección SQL removiendo comillas, punto y coma y comentarios SQL
    sanitized = re.sub(r"['\"\;/\*]|--", "", s)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized
def validate_inputs(data):
    """
    Realiza una validación estricta de tipos de datos, rangos y valores límite
    para evitar datos atípicos o manipulaciones en los endpoints de preventa.
    
    Retorna un tuple: (is_valid, error_message_or_dict_values)
    """
    try:
        revenue = float(data.get('annual_revenue', 10000000.0))
        if revenue <= 0.0:
            return False, "La facturación anual debe ser un número positivo mayor a cero."
    except (ValueError, TypeError):
        return False, "La facturación anual debe ser un valor numérico válido."
        
    try:
        consulting_rate = float(data.get('consulting_rate', 60.0))
        if not (10.0 <= consulting_rate <= 1000.0):
            return False, "La tarifa horaria del consultor debe estar entre $10 y $1000 USD."
    except (ValueError, TypeError):
        return False, "La tarifa horaria de consultoría debe ser un valor numérico válido."
        
    try:
        support_percentage = float(data.get('support_percentage', 15.0))
        if not (0.0 <= support_percentage <= 100.0):
            return False, "El porcentaje de soporte AMS debe estar entre 0% y 100%."
    except (ValueError, TypeError):
        return False, "El porcentaje de soporte AMS debe ser un valor numérico válido."
        
    custom_licenses = data.get('modular_licenses', {})
    modular_licenses = {}
    for k, v in custom_licenses.items():
        try:
            if v is not None:
                val = float(v)
                if val < 0.0:
                    return False, f"El costo de licencia para el módulo {k} no puede ser negativo."
                modular_licenses[k] = val
        except (ValueError, TypeError):
            return False, f"El costo de licencia para el módulo {k} debe ser un valor numérico válido."
            
    return True, {
        'revenue': revenue,
        'consulting_rate': consulting_rate,
        'support_percentage': support_percentage,
        'modular_licenses': modular_licenses
    }

def generate_preview_data(company_name, sector, description, complexity, financial_data):
    """
    Genera la estructura de contenido de las diapositivas en formato JSON
    para permitir la previsualización del Pitch Deck en la interfaz de usuario.
    
    Parámetros:
    - company_name (str): Nombre del cliente.
    - sector (str): Sector industrial.
    - description (str): Descripción comercial.
    - complexity (str): Complejidad ('Alta' o 'Media').
    - financial_data (dict): Resultados calculados del motor financiero.
    
    Retorna:
    - list: Colección estructurada de diapositivas con viñetas.
    """
    summary = financial_data['summary']
    modules = financial_data['modules']
    
    # Duración de fases
    exp_wks = max([m['explore_weeks'] for m in modules.values()]) if modules else 5.68
    real_wks = max([m['realize_weeks'] for m in modules.values()]) if modules else 10.68
    deploy_wks = max([m['deploy_weeks'] for m in modules.values()]) if modules else 4.0
    
    slides = [
        {
            "num": 1,
            "title": "Portada Corporativa SEIDOR",
            "subtitle": "GROW with SAP S/4HANA Public Cloud",
            "bullets": [
                f"Propuesta de Transformación Digital para: {company_name}",
                f"Sector Industrial de Enfoque: {sector}",
                "Presentado por: SEIDOR Perú - Lead Solution Architecture & Preventa SAP"
            ]
        },
        {
            "num": 2,
            "title": "Entendimiento del Cliente y Contexto",
            "subtitle": f"Operaciones en el Perú - Sector: {sector}",
            "bullets": [
                description,
                "Necesidad de optimización en la estructura funcional y contable para dar soporte al crecimiento.",
                "Estandarización de procesos logísticos y adopción de mejores prácticas SAP globales en la nube."
            ]
        },
        {
            "num": 3,
            "title": "Dolores Operativos Clave",
            "subtitle": "Retos principales mapeados en la gestión actual",
            "bullets": [
                "Dolor Logístico: Falta de trazabilidad en tiempo real del stock y procesos de compra manuales.",
                "Dolor Financiero: Cierres contables mensuales lentos y conciliaciones multibancos complejas.",
                "Dolor de Gestión: Silos de información desarticulados e inexistencia de control presupuestal."
            ]
        },
        {
            "num": 4,
            "title": "La Solución Estratégica: SAP S/4HANA Cloud",
            "subtitle": "Acelerando la eficiencia operativa en la nube",
            "bullets": [
                "Estandarización bajo la metodología de mejores prácticas preconfiguradas.",
                "Experiencia de usuario intuitiva mediante el portal de SAP Fiori.",
                "Copiloto inteligente (SAP Joule) para agilizar el análisis documental y compras."
            ]
        },
        {
            "num": 5,
            "title": "Alcance Funcional: Procesos Core (FI & MM)",
            "subtitle": "Detalle de Finanzas y Gestión de Materiales",
            "bullets": [
                "Finanzas (FI): Contabilidad general, CxP, CxC, Activos Fijos y localización oficial SUNAT.",
                "Materiales (MM): Compras nacionales e importaciones, control de almacenes y regularizaciones."
            ]
        }
    ]
    
    current_num = 6
    if complexity == "Alta":
        slides.append({
            "num": current_num,
            "title": "Alcance Funcional: Control y Proyectos (CO & PS)",
            "subtitle": "Módulos de Controlling y Project System para Alta Complejidad",
            "bullets": [
                "Controlling (CO): Estructura de CECO/CEBI, órdenes internas y análisis detallado de margen.",
                "Proyectos (PS): WBS/PEP para controlar proyectos CAPEX/OPEX y control presupuestal de disponibilidad."
            ]
        })
        current_num += 1
        
    slides.extend([
        {
            "num": current_num,
            "title": "Casos de Uso de Inteligencia Artificial (SAP Joule)",
            "subtitle": "Operación tradicional manual vs. Eficiencia automática con SAP S/4HANA",
            "bullets": [
                "Búsqueda documental lenta vs. Respuestas inmediatas en lenguaje natural de Joule.",
                "Descoordinación en cotizaciones vs. Acceso al historial completo de compras en Fiori.",
                "Toma de decisiones en silos vs. Integración nativa de una única fuente de verdad."
            ]
        },
        {
            "num": current_num + 1,
            "title": "Gestión del Cambio y Cultura Organizacional",
            "subtitle": "Estrategia 'Un Solo Equipo' de SEIDOR Perú",
            "bullets": [
                "Capacitación focalizada en prompts para Joule y transacciones directas en Fiori.",
                "Alineación preventiva y mitigación de resistencia al cambio en fases iniciales.",
                "Metodología de feedback firme en el contenido y empático en la forma para los líderes."
            ]
        },
        {
            "num": current_num + 2,
            "title": "Propuesta Económica Localizada",
            "subtitle": f"Inversión bimoneda estimada con impuestos (T.C.: {summary['tipo_cambio_pen']})",
            "bullets": [
                f"Inversión Inicial Neta: {summary['usd']['net_investment_str']} USD / {summary['pen']['net_investment_str']} PEN",
                f"Impuesto IGV ({int(summary['factor_igv']*100)}%): {summary['usd']['igv_str']} USD / {summary['pen']['igv_str']} PEN",
                f"Inversión Total Facturable: {summary['usd']['total_facturable_str']} USD / {summary['pen']['total_facturable_str']} PEN"
            ]
        },
        {
            "num": current_num + 3,
            "title": "Cronograma y Retorno de Inversión",
            "subtitle": f"Hitos clave del proyecto en {summary['total_weeks']} Semanas",
            "bullets": [
                f"Fase Explore: Talleres de diseño y BPD en {exp_wks:.1f} semanas.",
                f"Fase Realize: Configuración y pruebas integrales en {real_wks:.1f} semanas.",
                f"Retorno ROI Proyectado: Payback de {summary['payback_period']:.2f} años y ROI de {summary['roi_five_years']:.1f}%."
            ]
        },
        {
            "num": current_num + 4,
            "title": "Cierre y Agradecimientos",
            "subtitle": "GROW with SAP: El futuro de la gestión en la nube",
            "bullets": [
                "Estandarización y trazabilidad 100% digital impulsado por SEIDOR Perú.",
                "Contacto y consultas comerciales: preventape@seidor.com."
            ]
        }
    ])
    
    return slides

@app.route('/')
def index():
    """
    Ruta raíz para cargar la SPA (Single Page Application) de preventa SAP de SEIDOR.
    """
    return render_template('index.html')

@app.route('/api/proposals', methods=['GET'])
def get_proposals():
    """
    API endpoint para obtener el listado histórico de propuestas de la base de datos de forma concurrente y segura.
    """
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
                    except Exception:
                        pass
                
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
        print(f"Error al obtener propuestas: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """
    API endpoint para obtener la configuración comercial parametrizada en la base de datos SQLite.
    """
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
        print(f"Error al leer configuración comercial: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    """
    API endpoint para guardar y actualizar las tarifas base de preventa en la base de datos SQLite.
    """
    try:
        data = request.json or {}
        with closing(get_db_connection()) as conn:
            with conn: # Transacción atómica segura
                cursor = conn.cursor()
                # Parámetros financieros comerciales editables
                valid_params = ['tarifa_hora_consultor', 'porcentaje_ams', 'margen_saas', 'anos_roi', 'factor_igv', 'tipo_cambio_pen']
                
                for key in valid_params:
                    if key in data:
                        try:
                            valor = float(data[key])
                            if valor < 0:
                                raise ValueError("El valor no puede ser negativo.")
                                
                            # Validaciones de límites financieros (Edge Cases)
                            if key == 'tarifa_hora_consultor' and not (10.0 <= valor <= 1000.0):
                                raise ValueError("La tarifa del consultor debe estar entre $10 y $1000 USD.")
                            elif key == 'porcentaje_ams' and not (0.0 <= valor <= 1.0):
                                raise ValueError("El porcentaje AMS de soporte debe estar entre 0% y 100% (0.0 a 1.0).")
                            elif key == 'margen_saas' and not (0.0 <= valor <= 2.0):
                                raise ValueError("El margen SaaS de recargo debe estar entre 0% y 200% (0.0 a 2.0).")
                            elif key == 'anos_roi' and not (1 <= int(valor) <= 20):
                                raise ValueError("Los años de proyección del ROI deben estar entre 1 y 20 años.")
                            elif key == 'factor_igv' and not (0.0 <= valor <= 0.50):
                                raise ValueError("El factor IGV de impuestos debe estar entre 0% y 50% (0.0 a 0.50).")
                            elif key == 'tipo_cambio_pen' and not (1.0 <= valor <= 10.0):
                                raise ValueError("El tipo de cambio a PEN debe estar entre 1.0 y 10.0.")
                                
                            cursor.execute("""
                                UPDATE configuracion_comercial
                                SET valor = ?
                                WHERE parametro = ?
                            """, (valor, key))
                        except (ValueError, TypeError) as val_err:
                            return jsonify({'error': f"El valor para '{key}' no es válido: {val_err}"}), 400
        return jsonify({'success': True, 'message': 'Configuración comercial guardada con éxito en SQLite.'})
    except Exception as e:
        print(f"Error al actualizar configuración comercial: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview', methods=['POST'])
def preview_proposal():
    """
    API endpoint para retornar la estructura JSON de la presentación para previsualización asíncrona rápida en la UI,
    sin generar físicamente el archivo PPTX.
    """
    try:
        data = request.json or {}
        company_name = sanitize_input_string(data.get('company_name', ''))
        sector_input = sanitize_input_string(data.get('sector', ''))
        
        if not company_name:
            return jsonify({'error': 'El nombre de la empresa es un dato obligatorio.'}), 400
            
        # Validar y restringir rangos de entrada
        is_valid, validation_res = validate_inputs(data)
        if not is_valid:
            return jsonify({'error': validation_res}), 400
            
        revenue = validation_res['revenue']
        consulting_rate = validation_res['consulting_rate']
        support_percentage = validation_res['support_percentage']
        modular_licenses = validation_res['modular_licenses']
        complexity_mode = data.get('complexity_mode', 'auto')
        
        # 1. Obtener perfil comercial (Preset o Fallback sectorial)
        scraped_profile = scraper.get_company_profile(company_name, sector=sector_input)
        
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
        
        # 2. Ejecutar Motor Financiero
        config = {
            'consulting_rate': consulting_rate,
            'support_percentage': support_percentage,
            'annual_revenue': revenue,
            'modular_licenses': modular_licenses
        }
        fin_results = financial_engine.calculate_financials(active_modules_list, config)
        
        # 3. Generar la estructura de la presentación
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
    except Exception as e:
        print(f"Error al previsualizar la propuesta: {e}")
        err_msg = str(e)
        if "Estimador" in err_msg or "access the file" in err_msg.lower() or "permission denied" in err_msg.lower():
            err_msg = "El archivo de presupuesto 'Estimador S0 V2.0.xlsx' está bloqueado por otro usuario. Por favor, asegúrese de que el archivo Excel esté cerrado y vuelva a intentarlo."
        return jsonify({'error': err_msg}), 500

@app.route('/api/generate', methods=['POST'])
def generate_proposal():
    """
    API endpoint para procesar y compilar la propuesta final en PPTX, registrando en base de datos.
    """
    try:
        data = request.json or {}
        
        company_name = sanitize_input_string(data.get('company_name', ''))
        sector_input = sanitize_input_string(data.get('sector', ''))
        
        if not company_name:
            return jsonify({'error': 'El nombre de la empresa es un dato obligatorio.'}), 400
            
        # Validar y restringir rangos de entrada
        is_valid, validation_res = validate_inputs(data)
        if not is_valid:
            return jsonify({'error': validation_res}), 400
            
        revenue = validation_res['revenue']
        consulting_rate = validation_res['consulting_rate']
        support_percentage = validation_res['support_percentage']
        modular_licenses = validation_res['modular_licenses']
        complexity_mode = data.get('complexity_mode', 'auto')
        
        # 1. Scraper
        scraped_profile = scraper.get_company_profile(company_name, sector=sector_input)
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
        
        # 2. Motor Financiero
        config = {
            'consulting_rate': consulting_rate,
            'support_percentage': support_percentage,
            'annual_revenue': revenue,
            'modular_licenses': modular_licenses
        }
        fin_results = financial_engine.calculate_financials(active_modules_list, config)
        summary = fin_results['summary']
        
        # 3. Generar la estructura preview
        slides_preview = generate_preview_data(company_name, sector, description, complexity, fin_results)
        preview_json_str = json.dumps(slides_preview)
        
        # 4. Generar PowerPoint físico
        filename = f"Propuesta_{company_name.replace(' ', '_')}_{complexity}.pptx"
        ppt_path = os.path.join(OUTPUT_DIR, filename)
        
        ppt_generator.generate_deck(
            company_name=company_name,
            sector=sector,
            description=description,
            complexity=complexity,
            financial_data=fin_results,
            output_path=ppt_path
        )
        
        # 5. Insertar en base de datos SQLite de forma segura con transacción de contexto
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
    except Exception as e:
        print(f"Error al generar propuesta comercial SAP: {e}")
        traceback.print_exc()
        err_msg = str(e)
        if "Estimador" in err_msg or "access the file" in err_msg.lower() or "permission denied" in err_msg.lower():
            err_msg = "El archivo de presupuesto 'Estimador S0 V2.0.xlsx' está bloqueado por otro usuario. Por favor, asegúrese de que el archivo Excel esté cerrado y vuelva a intentarlo."
        return jsonify({'error': err_msg}), 500

@app.route('/download/<int:proposal_id>')
def download_ppt(proposal_id):
    """
    Ruta para descargar el entregable de PowerPoint final generado para un cliente.
    """
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
        print(f"Error al descargar la presentación: {e}")
        return "Internal Server Error", 500

if __name__ == '__main__':
    # Habilitar el servidor Flask local en el puerto estándar 5000
    app.run(debug=True, port=5000)
