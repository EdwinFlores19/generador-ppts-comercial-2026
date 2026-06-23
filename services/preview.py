import logging

log = logging.getLogger("preview")


def generate_preview_data(company_name, sector, description, complexity, financial_data):
    summary = financial_data['summary']
    modules = financial_data['modules']

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
                f"Fase Deploy: Migración y Go-Live en {deploy_wks:.1f} semanas.",
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
