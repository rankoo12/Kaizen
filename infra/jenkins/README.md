# Jenkins (Docker Compose)

This is a persistent Jenkins setup running on **http://localhost:8090** (port 8081 is used by the Portal, 8080 by Engine API).
Agent port 50000 is open for inbound agents (kept for defaults).

## Quick start

```bash
cd infra/jenkins
docker compose build
docker compose up -d

# Open Jenkins UI
# http://localhost:8090
```
