import pytest
from services import ai_chat


class TestAIChatDefaults:
    def test_default_proposal_data(self):
        engine_defaults = ai_chat.AIChatEngine._default_proposal_data(None)
        assert engine_defaults['company_name'] == 'Empresa Peruana S.A.C.'
        assert isinstance(engine_defaults['active_modules'], list)
        assert 'FI' in engine_defaults['active_modules']
        assert 'pains' in engine_defaults
        assert 'logistics' in engine_defaults['pains']
        assert 'financial' in engine_defaults['pains']
        assert 'management' in engine_defaults['pains']

    def test_default_values_valid(self):
        data = ai_chat.AIChatEngine._default_proposal_data(None)
        assert data['consulting_rate'] >= 10
        assert data['consulting_rate'] <= 1000
        assert data['support_percentage'] >= 0
        assert data['support_percentage'] <= 100
        assert data['exchange_rate'] >= 1
        assert data['exchange_rate'] <= 10
        assert data['revenue'] > 0

    def test_system_instruction_defined(self):
        assert len(ai_chat.SYSTEM_INSTRUCTION) > 100
        assert 'SEIDOR Perú' in ai_chat.SYSTEM_INSTRUCTION
        assert 'SAP' in ai_chat.SYSTEM_INSTRUCTION

    def test_extraction_prompt_defined(self):
        assert len(ai_chat.EXTRACTION_PROMPT) > 50
        assert 'company_name' in ai_chat.EXTRACTION_PROMPT
        assert 'revenue' in ai_chat.EXTRACTION_PROMPT

    def test_system_instruction_has_data_delimiters(self):
        assert '##DATA_READY' in ai_chat.SYSTEM_INSTRUCTION
        assert '##DATA_END' in ai_chat.SYSTEM_INSTRUCTION

    def test_system_instruction_no_hardcoded_numbers(self):
        assert '15000000' not in ai_chat.SYSTEM_INSTRUCTION
        assert 'consulting_rate": 60' not in ai_chat.SYSTEM_INSTRUCTION


class TestExtractDataBlock:
    def test_extracts_from_delimiters(self):
        text = "Gracias por los datos.\n##DATA_READY\n{\"company_name\": \"Minera Test\", \"sector\": \"Minería\"}\n##DATA_END\nSaludos."
        result = ai_chat.extract_data_block(text)
        assert result is not None
        assert result['company_name'] == 'Minera Test'
        assert result['sector'] == 'Minería'

    def test_extracts_from_delimiters_no_newline(self):
        text = "Texto ##DATA_READY {\"company_name\": \"A\"} ##DATA_END más texto"
        result = ai_chat.extract_data_block(text)
        assert result is not None
        assert result['company_name'] == 'A'

    def test_returns_none_on_no_json(self):
        text = "Solo texto conversacional sin datos estructurados."
        result = ai_chat.extract_data_block(text)
        assert result is None

    def test_extracts_fallback_json_braces(self):
        text = "Respuesta.\n{\"company_name\": \"Fallback\", \"sector\": \"Test\"}\nFin."
        result = ai_chat.extract_data_block(text)
        assert result is not None
        assert result['company_name'] == 'Fallback'

    def test_extracts_fallback_json_with_markdown(self):
        text = "```json\n{\"company_name\": \"MD\", \"sector\": \"Test\"}\n```"
        result = ai_chat.extract_data_block(text)
        assert result is not None
        assert result['company_name'] == 'MD'

    def test_returns_none_on_empty_string(self):
        assert ai_chat.extract_data_block('') is None
        assert ai_chat.extract_data_block('   ') is None
        assert ai_chat.extract_data_block(None) is None

    def test_extracts_complex_nested_json(self):
        text = """##DATA_READY
{"company_name": "Gloria S.A.", "sector": "Alimentos", "active_modules": ["FI", "CO", "MM", "SD"], "revenue": 150000000, "pains": {"logistics": "Problema A", "financial": "Problema B", "management": "Problema C"}}
##DATA_END"""
        result = ai_chat.extract_data_block(text)
        assert result is not None
        assert result['company_name'] == 'Gloria S.A.'
        assert result['pains']['logistics'] == 'Problema A'
        assert result['active_modules'] == ['FI', 'CO', 'MM', 'SD']
        assert result['revenue'] == 150000000


class TestValidateProposalData:
    def test_valid_data(self):
        data = {
            "company_name": "Test S.A.",
            "sector": "Minería",
            "active_modules": ["FI", "CO", "MM", "SD"],
            "revenue": 50000000,
            "complexity": "Alta",
            "pains": {"logistics": "A", "financial": "B", "management": "C"},
            "consulting_rate": 65,
            "support_percentage": 15,
            "exchange_rate": 3.78
        }
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is True
        assert err is None

    def test_invalid_not_dict(self):
        valid, err = ai_chat.validate_proposal_data("not a dict")
        assert valid is False

    def test_invalid_empty_company(self):
        data = {"company_name": "", "sector": "Test", "active_modules": ["FI"]}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'company_name' in err

    def test_invalid_modules(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["INVALIDO"]}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'INVALIDO' in err

    def test_invalid_revenue_non_positive(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"], "revenue": -100}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'revenue' in err

    def test_invalid_revenue_zero(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"], "revenue": 0}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False

    def test_invalid_complexity(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"], "complexity": "SuperAlta"}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'complexity' in err

    def test_accepts_partial_valid(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"]}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is True

    def test_invalid_pains_type(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"], "pains": {"logistics": 123}}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'pains' in err

    def test_invalid_support_percentage_out_of_range(self):
        data = {"company_name": "A", "sector": "B", "active_modules": ["FI"], "support_percentage": 150}
        valid, err = ai_chat.validate_proposal_data(data)
        assert valid is False
        assert 'support_percentage' in err
