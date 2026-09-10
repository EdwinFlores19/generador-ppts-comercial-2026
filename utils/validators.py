import logging
import math

log = logging.getLogger("validators")

# Cota superior de la facturación anual. No es un capricho: float("nan") e
# float("inf") superaban la comprobación `revenue <= 0` (toda comparación con
# NaN es False), se propagaban por todo el motor financiero y acababan en la
# respuesta como los literales `NaN` / `Infinity`, que **no son JSON válido**.
# El navegador reventaba con "Respuesta inesperada del servidor" en un 200, y
# /api/generate llegaba a escribir esos valores en la BBDD.
MAX_REVENUE = 1e15


def _numero_finito(valor, nombre_campo):
    """Convierte a float rechazando NaN e infinitos. Devuelve (ok, valor|mensaje)."""
    try:
        num = float(valor)
    except (ValueError, TypeError):
        return False, f"{nombre_campo} debe ser un valor numérico válido."
    if not math.isfinite(num):
        return False, f"{nombre_campo} debe ser un número finito (no se admiten NaN ni infinito)."
    return True, num

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
    'factor_ahorro': (0.001, 0.50, "El factor de ahorro anual debe estar entre 0.1% y 50% de la facturación (0.001 a 0.50)."),
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
    ok, revenue = _numero_finito(data.get('annual_revenue', 10000000.0), "La facturación anual")
    if not ok:
        return False, revenue
    if revenue <= 0.0:
        return False, "La facturación anual debe ser un número positivo mayor a cero."
    if revenue > MAX_REVENUE:
        return False, "La facturación anual excede el máximo admitido (1e15 USD). Verifique el dato."

    ok, consulting_rate = _numero_finito(data.get('consulting_rate', 60.0), "La tarifa horaria de consultoría")
    if not ok:
        return False, consulting_rate
    if not (10.0 <= consulting_rate <= 1000.0):
        return False, "La tarifa horaria del consultor debe estar entre $10 y $1000 USD."

    ok, support_percentage = _numero_finito(data.get('support_percentage', 15.0), "El porcentaje de soporte AMS")
    if not ok:
        return False, support_percentage
    if not (0.0 <= support_percentage <= 100.0):
        return False, "El porcentaje de soporte AMS debe estar entre 0% y 100%."

    custom_licenses = data.get('modular_licenses') or {}
    if not isinstance(custom_licenses, dict):
        return False, "El campo modular_licenses debe ser un objeto con módulos y costos."
    modular_licenses = {}
    for k, v in custom_licenses.items():
        if v is None:
            continue
        ok, val = _numero_finito(v, f"El costo de licencia para el módulo {k}")
        if not ok:
            return False, val
        if val < 0.0:
            return False, f"El costo de licencia para el módulo {k} no puede ser negativo."
        modular_licenses[k] = val

    return True, {
        'revenue': revenue,
        'consulting_rate': consulting_rate,
        'support_percentage': support_percentage,
        'modular_licenses': modular_licenses
    }
