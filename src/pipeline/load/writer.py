"""
Gravação da camada final / Final layer writer.

Grava uma tabela do DuckDB em Parquet com compressão Snappy,
particionado por ano e mês (estilo Hive: ano=2024/mes=1/...).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)


def gravar_parquet_particionado(
    con: duckdb.DuckDBPyConnection, tabela: str, destino: Path
) -> Path:
    """Grava `tabela` em `destino`/ano=AAAA/mes=M/*.parquet. Devolve a pasta."""
    # 1. Idempotência: apaga a saída anterior para não sobrar partição velha
    if destino.exists():
        shutil.rmtree(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # 2. Parquet + Snappy + partição por ano/mês, numa instrução só
    con.execute(
        f"""
        COPY {tabela} TO '{destino.as_posix()}'
        (FORMAT PARQUET, COMPRESSION SNAPPY, PARTITION_BY (ano, mes))
        """
    )

    arquivos = list(destino.rglob("*.parquet"))
    log.info("[saida] %s -> %s (%d arquivos)", tabela, destino, len(arquivos))
    return destino