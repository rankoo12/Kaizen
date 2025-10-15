FROM python:3.11-slim
RUN useradd -m app
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -U pip && pip wheel -w /wheels .
COPY . /app
USER app
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
