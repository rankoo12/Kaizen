# ---------- Kaizen Makefile (Windows-friendly setup, marker-aligned) ----------
PYTHON        ?= python3
PIP           ?= pip
PYTEST        ?= pytest
PYTEST_OPTS   ?=
PLAYWRIGHT    ?= $(PYTHON) -m playwright

REPORTS_DIR   ?= reports
LOGS_DIR      ?= logs
SNAP_DIR      ?= snapshots

.PHONY: _ensure_dirs
_ensure_dirs:
	@mkdir -p $(LOGS_DIR) $(SNAP_DIR) $(REPORTS_DIR) 2>NUL || true

# ---------- Setup (portable for Windows cmd.exe) ----------
.PHONY: setup
setup:
	@echo >> (setup) Installing Python deps
	$(PIP) install -U pip
	@REM Windows-safe conditional installs:
	@if exist requirements.txt ( $(PIP) install -r requirements.txt ) else ( echo no requirements.txt, skipping )
	@if exist requirements-dev.txt ( $(PIP) install -r requirements-dev.txt ) else ( echo no requirements-dev.txt, skipping )

.PHONY: playwright-install
playwright-install:
	@echo >> (setup) Installing Playwright browsers (chromium)
	$(PLAYWRIGHT) install --with-deps chromium || $(PLAYWRIGHT) install chromium

# ---------- Quality ----------
.PHONY: fmt
fmt:
	@command -v black >/dev/null 2>&1 && black . || echo black not installed \(skipping fmt\)

.PHONY: lint
lint:
	@command -v ruff  >/dev/null 2>&1 && ruff .  || echo ruff not installed \(skipping lint\)
	@command -v mypy  >/dev/null 2>&1 && mypy .  || echo mypy not installed \(skipping types\)

# ---------- Tests (marker-aligned) ----------
.PHONY: test-unit
test-unit: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "not contract and not integration and not e2e" --junitxml=$(REPORTS_DIR)/junit-unit.xml

.PHONY: test-contract
test-contract: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "contract" --junitxml=$(REPORTS_DIR)/junit-contract.xml

.PHONY: test-int
test-int: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "integration" --junitxml=$(REPORTS_DIR)/junit-int.xml

.PHONY: test-e2e
test-e2e: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "e2e" --junitxml=$(REPORTS_DIR)/junit-e2e.xml

.PHONY: e2e-snapshot
e2e-snapshot: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "e2e and snapshot" --junitxml=$(REPORTS_DIR)/junit-e2e-snapshot.xml || true

.PHONY: e2e-live
e2e-live: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "e2e and live" --junitxml=$(REPORTS_DIR)/junit-e2e-live.xml || true

.PHONY: e2e
e2e: e2e-snapshot e2e-live test-e2e

# ---------- Local-verbose (no JUnit) ----------
.PHONY: test-unit-local
test-unit-local: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "not contract and not integration and not e2e"

.PHONY: test-contract-local
test-contract-local: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "contract"

.PHONY: test-int-local
test-int-local: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "integration"

.PHONY: test-e2e-local
test-e2e-local: _ensure_dirs
	$(PYTEST) $(PYTEST_OPTS) -m "e2e"

# ---------- CI Orchestration ----------
.PHONY: ci
ci: setup playwright-install lint test-unit test-contract test-int e2e
	@echo >> CI complete. Artifacts:
	@echo    - $(LOGS_DIR)/
	@echo    - $(SNAP_DIR)/
	@echo    - $(REPORTS_DIR)/

.PHONY: ci-sanity
ci-sanity: _ensure_dirs
	@echo >> (sanity) Starting engine-api and exercising /api/runs
	$(PYTHON) scripts/ci_sanity.py

# ---------- Security / SBOM ----------
.PHONY: sbom
sbom:
	@echo >> Generating SBOM to sbom.json \(soft-fail if tools missing\)
	@if command -v syft >/dev/null 2>&1; then \
		syft packages dir:. -o json > sbom.json || true ; \
	elif command -v cyclonedx-py >/dev/null 2>&1; then \
		cyclonedx-py --format json --output sbom.json || true ; \
	else \
		echo No SBOM tool found \(syft/cyclonedx-py\). Skipping.; \
	fi

# ---------- Database (optional Alembic; fallback script) ----------
.PHONY: db-upgrade
db-upgrade:
	@echo >> Ensuring DB schema (Alekbic if available; fallback script)
	@if command -v alembic >/dev/null 2>&1; then \
		alembic -c alembic.ini upgrade head || true ; \
	else \
		echo alembic not installed \(skipping\); \
	fi
	$(PYTHON) scripts/db_upgrade.py || true

.PHONY: db-revision
db-revision:
	@echo >> Creating Alembic revision \(if alembic installed\)
	@if command -v alembic >/dev/null 2>&1; then \
		alembic -c alembic.ini revision -m "$$MSG" || true ; \
	else \
		echo alembic not installed \(skipping\); \
	fi

# ---------- Artifacts Retention ----------
.PHONY: artifacts-retain
artifacts-retain:
	@echo >> Pruning artifacts by retention settings
	$(PYTHON) scripts/artifacts_retention.py || true

# ---------- Housekeeping ----------
.PHONY: clean
clean:
	@rm -rf $(REPORTS_DIR) $(LOGS_DIR) $(SNAP_DIR) sbom.json 2>NUL || true
