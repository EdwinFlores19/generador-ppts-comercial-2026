import pytest
from services import scraper, financial_engine, joule_optimizer


class TestScraperProfiles:
    def test_mining_company_complexity(self):
        profile = scraper.get_company_profile(
            "Compañía Minera Las Bambas S.A.",
            sector="Minería y Recursos"
        )
        assert profile['complexity'] == 'Alta'
        modules = [m.strip() for m in profile['active_modules'].split(',')]
        assert len(modules) == 6

    def test_alicorp_preset(self):
        profile = scraper.get_company_profile("Alicorp S.A.A.")
        assert profile['complexity'] == 'Alta'
        assert 'Alimentos' in profile['sector']

    def test_service_company_complexity(self):
        profile = scraper.get_company_profile(
            "Consultoría Digital Lima S.A.C.",
            sector="Servicios Comerciales"
        )
        assert profile['complexity'] == 'Media'
        modules = [m.strip() for m in profile['active_modules'].split(',')]
        assert len(modules) == 4

    def test_retail_company_complexity(self):
        profile = scraper.get_company_profile(
            "Supermercados Peruanos S.A. (Plaza Vea)",
            sector="Retail y Consumo Masivo"
        )
        assert profile['complexity'] == 'Alta'
        modules = [m.strip() for m in profile['active_modules'].split(',')]
        assert len(modules) == 6

    def test_ssrf_protection(self):
        profile = scraper.get_company_profile("localhost", sector="Servicios")
        assert profile.get('is_fallback', False) is True

    def test_fallback_sectorial(self):
        profile = scraper.fallback_sectorial("Empresa Test", "Minería y Recursos")
        assert profile['complexity'] == 'Alta'
        assert profile['is_fallback'] is True
        assert 'Minería' in profile['sector']


class TestFinancialEngine:
    def test_calculate_financials_returns_dict(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD'])
        assert isinstance(result, dict)
        assert 'modules' in result
        assert 'summary' in result

    def test_summary_has_required_keys(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD'])
        s = result['summary']
        for key in ['total_weeks', 'total_hours', 'roi_five_years',
                     'payback_period', 'usd', 'pen']:
            assert key in s, f"Falta key: {key}"

    def test_bimoneda_calculation(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
        s = result['summary']
        usd_net = s['usd']['net_investment']
        usd_igv = s['usd']['igv']
        usd_total = s['usd']['total_facturable']

        config = financial_engine.load_db_config()
        igv_rate = config.get('factor_igv', 0.18)

        assert abs(usd_net * igv_rate - usd_igv) < 0.05
        assert abs(usd_net + usd_igv - usd_total) < 0.05

    def test_pen_conversion(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD'])
        s = result['summary']
        usd_net = s['usd']['net_investment']
        pen_net = s['pen']['net_investment']

        config = financial_engine.load_db_config()
        tc = config.get('tipo_cambio_pen', 3.78)

        assert abs(usd_net * tc - pen_net) < 0.05

    def test_roi_returns_number(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])
        roi = result['summary']['roi_five_years']
        assert isinstance(roi, (int, float)), f"ROI debe ser numérico, obtenido {type(roi)}"
        import math
        assert math.isfinite(roi), f"ROI debe ser finito, obtenido {roi}"

    def test_payback_reasonable(self):
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD'])
        assert 0 < result['summary']['payback_period'] < 10

    def test_with_custom_config(self):
        config = {
            'consulting_rate': 80,
            'support_percentage': 20,
            'annual_revenue': 50000000,
        }
        result = financial_engine.calculate_financials(['FI', 'CO', 'MM', 'SD'], config)
        assert result['summary']['total_investment'] > 0


class TestJouleOptimizer:
    def test_replaces_subjective_terms(self):
        q = "Muestra el saldo de los clientes morosos"
        opt = joule_optimizer.optimize_prompt(q)
        assert "facturas vencidas" in opt['optimized'].lower()
        assert "moroso" not in opt['optimized'].lower()

    def test_magic_word_mostrar(self):
        q = "Muestra el saldo de los clientes morosos"
        opt = joule_optimizer.optimize_prompt(q)
        assert opt['optimized'].startswith("MOSTRAR")

    def test_transactional_abrir(self):
        q = "crear una orden de servicio"
        opt = joule_optimizer.optimize_prompt(q)
        assert opt['optimized'].startswith("ABRIR")

    def test_buscar_becomes_mostrar(self):
        q = "buscar contrato de compras con mayor valor"
        opt = joule_optimizer.optimize_prompt(q)
        assert opt['optimized'].startswith("MOSTRAR")

    def test_buscar_facturas_becomes_listar(self):
        q = "buscar las facturas pendientes de clientes"
        opt = joule_optimizer.optimize_prompt(q)
        assert opt['optimized'].startswith("LISTAR")

    def test_picking_transaction(self):
        q = "realizar el picking del pedido 80000009"
        opt = joule_optimizer.optimize_prompt(q)
        assert "ABRIR App para Picking" in opt['optimized']
