"""Testes da extração: troca atômica, validação e paginação (sem internet)."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.extract.bcb import extrair_ptax
from pipeline.extract.eia import extrair_brent
from pipeline.extract.http_client import ErroHTTP, FormatoInesperado


def cliente_falso(*respostas: object) -> MagicMock:
    cliente = MagicMock()
    cliente.get_json.side_effect = list(respostas)
    return cliente


def test_falha_no_meio_mantem_a_bronze_anterior(tmp_path: Path):
    # 1ª extração completa: 2 blocos (2024 e 2025)
    extrair_ptax(cliente_falso({"value": [1]}, {"value": [2]}), date(2024, 1, 1), date(2025, 6, 1), tmp_path)
    antes = {a.name: a.read_text() for a in (tmp_path / "ptax").iterdir()}

    # 2ª extração falha no 2º bloco
    with pytest.raises(ErroHTTP):
        extrair_ptax(cliente_falso({"value": []}, ErroHTTP("caiu")), date(2024, 1, 1), date(2025, 6, 1), tmp_path)

    depois = {a.name: a.read_text() for a in (tmp_path / "ptax").iterdir()}
    assert depois == antes                        # bronze anterior intacta
    assert not (tmp_path / "ptax_tmp").exists()   # sem lixo temporário


def test_resposta_sem_a_lista_esperada_nao_e_gravada(tmp_path: Path):
    with pytest.raises(FormatoInesperado):
        extrair_ptax(cliente_falso({"erro": "formato novo"}), date(2024, 1, 1), date(2024, 2, 1), tmp_path)
    assert not (tmp_path / "ptax").exists()


def test_paginacao_pede_paginas_ate_o_total(tmp_path: Path):
    cliente = cliente_falso(
        {"response": {"total": "3", "data": [1, 2]}},
        {"response": {"total": "3", "data": [3]}},
    )
    arquivos = extrair_brent(cliente, "CHAVE", date(2024, 1, 1), date(2024, 3, 1), tmp_path)
    offsets = [chamada.kwargs["params"]["offset"] for chamada in cliente.get_json.call_args_list]
    assert offsets == [0, 2]
    assert [a.name for a in arquivos] == ["brent_2024-01-01_2024-03-01_p0.json", "brent_2024-01-01_2024-03-01_p1.json"]


def test_chave_nao_e_gravada_na_bronze(tmp_path: Path):
    cliente = cliente_falso({"response": {"total": "1", "data": [{"value": "80"}]}})
    arquivos = extrair_brent(cliente, "CHAVE_SECRETA_XYZ", date(2024, 1, 1), date(2024, 1, 31), tmp_path)
    assert all("CHAVE_SECRETA_XYZ" not in a.read_text() for a in arquivos)
