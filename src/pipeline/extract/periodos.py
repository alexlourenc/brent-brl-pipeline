"""Divisão de períodos em blocos / Period splitting."""
from __future__ import annotations

from datetime import date, timedelta


def dividir_em_blocos_anuais(inicio: date, fim: date) -> list[tuple[date, date]]:
    """Quebra [inicio, fim] em blocos que não atravessam a virada do ano.

    Ex.: 2024-03-01 a 2025-02-10 -> [(2024-03-01, 2024-12-31), (2025-01-01, 2025-02-10)]
    """
    blocos: list[tuple[date, date]] = []
    atual = inicio
    while atual <= fim:
        fim_bloco = min(date(atual.year, 12, 31), fim)
        blocos.append((atual, fim_bloco))
        atual = fim_bloco + timedelta(days=1)
    return blocos