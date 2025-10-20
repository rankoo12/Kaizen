#!/usr/bin/env bash
set -euo pipefail

echo ">> (setup) apt & make"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends make ca-certificates
rm -rf /var/lib/apt/lists/*

echo ">> (setup) Python deps"
python -m pip install -U pip
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

echo ">> (setup) Playwright runtime & browsers"
python -m pip install -U playwright || true
python -m playwright install-deps || true
python -m playwright install chromium

echo ">> (ensure artifact dirs)"
mkdir -p reports logs snapshots

echo ">> (verify) make/pytest versions"
make --version || { echo "make missing"; exit 127; }
pytest --version || true

echo ">> (run) make ci"
make ci

echo ">> done"
