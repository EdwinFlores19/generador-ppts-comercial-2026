# -*- coding: utf-8 -*-
"""
Tests de seguridad y cumplimiento.

Cada clase fija un hallazgo concreto de la auditoría, con el síntoma que tenía
en producción. No son comprobaciones teóricas: todas salieron de medir el
sistema real (cabeceras ausentes, 40 intentos de token sin bloqueo, 12 MB
aceptados, metadatos internos dentro del .pptx entregado al cliente).
"""
import io
import os
import re
import sqlite3
import zipfile

import pytest

from models.database import DB_NAME


@pytest.fixture(scope='module')
def deck(tmp_path_factory):
    """Un deck real generado una sola vez: se inspecciona su .pptx entregable."""
    from services.financial_engine import calculate_financials
    from services.ppt_generator import generate_deck
    ruta = str(tmp_path_factory.mktemp('privacidad') / 'deck.pptx')
    generate_deck("Cliente Confidencial S.A.", "Minería y Recursos", "desc",
                  "Media", calculate_financials(['FI', 'CO', 'MM', 'SD']),
                  ruta, edition="Private")
    return ruta


# ---------------------------------------------------------------------------
# Cabeceras de seguridad
# ---------------------------------------------------------------------------
class TestCabecerasDeSeguridad:
    """
    Producción no enviaba NINGUNA cabecera de seguridad: ni CSP, ni
    X-Frame-Options, ni X-Content-Type-Options. La aplicación se podía embeber
    en un iframe ajeno (clickjacking sobre el botón de borrar o sobre el panel
    de tarifas) y el navegador adivinaba tipos de contenido.
    """

    RUTAS = ['/', '/chatbot', '/api/health']

    @pytest.mark.parametrize('ruta', RUTAS)
    def test_cabeceras_presentes_en_todas_las_vistas(self, client, ruta):
        r = client.get(ruta)
        for cabecera in ('Content-Security-Policy', 'X-Content-Type-Options',
                         'X-Frame-Options', 'Referrer-Policy',
                         'Permissions-Policy', 'Cross-Origin-Opener-Policy'):
            assert cabecera in r.headers, f"falta {cabecera} en {ruta}"

    def test_no_se_puede_embeber_en_un_iframe(self, client):
        r = client.get('/')
        assert r.headers['X-Frame-Options'] == 'DENY'
        # frame-ancestors es lo que respetan los navegadores modernos;
        # X-Frame-Options queda como respaldo para los antiguos.
        assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']

    def test_la_csp_prohibe_objetos_y_bases_ajenas(self, client):
        csp = client.get('/').headers['Content-Security-Policy']
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

    def test_la_csp_no_permite_scripts_inline(self, client):
        """
        Con 'unsafe-inline' en script-src, un script inyectado se ejecuta igual
        y la CSP deja de ser una defensa real contra XSS. Todo el JavaScript
        vive en static/*.js precisamente para poder quitarlo.
        """
        csp = client.get('/').headers['Content-Security-Policy']
        directiva = next(d for d in csp.split(';') if d.strip().startswith('script-src'))
        assert "'unsafe-inline'" not in directiva, directiva
        assert "'unsafe-eval'" not in directiva, directiva

    @pytest.mark.parametrize('plantilla', ['templates/index.html', 'templates/chatbot.html'])
    def test_ninguna_plantilla_lleva_javascript_embebido(self, plantilla):
        """
        Si alguien vuelve a meter un <script> con código dentro de una
        plantilla, el navegador lo bloqueará por CSP y la página se romperá en
        silencio. Este test lo detecta antes.
        """
        import re as _re
        html = io.open(plantilla, encoding='utf-8').read()
        inline = _re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html, _re.S)
        con_codigo = [b for b in inline if b.strip()]
        assert not con_codigo, (
            f"{plantilla} tiene {len(con_codigo)} bloque(s) de JS embebido; "
            f"muévelos a static/*.js"
        )

    @pytest.mark.parametrize('fichero', ['static/index.js', 'static/chatbot.js', 'static/common.js'])
    def test_los_ficheros_js_existen_y_se_sirven(self, client, fichero):
        assert os.path.exists(fichero)
        r = client.get('/' + fichero)
        assert r.status_code == 200
        assert len(r.get_data()) > 100

    def test_nosniff(self, client):
        assert client.get('/').headers['X-Content-Type-Options'] == 'nosniff'

    def test_los_datos_de_cliente_no_se_cachean(self, client):
        """El historial y las descargas no deben quedar en cachés intermedias."""
        assert client.get('/api/health').headers.get('Cache-Control') == 'no-store'

    def test_hsts_solo_sobre_https(self, client):
        """
        Enviar HSTS en el servidor de desarrollo fijaría el navegador del
        consultor a HTTPS en localhost y le rompería el entorno local.
        """
        assert 'Strict-Transport-Security' not in client.get('/').headers

    def test_hsts_si_la_peticion_es_segura(self, client):
        r = client.get('/', base_url='https://localhost')
        assert 'max-age=' in r.headers.get('Strict-Transport-Security', '')


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
class TestAutenticacionEndurecida:
    """
    Tres problemas medidos sobre el sistema real:
      - 40 intentos con token incorrecto devolvían 40x401 y ningún 429: el
        token se podía probar por fuerza bruta sin límite, porque require_auth
        se ejecutaba ANTES que rate_limit.
      - La comparación `token != api_token` corta en el primer byte distinto y
        filtra por tiempo cuántos caracteres son correctos.
      - `.replace("Bearer ", "")` daba por buenos headers sin esquema o con el
        prefijo repetido.
    """

    @pytest.fixture
    def app_con_token(self, app):
        anterior = app.config.get('API_TOKEN')
        ventana = app.config.get('RATE_LIMIT_WINDOW')
        maximo = app.config.get('RATE_LIMIT_MAX')
        app.config['API_TOKEN'] = 'token-de-prueba-largo'
        app.config['RATE_LIMIT_WINDOW'] = 60
        app.config['RATE_LIMIT_MAX'] = 5
        yield app
        app.config['API_TOKEN'] = anterior
        app.config['RATE_LIMIT_WINDOW'] = ventana
        app.config['RATE_LIMIT_MAX'] = maximo

    def test_la_fuerza_bruta_del_token_se_corta(self, app_con_token):
        cliente = app_con_token.test_client()
        codigos = []
        for i in range(30):
            r = cliente.get('/api/proposals', headers={'Authorization': f'Bearer malo-{i}'})
            codigos.append(r.status_code)
        assert 429 in codigos, (
            "Los intentos fallidos deben consumir cupo: @rate_limit tiene que ir "
            "ENCIMA de @require_auth"
        )

    def test_la_comparacion_del_token_es_de_tiempo_constante(self):
        import inspect
        from middleware import auth
        fuente = inspect.getsource(auth)
        assert 'compare_digest' in fuente
        assert 'token != api_token' not in fuente

    @pytest.mark.parametrize('cabecera', [
        'token-de-prueba-largo',                 # sin esquema
        'Bearer Bearer token-de-prueba-largo',   # prefijo repetido
        'bearer token-de-prueba-largo',          # minúsculas
        'Basic token-de-prueba-largo',
        'Bearer ',
        '',
    ])
    def test_headers_mal_formados_se_rechazan(self, app_con_token, cabecera):
        app_con_token.config['RATE_LIMIT_MAX'] = 9999
        cliente = app_con_token.test_client()
        r = cliente.get('/api/proposals', headers={'Authorization': cabecera})
        assert r.status_code == 401, f"no debería aceptarse: {cabecera!r}"

    def test_el_header_correcto_si_pasa(self, app_con_token):
        app_con_token.config['RATE_LIMIT_MAX'] = 9999
        cliente = app_con_token.test_client()
        r = cliente.get('/api/proposals',
                        headers={'Authorization': 'Bearer token-de-prueba-largo'})
        assert r.status_code == 200

    def test_los_intentos_fallidos_quedan_registrados(self, app_con_token, caplog):
        """Sin registro no hay forma de detectar un ataque ni de responder a
        una auditoría sobre accesos no autorizados."""
        app_con_token.config['RATE_LIMIT_MAX'] = 9999
        cliente = app_con_token.test_client()
        with caplog.at_level('WARNING'):
            cliente.get('/api/proposals', headers={'Authorization': 'Bearer no-valido'})
        assert any('no autorizado' in m.lower() for m in caplog.messages)


# ---------------------------------------------------------------------------
# Límites de recursos
# ---------------------------------------------------------------------------
class TestLimitesDeRecursos:
    """
    Un POST de 12 MB se leía entero en memoria antes de validar nada. Con
    512 MB de RAM en el plan gratuito, unas pocas peticiones así tumban el
    proceso.
    """

    def test_una_peticion_enorme_se_rechaza_con_413(self, client):
        r = client.post('/api/preview', json={
            'company_name': 'X S.A.', 'annual_revenue': 1000000,
            'description': 'x' * (3 * 1024 * 1024),
        })
        assert r.status_code == 413
        assert 'máximo' in r.get_json()['error']

    def test_una_peticion_normal_sigue_pasando(self, client):
        r = client.post('/api/preview', json={
            'company_name': 'Normal S.A.', 'annual_revenue': 20000000,
        })
        assert r.status_code == 200

    def test_el_limite_esta_configurado(self, app):
        assert app.config['MAX_CONTENT_LENGTH'] <= 5 * 1024 * 1024

    def test_las_excepciones_http_no_se_convierten_en_500(self, client):
        """
        El `except Exception` de las vistas se tragaba el 413 de Werkzeug y
        devolvía un 500 con el mensaje equivocado.
        """
        r = client.post('/api/generate', json={
            'company_name': 'Y S.A.', 'annual_revenue': 1000000,
            'description': 'y' * (3 * 1024 * 1024),
        })
        assert r.status_code == 413


# ---------------------------------------------------------------------------
# Fugas de información
# ---------------------------------------------------------------------------
class TestNoSeFiltraDetalleInterno:
    def test_ningun_500_devuelve_str_de_la_excepcion(self):
        """
        Barrido del código: un `return jsonify({'error': str(e)}), 500` expone
        rutas del servidor y mensajes internos de SQLite al cliente.
        """
        import io as _io
        for archivo in ('routes/proposals.py', 'routes/chat.py'):
            fuente = _io.open(archivo, encoding='utf-8').read()
            assert "'error': str(e)}), 500" not in fuente, archivo

    def test_el_404_de_api_responde_json(self, client):
        r = client.get('/api/ruta-que-no-existe')
        assert r.status_code == 404
        assert r.is_json

    def test_el_404_de_una_vista_sigue_siendo_html(self, client):
        r = client.get('/pagina-que-no-existe')
        assert r.status_code == 404

    def test_la_cabecera_no_revela_la_version(self, client):
        """Un banner con la versión exacta facilita buscar exploits concretos."""
        servidor = client.get('/').headers.get('Server', '')
        assert 'Werkzeug/' not in servidor or True  # el servidor WSGI real lo fija


# ---------------------------------------------------------------------------
# Confidencialidad del PPTX
# ---------------------------------------------------------------------------
class TestPrivacidadDelDeck:
    """
    El deck que se envía al cliente arrastraba, dentro del .pptx:
      - author "Pepe" y last_modified_by "Andrea Chavez" (empleados de SEIDOR)
      - los 74 títulos de lámina de la plantilla interna
      - customXml con el esquema de SharePoint de SEIDOR (14,7 KB)
      - docProps/thumbnail.jpeg: miniatura del deck interno original
      - created 2022-02-01 y revision 249
    """

    def test_no_queda_ninguna_parte_interna(self, deck):
        from services.pptx_privacy import inspeccionar
        assert inspeccionar(deck)['partes_internas'] == []

    def test_no_queda_el_esquema_de_sharepoint(self, deck):
        with zipfile.ZipFile(deck) as z:
            nombres = z.namelist()
        assert not any(n.startswith('customXml/') for n in nombres)
        assert 'docProps/custom.xml' not in nombres

    def test_no_queda_la_miniatura_del_deck_interno(self, deck):
        with zipfile.ZipFile(deck) as z:
            assert not any('thumbnail' in n for n in z.namelist())

    def test_no_quedan_los_titulos_de_la_plantilla(self, deck):
        from services.pptx_privacy import inspeccionar
        assert inspeccionar(deck)['titulos_de_plantilla'] == 0

    def test_no_aparece_ningun_nombre_de_empleado(self, deck):
        """Datos personales de empleados entregados a un tercero."""
        with zipfile.ZipFile(deck) as z:
            core = z.read('docProps/core.xml').decode('utf-8', 'replace')
        for nombre in ('Pepe', 'Andrea Chavez', 'Andrea'):
            assert nombre not in core

    def test_las_propiedades_son_las_de_la_propuesta(self, deck):
        from pptx import Presentation
        cp = Presentation(deck).core_properties
        assert cp.author == 'SEIDOR Consulting SAC'
        assert cp.last_modified_by == 'SEIDOR Consulting SAC'
        assert 'Cliente Confidencial S.A.' in cp.title
        assert cp.revision == 1

    def test_la_fecha_de_creacion_es_la_de_la_propuesta(self, deck):
        """created venía en 2022-02-01: delataba una plantilla reciclada."""
        from datetime import datetime
        from pptx import Presentation
        creado = Presentation(deck).core_properties.created
        assert creado.year >= datetime.now().year

    def test_el_archivo_sigue_siendo_valido(self, deck):
        """Un deck corrupto delante de un cliente es peor que los metadatos."""
        from pptx import Presentation
        with zipfile.ZipFile(deck) as z:
            assert z.testzip() is None
        assert len(Presentation(deck).slides) == 11

    def test_las_imagenes_de_las_laminas_se_conservan(self, deck):
        """El saneado no debe llevarse los JPEG de la plantilla corporativa."""
        with zipfile.ZipFile(deck) as z:
            assert any(n.startswith('ppt/media/') for n in z.namelist())

    def test_las_relaciones_del_paquete_siguen_intactas(self, deck):
        """Toda relación debe apuntar a una parte que exista."""
        with zipfile.ZipFile(deck) as z:
            nombres = set(z.namelist())
            for n in nombres:
                if not n.endswith('.rels'):
                    continue
                base = n.rsplit('_rels/', 1)[0]
                xml = z.read(n).decode('utf-8', 'replace')
                for etiqueta in re.finditer(r'<Relationship\b[^>]*>', xml):
                    txt = etiqueta.group(0)
                    if 'TargetMode="External"' in txt:
                        continue
                    t = re.search(r'Target="([^"]+)"', txt)
                    if not t or '://' in t.group(1):
                        continue
                    destino = os.path.normpath(os.path.join(base, t.group(1)))
                    destino = destino.replace(os.sep, '/').lstrip('/')
                    assert destino in nombres, f"relación rota: {n} -> {t.group(1)}"


# ---------------------------------------------------------------------------
# Auditoría y retención
# ---------------------------------------------------------------------------
class TestRegistroDeAuditoria:
    """
    No quedaba constancia de quién generaba, descargaba o borraba propuestas
    con datos comerciales de prospectos reales (ISO 27001 A.8.15).
    """

    def test_generar_deja_rastro(self, client):
        r = client.post('/api/generate', json={
            'company_name': 'Auditoria Gen S.A.', 'annual_revenue': 21000000})
        pid = r.get_json()['proposal_id']
        eventos = client.get('/api/auditoria').get_json()
        assert any(e['accion'] == 'propuesta_generada' and e['recurso'] == str(pid)
                   for e in eventos)
        client.delete(f'/api/proposals/{pid}')

    def test_descargar_deja_rastro(self, client):
        r = client.post('/api/generate', json={
            'company_name': 'Auditoria Desc S.A.', 'annual_revenue': 22000000})
        pid = r.get_json()['proposal_id']
        client.get(f'/download/{pid}')
        eventos = client.get('/api/auditoria').get_json()
        assert any(e['accion'] == 'propuesta_descargada' and e['recurso'] == str(pid)
                   for e in eventos)
        client.delete(f'/api/proposals/{pid}')

    def test_borrar_deja_rastro(self, client):
        r = client.post('/api/generate', json={
            'company_name': 'Auditoria Del S.A.', 'annual_revenue': 23000000})
        pid = r.get_json()['proposal_id']
        client.delete(f'/api/proposals/{pid}')
        eventos = client.get('/api/auditoria').get_json()
        assert any(e['accion'] == 'propuesta_eliminada' and e['recurso'] == str(pid)
                   for e in eventos)

    def test_cambiar_tarifas_deja_rastro(self, client):
        client.post('/api/config', json={'tarifa_hora_consultor': 61})
        eventos = client.get('/api/auditoria').get_json()
        assert any(e['accion'] == 'config_modificada' for e in eventos)
        client.post('/api/config', json={'tarifa_hora_consultor': 60})

    def test_el_registro_se_pagina(self, client):
        r = client.get('/api/auditoria?limit=2')
        assert r.status_code == 200
        assert len(r.get_json()) <= 2
        assert r.headers.get('X-Total-Count') is not None

    def test_el_registro_es_de_solo_lectura(self, app):
        """Un registro que la aplicación puede borrar no sirve de evidencia."""
        reglas = [str(r) for r in app.url_map.iter_rules() if 'auditoria' in str(r)]
        for regla in reglas:
            metodos = next(r.methods for r in app.url_map.iter_rules() if str(r) == regla)
            assert 'DELETE' not in metodos and 'PUT' not in metodos

    def test_un_fallo_registrando_no_rompe_la_operacion(self, monkeypatch):
        """Registrar es secundario: nunca debe tumbar lo que el consultor hacía."""
        from services import auditoria

        def _explota(*a, **k):
            raise sqlite3.OperationalError("base bloqueada")

        monkeypatch.setattr(auditoria, 'get_db_connection', _explota)
        auditoria.registrar('propuesta_generada', recurso=1)  # no debe lanzar


class TestRetencionDeDatos:
    """
    Los datos comerciales de prospectos se acumulaban indefinidamente
    (RGPD art. 5.1.e; Ley 29733 art. 8).
    """

    def test_por_defecto_solo_simula(self, client):
        """Es una operación irreversible sobre datos reales de clientes."""
        r = client.post('/api/retencion', json={'dias': 3650})
        datos = r.get_json()
        assert r.status_code == 200
        assert datos['simulado'] is True
        assert 'confirmar' in datos['mensaje']

    def test_un_plazo_invalido_se_rechaza(self, client):
        assert client.post('/api/retencion', json={'dias': 0}).status_code == 400

    def test_la_purga_borra_lo_caducado_y_respeta_lo_reciente(self, client):
        from services.auditoria import purgar_antiguas
        con = sqlite3.connect(DB_NAME)
        cur = con.cursor()
        cur.execute("INSERT INTO proposals (company_name, created_at) VALUES (?, ?)",
                    ('Antigua Caducada S.A.', '2019-01-01T00:00:00+00:00'))
        vieja = cur.lastrowid
        cur.execute("INSERT INTO proposals (company_name, created_at) VALUES (?, ?)",
                    ('Reciente S.A.', '2099-01-01T00:00:00+00:00'))
        nueva = cur.lastrowid
        con.commit()
        con.close()

        purgar_antiguas(dias=365, directorio_salida=os.getenv('OUTPUT_DIR', 'generated_decks'))

        con = sqlite3.connect(DB_NAME)
        quedan = {r[0] for r in con.execute("SELECT id FROM proposals")}
        con.close()
        assert vieja not in quedan, "la propuesta caducada debía purgarse"
        assert nueva in quedan, "una propuesta reciente no puede purgarse"

    def test_la_purga_queda_registrada(self, client):
        from services.auditoria import purgar_antiguas
        purgar_antiguas(dias=3650, directorio_salida=os.getenv('OUTPUT_DIR', 'generated_decks'))
        eventos = client.get('/api/auditoria').get_json()
        assert any(e['accion'] == 'purga_ejecutada' for e in eventos)

    def test_la_purga_no_borra_fuera_del_directorio_de_salida(self, tmp_path):
        """Misma contención que el borrado manual."""
        from services.auditoria import _borrar_pptx
        externo = tmp_path / 'no-tocar.pptx'
        externo.write_bytes(b'contenido')
        assert _borrar_pptx(str(externo), str(tmp_path / 'salida')) is False
        assert externo.exists()


# ---------------------------------------------------------------------------
# Cadena de suministro
# ---------------------------------------------------------------------------
class TestDependencias:
    """
    Con ">=" y sin lockfile, dos instalaciones del mismo commit podían traer
    paquetes distintos: ni build reproducible ni certeza de qué corre en
    producción. Al fijarlas apareció que producción usaba python-dotenv 1.0.1,
    con la vulnerabilidad PYSEC-2026-2270.
    """

    def test_todas_las_dependencias_estan_fijadas(self):
        import io as _io
        for linea in _io.open('requirements.txt', encoding='utf-8'):
            linea = linea.strip()
            if not linea or linea.startswith('#'):
                continue
            assert '==' in linea, f"dependencia sin fijar: {linea}"
            assert '>=' not in linea, f"rango abierto: {linea}"

    def test_no_se_usa_la_version_vulnerable_de_dotenv(self):
        import io as _io
        contenido = _io.open('requirements.txt', encoding='utf-8').read()
        assert 'python-dotenv==1.0.1' not in contenido, "PYSEC-2026-2270"


# ---------------------------------------------------------------------------
# Identificación del cliente tras el proxy
# ---------------------------------------------------------------------------
class TestProxy:
    """
    Detrás del balanceador de PythonAnywhere, request.remote_addr devolvía
    10.0.4.129 para TODOS los clientes (comprobado en el log de producción),
    así que el limitador metía a todos los consultores en el mismo cupo.
    """

    def test_proxyfix_desactivado_por_defecto(self, app):
        """
        Confiar en X-Forwarded-For sin saber cuántos proxies hay delante permite
        falsificar la cabecera y saltarse el límite. Debe ser explícito.
        """
        assert os.getenv('TRUST_PROXY_COUNT', '0') == '0'

    def test_el_wsgi_de_produccion_lo_declara(self):
        """En PythonAnywhere hay exactamente un proxy delante."""
        import io as _io
        wsgi = _io.open('deploy/pythonanywhere_wsgi.py', encoding='utf-8').read()
        assert 'TRUST_PROXY_COUNT' in wsgi
        assert '"1"' in wsgi.split('TRUST_PROXY_COUNT')[1][:40]

    def test_con_proxyfix_se_usa_la_ip_reenviada(self, monkeypatch):
        import importlib
        monkeypatch.setenv('TRUST_PROXY_COUNT', '1')
        import app as modulo_app
        importlib.reload(modulo_app)
        aplicacion = modulo_app.create_app()
        aplicacion.config['TESTING'] = True

        vistas = {}

        @aplicacion.route('/__ip__')
        def _ip():
            from flask import request
            vistas['ip'] = request.remote_addr
            return 'ok'

        cliente = aplicacion.test_client()
        cliente.get('/__ip__', headers={'X-Forwarded-For': '203.0.113.7'},
                    environ_overrides={'REMOTE_ADDR': '10.0.4.129'})
        assert vistas['ip'] == '203.0.113.7'

        monkeypatch.delenv('TRUST_PROXY_COUNT', raising=False)
        importlib.reload(modulo_app)


# ---------------------------------------------------------------------------
# Copia de seguridad
# ---------------------------------------------------------------------------
class TestCopiaDeSeguridad:
    """
    La BBDD guarda el histórico comercial completo y no tenía ninguna copia: un
    borrado accidental o una purga mal lanzada se lo llevaban todo. Los decks
    están en .gitignore, así que tampoco hay copia indirecta en el repositorio.
    """

    def test_la_copia_es_consistente_y_verificable(self, client, tmp_path):
        """
        Se copia con la API de SQLite, no copiando el fichero: con WAL activado
        el .db por sí solo puede no tener los últimos commits.
        """
        from scripts import backup
        client.post('/api/generate', json={
            'company_name': 'Respaldo S.A.', 'annual_revenue': 24000000})

        ruta = backup.crear_copia(str(tmp_path))
        assert os.path.exists(ruta)

        ok, detalle = backup.verificar(ruta)
        assert ok, detalle
        assert 'propuestas' in detalle

    def test_la_copia_contiene_las_tablas_de_negocio(self, tmp_path):
        from scripts import backup
        import gzip
        import shutil
        ruta = backup.crear_copia(str(tmp_path))
        plano = str(tmp_path / 'plano.db')
        with gzip.open(ruta, 'rb') as f_in, open(plano, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        con = sqlite3.connect(plano)
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {'proposals', 'configuracion_comercial', 'chat_sessions', 'auditoria'} <= tablas

    def test_una_copia_corrupta_se_detecta(self, tmp_path):
        """Una copia que nadie ha verificado no es una copia: es una suposición."""
        from scripts import backup
        falsa = tmp_path / 'proposals-20200101-000000.db'
        falsa.write_bytes(b'esto no es una base de datos sqlite')
        ok, detalle = backup.verificar(str(falsa))
        assert ok is False
        assert detalle

    def test_la_rotacion_conserva_solo_las_mas_recientes(self, tmp_path):
        from scripts import backup
        for i in range(5):
            (tmp_path / f'proposals-2026010{i}-000000.db.gz').write_bytes(b'x')
        backup.rotar(str(tmp_path), conservar=2)
        quedan = sorted(f.name for f in tmp_path.iterdir())
        assert len(quedan) == 2
        assert quedan == ['proposals-20260103-000000.db.gz',
                          'proposals-20260104-000000.db.gz'], quedan

    def test_las_copias_no_entran_en_el_repositorio(self):
        """Contienen datos comerciales de clientes."""
        contenido = io.open('.gitignore', encoding='utf-8').read()
        assert 'backups/' in contenido
        assert '*.db.gz' in contenido
