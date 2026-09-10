from utils.sanitize import (
    sanitize_input_string,
    sanitize_chat_message,
    MAX_FIELD_LEN,
    MAX_CHAT_MESSAGE_LEN,
)


class TestSanitizeInputString:
    """
    El nombre de la empresa se imprime tal cual en la portada del PPTX que se
    entrega al cliente, así que la puntuación legítima de las razones sociales
    peruanas NO debe mutilarse.
    """

    def test_preserva_apostrofos_de_razones_sociales_reales(self):
        assert sanitize_input_string("D'Onofrio S.A.") == "D'Onofrio S.A."
        assert sanitize_input_string("O'Higgins S.A.C.") == "O'Higgins S.A.C."
        assert sanitize_input_string("D'Gallia") == "D'Gallia"

    def test_preserva_ampersand_puntos_guiones_y_barras(self):
        assert sanitize_input_string('Backus & Johnston') == 'Backus & Johnston'
        assert sanitize_input_string('Alicorp S.A.A.') == 'Alicorp S.A.A.'
        assert sanitize_input_string('Yura S.A. - Grupo Gloria') == 'Yura S.A. - Grupo Gloria'
        assert sanitize_input_string('Import/Export Perú SAC') == 'Import/Export Perú SAC'

    def test_preserva_tildes_y_enie(self):
        assert sanitize_input_string('Compañía Minera Poderosa S.A.') == 'Compañía Minera Poderosa S.A.'

    def test_elimina_corchetes_angulares(self):
        assert '<' not in sanitize_input_string('Hotel <script> SAC')
        assert '>' not in sanitize_input_string('Hotel <script> SAC')

    def test_elimina_caracteres_de_control(self):
        assert sanitize_input_string('Empresa\x00\x07 SAC') == 'Empresa SAC'

    def test_colapsa_espacios(self):
        assert sanitize_input_string('  Empresa    con   espacios  ') == 'Empresa con espacios'

    def test_limita_longitud(self):
        assert len(sanitize_input_string('x' * 500)) == MAX_FIELD_LEN

    def test_vacio_y_none(self):
        assert sanitize_input_string('') == ''
        assert sanitize_input_string(None) == ''


class TestSanitizeChatMessage:
    def test_preserva_notacion_sap_y_montos(self):
        msg = 'Necesitamos SAP S/4HANA; el presupuesto es S/. 150,000 ("aprox")'
        assert sanitize_chat_message(msg) == msg

    def test_elimina_caracteres_de_control(self):
        assert sanitize_chat_message('hola\x00mundo') == 'holamundo'

    def test_limita_longitud(self):
        assert len(sanitize_chat_message('x' * 9000)) == MAX_CHAT_MESSAGE_LEN

    def test_vacio_y_none(self):
        assert sanitize_chat_message('') == ''
        assert sanitize_chat_message(None) == ''
