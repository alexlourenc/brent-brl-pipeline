"""
Execução dos SQL no DuckDB / Running the SQL files on DuckDB.

Os arquivos .sql ficam em src/pipeline/sql/ e usam marcadores como {bronze},
que são trocados pelo caminho real antes de executar.
Cada SQL vira uma tabela dentro da conexão DuckDB; a prata também é salva
em Parquet em data/prata/, para conferência.
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)

# 1. Pasta dos .sql: src/pipeline/transform/ -> sobe 1 nível -> sql/
DIR_SQL: Path = Path(__file__).resolve().parent.parent / "sql"


def ler_sql(nome_arquivo: str, **marcadores: str) -> str:
    """Lê um .sql e troca cada {marcador} pelo valor informado."""
    sql = (DIR_SQL / nome_arquivo).read_text(encoding="utf-8")
    for chave, valor in marcadores.items():
        sql = sql.replace("{" + chave + "}", valor)
    # 2. Tira o ';' final: o SQL vai entrar dentro de um CREATE TABLE ... AS
    return sql.strip().rstrip(";")


def criar_tabela(
    con: duckdb.DuckDBPyConnection, tabela: str, nome_arquivo: str, **marcadores: str
) -> int:
    """Executa o SQL e guarda o resultado numa tabela. Devolve o nº de linhas."""
    sql = ler_sql(nome_arquivo, **marcadores)
    con.execute(f"CREATE OR REPLACE TABLE {tabela} AS\n{sql}")
    linhas: int = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    log.info("[sql] %s: %d linhas (%s)", tabela, linhas, nome_arquivo)
    return linhas


def construir_prata(
    con: duckdb.DuckDBPyConnection, dir_bronze: Path, dir_prata: Path
) -> dict[str, int]:
    """Cria as tabelas prata_ptax e prata_brent e salva cada uma em Parquet."""
    # 3. as_posix(): barras '/' (o DuckDB aceita no Windows também)
    bronze = dir_bronze.as_posix()
    contagens = {
        "prata_ptax": criar_tabela(con, "prata_ptax", "silver_ptax.sql", bronze=bronze),
        "prata_brent": criar_tabela(con, "prata_brent", "silver_brent.sql", bronze=bronze),
    }

    dir_prata.mkdir(parents=True, exist_ok=True)
    for tabela in contagens:
        destino = (dir_prata / f"{tabela}.parquet").as_posix()
        con.execute(f"COPY {tabela} TO '{destino}' (FORMAT PARQUET, COMPRESSION SNAPPY)")
        log.info("[prata] %s salva em %s", tabela, destino)

    return contagens

def construir_ouro(con: duckdb.DuckDBPyConnection) -> int:
    """Cria a tabela ouro_brent_brl a partir das tabelas prata (mesma conexão)."""
    return criar_tabela(con, "ouro_brent_brl", "gold_brent_brl.sql")

def contar_bronze(con: duckdb.DuckDBPyConnection, dir_bronze: Path) -> dict[str, int]:
    """Conta os registros brutos da bronze (antes de qualquer limpeza)."""
    b = dir_bronze.as_posix()
    ptax = con.execute(
        f"SELECT COUNT(*) FROM (SELECT UNNEST(value) FROM read_json('{b}/ptax/*.json'))"
    ).fetchone()[0]
    brent = con.execute(
        f"SELECT COUNT(*) FROM (SELECT UNNEST(response.data) FROM read_json('{b}/brent/*.json'))"
    ).fetchone()[0]
    return {"bronze_ptax": ptax, "bronze_brent": brent}