FROM python:3.11-slim AS base
RUN useradd -m app && apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -U pip && pip wheel -w /wheels .
COPY . /app
RUN pip install --no-cache-dir -r <(python - <<'PY'\nprint()\nPY) || true
USER app
CMD ["python", "-m", "engine.api.cli"]
