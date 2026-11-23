"""
Extração da PTAX (Banco Central) / PTAX extraction (Central Bank of Brazil).

API Olinda, serviço CotacaoDolarPeriodo: cotação de compra e venda do dólar,
um registro por dia útil. Não exige chave.
Saída: JSON cru, exatamente como veio, em data/bronze/ptax/.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from pipeline.extract.armazenamento import escrita_atomica
from pipeline.extract.http_client import ClienteHTTP, FormatoInesperado
from pipeline.extract.periodos import dividir_em_blocos_anuais

log = logging.getLogger(__name__)

URL_PTAX = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)


def _data_bcb(d: date) -> str:
    """A API do BCB espera 'MM-DD-AAAA', COM aspas simples."""
    return f"'{d:%m-%d-%Y}'"


def extrair_ptax(cliente: ClienteHTTP, inicio: date, fim: date, dir_bronze: Path) -> list[Path]:
    """Baixa a PTAX do período, um arquivo JSON por ano. Devolve os arquivos gravados."""
    destino = dir_bronze / "ptax"
    nomes: list[str] = []

    # 1. Troca atômica: grava numa pasta temporária; a bronze anterior só é
    #    substituída se TODOS os blocos derem certo (idempotente e segura)
    with escrita_atomica(destino) as pasta_tmp:
        # 2. Um bloco por ano: chamadas menores falham menos e são retentadas mais rápido
        for ini, fim_bloco in dividir_em_blocos_anuais(inicio, fim):
            params = {
                "@dataInicial": _data_bcb(ini),
                "@dataFinalCotacao": _data_bcb(fim_bloco),
                "$format": "json",
            }
            dados = cliente.get_json(URL_PTAX, params=params)

            # 3. Validação mínima da estrutura antes de gravar
            if not isinstance(dados, dict) or not isinstance(dados.get("value"), list):
                raise FormatoInesperado(f"[bcb] resposta sem a lista 'value' ({ini} a {fim_bloco})")

            # 4. Bronze = cru: grava o JSON inteiro, sem mexer em nada
            arquivo = pasta_tmp / f"ptax_{ini}_{fim_bloco}.json"
            arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
            log.info("[bcb] %s a %s: %d registros -> %s", ini, fim_bloco, len(dados["value"]), arquivo.name)
            nomes.append(arquivo.name)

    return [destino / nome for nome in nomes]
