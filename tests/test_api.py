class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'healthy'


class TestMainRoutes:
    def test_index(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'GROW' in resp.data or b'Seidor' in resp.data or b'SEIDOR' in resp.data

    def test_chatbot_page(self, client):
        resp = client.get('/chatbot')
        assert resp.status_code == 200
        assert b'Chatbot' in resp.data or b'chatbot' in resp.data


class TestProposalsAPI:
    def test_list_proposals(self, client):
        resp = client.get('/api/proposals')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_config(self, client):
        resp = client.get('/api/config')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tarifa_hora_consultor' in data
        assert 'factor_igv' in data
        assert 'tipo_cambio_pen' in data

    def test_preview_missing_company(self, client):
        resp = client.post('/api/preview', json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_preview_invalid_revenue(self, client):
        resp = client.post('/api/preview', json={
            'company_name': 'Test S.A.',
            'annual_revenue': -100
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_preview_valid_request(self, client):
        resp = client.post('/api/preview', json={
            'company_name': 'Alicorp S.A.A.',
            'sector': 'Alimentos y Agroindustria',
            'annual_revenue': 50000000,
            'consulting_rate': 70,
            'support_percentage': 15
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'slides_preview' in data
        assert len(data['slides_preview']) > 0
        assert data['company_name'] == 'Alicorp S.A.A.'


class TestChatAPI:
    def test_create_session(self, client):
        resp = client.post('/api/chat/create', json={
            'first_message': 'Hola, necesito una propuesta para una minera'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'session_id' in data
        assert data['title'] is not None

    def test_list_sessions(self, client):
        resp = client.get('/api/chat/sessions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_send_message_no_session(self, client):
        resp = client.post('/api/chat/message', json={
            'message': 'Hola'
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_create_and_delete(self, client):
        create = client.post('/api/chat/create', json={
            'first_message': 'Test'
        })
        session_id = create.get_json()['session_id']

        delete = client.delete(f'/api/chat/delete/{session_id}')
        assert delete.status_code == 200
        data = delete.get_json()
        assert data['success'] is True

    def test_delete_nonexistent(self, client):
        resp = client.delete('/api/chat/delete/99999')
        assert resp.status_code == 404

    def test_chat_generate_proposal_sanitization(self, client):
        resp = client.post('/api/chat/create', json={'first_message': 'Hola'})
        session_id = resp.get_json()['session_id']

        import os
        import sqlite3
        from models.database import DB_NAME
        import json

        malicious_data = {
            "company_name": "Empresa../Colón:Prueba?*",
            "sector": "Servicios Comerciales",
            "description": "Prueba",
            "complexity": "Media",
            "active_modules": ["FI", "CO", "MM", "SD"],
            "revenue": 10000000.0,
            "consulting_rate": 60.0,
            "support_percentage": 15.0,
            "exchange_rate": 3.78
        }

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET proposal_data = ? WHERE id = ?",
            (json.dumps(malicious_data), session_id)
        )
        conn.commit()
        conn.close()

        resp_gen = client.post(f'/api/chat/generate/{session_id}')
        assert resp_gen.status_code == 200
        data = resp_gen.get_json()
        assert data['success'] is True
        
        proposal_id = data['proposal_id']
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT ppt_path FROM proposals WHERE id = ?", (proposal_id,))
        ppt_path = cursor.fetchone()[0]
        conn.close()
        
        # Verificar prevención de Directory Traversal de forma robusta.
        # El directorio se lee de la configuración (OUTPUT_DIR): hardcodear
        # "generated_decks" hacía fallar el test al aislar la suite en /tmp y
        # además dejaba de comprobar la invariante real del despliegue.
        base_dir = os.path.abspath(os.getenv("OUTPUT_DIR", "generated_decks"))
        abs_ppt_path = os.path.abspath(ppt_path)
        assert abs_ppt_path.startswith(base_dir)

        # Verificar caracteres inválidos de archivos de Windows/Linux
        for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
            assert char not in os.path.basename(ppt_path)
            
        assert os.path.exists(ppt_path)
        
        if os.path.exists(ppt_path):
            os.remove(ppt_path)



class TestGenerate:
    def test_generate_missing_data(self, client):
        resp = client.post('/api/generate', json={})
        assert resp.status_code == 400

    def test_generate_valid(self, client):
        resp = client.post('/api/generate', json={
            'company_name': 'Alicorp S.A.A.',
            'annual_revenue': 50000000,
            'consulting_rate': 70,
            'support_percentage': 15
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['proposal_id'] is not None
        # /api/generate no retorna download_url (solo /api/chat/generate/<id> lo hace)
        assert 'download_url' not in data

    def test_generate_with_private_edition(self, client):
        resp = client.post('/api/generate', json={
            'company_name': 'Corporación Andina S.A.',
            'annual_revenue': 80000000,
            'edition': 'Private'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['edition'] == 'Private'

    def test_generate_default_edition_is_public(self, client):
        resp = client.post('/api/generate', json={
            'company_name': 'Comercial Lima S.A.',
            'annual_revenue': 20000000,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['edition'] == 'Public'

    def test_download_nonexistent(self, client):
        resp = client.get('/download/99999')
        assert resp.status_code == 404


class TestDeleteProposal:
    """Cobertura de DELETE /api/proposals/<id> (borrado del historial)."""

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete('/api/proposals/999999')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_generate_then_delete_removes_row_and_file(self, client):
        import os
        gen = client.post('/api/generate', json={
            'company_name': 'Empresa A Eliminar S.A.C.',
            'annual_revenue': 20000000,
        })
        assert gen.status_code == 200
        pid = gen.get_json()['proposal_id']

        listado = client.get('/api/proposals').get_json()
        assert any(p['id'] == pid for p in listado)

        import sqlite3
        from models.database import DB_NAME
        con = sqlite3.connect(DB_NAME)
        ruta = con.execute("SELECT ppt_path FROM proposals WHERE id = ?", (pid,)).fetchone()[0]
        con.close()
        assert os.path.exists(ruta), "El PPTX debe existir antes de borrar"

        resp = client.delete(f'/api/proposals/{pid}')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        listado = client.get('/api/proposals').get_json()
        assert not any(p['id'] == pid for p in listado), "La fila debe desaparecer del historial"
        assert not os.path.exists(ruta), "El PPTX debe borrarse del disco"

    def test_delete_twice_returns_404_the_second_time(self, client):
        gen = client.post('/api/generate', json={
            'company_name': 'Doble Borrado S.A.',
            'annual_revenue': 15000000,
        })
        pid = gen.get_json()['proposal_id']
        assert client.delete(f'/api/proposals/{pid}').status_code == 200
        assert client.delete(f'/api/proposals/{pid}').status_code == 404


class TestProposalsPagination:
    """
    El historial devolvía TODAS las propuestas con su preview_json: con 405
    filas eran varios MB por petición y el navegador pintaba 405 <tr> de golpe.
    Ahora se pagina en servidor y el total viaja en la cabecera X-Total-Count.
    """

    def _sembrar(self, cantidad):
        import sqlite3
        from models.database import DB_NAME
        con = sqlite3.connect(DB_NAME)
        for i in range(cantidad):
            con.execute(
                "INSERT INTO proposals (company_name, complexity, sector, created_at) VALUES (?, ?, ?, ?)",
                (f"Paginacion {i:03d} S.A.", "Media", "Test", f"2020-01-01 00:00:{i % 60:02d}")
            )
        con.commit()
        con.close()

    def test_expone_total_en_cabecera(self, client):
        resp = client.get('/api/proposals')
        assert resp.status_code == 200
        assert resp.headers.get('X-Total-Count') is not None
        assert int(resp.headers['X-Total-Count']) >= len(resp.get_json())

    def test_limita_por_defecto_a_50(self, client):
        self._sembrar(60)
        resp = client.get('/api/proposals')
        datos = resp.get_json()
        assert len(datos) == 50
        assert int(resp.headers['X-Total-Count']) >= 60

    def test_limit_y_offset_no_repiten_ni_saltan_filas(self, client):
        self._sembrar(30)
        p1 = client.get('/api/proposals?limit=10&offset=0').get_json()
        p2 = client.get('/api/proposals?limit=10&offset=10').get_json()
        ids1 = [p['id'] for p in p1]
        ids2 = [p['id'] for p in p2]
        assert len(ids1) == 10 and len(ids2) == 10
        assert not set(ids1) & set(ids2), "Las páginas no deben solaparse"

    def test_limit_se_topa_en_el_maximo(self, client):
        resp = client.get('/api/proposals?limit=99999')
        assert int(resp.headers['X-Limit']) == 200

    def test_parametros_basura_caen_al_defecto(self, client):
        resp = client.get('/api/proposals?limit=abc&offset=-5')
        assert resp.status_code == 200
        assert int(resp.headers['X-Limit']) == 50
        assert int(resp.headers['X-Offset']) == 0

    def test_offset_mas_alla_del_total_devuelve_lista_vacia(self, client):
        resp = client.get('/api/proposals?limit=10&offset=999999')
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestChatSessionsListado:
    """
    El listado de sesiones devolvía el JSON completo de mensajes de TODAS las
    conversaciones (la barra lateral solo necesita título y fecha). Ahora es
    ligero, paginado, y el detalle se pide con /api/chat/sessions/<id>.
    """

    def test_listado_no_incluye_los_mensajes(self, client):
        creada = client.post('/api/chat/create', json={'first_message': 'Hola, somos Minera Ligera S.A.'})
        assert creada.status_code == 200
        sesiones = client.get('/api/chat/sessions').get_json()
        assert len(sesiones) >= 1
        for s in sesiones:
            assert 'messages' not in s, "La lista no debe arrastrar los mensajes"
            assert 'proposal_data' not in s
            assert 'message_count' in s
            assert 'tiene_datos' in s

    def test_listado_expone_total_y_topa_el_limit(self, client):
        resp = client.get('/api/chat/sessions?limit=99999')
        assert resp.status_code == 200
        assert int(resp.headers['X-Limit']) == 200
        assert resp.headers.get('X-Total-Count') is not None

    def test_listado_parametros_basura_caen_al_defecto(self, client):
        resp = client.get('/api/chat/sessions?limit=hola&offset=-3')
        assert int(resp.headers['X-Limit']) == 50
        assert int(resp.headers['X-Offset']) == 0

    def _sembrar_mensajes(self, session_id, cuantos):
        """/api/chat/create abre la sesion vacia: los mensajes llegan luego por
        /api/chat/message, que necesita el proveedor de IA. Se siembran a mano."""
        import json as _json
        import sqlite3
        from models.database import DB_NAME
        mensajes = [{'role': 'user' if i % 2 == 0 else 'assistant',
                     'content': f'Mensaje {i}',
                     'ts': '2026-01-01T00:00:00+00:00'} for i in range(cuantos)]
        con = sqlite3.connect(DB_NAME)
        con.execute("UPDATE chat_sessions SET messages = ? WHERE id = ?",
                    (_json.dumps(mensajes), session_id))
        con.commit()
        con.close()

    def test_detalle_devuelve_los_mensajes(self, client):
        creada = client.post('/api/chat/create', json={'first_message': 'Detalle de prueba'})
        sid = creada.get_json()['session_id']
        self._sembrar_mensajes(sid, 4)
        resp = client.get(f'/api/chat/sessions/{sid}')
        assert resp.status_code == 200
        datos = resp.get_json()
        assert datos['id'] == sid
        import json as _json
        mensajes = _json.loads(datos['messages'] or '[]')
        assert isinstance(mensajes, list)
        assert len(mensajes) == 4

    def test_message_count_coincide_con_el_detalle(self, client):
        creada = client.post('/api/chat/create', json={'first_message': 'Contar mensajes'})
        sid = creada.get_json()['session_id']
        self._sembrar_mensajes(sid, 7)
        detalle = client.get(f'/api/chat/sessions/{sid}').get_json()
        import json as _json
        esperado = len(_json.loads(detalle['messages'] or '[]'))
        assert esperado == 7
        sesiones = client.get('/api/chat/sessions').get_json()
        fila = next(s for s in sesiones if s['id'] == sid)
        assert fila['message_count'] == 7

    def test_detalle_inexistente_devuelve_404(self, client):
        resp = client.get('/api/chat/sessions/999999')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()


class TestAuthCubreTodaLaSuperficie:
    """
    require_auth es un no-op mientras API_TOKEN no esté definido, así que las
    rutas sin proteger pasaban desapercibidas. Estos tests activan el token y
    comprueban que ninguna ruta sensible queda abierta.

    Faltaban cuatro, encontradas en la auditoría final:
      - /download/<id>: los ids son consecutivos, así que bastaba recorrer
        /download/1..N para bajarse todas las propuestas de todos los clientes.
      - /api/chat/message: gastaba la cuota de Gemini/Groq del servidor.
      - /api/chat/create.
      - /api/preview: expone tarifas, márgenes y el cálculo comercial.
    """

    RUTAS_PROTEGIDAS = [
        ('GET', '/api/proposals'),
        ('GET', '/api/config'),
        ('POST', '/api/config'),
        ('POST', '/api/preview'),
        ('POST', '/api/generate'),
        ('GET', '/download/1'),
        ('DELETE', '/api/proposals/1'),
        ('POST', '/api/chat/create'),
        ('POST', '/api/chat/message'),
        ('GET', '/api/chat/sessions'),
        ('GET', '/api/chat/sessions/1'),
        ('POST', '/api/chat/generate/1'),
        ('DELETE', '/api/chat/delete/1'),
    ]

    def test_sin_token_valido_todas_responden_401(self, app):
        anterior = app.config.get('API_TOKEN')
        app.config['API_TOKEN'] = 'token-de-prueba'
        try:
            cliente = app.test_client()
            for metodo, ruta in self.RUTAS_PROTEGIDAS:
                resp = cliente.open(ruta, method=metodo, json={})
                assert resp.status_code == 401, f"{metodo} {ruta} respondió {resp.status_code}, no 401"
        finally:
            app.config['API_TOKEN'] = anterior

    def test_token_incorrecto_tambien_es_401(self, app):
        anterior = app.config.get('API_TOKEN')
        app.config['API_TOKEN'] = 'token-de-prueba'
        try:
            cliente = app.test_client()
            resp = cliente.get('/api/proposals', headers={'Authorization': 'Bearer otro-token'})
            assert resp.status_code == 401
        finally:
            app.config['API_TOKEN'] = anterior

    def test_token_correcto_deja_pasar(self, app):
        anterior = app.config.get('API_TOKEN')
        app.config['API_TOKEN'] = 'token-de-prueba'
        try:
            cliente = app.test_client()
            resp = cliente.get('/api/proposals', headers={'Authorization': 'Bearer token-de-prueba'})
            assert resp.status_code == 200
        finally:
            app.config['API_TOKEN'] = anterior

    def test_health_e_index_siguen_publicos(self, app):
        """El health check tiene que responder sin token (lo usa el monitoreo)."""
        anterior = app.config.get('API_TOKEN')
        app.config['API_TOKEN'] = 'token-de-prueba'
        try:
            cliente = app.test_client()
            assert cliente.get('/api/health').status_code == 200
            assert cliente.get('/').status_code == 200
            assert cliente.get('/chatbot').status_code == 200
        finally:
            app.config['API_TOKEN'] = anterior
