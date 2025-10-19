# engine/Dockerfile — Kaizen Engine app image (Playwright-ready, non-root)

# 1) Use Microsoft’s Playwright Python image so browsers & OS deps are preinstalled
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy AS base

# Security hardening and non-root user
# (the image already has a non-root user 'pwuser', but we keep an explicit app user)
RUN useradd -m -u 10001 appuser

WORKDIR /app

# Environment for deterministic installs and faster pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# 2) Install Python deps
# Prefer pinned requirements; fall back to pyproject if needed later
COPY requirements.txt /app/requirements.txt
RUN python -m pip install -U pip && \
    pip install -r /app/requirements.txt

# 3) Copy app code last (to leverage layer caching)
COPY . /app

# 4) Switch to non-root
USER appuser

# 5) Default command: FastAPI server (same as your compose command)
# If you want CLI by default, change this to: ["python","-m","engine.api.cli"]
EXPOSE 8080
CMD ["uvicorn", "engine.api.server:create_app", "--host", "0.0.0.0", "--port", "8080"]
