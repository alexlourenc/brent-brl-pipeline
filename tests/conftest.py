"""
Fixtures compartilhadas pelos testes / Shared test fixtures.

Nenhum teste usa internet nem o .env real: os dados de entrada são
pequenos JSONs de exemplo, gravados numa pasta temporária (tmp_path).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.config import Config


def gravar_json(caminho: Path, conteudo: dict) -> None:
    """Grava um JSON de exemplo, criando as pastas."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")


def brent(data: str, valor: str) -> dict:
    """Um registro no formato da EIA (valor vem como TEXTO)."""
    return {"period": data, "series": "RBRTE", "units": "$/BBL", "value": valor}


def ptax(data_hora: str, compra: float, venda: float) -> dict:
    """Um registro no formato do BCB."""
    return {"cotacaoCompra": compra, "cotacaoVenda": venda, "dataHoraCotacao": data_hora}


@pytest.fixture
def bronze_exemplo(tmp_path: Path) -> Path:
    """
    Bronze pequena com os casos difíceis de propósito:
      - PTAX duplicada em 03/01 (fica a mais recente: venda 5.03);
      - Brent em 04/01 SEM PTAX no dia (feriado: usa a de 03/01);
      - Brent de 05/01 com valor vazio (deve ser descartado).
    """
    dir_bronze = tmp_path / "bronze"
    gravar_json(dir_bronze / "ptax" / "ptax_teste.json", {"value": [
        ptax("2024-01-02 13:00:00.000", 4.99, 5.00),
        ptax("2024-01-03 13:00:00.100", 5.01, 5.02),
        ptax("2024-01-03 13:00:00.200", 5.02, 5.03),  # duplicata, mais recente
        ptax("2024-01-05 13:00:00.000", 5.04, 5.05),
    ]})
    gravar_json(dir_bronze / "brent" / "brent_teste_p0.json", {"response": {"total": "4", "data": [
        brent("2024-01-02", "80.0"),
        brent("2024-01-03", "82.0"),
        brent("2024-01-04", "81.0"),  # sem PTAX neste dia
        brent("2024-01-05", ""),      # valor vazio
    ]}})
    return dir_bronze


@pytest.fixture
def cfg_teste(tmp_path: Path, bronze_exemplo: Path) -> Config:
    """Configuração apontando tudo para a pasta temporária."""
    return Config(
        eia_api_key="CHAVE_DE_TESTE",
        data_inicio=date(2024, 1, 1),
        data_fim=date(2024, 1, 31),
        log_level="INFO",
        dir_bronze=bronze_exemplo,
        dir_prata=tmp_path / "prata",
        dir_output=tmp_path / "output",
        dir_relatorios=tmp_path / "relatorios",
        http_max_tentativas=2,
        http_backoff_base_s=0.0,
        http_intervalo_min_s=0.0,
        http_timeout_s=1.0,
    )
