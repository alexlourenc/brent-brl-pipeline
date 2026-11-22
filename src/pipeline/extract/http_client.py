"""
Cliente HTTP resiliente / Resilient HTTP client.

Responsável por TODA chamada externa do pipeline:
- rate limit: intervalo mínimo entre chamadas à mesma API;
- retentativas com backoff exponencial para erros temporários;
- erro imediato (sem retentar) para erros definitivos, como chave inválida;
- estatísticas de chamadas, usadas depois no relatório de qualidade.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

# 1. Erros TEMPORÁRIOS: vale a pena tentar de novo
#    429 = muitas requisições | 5xx = problema no servidor
STATUS_RETENTAVEIS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class ErroHTTP(Exception):
    """Falha definitiva: erro não retentável ou retentativas esgotadas."""


class RateLimiter:
    """Garante um intervalo mínimo (em segundos) entre duas chamadas."""

    def __init__(self, intervalo_min_s: float) -> None:
        self.intervalo_min_s = intervalo_min_s
        self._ultima: float | None = None

    def aguardar(self) -> None:
        # 2. monotonic(): relógio que nunca volta atrás (imune a ajuste de hora)
        if self._ultima is not None:
            falta = self.intervalo_min_s - (time.monotonic() - self._ultima)
            if falta > 0:
                log.debug("rate limit: aguardando %.2fs", falta)
                time.sleep(falta)
        self._ultima = time.monotonic()


@dataclass
class EstatisticasHTTP:
    """Contadores que vão para o relatório de execução."""

    chamadas: int = 0
    retentativas: int = 0
    falhas: int = 0


class ClienteHTTP:
    """GET de JSON com rate limit, timeout e retentativas."""

    def __init__(
        self,
        nome: str,
        intervalo_min_s: float = 1.0,
        max_tentativas: int = 4,
        backoff_base_s: float = 1.0,
        timeout_s: float = 30.0,
        sessao: requests.Session | None = None,
    ) -> None:
        self.nome = nome
        self.max_tentativas = max_tentativas
        self.backoff_base_s = backoff_base_s
        self.timeout_s = timeout_s
        self.stats = EstatisticasHTTP()
        self._limiter = RateLimiter(intervalo_min_s)
        # 3. Session reaproveita a conexão entre chamadas (mais rápido)
        self._sessao = sessao or requests.Session()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Faz GET e devolve o JSON. Levanta ErroHTTP se não conseguir."""
        motivo = "desconhecido"
        for tentativa in range(1, self.max_tentativas + 1):
            self._limiter.aguardar()
            self.stats.chamadas += 1
            retry_after: str | None = None

            try:
                resp = self._sessao.get(url, params=params, timeout=self.timeout_s)
            except (requests.ConnectionError, requests.Timeout) as exc:
                # 4. Só o NOME do erro: a mensagem completa traz a URL com a chave
                motivo = type(exc).__name__
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        self.stats.falhas += 1
                        raise ErroHTTP(f"[{self.nome}] resposta não é um JSON válido") from exc

                # 5. Erro definitivo (400, 401, 403, 404...): retentar não resolve
                if resp.status_code not in STATUS_RETENTAVEIS:
                    self.stats.falhas += 1
                    raise ErroHTTP(
                        f"[{self.nome}] HTTP {resp.status_code} (erro definitivo, sem retentativa): "
                        f"{resp.text[:200]}"
                    )
                motivo = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After")

            # 6. Última tentativa: desiste
            if tentativa == self.max_tentativas:
                break

            espera = self._calcular_espera(tentativa, retry_after)
            self.stats.retentativas += 1
            log.warning(
                "[%s] %s - tentativa %d/%d falhou; nova tentativa em %.1fs",
                self.nome, motivo, tentativa, self.max_tentativas, espera,
            )
            time.sleep(espera)

        self.stats.falhas += 1
        raise ErroHTTP(f"[{self.nome}] falhou após {self.max_tentativas} tentativas ({motivo})")

    def _calcular_espera(self, tentativa: int, retry_after: str | None) -> float:
        """Backoff exponencial: 1s, 2s, 4s... ou o que o servidor pedir."""
        # 7. Se o servidor disse quanto esperar (Retry-After), obedece
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        return self.backoff_base_s * 2 ** (tentativa - 1)