# ADR-0001: Monorepo Decision

**Status:** Accepted
**Date:** 2025-10-15

### Decision

Use a monorepo (`kaizen/`) with clear bounded contexts: `engine/`, `portal/`, `infra/`, `docs/`.

### Rationale

- Faster iteration across contracts.
- Simpler CI.
- Shared standards and tooling.

### When to Split

If independent release cadence, access control differences, or external adopters require the engine standalone.

### Preparation

Maintain engine–portal API as versioned OpenAPI + DTOs so a future repo split is minimal.
