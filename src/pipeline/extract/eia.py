"""
Extração do Brent (EIA) / Brent extraction (U.S. Energy Information Administration).

API EIA Open Data v2, série RBRTE: preço spot do petróleo Brent em US$/barril,
um registro por dia útil. Exige chave (EIA_API_KEY, lida do .env).
Saída: JSON cru, exatamente como veio, em data/bronze/brent/.
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

URL_EIA = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
SERIE_BRENT = "RBRTE"
TAMANHO_PAGINA = 5000  # máximo de linhas que a EIA devolve por chamada


def extrair_brent(
    cliente: ClienteHTTP, api_key: str, inicio: date, fim: date, dir_bronze: Path
) -> list[Path]:
    """Baixa o Brent do período, por ano e com paginação. Devolve os arquivos gravados."""
    destino = dir_bronze / "brent"
    nomes: list[str] = []

    # 1. Troca atômica: a bronze anterior só é substituída se TUDO der certo
    with escrita_atomica(destino) as pasta_tmp:
        for ini, fim_bloco in dividir_em_blocos_anuais(inicio, fim):
            offset, pagina = 0, 0
            # 2. Paginação: pede páginas até ter recebido o 'total' anunciado pela API
            while True:
                params = {
                    "api_key": api_key,
                    "frequency": "daily",
                    "data[0]": "value",
                    "facets[series][]": SERIE_BRENT,
                    "start": ini.isoformat(),
                    "end": fim_bloco.isoformat(),
                    "sort[0][column]": "period",
                    "sort[0][direction]": "asc",
                    "offset": offset,
                    "length": TAMANHO_PAGINA,
                }
                dados = cliente.get_json(URL_EIA, params=params)

                # 3. Validação mínima da estrutura: lista em response -> data
                resposta = dados.get("response") if isinstance(dados, dict) else None
                if not isinstance(resposta, dict) or not isinstance(resposta.get("data"), list):
                    raise FormatoInesperado(f"[eia] resposta sem 'response.data' ({ini} a {fim_bloco})")
                registros = resposta["data"]
                total = int(resposta.get("total", 0))  # a EIA manda o total como texto

                # 4. Bronze = cru: uma página por arquivo
                arquivo = pasta_tmp / f"brent_{ini}_{fim_bloco}_p{pagina}.json"
                arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                log.info(
                    "[eia] %s a %s (página %d): %d de %d registros -> %s",
                    ini, fim_bloco, pagina, offset + len(registros), total, arquivo.name,
                )
                nomes.append(arquivo.name)

                offset += len(registros)
                pagina += 1
                if not registros or offset >= total:
                    break

    return [destino / nome for nome in nomes]
