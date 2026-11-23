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
    dir_relatorios: Path
    # 3. Comportamento do cliente HTTP (ajustável sem mexer no código)
    http_max_tentativas: int
    http_backoff_base_s: float
    http_intervalo_min_s: float
    http_timeout_s: float

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


def _ler_numero(nome: str, padrao: float, minimo: float) -> float:
    """Lê um número do ambiente; vazio = padrão; abaixo do mínimo = erro."""
    valor = os.getenv(nome, "").strip()
    if not valor:
        return padrao
    try:
        numero = float(valor)
    except ValueError as exc:
        raise ConfigError(f"{nome} inválido: '{valor}'. Use um número.") from exc
    if numero < minimo:
        raise ConfigError(f"{nome} deve ser no mínimo {minimo} (recebido: {numero}).")
    return numero


def carregar_config() -> Config:
    """Carrega o .env, valida e devolve a configuração."""
    # 4. Carrega o .env da raiz (se não existir, usa o ambiente do sistema)
    load_dotenv(RAIZ / ".env")

    # 5. Falhar cedo: sem chave válida, não adianta seguir
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
        dir_relatorios=RAIZ / "data" / "relatorios",
        http_max_tentativas=int(_ler_numero("HTTP_MAX_TENTATIVAS", 4, minimo=1)),
        http_backoff_base_s=_ler_numero("HTTP_BACKOFF_BASE_S", 1.0, minimo=0),
        http_intervalo_min_s=_ler_numero("HTTP_INTERVALO_MIN_S", 1.0, minimo=0),
        http_timeout_s=_ler_numero("HTTP_TIMEOUT_S", 30.0, minimo=1),
    )
