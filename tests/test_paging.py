# -*- coding: utf-8 -*-
"""
Tests del saneo de paginación compartido (utils/paging.py).

Cubren la función directamente, sin pasar por HTTP: los endpoints ya se prueban
en test_api.py y aquí interesa el comportamiento ante entradas hostiles.
"""
from utils.paging import (
    DEFAULT_PAGE_SIZE,
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    parse_paging,
)


class TestParsePaging:
    def test_sin_parametros_usa_los_defectos(self):
        assert parse_paging({}) == (DEFAULT_PAGE_SIZE, 0)

    def test_valores_validos_se_respetan(self):
        assert parse_paging({'limit': '25', 'offset': '75'}) == (25, 75)

    def test_acepta_numeros_con_espacios(self):
        assert parse_paging({'limit': ' 30 ', 'offset': ' 10 '}) == (30, 10)

    def test_cadena_vacia_cae_al_defecto(self):
        assert parse_paging({'limit': '', 'offset': ''}) == (DEFAULT_PAGE_SIZE, 0)

    def test_texto_no_numerico_cae_al_defecto(self):
        assert parse_paging({'limit': 'abc', 'offset': 'xyz'}) == (DEFAULT_PAGE_SIZE, 0)

    def test_decimal_cae_al_defecto(self):
        # int('10.5') lanza ValueError: no se trunca en silencio.
        assert parse_paging({'limit': '10.5'})[0] == DEFAULT_PAGE_SIZE

    def test_limit_por_encima_del_tope_se_recorta(self):
        assert parse_paging({'limit': '999999'})[0] == MAX_PAGE_SIZE

    def test_limit_cero_o_negativo_sube_al_minimo(self):
        # Un limit de 0 devolvería una página vacía para siempre.
        assert parse_paging({'limit': '0'})[0] == 1
        assert parse_paging({'limit': '-5'})[0] == 1

    def test_offset_negativo_se_normaliza_a_cero(self):
        # SQLite trata OFFSET -1 como 0, pero no hay que depender de eso.
        assert parse_paging({'offset': '-100'})[1] == 0

    def test_offset_absurdo_se_recorta(self):
        # Sin tope, SQLite recorre la tabla entera para no devolver nada.
        assert parse_paging({'offset': '99999999999999'})[1] == MAX_OFFSET

    def test_page_size_personalizado(self):
        assert parse_paging({}, page_size=10) == (10, 0)
        assert parse_paging({'limit': '500'}, page_size=10, max_page_size=20)[0] == 20

    def test_none_explicito_cae_al_defecto(self):
        class ArgsConNone(dict):
            def get(self, clave, defecto=None):
                return None
        assert parse_paging(ArgsConNone()) == (DEFAULT_PAGE_SIZE, 0)


class TestPagingHeaders:
    def test_adjunta_las_tres_cabeceras(self, app):
        from flask import jsonify
        from utils.paging import paging_headers
        with app.app_context():
            resp = paging_headers(jsonify([]), total=405, limit=50, offset=100)
            assert resp.headers['X-Total-Count'] == '405'
            assert resp.headers['X-Limit'] == '50'
            assert resp.headers['X-Offset'] == '100'
            # Sin esta cabecera el navegador oculta las anteriores al JavaScript
            # cuando la API se consume desde otro origen.
            assert 'X-Total-Count' in resp.headers['Access-Control-Expose-Headers']

    def test_devuelve_la_misma_respuesta(self, app):
        from flask import jsonify
        from utils.paging import paging_headers
        with app.app_context():
            original = jsonify([])
            assert paging_headers(original, 0, 50, 0) is original
