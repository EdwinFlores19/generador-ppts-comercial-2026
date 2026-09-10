# -*- coding: utf-8 -*-
"""
Tests de la auditoría global.

Cada clase fija un fallo concreto que estaba en producción. El comentario de
cada una describe el síntoma real, no la implementación: si alguien refactoriza
y el síntoma vuelve, el test tiene que fallar por la razón correcta.
"""
import os
import sqlite3

import pytest

from models.database import DB_NAME


class TestConfigComercialEsAtomica:
    """
    Guardar {tarifa: 999, igv: 0.99} devolvía 400 por el IGV **pero dejaba la
    tarifa en 999**: el `return` a mitad del bucle salía del bloque
    `with conn:` de forma normal, o sea haciendo commit. El consultor leía "no
    válido", creía que no se había guardado nada, y todas las propuestas
    siguientes salían con una tarifa que nunca aprobó.
    """

    def _tarifa(self, client):
        return client.get('/api/config').get_json()['tarifa_hora_consultor']['valor']

    def test_un_parametro_invalido_no_guarda_ninguno(self, client):
        original = self._tarifa(client)
        resp = client.post('/api/config', json={
            'tarifa_hora_consultor': 999.0,   # válido
            'factor_igv': 0.99,               # inválido (tope 0.50)
        })
        assert resp.status_code == 400
        assert self._tarifa(client) == original, "La tarifa no debe haberse guardado"

    def test_el_orden_de_las_claves_no_cambia_el_resultado(self, client):
        """El parámetro válido iba antes o después del inválido según el orden
        del bucle; el resultado debe ser el mismo en ambos casos."""
        original = self._tarifa(client)
        resp = client.post('/api/config', json={
            'factor_igv': 0.99,
            'tarifa_hora_consultor': 888.0,
        })
        assert resp.status_code == 400
        assert self._tarifa(client) == original

    def test_todos_validos_si_se_guardan(self, client):
        resp = client.post('/api/config', json={'tarifa_hora_consultor': 75.0})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        assert self._tarifa(client) == 75.0
        client.post('/api/config', json={'tarifa_hora_consultor': 60.0})  # se restaura

    def test_nan_en_config_se_rechaza(self, client):
        original = self._tarifa(client)
        resp = client.post('/api/config', json={'tarifa_hora_consultor': float('nan')})
        assert resp.status_code == 400
        assert self._tarifa(client) == original

    def test_payload_sin_parametros_conocidos_devuelve_400(self, client):
        resp = client.post('/api/config', json={'parametro_inventado': 1})
        assert resp.status_code == 400


class TestNoFinitosRechazados:
    """
    float('nan') pasaba la comprobación `revenue <= 0` (toda comparación con
    NaN es False), atravesaba el motor financiero y salía en la respuesta como
    el literal `NaN`, que NO es JSON válido: el navegador reventaba con
    "Respuesta inesperada del servidor" ante un HTTP 200, y /api/generate
    llegaba a escribir NaN en la BBDD.
    """

    @pytest.mark.parametrize('valor', ['nan', 'inf', '-inf', '1e400'])
    def test_preview_rechaza_no_finitos(self, client, valor):
        resp = client.post('/api/preview', json={
            'company_name': 'Prueba No Finitos S.A.',
            'annual_revenue': valor,
        })
        assert resp.status_code == 400

    @pytest.mark.parametrize('valor', ['nan', 'inf'])
    def test_generate_rechaza_no_finitos(self, client, valor):
        resp = client.post('/api/generate', json={
            'company_name': 'Prueba No Finitos S.A.',
            'annual_revenue': valor,
        })
        assert resp.status_code == 400

    def test_ninguna_respuesta_contiene_literales_no_json(self, client):
        resp = client.post('/api/preview', json={
            'company_name': 'Prueba Limpia S.A.',
            'annual_revenue': 30000000,
        })
        cuerpo = resp.get_data(as_text=True)
        assert 'NaN' not in cuerpo
        assert 'Infinity' not in cuerpo

    def test_facturacion_absurda_se_rechaza(self, client):
        resp = client.post('/api/preview', json={
            'company_name': 'Prueba Absurda S.A.',
            'annual_revenue': 1e20,
        })
        assert resp.status_code == 400

    def test_licencia_modular_no_finita_se_rechaza(self, client):
        resp = client.post('/api/preview', json={
            'company_name': 'Prueba Licencias S.A.',
            'annual_revenue': 20000000,
            'modular_licenses': {'FI': 'inf'},
        })
        assert resp.status_code == 400


class TestScraperNoBloqueaLaGeneracion:
    """
    El raspado a DuckDuckGo fallaba SIEMPRE (bloqueado por la lista blanca del
    plan gratuito, y 202/timeout fuera de él), pero antes de rendirse gastaba
    3 intentos x 10 s + backoff = ~33 s por llamada, y /api/preview y
    /api/generate lo llamaban por separado.
    """

    def test_desactivado_por_defecto(self):
        from services import scraper
        assert scraper.scraping_habilitado() is False

    def test_no_toca_la_red_y_es_inmediato(self, monkeypatch):
        import time
        from services import scraper

        def _explota(*args, **kwargs):
            raise AssertionError("No debe hacerse ninguna petición HTTP con el raspado desactivado")

        monkeypatch.setattr(scraper.requests, 'get', _explota)
        inicio = time.time()
        perfil = scraper.get_company_profile('Empresa Sin Red S.A.', sector='')
        assert time.time() - inicio < 1.0
        assert perfil['sector']
        assert perfil['complexity'] in ('Alta', 'Media')

    def test_cortacircuitos_no_reintenta_un_host_caido(self, monkeypatch):
        """Con el raspado activado, un host caído se paga una vez, no en cada
        propuesta."""
        from services import scraper

        llamadas = []

        def _falla(*args, **kwargs):
            llamadas.append(1)
            raise OSError("host inalcanzable")

        monkeypatch.setenv('SCRAPER_ENABLED', '1')
        monkeypatch.setenv('SCRAPER_MAX_RETRIES', '1')
        monkeypatch.setattr(scraper.requests, 'get', _falla)
        monkeypatch.setattr(scraper, '_scraper_disponible', True)

        scraper.get_company_profile('Primera Empresa S.A.', sector='')
        tras_la_primera = len(llamadas)
        scraper.get_company_profile('Segunda Empresa S.A.', sector='')
        assert len(llamadas) == tras_la_primera, "La segunda propuesta no debe reintentar el host caído"


class TestClasificacionPorNombre:
    """
    La clasificación por nombre existía pero solo se alcanzaba por la rama del
    raspado, que nunca se ejecuta. Resultado: "Minera Las Bambas S.A." se
    proponía como "Servicios Comerciales / Media" — alcance de empresa de
    servicios para una minera.
    """

    @pytest.mark.parametrize('nombre,sector_esperado', [
        ('Minera Las Bambas S.A.', 'Minería y Recursos'),
        ('Constructora Norte S.A.C.', 'Construcción e Infraestructura'),
        ('Cementos Interoceanicos S.A.', 'Construcción e Infraestructura'),
        ('Agroindustrial Laredo S.A.A.', 'Alimentos y Agroindustria'),
        ('Pesquera Diamante S.A.', 'Alimentos y Agroindustria'),
    ])
    def test_el_nombre_industrial_da_sector_y_alta(self, nombre, sector_esperado):
        from services.scraper import get_company_profile
        perfil = get_company_profile(nombre, sector='')
        assert perfil['sector'] == sector_esperado
        assert perfil['complexity'] == 'Alta'
        assert 'PS' in perfil['active_modules']

    @pytest.mark.parametrize('nombre', [
        'Distribuidora Lima E.I.R.L.',
        'Consultora Andina S.A.C.',
        'Empresa Generica S.A.C.',
    ])
    def test_los_nombres_sin_señal_siguen_en_media(self, nombre):
        from services.scraper import get_company_profile
        perfil = get_company_profile(nombre, sector='')
        assert perfil['complexity'] == 'Media'

    def test_el_sector_indicado_por_el_consultor_manda(self):
        from services.scraper import get_company_profile
        perfil = get_company_profile('Minera Las Bambas S.A.', sector='Retail y Consumo Masivo')
        assert perfil['sector'] == 'Retail y Consumo Masivo'
        # ...pero el nombre sigue diciendo que la operación es industrial.
        assert perfil['complexity'] == 'Alta'

    def test_los_presets_siguen_teniendo_prioridad(self):
        from services.scraper import get_company_profile
        perfil = get_company_profile('Alicorp', sector='')
        assert perfil['sector'] == 'Alimentos y Agroindustria'
        assert perfil['is_fallback'] is False


class TestDescargaContenida:
    """
    /download servía la ruta guardada en la BBDD sin comprobar que estuviera
    dentro de OUTPUT_DIR (el borrado sí lo comprobaba), y componía el nombre
    del archivo sin quitar los caracteres que rompen Content-Disposition.
    """

    def test_ruta_fuera_del_directorio_de_salida_se_rechaza(self, client, app):
        con = sqlite3.connect(DB_NAME)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO proposals (company_name, complexity, ppt_path) VALUES (?, ?, ?)",
            ('Ruta Maliciosa S.A.', 'Media', os.path.abspath(__file__))
        )
        pid = cur.lastrowid
        con.commit()
        con.close()

        resp = client.get(f'/download/{pid}')
        assert resp.status_code == 404, "No debe servirse un archivo fuera de OUTPUT_DIR"

    def test_nombre_de_descarga_sin_caracteres_ilegales(self):
        from routes.proposals import _nombre_descarga
        nombre = _nombre_descarga('Con/Barras\\y:dos*puntos"y comillas"', 'Alta')
        assert not any(c in nombre for c in '\\/:*?"<>|\r\n')
        assert nombre.endswith('.pptx')

    def test_nombre_de_descarga_conserva_la_razon_social(self):
        from routes.proposals import _nombre_descarga
        nombre = _nombre_descarga("D'Onofrio Perú S.A. & Cía", 'Alta')
        assert "D'Onofrio" in nombre
        assert '&' in nombre

    def test_nombre_de_descarga_tolera_vacios(self):
        from routes.proposals import _nombre_descarga
        assert _nombre_descarga(None, None).endswith('.pptx')
        assert _nombre_descarga('', '').endswith('.pptx')


class TestErroresNoFiltranDetalleInterno:
    """
    Los manejadores devolvían str(e) al cliente, exponiendo rutas del servidor
    y mensajes internos de SQLite en la respuesta HTTP.
    """

    def test_config_invalida_no_expone_trazas(self, client):
        resp = client.post('/api/config', json={'factor_igv': 0.99})
        cuerpo = resp.get_data(as_text=True)
        assert 'Traceback' not in cuerpo
        assert 'sqlite3' not in cuerpo.lower()
        assert 'C:\\' not in cuerpo and '/home/' not in cuerpo


class TestCORSCerradoPorDefecto:
    """
    `CORS(app)` a secas abría la API a cualquier origen. Con API_TOKEN vacío
    —el caso por defecto— cualquier web que el consultor visitara podía leer
    /api/proposals y llevarse el historial completo de clientes y montos.
    """

    def test_sin_cors_origins_no_se_emite_cabecera(self, client):
        resp = client.get('/api/proposals', headers={'Origin': 'https://sitio-malicioso.example'})
        assert 'Access-Control-Allow-Origin' not in resp.headers


class TestIndicesDePaginacion:
    """Los listados ordenan por fecha; sin índice SQLite recorre y ordena la
    tabla entera en cada página."""

    def test_los_indices_existen(self):
        con = sqlite3.connect(DB_NAME)
        indices = {fila[0] for fila in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )}
        con.close()
        assert 'idx_proposals_creadas' in indices
        assert 'idx_chat_sessions_actualizadas' in indices


class TestAdvertenciaPaybackNoCalculable:
    """payback valía 0.0 cuando no hay ahorro anual, y se mostraba como
    "0 años", que se lee como recupero instantáneo: lo contrario de la
    realidad."""

    def test_payback_cero_genera_advertencia(self):
        from services.financial_engine import _build_advisories
        cfg = {'anos_roi': 5, 'factor_ahorro': 0.015}
        avisos = _build_advisories(roi_project=120.0, payback_period=0.0, cfg=cfg)
        assert any('no calculable' in a or 'no se recupera' in a for a in avisos)

    def test_payback_normal_no_genera_esa_advertencia(self):
        from services.financial_engine import _build_advisories
        cfg = {'anos_roi': 5, 'factor_ahorro': 0.015}
        avisos = _build_advisories(roi_project=200.0, payback_period=1.5, cfg=cfg)
        assert not any('no calculable' in a for a in avisos)
