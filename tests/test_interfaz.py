# -*- coding: utf-8 -*-
"""
Tests de la interfaz servida.

Cubren fallos que ningún test de API detectaba porque viven en el HTML o en la
coherencia entre lo que el consultor ve en la web y lo que recibe el cliente en
el PPTX. Se validan sobre el HTML realmente servido, no sobre el fichero.
"""
import io
import re

import pytest

from services.financial_engine import calculate_financials
from services.preview import generate_preview_data


@pytest.fixture(scope='module')
def financieros():
    """Cálculo financiero real, compartido por los tests de previsualización."""
    return calculate_financials(['FI', 'CO', 'MM', 'SD', 'PP', 'PS'])


@pytest.fixture(scope='module')
def style_css():
    return io.open('static/style.css', encoding='utf-8').read()


@pytest.fixture(scope='module')
def index_js():
    return io.open('static/index.js', encoding='utf-8').read()


@pytest.fixture(scope='module')
def chatbot_css():
    return io.open('static/chatbot.css', encoding='utf-8').read()


def _atributos_input(html, input_id):
    """Extrae los atributos del <input> con ese id del HTML servido."""
    m = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(input_id), html)
    assert m, f"No se encontró el input #{input_id} en el HTML"
    etiqueta = m.group(0)
    return dict(re.findall(r'(\w+)="([^"]*)"', etiqueta))


class TestCamposNumericosAceptanValoresReales:
    """
    `min="1" step="1000"` hacía que el navegador solo aceptara 1, 1001, 2001...
    porque en HTML el step es un DESPLAZAMIENTO desde min, no un redondeo.
    Resultado: toda cifra redonda era inválida — incluido el valor por defecto
    del propio campo — y el formulario no se podía enviar. La función principal
    de la aplicación estaba rota desde la interfaz.
    """

    def test_facturacion_no_restringe_por_step(self, client):
        html = client.get('/').get_data(as_text=True)
        attrs = _atributos_input(html, 'annualRevenue')
        assert attrs.get('step') == 'any', (
            "step debe ser 'any': cualquier otro valor con min distinto de 0 "
            "invalida las cifras redondas"
        )

    def test_el_valor_por_defecto_es_valido_segun_sus_propios_atributos(self, client):
        """Un formulario que no se puede enviar tal y como se carga es un fallo."""
        html = client.get('/').get_data(as_text=True)
        attrs = _atributos_input(html, 'annualRevenue')
        valor = float(attrs['value'])
        minimo = float(attrs['min'])
        assert valor >= minimo
        if attrs.get('step') not in (None, 'any'):
            paso = float(attrs['step'])
            resto = (valor - minimo) % paso
            assert abs(resto) < 1e-9, (
                f"El valor por defecto {valor} no es múltiplo de step={paso} "
                f"desde min={minimo}: el navegador lo rechaza"
            )

    @pytest.mark.parametrize('importe', [250000, 1500000, 15000000, 62000000, 85000000])
    def test_importes_redondos_tipicos_son_validos(self, client, importe):
        html = client.get('/').get_data(as_text=True)
        attrs = _atributos_input(html, 'annualRevenue')
        if attrs.get('step') in (None, 'any'):
            return  # sin restricción de paso: cualquier importe vale
        paso = float(attrs['step'])
        minimo = float(attrs['min'])
        assert abs((importe - minimo) % paso) < 1e-9, (
            f"{importe} sería rechazado por el navegador"
        )

    def test_el_tope_del_campo_coincide_con_el_del_backend(self, client):
        from utils.validators import MAX_REVENUE
        html = client.get('/').get_data(as_text=True)
        attrs = _atributos_input(html, 'annualRevenue')
        assert float(attrs['max']) == MAX_REVENUE


class TestPreviewCoincideConElDeck:
    """
    La previsualización web tenía "GROW with SAP" fijo en la lámina de cierre y
    omitía la edición en el título de la solución. En una propuesta Private el
    consultor revisaba "GROW with SAP" y el cliente recibía "RISE with SAP".
    """

    @pytest.mark.parametrize('edition,programa,nombre', [
        ('Public', 'GROW with SAP', 'SAP S/4HANA Cloud, Public Edition'),
        ('Private', 'RISE with SAP', 'SAP S/4HANA Cloud, Private Edition'),
    ])
    def test_el_cierre_usa_el_programa_de_la_edicion(self, financieros, edition, programa, nombre):
        slides = generate_preview_data("Prueba S.A.", "Minería y Recursos", "desc",
                                       "Alta", financieros, edition=edition)
        cierre = slides[-1]
        assert programa in cierre['subtitle']

    @pytest.mark.parametrize('edition,nombre', [
        ('Public', 'SAP S/4HANA Cloud, Public Edition'),
        ('Private', 'SAP S/4HANA Cloud, Private Edition'),
    ])
    def test_la_lamina_de_solucion_nombra_la_edicion(self, financieros, edition, nombre):
        slides = generate_preview_data("Prueba S.A.", "Minería y Recursos", "desc",
                                       "Alta", financieros, edition=edition)
        solucion = next(s for s in slides if s['title'].startswith('La Solución'))
        assert solucion['title'].endswith(nombre)

    def test_ninguna_lamina_menciona_el_programa_contrario(self, financieros):
        """En una propuesta Private no debe aparecer GROW por ningún lado."""
        slides = generate_preview_data("Prueba S.A.", "Minería y Recursos", "desc",
                                       "Alta", financieros, edition='Private')
        texto = " ".join(
            [s.get('title', '') + s.get('subtitle', '') + " ".join(s.get('bullets', []))
             for s in slides]
        )
        assert 'GROW with SAP' not in texto

    def test_el_preview_y_el_pptx_declaran_las_mismas_laminas(self, financieros):
        """Si se añade una lámina al deck hay que añadirla también al preview."""
        media = generate_preview_data("X S.A.", "Servicios Comerciales", "d", "Media", financieros)
        alta = generate_preview_data("X S.A.", "Minería y Recursos", "d", "Alta", financieros)
        assert len(media) == 11
        assert len(alta) == 12


class TestIndicadorDeIAHonesto:
    """
    El frontend deducía "falta la API key" buscando un trozo del TEXTO del
    mensaje de error. Al reescribir ese texto, la detección dejó de casar en
    silencio y el indicador decía "Conectado" sin motor de IA. Encima
    loadSessions() ponía 'Conectado' incondicionalmente justo después, así que
    habría pisado el aviso igualmente.
    """

    def test_la_respuesta_sin_clave_trae_la_senal_explicita(self, client):
        creada = client.post('/api/chat/create', json={'first_message': 'Hola'})
        sid = creada.get_json()['session_id']
        resp = client.post('/api/chat/message', json={'session_id': sid, 'message': 'Hola'})
        datos = resp.get_json()
        # Sin API key en el entorno de tests, el motor no arranca.
        assert datos.get('ia_disponible') is False
        client.delete(f'/api/chat/delete/{sid}')

    def test_el_indicador_no_depende_del_texto_del_mensaje(self):
        """
        Regresión concreta: la comparación por substring. Si vuelve a aparecer
        un `includes('...motor de IA...')` en la plantilla, este test cae.
        """
        js = io.open('static/chatbot.js', encoding='utf-8').read()
        assert "includes('motor de IA" not in js
        assert 'ia_disponible' in js, "El frontend debe usar la señal del servidor"

    def test_la_plantilla_recibe_la_disponibilidad_en_el_primer_render(self, client):
        """
        El estado debe ser honesto antes de que el usuario escriba nada.

        Al sacar el JavaScript del HTML (para poder quitar 'unsafe-inline' de la
        CSP), el valor ya no se interpola dentro del script: viaja como atributo
        data-* del <body>, que es lo que lee el JS externo.
        """
        html = client.get('/chatbot').get_data(as_text=True)
        assert re.search(r'data-ia-disponible="(true|false)"', html), \
            "La disponibilidad debe resolverse en el HTML servido"
        js = io.open('static/chatbot.js', encoding='utf-8').read()
        assert 'document.body.dataset.iaDisponible' in js, \
            "El JS debe leer la señal del atributo, no de un literal inyectado"

    def test_conectado_se_decide_en_un_unico_sitio(self):
        """
        'Conectado' debe salir solo del helper que consulta iaDisponible.
        loadSessions() lo fijaba por su cuenta y pisaba el aviso que acababa de
        mostrar el envío del mensaje.
        """
        js = io.open('static/chatbot.js', encoding='utf-8').read()
        assert js.count("fijarEstado('ok', 'Conectado')") == 1,             "Solo fijarEstadoConectado() debe poder poner 'Conectado'"
        inicio = js.index('function fijarEstadoConectado()')
        fin = js.index('function fijarEstado(', inicio)
        assert "fijarEstado('ok', 'Conectado')" in js[inicio:fin],             "La única ocurrencia debe estar dentro del helper"
        assert 'fijarEstadoConectado();' in js, "loadSessions debe usar el helper"


def _regla(css, selector, dentro_de=None):
    """Devuelve el cuerpo de la primera regla para `selector`, opcionalmente
    restringido al bloque @media que contenga `dentro_de`."""
    ambito = css
    if dentro_de:
        i = css.index(dentro_de)
        ambito = css[i:]
    j = ambito.index(selector + ' {')
    return ambito[j:ambito.index('}', j)]


class TestLayoutMovil:
    """
    Dos fallos que solo se ven con el navegador en 375 px:

    - El nav no envolvía: logo + los dos botones sumaban 473 px y hacían
      scrollear TODA la página en horizontal.
    - La barra de conversaciones quedaba aplastada a 1 px. En un contenedor
      flex en columna, el flex-shrink por defecto la comprimía contra el chat;
      `max-height` limita por arriba pero no pone suelo. En móvil no había
      forma de ver ni cambiar de conversación.
    """

    def test_el_nav_envuelve(self, style_css):
        assert 'flex-wrap: wrap' in _regla(style_css, 'nav')

    def test_las_acciones_del_nav_pueden_encoger(self, style_css):
        regla = _regla(style_css, '.nav-actions')
        assert 'flex-wrap: wrap' in regla
        assert 'min-width: 0' in regla

    def test_el_nav_no_es_sticky_en_movil(self, style_css):
        regla = _regla(style_css, 'nav', dentro_de='@media (max-width: 767px)')
        assert 'position: static' in regla, (
            "Envuelto en dos filas el nav mide ~149 px; pegado se come el 18% "
            "de la pantalla del móvil"
        )

    def test_la_barra_de_conversaciones_no_se_aplasta(self, chatbot_css):
        regla = _regla(chatbot_css, '.sidebar', dentro_de='@media (max-width: 640px)')
        assert 'flex: 0 0 auto' in regla, (
            "Sin esto el flex-shrink por defecto deja la barra en 1 px y las "
            "conversaciones son inalcanzables en móvil"
        )
        assert 'max-height' in regla


class TestElAtributoHiddenOculta:
    """
    `hidden` tiene que ganar a cualquier `display` propio.

    La regla del navegador para `[hidden]` es `display: none` con la
    especificidad más baja que existe, así que basta una regla propia con
    `display` para anularla en silencio. Pasó con `.history-footer`
    (`display: flex`): al buscar algo sin coincidencias el JS ponía
    `pie.hidden = true`, el pie seguía en pantalla y mostraba el recuento de la
    carga anterior —"Mostrando 50 de 403 propuestas" sobre una tabla vacía—.
    El JS parecía correcto porque lo era; el fallo estaba en el CSS.
    """

    def test_existe_la_regla_global(self, style_css):
        regla = _regla(style_css, '[hidden]')
        assert 'display: none !important' in regla, (
            "Sin esta regla, cualquier elemento con `display` propio ignora el "
            "atributo hidden que pone el JS"
        )

    def test_ningun_elemento_que_el_js_oculta_queda_sin_cubrir(self):
        """
        Los ids que el JS oculta con `.hidden = true` tienen que estar bajo esa
        regla. Es una comprobación de inventario: si mañana se oculta un
        elemento nuevo, sigue cubierto por ser global, pero el test documenta
        cuáles son y falla si alguien la sustituye por parches puntuales.
        """
        ocultados = set()
        for fichero in ('static/index.js', 'static/chatbot.js'):
            js = io.open(fichero, encoding='utf-8').read()
            for variable in re.findall(r'(\w+)\.hidden\s*=\s*(?:true|false)', js):
                ocultados.add(variable)
        assert ocultados, "no se encontró ningún elemento ocultado desde el JS"

        css = io.open('static/style.css', encoding='utf-8').read()
        assert re.search(r'\[hidden\]\s*\{[^}]*display:\s*none\s*!important', css), (
            f"{len(ocultados)} elementos se ocultan desde el JS y dependen de "
            f"la regla global [hidden]"
        )


class TestReutilizarUnaPropuesta:
    """
    "Reutilizar" carga en el formulario los datos de una propuesta del
    historial. Lo que se comprueba aquí es la costura frágil: el historial
    guarda la complejidad como RESULTADO ('Alta') y el formulario pide el MODO
    ('alta'); los une un .toLowerCase(). Si alguien renombra las opciones del
    selector, el valor deja de casar, el campo se queda en "automático" y la
    copia se generaría recalculando otra complejidad — en silencio, porque
    rellenar el formulario no da error.
    """

    def test_los_modos_del_selector_cubren_las_complejidades_guardadas(self, client):
        html = client.get('/').get_data(as_text=True)
        bloque = re.search(r'<select id="complexityMode".*?</select>', html, re.S)
        assert bloque, "no se encontró el selector de complejidad"
        opciones = set(re.findall(r'value="([^"]*)"', bloque.group(0)))
        # Son las dos que escribe /api/generate en la columna complexity.
        for guardada in ('Alta', 'Media'):
            assert guardada.lower() in opciones, (
                f"la complejidad '{guardada}' del historial no casa con ninguna "
                f"opción del formulario: al reutilizar se quedaría en automático"
            )

    def test_solo_asigna_valores_que_el_selector_admite(self, index_js):
        """
        Un sector escrito a mano por el chatbot puede no estar en la lista;
        asignarlo dejaría el <select> en blanco y el formulario no se podría
        enviar.
        """
        assert 'function reutilizarPropuesta' in index_js
        assert '.options].some(' in index_js, (
            "cada campo debe comprobarse contra las opciones del selector "
            "antes de asignarlo"
        )

    def test_no_inventa_una_facturacion_en_las_propuestas_antiguas(self, index_js):
        cuerpo = index_js[index_js.index('function reutilizarPropuesta'):]
        cuerpo = cuerpo[:cuerpo.index('\nfunction ')]
        assert 'if (prop.annual_revenue)' in cuerpo, (
            "las propuestas anteriores al guardado de la facturación traen "
            "null: hay que conservar el valor del campo, no poner un 0"
        )

    def test_no_genera_nada_por_su_cuenta(self, index_js):
        """Rellena y devuelve el control: el consultor revisa antes de generar."""
        cuerpo = index_js[index_js.index('function reutilizarPropuesta'):]
        cuerpo = cuerpo[:cuerpo.index('\nfunction ')]
        assert '/api/generate' not in cuerpo
        assert 'submit()' not in cuerpo
