"""
Data Quality / Qualidade de dados.

Checks automáticos sobre as tabelas da prata e da ouro (na conexão DuckDB).
Dois níveis de severidade:
- bloqueante: o dado está ERRADO (schema, nulos, duplicata, fora do intervalo);
- alerta: o dado está ESTRANHO e merece análise (variação extrema num dia).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import duckdb

log = logging.getLogger(__name__)

BLOQUEANTE = "bloqueante"
ALERTA = "alerta"

# 1. Contratos de schema: coluna -> tipo esperado no DuckDB
SCHEMA_PRATA_PTAX: dict[str, str] = {
    "data": "DATE",
    "ptax_compra": "DOUBLE",
    "ptax_venda": "DOUBLE",
    "data_hora_cotacao": "TIMESTAMP",
}
SCHEMA_PRATA_BRENT: dict[str, str] = {
    "data": "DATE",
    "brent_usd": "DOUBLE",
    "serie": "VARCHAR",
    "unidade": "VARCHAR",
}
SCHEMA_OURO: dict[str, str] = {
    "data": "DATE",
    "ano": "BIGINT",
    "mes": "BIGINT",
    "brent_usd": "DOUBLE",
    "ptax_compra": "DOUBLE",
    "ptax_venda": "DOUBLE",
    "spread_ptax": "DOUBLE",
    "brent_brl": "DOUBLE",
    "variacao_brl": "DOUBLE",
    "variacao_brl_pct": "DOUBLE",
    "efeito_preco_brl": "DOUBLE",
    "efeito_cambio_brl": "DOUBLE",
    "media_movel_7_pregoes_brl": "DOUBLE",
    "ptax_preenchida": "BOOLEAN",
    "data_ptax_usada": "DATE",
}


@dataclass
class ResultadoCheck:
    """Resultado de um check: vai, do jeito que está, para o relatório JSON."""

    tabela: str
    check: str
    descricao: str
    severidade: str
    passou: bool
    medido: dict[str, Any] = field(default_factory=dict)


def _consulta(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> tuple:
    """Executa um SELECT que devolve uma linha só."""
    return con.execute(sql, params or []).fetchone()


# ---------------------------------------------------------------------
# 2. Checks genéricos (servem para qualquer tabela)
# ---------------------------------------------------------------------
def checar_schema(con: duckdb.DuckDBPyConnection, tabela: str, esperado: dict[str, str]) -> ResultadoCheck:
    """Colunas e tipos conferem com o contrato?"""
    real = {linha[0]: linha[1] for linha in con.execute(f"DESCRIBE {tabela}").fetchall()}
    faltando = sorted(set(esperado) - set(real))
    tipos_errados = {
        coluna: {"esperado": tipo, "real": real[coluna]}
        for coluna, tipo in esperado.items()
        if coluna in real and real[coluna] != tipo
    }
    return ResultadoCheck(
        tabela, "schema", f"{len(esperado)} colunas com os tipos do contrato", BLOQUEANTE,
        passou=not faltando and not tipos_errados,
        medido={"faltando": faltando, "tipos_errados": tipos_errados,
                "extras": sorted(set(real) - set(esperado))},
    )


def checar_nulos(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna: str,
    limite: float = 0.0,
    nulos_permitidos: int = 0,
) -> ResultadoCheck:
    """Nulos na coluna dentro do limite (proporção OU quantidade fixa de linhas)?"""
    total, preenchidos = _consulta(con, f"SELECT COUNT(*), COUNT({coluna}) FROM {tabela}")
    nulos = total - preenchidos
    ratio = nulos / total if total else 1.0
    descricao = (
        f"nulos em '{coluna}' <= {nulos_permitidos} linha(s)"
        if nulos_permitidos
        else f"nulos em '{coluna}' <= {limite:.1%}"
    )
    return ResultadoCheck(
        tabela, "null_ratio", descricao, BLOQUEANTE,
        # tabela vazia é sempre reprovada
        passou=total > 0 and (nulos <= nulos_permitidos or ratio <= limite),
        medido={"coluna": coluna, "linhas": total, "nulos": nulos, "null_ratio": round(ratio, 6)},
    )


def checar_unicidade(con: duckdb.DuckDBPyConnection, tabela: str, coluna: str) -> ResultadoCheck:
    """Cada valor da coluna aparece uma vez só?"""
    total, distintos = _consulta(con, f"SELECT COUNT(*), COUNT(DISTINCT {coluna}) FROM {tabela}")
    return ResultadoCheck(
        tabela, "unicidade", f"'{coluna}' sem repetição", BLOQUEANTE,
        passou=total == distintos,
        medido={"coluna": coluna, "linhas": total, "duplicadas": total - distintos},
    )


def checar_intervalo(
    con: duckdb.DuckDBPyConnection, tabela: str, coluna: str, minimo: Any, maximo: Any
) -> ResultadoCheck:
    """Todos os valores estão entre `minimo` e `maximo`?"""
    # 3. Valores entram como parâmetros (?), nunca colados no texto do SQL
    fora, menor, maior = _consulta(
        con,
        f"SELECT COUNT(*) FILTER (WHERE {coluna} < ? OR {coluna} > ?), "
        f"MIN({coluna}), MAX({coluna}) FROM {tabela}",
        [minimo, maximo],
    )
    return ResultadoCheck(
        tabela, "intervalo", f"'{coluna}' entre {minimo} e {maximo}", BLOQUEANTE,
        passou=fora == 0,
        medido={"coluna": coluna, "fora_do_intervalo": fora, "minimo": str(menor), "maximo": str(maior)},
    )


# ---------------------------------------------------------------------
# 4. Checks de regra de negócio (específicos da ouro)
# ---------------------------------------------------------------------
def checar_decomposicao(con: duckdb.DuckDBPyConnection, tabela: str, tolerancia: float = 0.001) -> ResultadoCheck:
    """efeito_preco + efeito_cambio = variacao_brl (a conta tem que fechar)."""
    (divergentes,) = _consulta(
        con,
        f"SELECT COUNT(*) FROM {tabela} "
        f"WHERE ABS(efeito_preco_brl + efeito_cambio_brl - variacao_brl) > ?",
        [tolerancia],
    )
    return ResultadoCheck(
        tabela, "regra_negocio", f"efeito preço + efeito câmbio = variação (tolerância {tolerancia})",
        BLOQUEANTE, passou=divergentes == 0, medido={"linhas_divergentes": divergentes},
    )


def checar_variacao_extrema(
    con: duckdb.DuckDBPyConnection, tabela: str, coluna: str, limite_pct: float
) -> ResultadoCheck:
    """ALERTA: dias com variação maior que `limite_pct` (%) merecem análise."""
    linhas = con.execute(
        f"SELECT data, {coluna} FROM {tabela} WHERE ABS({coluna}) > ? ORDER BY ABS({coluna}) DESC",
        [limite_pct],
    ).fetchall()
    return ResultadoCheck(
        tabela, "anomalia", f"|{coluna}| > {limite_pct}% em um dia", ALERTA,
        passou=len(linhas) == 0,
        medido={"dias": len(linhas), "maiores": [{"data": str(d), coluna: v} for d, v in linhas[:5]]},
    )


def checar_proporcao_preenchida(
    con: duckdb.DuckDBPyConnection, tabela: str, limite: float
) -> ResultadoCheck:
    """ALERTA: muitos dias com PTAX emprestada indicariam falha na extração do BCB."""
    total, preenchidos = _consulta(
        con, f"SELECT COUNT(*), COUNT(*) FILTER (WHERE ptax_preenchida) FROM {tabela}"
    )
    proporcao = preenchidos / total if total else 0.0
    return ResultadoCheck(
        tabela, "anomalia", f"dias com PTAX preenchida <= {limite:.0%}", ALERTA,
        passou=proporcao <= limite,
        medido={"dias_preenchidos": preenchidos, "proporcao": round(proporcao, 4)},
    )


# ---------------------------------------------------------------------
# 5. O conjunto de checks do pipeline
# ---------------------------------------------------------------------
def executar_checks(con: duckdb.DuckDBPyConnection, inicio: date, fim: date) -> list[ResultadoCheck]:
    """Roda todos os checks e devolve os resultados (não levanta erro)."""
    resultados = [
        # Prata PTAX
        checar_schema(con, "prata_ptax", SCHEMA_PRATA_PTAX),
        checar_unicidade(con, "prata_ptax", "data"),
        checar_nulos(con, "prata_ptax", "ptax_venda"),
        checar_intervalo(con, "prata_ptax", "ptax_venda", 1.0, 15.0),
        # Prata Brent
        checar_schema(con, "prata_brent", SCHEMA_PRATA_BRENT),
        checar_unicidade(con, "prata_brent", "data"),
        checar_nulos(con, "prata_brent", "brent_usd"),
        checar_intervalo(con, "prata_brent", "brent_usd", 10.0, 200.0),
        # Ouro
        checar_schema(con, "ouro_brent_brl", SCHEMA_OURO),
        checar_unicidade(con, "ouro_brent_brl", "data"),
        checar_nulos(con, "ouro_brent_brl", "brent_brl"),
        checar_nulos(con, "ouro_brent_brl", "ptax_venda"),
        checar_nulos(con, "ouro_brent_brl", "variacao_brl", nulos_permitidos=1),  # só a 1ª linha
        checar_intervalo(con, "ouro_brent_brl", "data", inicio, fim),
        checar_intervalo(con, "ouro_brent_brl", "brent_brl", 10.0, 3000.0),
        checar_intervalo(con, "ouro_brent_brl", "spread_ptax", 0.0, 0.05),
        checar_decomposicao(con, "ouro_brent_brl"),
        # Alertas
        checar_variacao_extrema(con, "ouro_brent_brl", "variacao_brl_pct", 10.0),
        checar_proporcao_preenchida(con, "ouro_brent_brl", 0.05),
    ]
    for r in resultados:
        nivel = logging.INFO if r.passou else (logging.ERROR if r.severidade == BLOQUEANTE else logging.WARNING)
        log.log(nivel, "[qualidade] %-15s %-13s %s: %s", r.tabela, r.check, r.descricao,
                "ok" if r.passou else ("FALHOU" if r.severidade == BLOQUEANTE else "ALERTA"))
    return resultados