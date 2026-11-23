"""Testes dos checks de qualidade: passam com dado bom e PEGAM dado ruim."""
from datetime import date

import duckdb
import pytest

from pipeline.quality.checks import (
    ALERTA,
    BLOQUEANTE,
    ResultadoCheck,
    checar_intervalo,
    checar_nulos,
    checar_schema,
    checar_unicidade,
    executar_checks,
)
from pipeline.quality.relatorio import APROVADO, APROVADO_COM_ALERTAS, REPROVADO, calcular_status
from pipeline.transform.duckdb_runner import construir_ouro, construir_prata


@pytest.fixture
def con_ruim():
    """Tabela sabotada: data duplicada, preço negativo e preço nulo."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t (data DATE, brent_usd DOUBLE);"
        "INSERT INTO t VALUES ('2024-01-02', 80.0), ('2024-01-02', -5.0), ('2024-01-03', NULL);"
    )
    return con


def test_dados_de_exemplo_passam_em_todos_os_checks_bloqueantes(bronze_exemplo, tmp_path):
    con = duckdb.connect()
    construir_prata(con, bronze_exemplo, tmp_path / "prata")
    construir_ouro(con)
    resultados = executar_checks(con, date(2024, 1, 1), date(2024, 1, 31))
    falhas = [r.descricao for r in resultados if r.severidade == BLOQUEANTE and not r.passou]
    assert falhas == []


def test_unicidade_pega_data_duplicada(con_ruim):
    r = checar_unicidade(con_ruim, "t", "data")
    assert not r.passou and r.medido["duplicadas"] == 1


def test_intervalo_pega_preco_negativo(con_ruim):
    r = checar_intervalo(con_ruim, "t", "brent_usd", 10.0, 200.0)
    assert not r.passou and r.medido["fora_do_intervalo"] == 1


def test_nulos_pega_valor_vazio(con_ruim):
    assert not checar_nulos(con_ruim, "t", "brent_usd").passou


def test_tabela_vazia_e_reprovada():
    con = duckdb.connect()
    con.execute("CREATE TABLE vazia (x DOUBLE)")
    assert not checar_nulos(con, "vazia", "x", nulos_permitidos=1).passou


def test_schema_pega_coluna_faltando(con_ruim):
    r = checar_schema(con_ruim, "t", {"data": "DATE", "brent_usd": "DOUBLE", "serie": "VARCHAR"})
    assert not r.passou and r.medido["faltando"] == ["serie"]


def _check(passou: bool, severidade: str) -> ResultadoCheck:
    return ResultadoCheck("t", "x", "x", severidade, passou)


@pytest.mark.parametrize(
    ("checks", "esperado"),
    [
        ([_check(True, BLOQUEANTE), _check(True, ALERTA)], APROVADO),
        ([_check(True, BLOQUEANTE), _check(False, ALERTA)], APROVADO_COM_ALERTAS),
        ([_check(False, BLOQUEANTE), _check(True, ALERTA)], REPROVADO),
    ],
)
def test_status_geral(checks, esperado):
    assert calcular_status(checks) == esperado
