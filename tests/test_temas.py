# -*- coding: utf-8 -*-
"""
Tests del sistema de temas visuales.

Se generan PPTX de verdad y se inspecciona su XML: es la única forma de
comprobar que el color elegido llega al archivo que recibe el cliente. Un test
que solo mire el diccionario del tema no habría detectado el fallo de los
argumentos por defecto, que es justo el que apareció al construir esto.
"""
import os
import re
import sqlite3
import threading
import zipfile

import pytest

from models.database import DB_NAME
from services.financial_engine import calculate_financials
from services.ppt_generator import generate_deck
from services.themes import (
    CLAVES_COLOR,
    CONTRASTE_MINIMO,
    FUENTES_SEGURAS,
    TEMAS,
    TEMA_POR_DEFECTO,
    TemaInvalido,
    listar_temas,
    normalizar_tema,
    ratio_contraste,
)


@pytest.fixture(scope='module')
def financieros():
    return calculate_financials(['FI', 'CO', 'MM', 'SD'])


def _colores_del_pptx(ruta):
    """Colores srgbClr presentes en las láminas (no en masters ni layouts)."""
    encontrados = set()
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            if nombre.startswith('ppt/slides/slide') and nombre.endswith('.xml'):
                xml = z.read(nombre).decode('utf-8', 'replace')
                encontrados.update(c.upper() for c in re.findall(r'srgbClr val="([0-9a-fA-F]{6})"', xml))
    return encontrados


def _fuentes_del_pptx(ruta):
    fuentes = set()
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            if nombre.startswith('ppt/slides/slide') and nombre.endswith('.xml'):
                xml = z.read(nombre).decode('utf-8', 'replace')
                fuentes.update(re.findall(r'typeface="([^"]+)"', xml))
    return fuentes


class TestCatalogoDeTemas:
    def test_hay_varios_temas_y_el_por_defecto_existe(self):
        assert TEMA_POR_DEFECTO in TEMAS
        assert len(TEMAS) >= 3

    def test_todos_definen_todas_las_claves_de_color(self):
        for tid, tema in TEMAS.items():
            faltan = set(CLAVES_COLOR) - set(tema['colores'])
            assert not faltan, f"Al tema '{tid}' le faltan colores: {faltan}"

    def test_todos_usan_fuentes_seguras(self):
        """Una fuente que el cliente no tenga instalada descuadra las láminas."""
        for tid, tema in TEMAS.items():
            assert tema['fuente_titulos'] in FUENTES_SEGURAS, tid
            assert tema['fuente_cuerpo'] in FUENTES_SEGURAS, tid

    @pytest.mark.parametrize('tid', list(TEMAS))
    def test_ningun_tema_incorporado_es_ilegible(self, tid):
        """Los pares críticos de cada tema del catálogo cumplen WCAG AA."""
        c = TEMAS[tid]['colores']
        for frente, fondo in [('text', 'background'), ('white', 'primary'), ('white', 'royal')]:
            ratio = ratio_contraste(c[frente], c[fondo])
            assert ratio >= CONTRASTE_MINIMO, (
                f"{tid}: {frente} sobre {fondo} da {ratio:.1f}:1"
            )

    def test_el_tema_seidor_conserva_la_paleta_corporativa(self):
        """Cambiar estos valores altera TODAS las propuestas nuevas."""
        c = TEMAS['seidor']['colores']
        assert c['primary'] == '#07153A'
        assert c['secondary'] == '#66B6FF'
        assert c['text'] == '#242528'
        assert TEMAS['seidor']['fuente_titulos'] == 'Arial'

    def test_listar_temas_no_expone_estructuras_mutables(self):
        """Mutar lo devuelto no debe corromper el catálogo del proceso."""
        catalogo = listar_temas()
        catalogo[0]['colores']['primary'] = '#000000'
        assert TEMAS[catalogo[0]['id']]['colores']['primary'] != '#000000'


class TestNormalizacion:
    def test_sin_tema_devuelve_el_corporativo(self):
        for entrada in (None, ''):
            assert normalizar_tema(entrada)['id'] == TEMA_POR_DEFECTO

    def test_id_del_catalogo(self):
        assert normalizar_tema('cobre')['colores']['secondary'] == '#D98B4A'

    def test_id_desconocido_se_rechaza_listando_los_validos(self):
        with pytest.raises(TemaInvalido) as e:
            normalizar_tema('inexistente')
        assert 'seidor' in str(e.value)

    def test_hereda_del_base_lo_que_no_se_toca(self):
        t = normalizar_tema({'base': 'esmeralda', 'colores': {'secondary': '#FF6600'}})
        assert t['colores']['secondary'] == '#FF6600'
        assert t['colores']['primary'] == TEMAS['esmeralda']['colores']['primary']
        assert t['base'] == 'esmeralda'

    def test_normaliza_el_hexadecimal(self):
        t = normalizar_tema({'colores': {'secondary': 'ff6600'}})
        assert t['colores']['secondary'] == '#FF6600'

    @pytest.mark.parametrize('valor', ['#FFF', 'rojo', '#GGGGGG', '', 123, None])
    def test_hexadecimal_invalido_se_rechaza(self, valor):
        with pytest.raises(TemaInvalido):
            normalizar_tema({'colores': {'secondary': valor}})

    def test_clave_de_color_desconocida_se_rechaza(self):
        with pytest.raises(TemaInvalido) as e:
            normalizar_tema({'colores': {'inventado': '#000000'}})
        assert 'inventado' in str(e.value)

    def test_fuente_no_segura_se_rechaza(self):
        with pytest.raises(TemaInvalido) as e:
            normalizar_tema({'fuente_titulos': 'Comic Sans MS'})
        assert 'Comic Sans MS' in str(e.value)

    def test_es_idempotente(self):
        """
        La ruta valida el tema y luego se lo pasa al generador, que lo vuelve a
        normalizar. Sin idempotencia el deck quedaba etiquetado 'personalizado'
        aunque fuese un tema del catálogo sin tocar.
        """
        t1 = normalizar_tema('esmeralda')
        t2 = normalizar_tema(t1)
        t3 = normalizar_tema(t2)
        assert t1['id'] == t2['id'] == t3['id'] == 'esmeralda'
        assert t1['colores'] == t3['colores']

    def test_pasar_los_colores_exactos_del_catalogo_no_lo_hace_personalizado(self):
        t = normalizar_tema({'base': 'cobre', 'colores': dict(TEMAS['cobre']['colores'])})
        assert t['id'] == 'cobre'

    def test_cambiar_solo_la_fuente_ya_es_personalizado(self):
        t = normalizar_tema({'base': 'seidor', 'fuente_titulos': 'Georgia'})
        assert t['id'] == 'personalizado'
        assert t['fuente_titulos'] == 'Georgia'
        assert t['fuente_cuerpo'] == 'Arial'


class TestContraste:
    def test_blanco_sobre_blanco_se_rechaza(self):
        """El fallo original del proyecto: texto invisible en el deck."""
        with pytest.raises(TemaInvalido) as e:
            normalizar_tema({'colores': {'text': '#FFFFFF', 'background': '#FFFFFF'}})
        assert '1.0:1' in str(e.value)

    def test_texto_de_cabecera_ilegible_se_rechaza(self):
        with pytest.raises(TemaInvalido):
            normalizar_tema({'colores': {'primary': '#FFFFFF'}})

    def test_el_mensaje_dice_que_color_arreglar(self):
        with pytest.raises(TemaInvalido) as e:
            normalizar_tema({'colores': {'text': '#EEEEEE'}})
        mensaje = str(e.value)
        assert '#EEEEEE' in mensaje
        assert ':1' in mensaje

    def test_el_gris_flojo_avisa_pero_no_bloquea(self):
        """
        El gris corporativo (#919191 sobre #F6F6F6) se queda en 2.9:1. Un umbral
        duro rechazaría la propia paleta de SEIDOR y, peor, rechazaría un tema a
        medida por un color que el consultor ni tocó.
        """
        t = normalizar_tema('seidor')
        assert t['id'] == 'seidor'
        assert any('secundario' in a for a in t['advertencias'])

    def test_ratio_de_contraste_conocido(self):
        assert ratio_contraste('#FFFFFF', '#000000') == pytest.approx(21.0, abs=0.1)
        assert ratio_contraste('#FFFFFF', '#FFFFFF') == pytest.approx(1.0, abs=0.01)


class TestElTemaLlegaAlPPTX:
    """
    Lo único que importa de verdad: que el color elegido esté en el archivo.
    """

    @pytest.mark.parametrize('tid', ['seidor', 'grafito', 'esmeralda', 'cobre'])
    def test_todos_los_colores_del_tema_aparecen_en_las_laminas(self, financieros, tid, tmp_path):
        ruta = str(tmp_path / f'{tid}.pptx')
        aplicado = generate_deck("Tema Test S.A.", "Servicios Comerciales", "d",
                                 "Media", financieros, ruta, theme=tid)
        assert aplicado['id'] == tid
        usados = _colores_del_pptx(ruta)
        for clave, valor in aplicado['colores'].items():
            assert valor.lstrip('#') in usados, f"{tid}: falta {clave} ({valor})"

    def test_no_se_cuela_ningun_color_de_otro_tema(self, financieros, tmp_path):
        """
        Regresión del fallo de los argumentos por defecto: Python los evalúa al
        definir la función, así que `line_color=COLOR_CARD_LINE` congelaba el
        azul de SEIDOR y se colaba en todos los demás temas.
        """
        ruta = str(tmp_path / 'esmeralda.pptx')
        generate_deck("Solo Esmeralda S.A.", "Servicios Comerciales", "d",
                      "Media", financieros, ruta, theme='esmeralda')
        usados = _colores_del_pptx(ruta)
        propios = {v.lstrip('#') for v in TEMAS['esmeralda']['colores'].values()}
        for otro, datos in TEMAS.items():
            if otro == 'esmeralda':
                continue
            exclusivos = {v.lstrip('#') for v in datos['colores'].values()} - propios
            intrusos = exclusivos & usados
            assert not intrusos, f"Colores de '{otro}' en un deck esmeralda: {intrusos}"

    def test_la_tipografia_del_tema_se_aplica(self, financieros, tmp_path):
        ruta = str(tmp_path / 'grafito.pptx')
        generate_deck("Tipografía S.A.", "Servicios Comerciales", "d",
                      "Media", financieros, ruta, theme='grafito')
        fuentes = _fuentes_del_pptx(ruta)
        assert 'Calibri' in fuentes
        assert 'Arial' not in fuentes

    def test_un_color_a_medida_sustituye_al_del_tema_base(self, financieros, tmp_path):
        ruta = str(tmp_path / 'medida.pptx')
        generate_deck("A Medida S.A.", "Servicios Comerciales", "d", "Media", financieros, ruta,
                      theme={'base': 'esmeralda', 'colores': {'secondary': '#FF6600'}})
        usados = _colores_del_pptx(ruta)
        assert 'FF6600' in usados
        assert '4FBF95' not in usados, "El acento del tema base no debe seguir presente"
        assert '0B3D2E' in usados, "El resto del tema base sí debe conservarse"

    def test_el_tema_no_altera_el_numero_de_laminas(self, financieros, tmp_path):
        from pptx import Presentation
        for tid in ('seidor', 'cobre'):
            ruta = str(tmp_path / f'n_{tid}.pptx')
            generate_deck("Conteo S.A.", "Minería y Recursos", "d", "Alta",
                          financieros, ruta, theme=tid)
            assert len(Presentation(ruta).slides) == 12

    def test_un_tema_ilegible_no_llega_a_generar_archivo(self, financieros, tmp_path):
        ruta = str(tmp_path / 'nunca.pptx')
        with pytest.raises(TemaInvalido):
            generate_deck("Ilegible S.A.", "Servicios Comerciales", "d", "Media", financieros,
                          ruta, theme={'colores': {'text': '#FFFFFF', 'background': '#FFFFFF'}})
        assert not os.path.exists(ruta), "No debe quedar un PPTX a medio hacer"


class TestAislamientoEntreHilos:
    """
    El tema se aplica intercambiando globales del módulo, así que dos
    generaciones simultáneas con temas distintos podrían pisarse. El cerrojo lo
    impide; este test lo demuestra en vez de confiar en ello.
    """

    def test_cuatro_temas_en_paralelo_no_se_mezclan(self, financieros, tmp_path):
        temas = ['seidor', 'esmeralda', 'cobre', 'grafito']
        resultados = {}
        fallos = []

        def generar(tid):
            try:
                ruta = str(tmp_path / f'hilo_{tid}.pptx')
                generate_deck("Paralelo S.A.", "Servicios Comerciales", "d",
                              "Media", financieros, ruta, theme=tid)
                resultados[tid] = _colores_del_pptx(ruta)
            except Exception as e:                      # pragma: no cover
                fallos.append((tid, e))

        hilos = [threading.Thread(target=generar, args=(t,)) for t in temas]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        assert not fallos, f"Fallos en los hilos: {fallos}"
        assert len(resultados) == len(temas)

        for tid, usados in resultados.items():
            propios = {v.lstrip('#') for v in TEMAS[tid]['colores'].values()}
            assert propios <= usados, f"{tid}: faltan colores propios"
            for otro, datos in TEMAS.items():
                if otro == tid:
                    continue
                intrusos = ({v.lstrip('#') for v in datos['colores'].values()} - propios) & usados
                assert not intrusos, f"{tid} contaminado con colores de {otro}: {intrusos}"

    def test_los_globales_quedan_restaurados_tras_generar(self, financieros, tmp_path):
        """Generar con un tema no debe dejar el módulo teñido para el siguiente."""
        import services.ppt_generator as gen
        antes = (gen.COLOR_PRIMARY, gen.FONT_BODY)
        generate_deck("Restaurar S.A.", "Servicios Comerciales", "d", "Media",
                      financieros, str(tmp_path / 'r.pptx'), theme='esmeralda')
        assert (gen.COLOR_PRIMARY, gen.FONT_BODY) == antes

    def test_los_globales_se_restauran_aunque_falle_la_generacion(self, financieros, tmp_path):
        import services.ppt_generator as gen
        antes = (gen.COLOR_PRIMARY, gen.FONT_BODY)
        with pytest.raises(Exception):
            generate_deck("Falla S.A.", "Servicios Comerciales", "d", "Media", financieros,
                          os.path.join(str(tmp_path), 'no', 'existe', 'x.pptx'), theme='cobre')
        assert (gen.COLOR_PRIMARY, gen.FONT_BODY) == antes


class TestAPIDeTemas:
    def test_el_catalogo_se_sirve_completo(self, client):
        d = client.get('/api/themes').get_json()
        assert len(d['temas']) == len(TEMAS)
        assert d['por_defecto'] == TEMA_POR_DEFECTO
        assert set(d['claves_color']) == set(CLAVES_COLOR)
        assert 'Arial' in d['fuentes']

    def test_preview_devuelve_el_tema_aplicado(self, client):
        r = client.post('/api/preview', json={
            'company_name': 'Preview Tema S.A.', 'annual_revenue': 20000000, 'theme': 'cobre'
        })
        assert r.status_code == 200
        assert r.get_json()['theme']['id'] == 'cobre'

    def test_un_tema_ilegible_devuelve_400_y_no_500(self, client):
        r = client.post('/api/preview', json={
            'company_name': 'X S.A.', 'annual_revenue': 20000000,
            'theme': {'colores': {'text': '#FFFFFF', 'background': '#FFFFFF'}},
        })
        assert r.status_code == 400
        assert 'legible' in r.get_json()['error']

    def test_generate_persiste_el_tema(self, client):
        r = client.post('/api/generate', json={
            'company_name': 'Persistencia Tema S.A.', 'annual_revenue': 25000000, 'theme': 'grafito'
        })
        assert r.status_code == 200
        pid = r.get_json()['proposal_id']
        assert r.get_json()['theme']['id'] == 'grafito'

        con = sqlite3.connect(DB_NAME)
        fila = con.execute("SELECT theme_id, theme_json FROM proposals WHERE id = ?", (pid,)).fetchone()
        con.close()
        assert fila[0] == 'grafito'
        import json as _json
        assert _json.loads(fila[1])['colores']['primary'] == TEMAS['grafito']['colores']['primary']

        listado = client.get('/api/proposals').get_json()
        fila_api = next(p for p in listado if p['id'] == pid)
        assert fila_api['theme_id'] == 'grafito'
        client.delete(f'/api/proposals/{pid}')

    def test_las_propuestas_antiguas_sin_tema_no_rompen_el_historial(self, client):
        """Filas anteriores a la columna theme_id deben seguir listándose."""
        con = sqlite3.connect(DB_NAME)
        cur = con.cursor()
        cur.execute("INSERT INTO proposals (company_name, complexity) VALUES (?, ?)",
                    ('Antigua Sin Tema S.A.', 'Media'))
        pid = cur.lastrowid
        cur.execute("UPDATE proposals SET theme_id = NULL WHERE id = ?", (pid,))
        con.commit()
        con.close()

        r = client.get('/api/proposals?limit=200')
        assert r.status_code == 200
        fila = next((p for p in r.get_json() if p['id'] == pid), None)
        assert fila is not None
        client.delete(f'/api/proposals/{pid}')
