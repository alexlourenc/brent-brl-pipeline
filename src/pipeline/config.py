"""
Configuração do pipeline / Pipeline configuration.

Lê variáveis de ambiente (arquivo .env) e devolve um objeto imutável.
Nenhuma chave de API fica escrita no código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# 1. Raiz do projeto: src/pipeline/config.py -> sobe 2 níveis
RAIZ: Path = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """Erro de configuração: o pipeline não deve nem começar."""


@dataclass(frozen=True)
class Config:
    # 2. repr=False: a chave nunca aparece ao imprimir o objeto
    eia_api_key: str = field(repr=False)
    data_inicio: date
    data_fim: date
    log_level: str
    dir_bronze: Path
    dir_prata: Path
    dir_output: Path

    @property
    def chave_mascarada(self) -> str:
        """Mostra só os 4 últimos caracteres, para conferência."""
        return "****" + self.eia_api_key[-4:]


def _ler_data(nome: str, padrao: date) -> date:
    """Lê uma data AAAA-MM-DD do ambiente; vazio = valor padrão."""
    valor = os.getenv(nome, "").strip()
    if not valor:
        return padrao
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise ConfigError(f"{nome} inválida: '{valor}'. Use AAAA-MM-DD.") from exc


def carregar_config() -> Config:
    """Carrega o .env, valida e devolve a configuração."""
    # 3. Carrega o .env da raiz (se não existir, usa o ambiente do sistema)
    load_dotenv(RAIZ / ".env")

    # 4. Falhar cedo: sem chave válida, não adianta seguir
    chave = os.getenv("EIA_API_KEY", "").strip()
    if not chave or chave == "coloque_sua_chave_aqui":
        raise ConfigError(
            "EIA_API_KEY não definida. Copie .env.example para .env e preencha a chave."
        )

    inicio = _ler_data("DATA_INICIO", date(2024, 1, 1))
    fim = _ler_data("DATA_FIM", date.today())
    if inicio > fim:
        raise ConfigError(f"DATA_INICIO ({inicio}) é maior que DATA_FIM ({fim}).")

    return Config(
        eia_api_key=chave,
        data_inicio=inicio,
        data_fim=fim,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        dir_bronze=RAIZ / "data" / "bronze",
        dir_prata=RAIZ / "data" / "prata",
        dir_output=RAIZ / "output",
    )