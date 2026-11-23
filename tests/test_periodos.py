"""Testes do fatiamento do período em blocos anuais."""
from datetime import date

from pipeline.extract.periodos import dividir_em_blocos_anuais


def test_periodo_de_varios_anos_vira_um_bloco_por_ano():
    blocos = dividir_em_blocos_anuais(date(2024, 1, 1), date(2026, 11, 22))
    assert blocos == [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 11, 22)),
    ]


def test_periodo_dentro_de_um_ano_vira_um_bloco_so():
    assert dividir_em_blocos_anuais(date(2026, 3, 10), date(2026, 5, 20)) == [
        (date(2026, 3, 10), date(2026, 5, 20))
    ]


def test_blocos_nao_se_sobrepoem_nem_deixam_buraco():
    blocos = dividir_em_blocos_anuais(date(2023, 6, 15), date(2025, 2, 1))
    for (_, fim_anterior), (inicio_seguinte, _) in zip(blocos, blocos[1:]):
        assert (inicio_seguinte - fim_anterior).days == 1
