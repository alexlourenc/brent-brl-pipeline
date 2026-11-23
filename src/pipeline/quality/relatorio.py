"""
Relatório de execução e qualidade / Run and quality report.

Junta, num JSON só, tudo o que aconteceu numa execução:
status geral, tempos, chamadas às APIs, volumes por camada e os checks.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline.extract.http_client import EstatisticasHTTP
from pipeline.quality.checks import BLOQUEANTE, ResultadoCheck

log = logging.getLogger(__name__)

APROVADO = "aprovado"
APROVADO_COM_ALERTAS = "aprovado_com_alertas"
REPROVADO = "reprovado"


def calcular_status(checks: list[ResultadoCheck]) -> str:
    """1 bloqueante falhou = reprovado; só alertas = aprovado com alertas."""
    if any(not c.passou and c.severidade == BLOQUEANTE for c in checks):
        return REPROVADO
    if any(not c.passou for c in checks):
        return APROVADO_COM_ALERTAS
    return APROVADO


def montar_relatorio(
    *,
    inicio_execucao: datetime,
    fim_execucao: datetime,
    periodo: tuple[date, date],
    estatisticas_http: dict[str, EstatisticasHTTP],
    volumes: dict[str, int],
    checks: list[ResultadoCheck],
) -> dict[str, Any]:
    """Monta o dicionário do relatório (ainda sem gravar)."""
    return {
        "status_geral": calcular_status(checks),
        "execucao": {
            "inicio": inicio_execucao.isoformat(timespec="seconds"),
            "fim": fim_execucao.isoformat(timespec="seconds"),
            "duracao_s": round((fim_execucao - inicio_execucao).total_seconds(), 2),
            "periodo": {"inicio": str(periodo[0]), "fim": str(periodo[1])},
        },
        "extracao": {nome: asdict(est) for nome, est in estatisticas_http.items()},
        "volumes": volumes,
        "resumo_checks": {
            "total": len(checks),
            "aprovados": sum(c.passou for c in checks),
            "falhas_bloqueantes": sum(not c.passou and c.severidade == BLOQUEANTE for c in checks),
            "alertas": sum(not c.passou and c.severidade != BLOQUEANTE for c in checks),
        },
        "checks": [asdict(c) for c in checks],
    }


def gravar_relatorio(relatorio: dict[str, Any], caminho: Path) -> Path:
    """Grava o relatório em JSON legível (indentado, com acentos)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    log.info("[relatorio] %s -> %s", relatorio["status_geral"], caminho)
    return caminho