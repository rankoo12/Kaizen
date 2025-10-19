#!/usr/bin/env bash
set -euo pipefail

echo ">> (setup) Ensuring artifact directories"
mkdir -p reports logs snapshots

PYTEST_OPTS=${PYTEST_OPTS:-}

echo ">> (setup) Upgrading pip and installing requirements"
python -m pip install --upgrade pip --root-user-action=ignore
if [ -f requirements.txt ]; then
  python -m pip install --no-cache-dir -r requirements.txt --root-user-action=ignore
else
  echo ">> no requirements.txt, skipping"
fi
if [ -f requirements-dev.txt ]; then
  python -m pip install --no-cache-dir -r requirements-dev.txt --root-user-action=ignore || true
else
  echo ">> no requirements-dev.txt, skipping"
fi

# Playwright browsers are preinstalled in the base image at /ms-playwright
# and PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 is set via compose env.
# We skip install to avoid redundant downloads and apt usage.

echo ">> (lint) Running optional linters"
if command -v ruff >/dev/null 2>&1; then ruff . || true; else echo "ruff not installed (skipping)"; fi
if command -v mypy >/dev/null 2>&1; then mypy . || true; else echo "mypy not installed (skipping)"; fi
if command -v black >/dev/null 2>&1; then black --check . || true; else echo "black not installed (skipping)"; fi

echo ">> (tests) Unit"
pytest ${PYTEST_OPTS} -m "not contract and not integration and not e2e" --junitxml=reports/junit-unit.xml

echo ">> (tests) Contract"
pytest ${PYTEST_OPTS} -m "contract" --junitxml=reports/junit-contract.xml

echo ">> (tests) Integration"
pytest ${PYTEST_OPTS} -m "integration" --junitxml=reports/junit-int.xml

echo ">> (tests) E2E snapshot"
pytest ${PYTEST_OPTS} -m "e2e and snapshot" --junitxml=reports/junit-e2e-snapshot.xml || true

echo ">> (tests) E2E live"
pytest ${PYTEST_OPTS} -m "e2e and live" --junitxml=reports/junit-e2e-live.xml || true

echo ">> (tests) E2E all"
pytest ${PYTEST_OPTS} -m "e2e" --junitxml=reports/junit-e2e.xml

echo ">> CI complete. Artifacts: logs/ snapshots/ reports/"
