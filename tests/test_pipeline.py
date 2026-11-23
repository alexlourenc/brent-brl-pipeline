"""Testes do pipeline inteiro (__main__.executar): código de saída e proteção da output/."""
import json

from conftest import brent, gravar_json

from pipeline import __main__ as maestro
from pipeline.extract.http_client import ErroHTTP


def test_pipeline_aprovado_grava_a_saida_e_devolve_0(cfg_teste):
    assert maestro.executar(cfg_teste, extrair=False) == 0

    relatorio = json.loads((cfg_teste.dir_output / "quality_report.json").read_text(encoding="utf-8"))
    assert relatorio["status_geral"] != "reprovado"
    assert relatorio["volumes"] == {
        "bronze_ptax": 4, "bronze_brent": 4,
        "prata_ptax": 3, "prata_brent": 3,
        "ouro_brent_brl": 3,
    }
    assert list((cfg_teste.dir_output / "brent_brl").rglob("*.parquet"))


def test_pipeline_reprovado_nao_toca_na_output_e_devolve_1(cfg_teste, bronze_exemplo):
    # Sabota a bronze: um Brent de 950 dólares (fora do intervalo plausível)
    gravar_json(bronze_exemplo / "brent" / "brent_teste_p0.json", {"response": {"total": "2", "data": [
        brent("2024-01-02", "80.0"),
        brent("2024-01-03", "950.0"),
    ]}})

    assert maestro.executar(cfg_teste, extrair=False) == 1
    assert not cfg_teste.dir_output.exists()  # nada foi gravado na output/
    assert len(list(cfg_teste.dir_relatorios.glob("quality_report_reprovado_*.json"))) == 1


def test_falha_na_extracao_devolve_1_sem_processar_nada(cfg_teste, monkeypatch):
    def api_fora_do_ar(*args, **kwargs):
        raise ErroHTTP("[bcb] falhou após 4 tentativas (HTTP 503)")

    monkeypatch.setattr(maestro, "extrair_ptax", api_fora_do_ar)
    assert maestro.executar(cfg_teste, extrair=True) == 1
    assert not cfg_teste.dir_output.exists()
