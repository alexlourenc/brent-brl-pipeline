-- =====================================================================
-- Camada prata: Brent (EIA) / Silver layer: Brent
-- Bronze (JSON aninhado) -> tabela limpa, 1 linha por dia
-- =====================================================================

WITH expandido AS (
    -- Etapa 1. Desaninhamento: a lista fica DOIS níveis abaixo (response -> data)
    SELECT UNNEST(response.data, recursive := true)
    FROM read_json('{bronze}/brent/*.json')
),

tipado AS (
    -- Etapa 2. Padronização de tipos e datas
    --   period: texto 'AAAA-MM-DD' -> DATE
    --   value : texto '77.18'      -> DOUBLE (TRY_CAST: se não converter, vira NULL)
    SELECT
        CAST(period AS DATE)       AS data,
        TRY_CAST(value AS DOUBLE)  AS brent_usd,
        series                     AS serie,
        units                      AS unidade
    FROM expandido
    WHERE series = 'RBRTE'          -- garante que é só a série do Brent
),

numerado AS (
    -- Etapa 3. Deduplicação: se a mesma data vier repetida,
    -- prefere o registro COM valor (NULLs por último)
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY data
            ORDER BY brent_usd DESC NULLS LAST
        ) AS ordem
    FROM tipado
)

-- Etapa 4. Fica 1 por data e descarta preço nulo
SELECT
    data,
    brent_usd,
    serie,
    unidade
FROM numerado
WHERE ordem = 1
  AND brent_usd IS NOT NULL
ORDER BY data;