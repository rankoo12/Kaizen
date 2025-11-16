# Kaizen Helm Chart (dev)

This chart deploys the Kaizen Engine API, Runner, and Portal with optional Postgres and OTEL Collector for a local/dev cluster (kind/Minikube).

Quickstart (kind)

- Create namespace:
  kubectl create ns kaizen

- Render and apply:
  helm template kaizen ./helm/kaizen -n kaizen | kubectl apply -n kaizen -f -

- Port-forward:
  kubectl -n kaizen port-forward svc/RELEASE-NAME-kaizen-engine-api 8080:8080
  kubectl -n kaizen port-forward svc/RELEASE-NAME-kaizen-portal 8081:8080

Values Highlights
- engineApi.image / engineRunner.image: set to your built image (e.g., kaizen-engine:dev)
- postgres.enabled: true for dev DB (default)
- otelCollector.enabled: true to expose Prometheus metrics (port 9464 inside pod)
- hpa.runner.enabled: enable HorizontalPodAutoscaler for engine-runner

Security
- No secrets are committed. Provide admin secrets via your own Secret and reference them through env or values overrides.

Notes
- This is a dev chart. For production, harden security, use proper Secrets, and configure pull secrets and ingress.
