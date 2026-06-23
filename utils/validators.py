import logging

log = logging.getLogger("validators")

EXCEL_LOCK_INDICATORS = ["Estimador", "access the file", "permission denied"]
EXCEL_LOCKED_MSG = (
    "El archivo de presupuesto 'Estimador S0 V2.0.xlsx' está bloqueado "
    "por otro usuario. Por favor, asegúrese de que el archivo Excel esté "
    "cerrado y vuelva a intentarlo."
)

RANGE_VALIDATORS = {
    'tarifa_hora_consultor': (10.0, 1000.0, "La tarifa del consultor debe estar entre $10 y $1000 USD."),
    'porcentaje_ams': (0.0, 1.0, "El porcentaje AMS de soporte debe estar entre 0% y 100% (0.0 a 1.0)."),
    'margen_saas': (0.0, 2.0, "El margen SaaS de recargo debe estar entre 0% y 200% (0.0 a 2.0)."),
    'anos_roi': (1, 20, "Los años de proyección del ROI deben estar entre 1 y 20 años."),
    'factor_igv': (0.0, 0.50, "El factor IGV de impuestos debe estar entre 0% y 50% (0.0 a 0.50)."),
    'tipo_cambio_pen': (1.0, 10.0, "El tipo de cambio a PEN debe estar entre 1.0 y 10.0."),
}


def _validate_and_convert_param(key, valor):
    if key in RANGE_VALIDATORS:
        min_val, max_val, msg = RANGE_VALIDATORS[key]
        check_val = int(valor) if key == 'anos_roi' else valor
        if not (min_val <= check_val <= max_val):
            raise ValueError(msg)
        return int(valor) if key == 'anos_roi' else valor
    return valor


def validate_inputs(data):
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
