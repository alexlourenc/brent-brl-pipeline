"""Testes do cliente HTTP: retry, backoff, erro definitivo e rate limit (sem internet)."""
from unittest.mock import MagicMock

import pytest
import requests

from pipeline.extract import http_client
from pipeline.extract.http_client import ClienteHTTP, ErroHTTP


def resposta(status: int, json_: object = None, headers: dict | None = None) -> MagicMock:
    """Resposta HTTP falsa."""
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_
    r.headers = headers or {}
    r.text = "erro simulado"
    return r


@pytest.fixture
def esperas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Troca o time.sleep por um 'gravador': o teste roda na hora e sabemos quanto esperaria."""
    registro: list[float] = []
    monkeypatch.setattr(http_client.time, "sleep", registro.append)
    return registro


def cliente_com(*respostas: object) -> ClienteHTTP:
    sessao = MagicMock()
    sessao.get.side_effect = list(respostas)
    return ClienteHTTP("teste", intervalo_min_s=0, max_tentativas=4, backoff_base_s=1.0, sessao=sessao)


def test_erro_temporario_e_retentado_ate_dar_certo(esperas):
    cliente = cliente_com(resposta(503), requests.Timeout("lento"), resposta(200, {"ok": True}))
    assert cliente.get_json("https://api.exemplo") == {"ok": True}
    assert cliente.stats.chamadas == 3
    assert cliente.stats.retentativas == 2
    assert esperas == [1.0, 2.0]  # backoff exponencial


def test_erro_definitivo_falha_na_hora_sem_retentar(esperas):
    cliente = cliente_com(resposta(404))
    with pytest.raises(ErroHTTP, match="404"):
        cliente.get_json("https://api.exemplo")
    assert cliente.stats.chamadas == 1
    assert esperas == []


def test_desiste_depois_do_maximo_de_tentativas(esperas):
    cliente = cliente_com(*[resposta(500)] * 4)
    with pytest.raises(ErroHTTP, match="4 tentativas"):
        cliente.get_json("https://api.exemplo")
    assert cliente.stats.chamadas == 4
    assert cliente.stats.falhas == 1
    assert esperas == [1.0, 2.0, 4.0]


def test_obedece_retry_after_do_servidor(esperas):
    cliente = cliente_com(resposta(429, headers={"Retry-After": "7"}), resposta(200, []))
    cliente.get_json("https://api.exemplo")
    assert esperas == [7.0]


def test_erro_de_conexao_nao_vaza_a_url_com_a_chave(esperas, caplog):
    erro = requests.ConnectionError("falhou https://api.exemplo?api_key=SEGREDO123")
    cliente = cliente_com(erro, resposta(200, {}))
    cliente.get_json("https://api.exemplo", params={"api_key": "SEGREDO123"})
    assert "SEGREDO123" not in caplog.text


def test_rate_limit_espera_o_intervalo_minimo(monkeypatch, esperas):
    relogio = iter([100.0, 100.3, 101.0])  # 1a chamada em 100s; 2a chega em 100,3s
    monkeypatch.setattr(http_client.time, "monotonic", lambda: next(relogio))
    limitador = http_client.RateLimiter(intervalo_min_s=1.0)
    limitador.aguardar()
    limitador.aguardar()
    assert esperas == [pytest.approx(0.7)]
