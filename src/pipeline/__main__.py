"""Ponto de entrada: python -m pipeline"""
from __future__ import annotations

import argparse
import sys

from pipeline import __version__
from pipeline.config import ConfigError, carregar_config


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
    args = parser.parse_args(argv)

    # 2. Configuração: se falhar, sai com código 1 (erro)
    try:
        cfg = carregar_config()
    except ConfigError as erro:
        print(f"Erro de configuração: {erro}", file=sys.stderr)
        return 1

    if args.verificar_config:
        print("Configuração OK")
        print(f"  Período : {cfg.data_inicio} a {cfg.data_fim}")
        print(f"  Chave   : {cfg.chave_mascarada}")
        print(f"  Saída   : {cfg.dir_output}")
        return 0

    print("Etapas do pipeline ainda não implementadas (Fase 2 em diante).")
    return 0


if __name__ == "__main__":
    sys.exit(main())