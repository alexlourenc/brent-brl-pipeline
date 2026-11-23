"""Testes da configuração: falhar cedo com mensagem clara."""
from pathlib import Path

import pytest

from pipeline import config
from pipeline.config import ConfigError, carregar_config

VARIAVEIS = ["EIA_API_KEY", "DATA_INICIO", "DATA_FIM", "HTTP_MAX_TENTATIVAS", "HTTP_TIMEOUT_S"]


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isola o teste: sem as variáveis da máquina e sem ler o .env real."""
    for nome in VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(config, "RAIZ", tmp_path)  # tmp_path não tem .env


def test_sem_chave_falha_com_mensagem_clara():
    with pytest.raises(ConfigError, match="EIA_API_KEY"):
        carregar_config()


def test_chave_de_exemplo_e_recusada(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "coloque_sua_chave_aqui")
    with pytest.raises(ConfigError):
        carregar_config()


def test_data_em_formato_errado_e_recusada(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "abc123")
    monkeypatch.setenv("DATA_INICIO", "22/11/2026")
    with pytest.raises(ConfigError, match="AAAA-MM-DD"):
        carregar_config()


def test_inicio_depois_do_fim_e_recusado(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "abc123")
    monkeypatch.setenv("DATA_INICIO", "2026-01-01")
    monkeypatch.setenv("DATA_FIM", "2025-01-01")
    with pytest.raises(ConfigError, match="maior"):
        carregar_config()


def test_parametro_http_invalido_e_recusado(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "abc123")
    monkeypatch.setenv("HTTP_MAX_TENTATIVAS", "0")
    with pytest.raises(ConfigError, match="HTTP_MAX_TENTATIVAS"):
        carregar_config()


def test_config_valida_esconde_a_chave(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "abcdef123456")
    cfg = carregar_config()
    assert cfg.http_max_tentativas == 4  # padrão
    assert "abcdef123456" not in repr(cfg)
    assert cfg.chave_mascarada == "****3456"
