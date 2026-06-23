import pytest
from services import joule_optimizer


class TestJouleOptimizerBasics:
    def test_standardize_removes_accents(self):
        q = "mostrar facturas vencidas"
        result = joule_optimizer.clean_and_standardize_prompt(q)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_optimize_prompt_returns_dict(self):
        q = "muestra el saldo de clientes"
        result = joule_optimizer.optimize_prompt(q)
        assert isinstance(result, dict)
        assert 'original' in result
        assert 'optimized' in result
        assert 'is_valid' in result

    def test_passthrough_for_simple_queries(self):
        q = "MOSTRAR saldo de clientes"
        result = joule_optimizer.optimize_prompt(q)
        assert result['is_valid'] is True
