# Jenkins (Docker Compose)

This is a persistent Jenkins setup running on **http://localhost:8081** (port 8080 is used by the API).
Agent port 50000 is open for inbound agents (kept for defaults).

## Quick start

```bash
cd infra/jenkins
docker compose build
docker compose up -d
```
