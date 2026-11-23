#!/usr/bin/env bash
# =====================================================================
# Executa o pipeline ponta a ponta / Runs the pipeline end to end
#
# Uso / Usage:
#   ./run.sh                  -> pipeline completo (extração real)
#   ./run.sh --sem-extracao   -> reprocessa a partir da bronze existente
#
# No Windows, rode pelo Git Bash.
# =====================================================================
set -euo pipefail          # para no primeiro erro; variável indefinida = erro
cd "$(dirname "$0")"       # roda sempre a partir da raiz do projeto

# 1. Python: 'python' no Windows, 'python3' no Linux/Mac
if python --version >/dev/null 2>&1; then PY=python; else PY=python3; fi

# 2. Ambiente virtual (criado na primeira execução)
if [ ! -d ".venv" ]; then
    echo ">> Criando o ambiente virtual .venv"
    "$PY" -m venv .venv
fi
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate      # Windows (Git Bash)
else
    source .venv/bin/activate          # Linux / Mac
fi

# 3. Dependências com versões fixadas
echo ">> Instalando dependências (requirements.txt)"
python -m pip install --quiet --disable-pip-version-check -r requirements.txt

# 4. Credenciais: sem .env não há chave da EIA
if [ ! -f ".env" ]; then
    echo "ERRO: arquivo .env não encontrado." >&2
    echo "      Rode: cp .env.example .env   e preencha a EIA_API_KEY." >&2
    exit 1
fi

# 5. Testes automáticos (rápidos e sem internet): se algum falhar, o script para aqui
echo ">> Rodando os testes (pytest)"
python -m pytest -q

# 6. O pipeline (o código de saída dele vira o código de saída do script)
echo ">> Executando o pipeline"
python -m pipeline "$@"
