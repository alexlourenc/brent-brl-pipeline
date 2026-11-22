-- =====================================================================
-- Camada ouro: Brent em reais / Gold layer: Brent in BRL
-- 1 linha por dia de negociação do Brent
-- Entrada: tabelas prata_brent e prata_ptax (mesma conexão DuckDB)
-- =====================================================================

WITH cruzado AS (
    -- Etapa 1. Cruzamento (JOIN): cada dia de Brent recebe a PTAX
    -- mais recente até aquela data; feriados BR ficam marcados
    SELECT
        b.data,
        b.brent_usd,
        p.ptax_compra,
        p.ptax_venda,
        p.data           AS data_ptax_usada,
        p.data <> b.data AS ptax_preenchida
    FROM prata_brent AS b
    ASOF LEFT JOIN prata_ptax AS p
        ON b.data >= p.data
    WHERE p.ptax_venda IS NOT NULL
),

convertido AS (
    -- Etapa 2. Enriquecimento: o barril em reais
    SELECT
        *,
        brent_usd * ptax_venda AS brent_brl
    FROM cruzado
),

metricas AS (
    -- Etapa 3. Enriquecimento: métricas olhando para o dia anterior (LAG)
    SELECT
        *,
        ptax_venda - ptax_compra                                      AS spread_ptax,
        brent_brl - LAG(brent_brl) OVER w                             AS variacao_brl,
        100 * (brent_brl / LAG(brent_brl) OVER w - 1)                 AS variacao_brl_pct,
        (brent_usd - LAG(brent_usd) OVER w) * LAG(ptax_venda) OVER w  AS efeito_preco_brl,
        brent_usd * (ptax_venda - LAG(ptax_venda) OVER w)             AS efeito_cambio_brl,
        AVG(brent_brl) OVER (
            ORDER BY data ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                                             AS media_movel_7_pregoes_brl
    FROM convertido
    WINDOW w AS (ORDER BY data)
)

-- Etapa 4. Colunas finais (arredondadas em 4 casas) + ano/mês para o particionamento
SELECT
    data,
    YEAR(data)                          AS ano,
    MONTH(data)                         AS mes,
    brent_usd,
    ptax_compra,
    ptax_venda,
    ROUND(spread_ptax, 4)               AS spread_ptax,
    ROUND(brent_brl, 4)                 AS brent_brl,
    ROUND(variacao_brl, 4)              AS variacao_brl,
    ROUND(variacao_brl_pct, 4)          AS variacao_brl_pct,
    ROUND(efeito_preco_brl, 4)          AS efeito_preco_brl,
    ROUND(efeito_cambio_brl, 4)         AS efeito_cambio_brl,
    ROUND(media_movel_7_pregoes_brl, 4) AS media_movel_7_pregoes_brl,
    ptax_preenchida,
    data_ptax_usada
FROM metricas
ORDER BY data;
