# Security Policy

- **Secrets:** Never commit real `.env` values. Only `.env.example` is versioned.
- **Containers:** Run as non-root; read-only FS where possible.
- **Network:** LLM runs locally (Ollama). Disable outbound calls by default.
- **Validation:** Every LLM plan and API payload must pass JSON Schema validation.
- **Logging:** Structured JSON logs, redact credentials.
- **Dependencies:** Use lockfiles, SBOMs, and regular Trivy/Grype scans.
- **CI:** Jenkins runs security stage automatically (`make sbom` + `gitleaks`).
## Live Execution Policy

- Live `open()` is restricted by `ALLOWED_URL_SCHEMES` (default: `data:` and `about:blank`).
- To broaden in a controlled way, set `KAIZEN_ALLOWED_URL_SCHEMES` to a comma-separated list (e.g., `data:,about:blank,file:`).

## Execution Path Toggle

- The engine defaults to the orchestrator path for live runs.
- Override with `KAIZEN_EXECUTION_PATH=legacy` to revert to the legacy runner.
