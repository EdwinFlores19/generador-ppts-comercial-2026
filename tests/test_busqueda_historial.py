# -*- coding: utf-8 -*-
"""
Tests de la búsqueda y los filtros del historial (`GET /api/proposals`).

Con cientos de propuestas, encontrar la de un cliente concreto obligaba a
recorrer página por página. Lo que se prueba aquí:

- que el filtro devuelve **lo que debe y solo eso**;
- que el total de la cabecera respeta el filtro (si no, el pie de la tabla
  diría "50 de 403" con tres resultados en pantalla);
- que un nombre con `%` o `_` se busca literalmente y no como comodín;
- que un parámetro con basura no filtra en vez de reventar.
"""
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from models.database import DB_NAME
from routes.proposals import _filtros_del_historial

# Prefijo propio para no chocar con las filas que siembran otros tests sobre
# la misma BBDD de sesión: todas las aserciones filtran por él.
PREFIJO = 'Busqueda'


def _insertar(company_name, sector='Minería y Recursos', complexity='Alta',
              edition='Public', dias_atras=0):
    creado = (datetime.now(timezone.utc) - timedelta(days=dias_atras)
              ).strftime('%Y-%m-%d %H:%M:%S')
    con = sqlite3.connect(DB_NAME)
    con.execute(
        "INSERT INTO proposals (company_name, sector, complexity, edition, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (company_name, sector, complexity, edition, creado))
    con.commit()
    con.close()


@pytest.fixture(scope='module', autouse=True)
def catalogo():
    """Un puñado de propuestas con las combinaciones que interesan."""
    _insertar(f'{PREFIJO} Minera Las Bambas S.A.', 'Minería y Recursos', 'Alta', 'Public', 2)
    _insertar(f'{PREFIJO} Minera Antamina S.A.', 'Minería y Recursos', 'Alta', 'Private', 400)
    _insertar(f'{PREFIJO} Agro del Norte S.A.C.', 'Agroindustria', 'Media', 'Public', 5)
    _insertar(f'{PREFIJO} Textiles Unidos S.A.', 'Manufactura', 'Media', 'Public', 200)
    # Nombres con los comodines de LIKE dentro: deben buscarse literalmente.
    _insertar(f'{PREFIJO} Especial_S S.A.', 'Servicios Comerciales', 'Media', 'Public', 1)
    _insertar(f'{PREFIJO} Descuento 100% S.A.', 'Servicios Comerciales', 'Media', 'Public', 1)


def _buscar(client, consulta=''):
    """Devuelve (nombres_propios, total_cabecera) de una consulta."""
    sufijo = ('&' + consulta) if consulta else ''
    resp = client.get(f'/api/proposals?limit=200{sufijo}')
    assert resp.status_code == 200
    filas = resp.get_json()
    nombres = [f['company_name'] for f in filas
               if (f['company_name'] or '').startswith(PREFIJO)]
    return nombres, int(resp.headers['X-Total-Count'])


class TestBusquedaPorTexto:
    def test_encuentra_por_razon_social(self, client):
        nombres, _ = _buscar(client, f'q={PREFIJO} Minera')
        assert len(nombres) == 2
        assert all('Minera' in n for n in nombres)

    def test_encuentra_por_sector(self, client):
        nombres, _ = _buscar(client, 'q=Agroindustria')
        assert nombres == [f'{PREFIJO} Agro del Norte S.A.C.']

    def test_no_distingue_mayusculas(self, client):
        assert _buscar(client, f'q={PREFIJO} MINERA')[0] == _buscar(client, f'q={PREFIJO} minera')[0]

    def test_un_termino_sin_coincidencias_no_devuelve_nada(self, client):
        nombres, total = _buscar(client, 'q=zzz-no-existe-zzz')
        assert nombres == []
        assert total == 0

    def test_termino_vacio_o_en_blanco_no_filtra(self, client):
        assert len(_buscar(client, 'q=')[0]) == 6
        assert len(_buscar(client, 'q=%20%20')[0]) == 6


class TestComodinesDeLike:
    """
    Un nombre con `%` o `_` no puede convertir la búsqueda en un comodín: sin
    el ESCAPE, buscar "100%" devolvía el historial entero y "Especial_S"
    casaba con cualquier letra en esa posición.
    """

    def test_el_porcentaje_se_busca_literal(self, client):
        nombres, _ = _buscar(client, 'q=100%25 S.A.')
        assert nombres == [f'{PREFIJO} Descuento 100% S.A.']

    def test_el_guion_bajo_no_es_comodin(self, client):
        assert _buscar(client, 'q=Especial_S')[0] == [f'{PREFIJO} Especial_S S.A.']
        # 'EspecialXS' solo casaría si '_' actuara como comodín.
        assert _buscar(client, 'q=EspecialXS')[0] == []

    def test_un_porcentaje_suelto_no_devuelve_todo(self, client):
        # Sin ESCAPE, '%' es "cualquier cosa" y la búsqueda devolvía el
        # historial entero. Escapado solo casa el nombre que lo lleva dentro.
        nombres, _ = _buscar(client, 'q=%25')
        assert nombres == [f'{PREFIJO} Descuento 100% S.A.']


class TestFiltrosDeCatalogo:
    def test_filtra_por_complejidad(self, client):
        nombres, _ = _buscar(client, f'q={PREFIJO}&complejidad=Alta')
        assert len(nombres) == 2

    def test_filtra_por_edicion(self, client):
        nombres, _ = _buscar(client, f'q={PREFIJO}&edicion=Private')
        assert nombres == [f'{PREFIJO} Minera Antamina S.A.']

    def test_los_filtros_se_combinan_con_Y(self, client):
        nombres, _ = _buscar(client, f'q={PREFIJO} Minera&edicion=Public')
        assert nombres == [f'{PREFIJO} Minera Las Bambas S.A.']

    @pytest.mark.parametrize('parametro', [
        'complejidad=XX', 'complejidad=alta', 'edicion=publico',
        'edicion=<script>', 'dias=abc', 'dias=-5', "complejidad=' OR 1=1--",
    ])
    def test_un_valor_invalido_no_rompe_ni_filtra_de_mas(self, client, parametro):
        """Lo que no se reconoce se ignora: nunca un 500 ni una consulta rota."""
        resp = client.get(f'/api/proposals?limit=200&q={PREFIJO}&{parametro}')
        assert resp.status_code == 200


class TestFiltroPorAntiguedad:
    def test_el_ultimo_mes_deja_fuera_lo_antiguo(self, client):
        nombres, _ = _buscar(client, f'q={PREFIJO}&dias=30')
        assert f'{PREFIJO} Minera Antamina S.A.' not in nombres  # 400 días
        assert f'{PREFIJO} Textiles Unidos S.A.' not in nombres  # 200 días
        assert f'{PREFIJO} Minera Las Bambas S.A.' in nombres    # 2 días

    def test_el_corte_usa_el_formato_en_que_sqlite_guarda_la_fecha(self):
        """
        Esta es la comprobación que ancla el bug, y va contra el formato y no
        contra el resultado a propósito: un test funcional solo lo detecta si
        la propuesta cae en el MISMO día del corte, así que pasaba por azar.

        created_at lo escribe SQLite con CURRENT_TIMESTAMP:
        'YYYY-MM-DD HH:MM:SS' en UTC, y la comparación de created_at con el
        corte es de TEXTO. Con .isoformat() el corte salía como
        '...T...+00:00'; como ' ' (0x20) < 'T' (0x54), toda propuesta del día
        del corte quedaba fuera y "último mes" devolvía 29 días.
        """
        _, parametros = _filtros_del_historial({'dias': '30'})
        assert len(parametros) == 1
        corte = parametros[0]
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', corte), (
            f"el corte debe ir en el formato de SQLite, no como {corte!r}")

    def test_el_corte_se_topa_para_no_desbordar_la_fecha(self):
        """datetime no admite restar cualquier número de días sin reventar."""
        assert _filtros_del_historial({'dias': '99999999'})[1]
        assert _filtros_del_historial({'dias': '0'})[1]

    def test_un_horizonte_amplio_las_incluye_todas(self, client):
        assert len(_buscar(client, f'q={PREFIJO}&dias=3650')[0]) >= 6


class TestElTotalRespetaElFiltro:
    """
    El pie de la tabla dice "Mostrando N de TOTAL". Si el COUNT ignorase el
    filtro, una búsqueda con 2 resultados mostraría "2 de 403" y el botón
    "Cargar más" ofrecería páginas que no existen.
    """

    def test_el_total_filtrado_es_menor_que_el_global(self, client):
        _, total_global = _buscar(client)
        _, total_filtrado = _buscar(client, f'q={PREFIJO} Minera')
        assert total_filtrado == 2
        assert total_filtrado < total_global

    def test_el_total_coincide_con_las_filas_devueltas(self, client):
        nombres, total = _buscar(client, f'q={PREFIJO}&edicion=Private')
        assert total == len(nombres) == 1

    def test_la_paginacion_mantiene_el_filtro(self, client):
        p1 = client.get(f'/api/proposals?limit=2&offset=0&q={PREFIJO}').get_json()
        p2 = client.get(f'/api/proposals?limit=2&offset=2&q={PREFIJO}').get_json()
        assert len(p1) == 2 and len(p2) == 2
        assert not {f['id'] for f in p1} & {f['id'] for f in p2}
        assert all(f['company_name'].startswith(PREFIJO) for f in p1 + p2)
