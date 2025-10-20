# Jenkins CI for Kaizen

This document shows how to run Kaizen CI on Jenkins using a Docker agent and a thin pipeline that delegates all logic to `scripts/ci.sh`.

## Prerequisites

- **Jenkins** 2.4x+
- Plugins:
  - **Pipeline** (Declarative)
  - **Docker Pipeline** (to use `agent { docker { ... } }`)
  - **JUnit** (test reporting)
- Jenkins node with:
  - **Docker** daemon access (the Jenkins agent must be able to run Docker)
- Repository access (GitHub App integration or Personal Access Token)

> **Why Docker agent?**
> Builds run inside a reproducible container (same as local `docker compose`), reducing “works on my machine” issues.

## Job Setup (Multibranch recommended)

1. In Jenkins, create **New Item → Multibranch Pipeline**.
2. Configure **Branch Sources** to your Git repository.
3. In **Build Configuration**, ensure it uses **Jenkinsfile** at `infra/Jenkinsfile`.
4. Save. Jenkins will scan branches/PRs and build them automatically.

### Webhook (GitHub)

1. In GitHub repo: **Settings → Webhooks → Add webhook**
   - Payload URL: `https://<your-jenkins>/github-webhook/`
   - Content type: `application/json`
   - Events: “Just the push event” (or add PR events too)
2. Save. Push to your repo → Jenkins triggers automatically.

## Environment

The Jenkinsfile sets:

- `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` (browsers are preinstalled in the Docker image)
- `PYTEST_OPTS` (optional flags for pytest)
- Artifact dirs: `reports/`, `logs/`, `snapshots/`

> **Tip:** You can override `PYTEST_OPTS` in the job configuration (e.g., `-q` or `-vv`).

## Caching

The Docker agent mounts `~/.cache/pip` to speed up Python deps installation across builds.

> **Why?**
> **pip cache** reuses downloaded wheels, cutting install time without changing your image.

## Artifacts & Reports

- **JUnit**: Jenkins picks up `reports/junit-*.xml` for test results.
- **Artifacts**: Jenkins archives `reports/**`, `logs/**`, `snapshots/**` after every build (success or fail).

Set retention in **Job → Configure → Build Discarder** (e.g., keep last 50 builds).

## Local Parity

The pipeline runs `./scripts/ci.sh` — the same entrypoint you use locally.
To reproduce a CI failure locally:

```bash
docker compose run --rm kaizen-engine-runner bash -lc './scripts/ci.sh'
```
