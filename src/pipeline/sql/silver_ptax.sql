-- =====================================================================
-- Camada prata: PTAX (BCB) / Silver layer: PTAX
-- Bronze (JSON aninhado) -> tabela limpa, 1 linha por dia
-- =====================================================================

WITH expandido AS (
    -- Etapa 1. Desaninhamento: uma linha por cotação
    SELECT UNNEST(value, recursive := true)
    FROM read_json('{bronze}/ptax/*.json')
),

tipado AS (
    -- Etapa 2. Padronização de tipos e datas
    SELECT
        CAST(dataHoraCotacao AS DATE)      AS data,
        CAST(dataHoraCotacao AS TIMESTAMP) AS data_hora_cotacao,
        CAST(cotacaoCompra AS DOUBLE)      AS ptax_compra,
        CAST(cotacaoVenda AS DOUBLE)       AS ptax_venda
    FROM expandido
),

numerado AS (
    -- Etapa 3. Deduplicação (parte 1): numera os registros de cada data,
    -- do mais recente para o mais antigo
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY data
            ORDER BY data_hora_cotacao DESC
        ) AS ordem
    FROM tipado
)

-- Etapa 4. Deduplicação (parte 2) + nulos: fica só o nº 1 de cada data,
-- e descarta cotações sem valor
SELECT
    data,
    ptax_compra,
    ptax_venda,
    data_hora_cotacao
FROM numerado
WHERE ordem = 1
  AND ptax_compra IS NOT NULL
  AND ptax_venda IS NOT NULL
ORDER BY data;