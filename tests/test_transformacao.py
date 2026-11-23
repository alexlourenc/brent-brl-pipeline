"""Testes da prata, da ouro e da gravação em Parquet (SQL real no DuckDB, dados de exemplo)."""
import duckdb
import pytest

from pipeline.load.writer import gravar_parquet_particionado
from pipeline.transform.duckdb_runner import construir_ouro, construir_prata, contar_bronze


@pytest.fixture
def con(bronze_exemplo, tmp_path):
    """Conexão com a prata e a ouro já construídas a partir da bronze de exemplo."""
    conexao = duckdb.connect()
    construir_prata(conexao, bronze_exemplo, tmp_path / "prata")
    construir_ouro(conexao)
    return conexao


def test_bronze_e_contada_antes_de_qualquer_limpeza(bronze_exemplo):
    assert contar_bronze(duckdb.connect(), bronze_exemplo) == {"bronze_ptax": 4, "bronze_brent": 4}


def test_prata_ptax_remove_duplicata_ficando_com_a_mais_recente(con):
    linhas = con.execute("SELECT data, ptax_venda FROM prata_ptax ORDER BY data").fetchall()
    assert [(str(d), v) for d, v in linhas] == [
        ("2024-01-02", 5.00),
        ("2024-01-03", 5.03),  # a duplicata mais recente
        ("2024-01-05", 5.05),
    ]


def test_prata_brent_converte_texto_em_numero_e_descarta_vazio(con):
    linhas = con.execute("SELECT data, brent_usd FROM prata_brent ORDER BY data").fetchall()
    assert [(str(d), v) for d, v in linhas] == [
        ("2024-01-02", 80.0),
        ("2024-01-03", 82.0),
        ("2024-01-04", 81.0),
    ]
    assert con.execute("SELECT typeof(brent_usd) FROM prata_brent LIMIT 1").fetchone()[0] == "DOUBLE"


def test_ouro_usa_a_ultima_ptax_no_dia_sem_cotacao(con):
    ptax, usada, preenchida, efeito_cambio = con.execute(
        "SELECT ptax_venda, data_ptax_usada, ptax_preenchida, efeito_cambio_brl "
        "FROM ouro_brent_brl WHERE data = DATE '2024-01-04'"
    ).fetchone()
    assert ptax == 5.03
    assert str(usada) == "2024-01-03"
    assert preenchida is True
    assert efeito_cambio == 0.0  # câmbio "parado" por construção no feriado


def test_ouro_converte_o_barril_para_reais(con):
    (brent_brl,) = con.execute(
        "SELECT brent_brl FROM ouro_brent_brl WHERE data = DATE '2024-01-03'"
    ).fetchone()
    assert brent_brl == pytest.approx(82.0 * 5.03, abs=0.0001)


def test_decomposicao_preco_mais_cambio_fecha_a_variacao(con):
    linhas = con.execute(
        "SELECT variacao_brl, efeito_preco_brl, efeito_cambio_brl "
        "FROM ouro_brent_brl WHERE variacao_brl IS NOT NULL"
    ).fetchall()
    assert len(linhas) == 2
    for variacao, preco, cambio in linhas:
        assert preco + cambio == pytest.approx(variacao, abs=0.001)


def test_saida_em_parquet_particionado_por_ano_e_mes(con, tmp_path):
    pasta = gravar_parquet_particionado(con, "ouro_brent_brl", tmp_path / "output" / "brent_brl")
    arquivos = list(pasta.rglob("*.parquet"))
    assert arquivos
    assert all(a.parent.name == "mes=1" and a.parent.parent.name == "ano=2024" for a in arquivos)

    caminho = (pasta / "**" / "*.parquet").as_posix()
    total = duckdb.sql(f"SELECT COUNT(*) FROM read_parquet('{caminho}', hive_partitioning = true)").fetchall()[0][0]
    assert total == 3
