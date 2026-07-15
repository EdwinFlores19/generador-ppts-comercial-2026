import pytest
from services import scope_items


class TestNormalizeEdition:
    def test_public_variants(self):
        assert scope_items.normalize_edition('Public') == 'Public'
        assert scope_items.normalize_edition('public') == 'Public'
        assert scope_items.normalize_edition(None) == 'Public'
        assert scope_items.normalize_edition('') == 'Public'
        assert scope_items.normalize_edition('cualquier cosa') == 'Public'
        assert scope_items.normalize_edition(123) == 'Public'

    def test_private_variants(self):
        assert scope_items.normalize_edition('Private') == 'Private'
        assert scope_items.normalize_edition('private') == 'Private'
        assert scope_items.normalize_edition('Privada') == 'Private'
        assert scope_items.normalize_edition('RISE with SAP') == 'Private'
        assert scope_items.normalize_edition('rise') == 'Private'


class TestEditionLabels:
    def test_both_editions_have_required_keys(self):
        for edition in scope_items.VALID_EDITIONS:
            label = scope_items.EDITION_LABELS[edition]
            assert label['nombre']
            assert label['programa']
            assert label['descripcion']

    def test_public_is_grow_private_is_rise(self):
        assert 'GROW' in scope_items.EDITION_LABELS['Public']['programa']
        assert 'RISE' in scope_items.EDITION_LABELS['Private']['programa']


class TestLoadScopeCatalog:
    def test_loads_from_excel_or_fallback(self):
        catalog = scope_items.load_scope_catalog()
        assert isinstance(catalog, dict)
        assert len(catalog) > 0
        # Módulos core siempre deben tener al menos un scope item
        for mod in ('FI', 'MM'):
            assert mod in catalog
            assert len(catalog[mod]) > 0

    def test_catalog_entries_are_id_name_tuples(self):
        catalog = scope_items.load_scope_catalog()
        for mod, items in catalog.items():
            for entry in items:
                assert isinstance(entry, tuple)
                assert len(entry) == 2
                sid, name = entry
                assert sid is None or isinstance(sid, str)
                assert isinstance(name, str) and name.strip()

    def test_cache_returns_same_object_on_second_call(self):
        first = scope_items.load_scope_catalog()
        second = scope_items.load_scope_catalog()
        assert first == second


class TestGetScopeItems:
    def test_returns_only_active_modules(self):
        result = scope_items.get_scope_items(['FI', 'MM'])
        modules_returned = [mod for mod, _ in result]
        assert 'FI' in modules_returned
        assert 'MM' in modules_returned
        assert 'SD' not in modules_returned

    def test_respects_canonical_order(self):
        result = scope_items.get_scope_items(['PS', 'MM', 'FI', 'SD'])
        modules_returned = [mod for mod, _ in result]
        # MODULE_ORDER = FI, CO, MM, SD, PP, PS, ...
        expected_order = [m for m in scope_items.MODULE_ORDER if m in modules_returned]
        assert modules_returned == expected_order

    def test_empty_active_modules_returns_empty(self):
        assert scope_items.get_scope_items([]) == []

    def test_unknown_module_ignored(self):
        result = scope_items.get_scope_items(['ZZ'])
        assert result == []


class TestExtractBaseIds:
    def test_single_id(self):
        assert scope_items._extract_base_ids('J58') == ['J58']

    def test_id_with_suffix(self):
        assert scope_items._extract_base_ids('J60-05') == ['J60']

    def test_multiple_ids_newline_separated(self):
        result = scope_items._extract_base_ids('J58-00_J58-02')
        assert result == ['J58']

    def test_multiple_distinct_ids(self):
        result = scope_items._extract_base_ids('BDK BD3')
        assert result == ['BDK', 'BD3']

    def test_none_or_dash_returns_empty(self):
        assert scope_items._extract_base_ids(None) == []
        assert scope_items._extract_base_ids('-') == []


class TestCleanProcessName:
    def test_strips_prefix_and_suffix(self):
        result = scope_items._clean_process_name('FI-05_Cuentas por Pagar(FI_P020)')
        assert result == 'Cuentas por Pagar'
