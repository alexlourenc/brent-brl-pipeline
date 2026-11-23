"""
Gravação segura na bronze / Safe writes to the bronze layer.

Troca atômica: a extração grava numa pasta temporária e, só se TUDO der certo,
essa pasta substitui a anterior. Se algo falhar no meio, a bronze anterior
continua intacta e a pasta temporária é descartada.
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


@contextmanager
def escrita_atomica(destino: Path) -> Iterator[Path]:
    """Uso: `with escrita_atomica(pasta) as tmp:` -> grave tudo em `tmp`."""
    tmp = destino.with_name(destino.name + "_tmp")
    antigo = destino.with_name(destino.name + "_antigo")

    # 1. Começa sempre com uma pasta temporária limpa
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    try:
        yield tmp  # 2. Aqui roda o código de dentro do `with` (a extração)
    except BaseException:
        # 3. Falhou: descarta o temporário e deixa a bronze anterior intacta
        shutil.rmtree(tmp, ignore_errors=True)
        log.error("[bronze] falha na extração; %s anterior mantida", destino.name)
        raise

    # 4. Deu tudo certo: troca a pasta antiga pela nova
    if antigo.exists():
        shutil.rmtree(antigo)
    if destino.exists():
        destino.rename(antigo)
    tmp.rename(destino)
    shutil.rmtree(antigo, ignore_errors=True)
