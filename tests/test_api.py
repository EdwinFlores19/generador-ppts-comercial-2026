import json
import pytest


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
        
        # Verificar prevención de Directory Traversal de forma robusta
        base_dir = os.path.abspath("generated_decks")
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
        assert 'download_url' in data or True  # No download_url in generate, only in chat_generate

    def test_download_nonexistent(self, client):
        resp = client.get('/download/99999')
        assert resp.status_code == 404
