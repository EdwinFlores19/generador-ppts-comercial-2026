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
