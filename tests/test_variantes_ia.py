# -*- coding: utf-8 -*-
"""
Tests de las variantes de modelo de IA.

El modelo estaba fijado en el `.env` del servidor: cambiarlo obligaba a editar
un fichero y reiniciar el proceso. Ahora se elige por conversación y viaja en
cada mensaje. Estos tests fijan ese contrato sin llamar a ningún proveedor real
(no hay claves en el entorno de tests, y gastarlas en CI sería absurdo).
"""
import inspect
import os

import pytest

from services import ai_chat
from services.ai_models import (
    MODELOS,
    ModeloInvalido,
    listar_modelos,
    modelo_por_defecto,
    normalizar_modelo,
)


@pytest.fixture
def entorno_limpio():
    """Aísla las variables que deciden proveedor y modelo."""
    claves = ['AI_PROVIDER', 'GEMINI_MODEL', 'GROQ_MODEL', 'GEMINI_API_KEY', 'GROQ_API_KEY']
    guardado = {k: os.environ.get(k) for k in claves}
    for k in claves:
        os.environ.pop(k, None)
    yield
    for k, v in guardado.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestCatalogoDeModelos:
    def test_cada_proveedor_ofrece_variantes(self):
        for proveedor, modelos in MODELOS.items():
            assert modelos, f"{proveedor} no ofrece ninguna variante"

    def test_cada_proveedor_tiene_exactamente_un_modelo_por_defecto(self):
        for proveedor, modelos in MODELOS.items():
            por_defecto = [m for m in modelos if m['por_defecto']]
            assert len(por_defecto) == 1, f"{proveedor} tiene {len(por_defecto)} por defecto"

    def test_las_variantes_describen_para_que_sirven(self):
        """El consultor elige por el texto: sin descripción el selector no ayuda."""
        for modelos in MODELOS.values():
            for m in modelos:
                assert len(m['descripcion']) > 25
                assert m['perfil'] in ('rapido', 'equilibrado', 'calidad')

    def test_no_hay_ids_repetidos(self):
        for proveedor, modelos in MODELOS.items():
            ids = [m['id'] for m in modelos]
            assert len(ids) == len(set(ids)), f"{proveedor} repite ids"

    def test_listar_modelos_de_un_proveedor_desconocido_no_revienta(self):
        assert listar_modelos('inventado') == []

    def test_listar_modelos_no_expone_el_catalogo_mutable(self):
        copia = listar_modelos('gemini')
        copia[0]['nombre'] = 'MODIFICADO'
        assert MODELOS['gemini'][0]['nombre'] != 'MODIFICADO'


class TestModeloPorDefecto:
    def test_sin_variables_usa_el_del_catalogo(self, entorno_limpio):
        assert modelo_por_defecto('gemini') == 'gemini-2.0-flash'
        assert modelo_por_defecto('groq') == 'llama-3.3-70b-versatile'

    def test_respeta_la_variable_de_entorno_existente(self, entorno_limpio):
        """
        Quien ya tenía GEMINI_MODEL en su .env no debe ver cambiar el
        comportamiento al actualizar.
        """
        os.environ['GEMINI_MODEL'] = 'gemini-1.5-pro'
        assert modelo_por_defecto('gemini') == 'gemini-1.5-pro'

    def test_variable_vacia_no_cuenta(self, entorno_limpio):
        os.environ['GEMINI_MODEL'] = '   '
        assert modelo_por_defecto('gemini') == 'gemini-2.0-flash'

    def test_proveedor_none_cae_a_gemini(self, entorno_limpio):
        assert modelo_por_defecto(None) == 'gemini-2.0-flash'


class TestValidacionDeModelo:
    def test_vacio_devuelve_el_por_defecto(self, entorno_limpio):
        for valor in (None, '', '   '):
            assert normalizar_modelo('gemini', valor) == 'gemini-2.0-flash'

    def test_modelo_del_catalogo_se_acepta(self, entorno_limpio):
        assert normalizar_modelo('gemini', 'gemini-2.5-flash') == 'gemini-2.5-flash'
        assert normalizar_modelo('groq', 'llama-3.1-8b-instant') == 'llama-3.1-8b-instant'

    def test_modelo_de_otro_proveedor_se_rechaza(self, entorno_limpio):
        """Pedirle a Groq un modelo de Gemini debe fallar aquí, no en la API."""
        with pytest.raises(ModeloInvalido):
            normalizar_modelo('groq', 'gemini-2.0-flash')

    def test_modelo_inventado_se_rechaza_con_las_opciones(self, entorno_limpio):
        with pytest.raises(ModeloInvalido) as e:
            normalizar_modelo('gemini', 'gpt-9')
        assert 'gemini-2.0-flash' in str(e.value)

    def test_el_modelo_del_env_se_admite_aunque_no_este_en_el_catalogo(self, entorno_limpio):
        """
        Puede ser un modelo nuevo, o uno al que ese consultor sí tiene acceso.
        Bloquearlo rompería un despliegue que funcionaba.
        """
        os.environ['GEMINI_MODEL'] = 'gemini-exp-1206'
        assert normalizar_modelo('gemini', 'gemini-exp-1206') == 'gemini-exp-1206'


class TestContratoDelMotor:
    """El motor debe aceptar la variante por llamada, no en el constructor."""

    def test_send_message_acepta_modelo(self):
        firma = inspect.signature(ai_chat.AIChatEngine.send_message)
        assert 'modelo' in firma.parameters
        assert firma.parameters['modelo'].default is None

    def test_extract_proposal_data_acepta_modelo(self):
        firma = inspect.signature(ai_chat.AIChatEngine.extract_proposal_data)
        assert 'modelo' in firma.parameters

    def test_resolver_modelo_cae_al_del_motor_si_no_se_pide_otro(self, entorno_limpio):
        class MotorFalso:
            provider = 'gemini'
            model = 'gemini-2.0-flash'
        assert ai_chat._resolver_modelo(MotorFalso(), None) == 'gemini-2.0-flash'
        assert ai_chat._resolver_modelo(MotorFalso(), '') == 'gemini-2.0-flash'

    def test_resolver_modelo_valida_la_variante_pedida(self, entorno_limpio):
        class MotorFalso:
            provider = 'gemini'
            model = 'gemini-2.0-flash'
        assert ai_chat._resolver_modelo(MotorFalso(), 'gemini-2.5-flash') == 'gemini-2.5-flash'
        with pytest.raises(ModeloInvalido):
            ai_chat._resolver_modelo(MotorFalso(), 'no-existe')

    def test_el_motor_arranca_con_el_modelo_del_catalogo(self, entorno_limpio):
        os.environ['AI_PROVIDER'] = 'groq'
        os.environ['GROQ_API_KEY'] = 'clave-de-prueba'
        motor = ai_chat.AIChatEngine()
        assert motor.model == 'llama-3.3-70b-versatile'

    def test_el_motor_sigue_respetando_la_variable_de_entorno(self, entorno_limpio):
        os.environ['AI_PROVIDER'] = 'groq'
        os.environ['GROQ_API_KEY'] = 'clave-de-prueba'
        os.environ['GROQ_MODEL'] = 'llama-3.1-8b-instant'
        assert ai_chat.AIChatEngine().model == 'llama-3.1-8b-instant'


class TestAPIDeVariantes:
    def test_el_endpoint_lista_las_variantes_del_proveedor_activo(self, client):
        d = client.get('/api/ai/models').get_json()
        assert d['proveedor'] in ('gemini', 'groq')
        assert d['por_defecto']
        assert len(d['modelos']) >= 2
        assert all('descripcion' in m for m in d['modelos'])

    def test_informa_de_si_el_motor_esta_disponible(self, client):
        """Sin API key en el entorno de tests, el selector debe salir apagado."""
        assert client.get('/api/ai/models').get_json()['disponible'] is False

    def test_una_variante_invalida_no_llega_al_proveedor(self, client):
        """
        Sin motor de IA la ruta corta antes; con motor, devolvería 400. En
        ambos casos, nunca un 500.
        """
        creada = client.post('/api/chat/create', json={'first_message': 'Hola'})
        sid = creada.get_json()['session_id']
        r = client.post('/api/chat/message',
                        json={'session_id': sid, 'message': 'Hola', 'modelo': 'modelo-inventado'})
        assert r.status_code in (200, 400)
        assert r.status_code != 500
        client.delete(f'/api/chat/delete/{sid}')
