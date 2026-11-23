"""
Ponto de entrada: python -m pipeline / Entry point.

Orquestra o pipeline inteiro, nesta ordem:
  1. Extração   -> bronze (JSON cru, troca atômica)
  2. Prata/Ouro -> tabelas na memória do DuckDB
  3. Qualidade  -> checks sobre as tabelas, ANTES de gravar qualquer saída
  4. Saída      -> só se aprovado: Parquet particionado + quality_report.json
Código de saída: 0 = sucesso | 1 = falha (configuração, extração ou qualidade).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

import duckdb

from pipeline import __version__
from pipeline.config import Config, ConfigError, carregar_config
from pipeline.extract.bcb import extrair_ptax
from pipeline.extract.eia import extrair_brent
from pipeline.extract.http_client import ClienteHTTP, ErroHTTP, EstatisticasHTTP, FormatoInesperado
from pipeline.load.writer import gravar_parquet_particionado
from pipeline.quality.checks import executar_checks
from pipeline.quality.relatorio import REPROVADO, calcular_status, gravar_relatorio, montar_relatorio
from pipeline.transform.duckdb_runner import construir_ouro, construir_prata, contar_bronze

log = logging.getLogger("pipeline")


def configurar_logs(nivel: str) -> None:
    """Formato único de log para todo o pipeline, com horário."""
    logging.basicConfig(
        level=getattr(logging, nivel, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def _novo_cliente(nome: str, cfg: Config) -> ClienteHTTP:
    """Cria um cliente HTTP com os parâmetros do .env."""
    return ClienteHTTP(
        nome,
        intervalo_min_s=cfg.http_intervalo_min_s,
        max_tentativas=cfg.http_max_tentativas,
        backoff_base_s=cfg.http_backoff_base_s,
        timeout_s=cfg.http_timeout_s,
    )


def executar(cfg: Config, extrair: bool = True) -> int:
    """Roda o pipeline completo. Devolve o código de saída (0 ou 1)."""
    inicio = datetime.now()
    estatisticas: dict[str, EstatisticasHTTP] = {}

    # ETAPA 1. Extração -> bronze
    if extrair:
        bcb, eia = _novo_cliente("bcb", cfg), _novo_cliente("eia", cfg)
        try:
            extrair_ptax(bcb, cfg.data_inicio, cfg.data_fim, cfg.dir_bronze)
            extrair_brent(eia, cfg.eia_api_key, cfg.data_inicio, cfg.data_fim, cfg.dir_bronze)
        except (ErroHTTP, FormatoInesperado) as erro:
            log.error("Extração falhou: %s. Bronze e output anteriores foram mantidas.", erro)
            return 1
        estatisticas = {"bcb": bcb.stats, "eia": eia.stats}
    else:
        log.info("Extração pulada (--sem-extracao): usando a bronze existente.")

    # ETAPA 2. Prata e ouro: uma única conexão DuckDB para todas as etapas
    con = duckdb.connect()
    volumes = contar_bronze(con, cfg.dir_bronze)
    volumes.update(construir_prata(con, cfg.dir_bronze, cfg.dir_prata))
    volumes["ouro_brent_brl"] = construir_ouro(con)

    # ETAPA 3. Qualidade: roda sobre as tabelas em memória, ANTES de gravar a saída
    checks = executar_checks(con, cfg.data_inicio, cfg.data_fim)
    reprovado = calcular_status(checks) == REPROVADO

    # ETAPA 4. Saída: só dado aprovado chega à output/
    if not reprovado:
        gravar_parquet_particionado(con, "ouro_brent_brl", cfg.dir_output / "brent_brl")

    relatorio = montar_relatorio(
        inicio_execucao=inicio,
        fim_execucao=datetime.now(),
        periodo=(cfg.data_inicio, cfg.data_fim),
        estatisticas_http=estatisticas,
        volumes=volumes,
        checks=checks,
    )

    if reprovado:
        # A output/ anterior fica intacta; o relatório da falha vai para diagnóstico
        caminho = cfg.dir_relatorios / f"quality_report_reprovado_{inicio:%Y%m%d_%H%M%S}.json"
        gravar_relatorio(relatorio, caminho)
        log.error("Qualidade REPROVADA: output/ anterior mantida. Veja %s", caminho)
        return 1

    gravar_relatorio(relatorio, cfg.dir_output / "quality_report.json")
    log.info(
        "Pipeline concluído: %s em %.1fs",
        relatorio["status_geral"], relatorio["execucao"]["duracao_s"],
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    # 1. Argumentos de linha de comando
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Pipeline Brent (EIA) x PTAX (BCB): custo do barril em reais.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--verificar-config",
        action="store_true",
        help="só valida o .env e mostra a configuração (sem chamar APIs)",
    )
    parser.add_argument(
        "--sem-extracao",
        action="store_true",
        help="não chama as APIs; reprocessa a partir da bronze existente",
    )
    args = parser.parse_args(argv)

    # 2. Configuração: se falhar, sai com código 1 (erro)
    try:
        cfg = carregar_config()
    except ConfigError as erro:
        print(f"Erro de configuração: {erro}", file=sys.stderr)
        return 1

    configurar_logs(cfg.log_level)

    if args.verificar_config:
        print("Configuração OK")
        print(f"  Período : {cfg.data_inicio} a {cfg.data_fim}")
        print(f"  Chave   : {cfg.chave_mascarada}")
        print(f"  Saída   : {cfg.dir_output}")
        print(f"  HTTP    : {cfg.http_max_tentativas} tentativas, backoff {cfg.http_backoff_base_s}s, "
              f"intervalo {cfg.http_intervalo_min_s}s, timeout {cfg.http_timeout_s}s")
        return 0

    # 3. O pipeline completo
    return executar(cfg, extrair=not args.sem_extracao)


if __name__ == "__main__":
    sys.exit(main())
