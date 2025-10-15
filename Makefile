.PHONY: dev stop test e2e fmt lint sbom clean

dev:
\tdocker compose -f infra/docker-compose.yml up -d --build

stop:
\tdocker compose -f infra/docker-compose.yml down

test:
\tpytest -q

e2e:
\t# placeholder; will run a minimal test after M1 wiring
\tpytest -q -m e2e || true

fmt:
\truff --fix . || true
\tblack .

lint:
\truff .
\tmypy engine portal/backend || true

sbom:
\tsyft dir:. -o json > sbom.json || true

clean:
\trm -rf .pytest_cache **/__pycache__ artifacts/ || true

playwright-install:
	python -m playwright install --with-deps chromium
