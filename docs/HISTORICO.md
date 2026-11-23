# Histórico de alterações

Formato: [versão] – data – o que mudou. Versões seguem o padrão MAJOR.MINOR.PATCH.

## [1.0.0] – 2026-11-22

Primeira versão completa, entregue no Desafio Python FT03 – Projeto 1.

### Extração (bronze)
- Cliente HTTP com rate limit, retentativa com backoff exponencial, `Retry-After` e timeout; erros definitivos (4xx) sem retentativa.
- Extração da PTAX (BCB, Olinda) e do Brent (EIA v2, série RBRTE), em blocos anuais; paginação na EIA.
- Validação da estrutura do JSON antes de gravar.
- Troca atômica da bronze: a extração anterior só é substituída se todos os blocos derem certo.

### Transformação (prata e ouro)
- Prata em SQL (DuckDB): desaninhamento com `UNNEST`, tipos, descarte de nulos e deduplicação com `ROW_NUMBER`.
- Ouro: `ASOF JOIN` (última PTAX até a data), Brent em reais, variação, decomposição em efeito preço e efeito câmbio, média móvel de 7 pregões.
- Saída em Parquet com Snappy, particionada por ano e mês.

### Qualidade
- 19 checks (schema, null ratio, unicidade, intervalo, regra de negócio, anomalias), em dois níveis: bloqueante e alerta.
- Relatório `quality_report.json` com status geral, tempos, estatísticas da extração, volumes por camada e checks.
- Dado reprovado não chega à `output/`; o relatório da falha vai para `data/relatorios/`.

### Operação
- Orquestração em `python -m pipeline`, com código de saída 0/1 e opção `--sem-extracao`.
- Parâmetros HTTP configuráveis pelo `.env`.
- `run.sh` para execução ponta a ponta (ambiente, dependências, testes e pipeline).
- 38 testes automáticos com pytest, sem internet.

### Correções durante o desenvolvimento
- Pacotes `load` e `quality` sem `__init__.py` (seriam ignorados numa instalação sem `-e`).
- Log de check de alerta mostrava "FALHOU" em vez de "ALERTA".
- Regra de nulos da `variacao_brl` dependia do tamanho do período; passou a aceitar exatamente a 1ª linha.
