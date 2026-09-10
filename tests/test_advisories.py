import time
import pytest
from services import financial_engine as fe


class TestFactorAhorroConfigurable:
    """
    El factor de ahorro era el único supuesto comercial hardcodeado (1.5%),
    a diferencia de los otros seis que ya vivían en configuracion_comercial.
    """

    def test_esta_en_la_configuracion_por_defecto(self):
        cfg = fe.load_db_config()
        assert 'factor_ahorro' in cfg
        assert 0 < cfg['factor_ahorro'] <= 0.5

    def test_override_por_config_cambia_el_ahorro(self):
        base = fe.calculate_financials(['FI', 'MM'], {'annual_revenue': 10_000_000})['summary']
        alto = fe.calculate_financials(
            ['FI', 'MM'], {'annual_revenue': 10_000_000, 'savings_factor': 0.05}
        )['summary']
        assert alto['savings_annual'] > base['savings_annual']
        assert alto['roi_five_years'] > base['roi_five_years']

    def test_rechaza_factor_fuera_de_rango(self):
        with pytest.raises(ValueError, match="factor de ahorro"):
            fe.calculate_financials(['FI'], {'annual_revenue': 1_000_000, 'savings_factor': 0.9})
        with pytest.raises(ValueError, match="factor de ahorro"):
            fe.calculate_financials(['FI'], {'annual_revenue': 1_000_000, 'savings_factor': 0})


class TestAdvertenciasComerciales:
    """
    Un ROI negativo es matemáticamente correcto pero imposible de defender ante
    un cliente: el sistema debe avisar al consultor antes de que lo presente.
    """

    def test_prospecto_pequeno_genera_advertencia_de_roi_negativo(self):
        r = fe.calculate_financials(['FI', 'CO', 'MM', 'SD'], {'annual_revenue': 2_000_000})['summary']
        assert r['roi_five_years'] < 0
        avisos = r['advertencias']
        assert avisos, "Un ROI negativo debe generar al menos una advertencia"
        assert any('ROI negativo' in a for a in avisos)

    def test_advierte_payback_mayor_al_horizonte(self):
        r = fe.calculate_financials(['FI', 'CO', 'MM', 'SD'], {'annual_revenue': 2_000_000})['summary']
        assert r['payback_period'] > r['anos_roi']
        assert any('recupero' in a.lower() for a in r['advertencias'])

    def test_prospecto_solido_no_genera_advertencias(self):
        r = fe.calculate_financials(['FI', 'CO', 'MM', 'SD'], {'annual_revenue': 45_000_000})['summary']
        assert r['roi_five_years'] > 50
        assert r['advertencias'] == []

    def test_advertencia_menciona_el_factor_de_ahorro_actual(self):
        r = fe.calculate_financials(['FI', 'CO', 'MM', 'SD'], {'annual_revenue': 2_000_000})['summary']
        assert any('factor de ahorro' in a for a in r['advertencias'])

    def test_summary_siempre_incluye_la_clave(self):
        r = fe.calculate_financials(['FI'], {'annual_revenue': 50_000_000})['summary']
        assert isinstance(r['advertencias'], list)


class TestRateLimiterSinFugaDeMemoria:
    """
    El store solo purgaba las marcas de la IP que hacía la petición: las IPs de
    visitantes que no regresaban quedaban para siempre en memoria.
    """

    def test_barrido_expulsa_ips_inactivas(self):
        import middleware.rate_limit as rl
        rl._rate_limit_store.clear()
        rl._last_sweep = 0.0

        ahora = time.time()
        for i in range(500):
            rl._rate_limit_store[f'10.0.0.{i}'] = [ahora - 3600]   # fuera de la ventana
        rl._rate_limit_store['10.0.1.1'] = [ahora]                  # activa

        rl._sweep_stale_entries(ahora, window=60)

        assert '10.0.1.1' in rl._rate_limit_store, "No debe expulsar IPs activas"
        assert len(rl._rate_limit_store) == 1, "Debe expulsar las 500 IPs inactivas"

    def test_barrido_respeta_el_intervalo(self):
        import middleware.rate_limit as rl
        rl._rate_limit_store.clear()
        ahora = time.time()
        rl._last_sweep = ahora            # barrido recién hecho
        rl._rate_limit_store['10.0.0.9'] = [ahora - 3600]
        rl._sweep_stale_entries(ahora, window=60)
        assert '10.0.0.9' in rl._rate_limit_store, "No debe barrer antes del intervalo"
