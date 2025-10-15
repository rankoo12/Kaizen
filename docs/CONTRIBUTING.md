# Contributing Guidelines

## Commit Style

Use **Conventional Commits**:

- `feat:` new feature
- `fix:` bug fix
- `refactor:` non-breaking internal changes
- `docs:` documentation updates
- `test:` testing improvements
- `chore:` CI, tooling, dependencies

## Workflow

1. Create a short-lived branch (`feat/…` or `fix/…`).
2. Run `pre-commit install` before committing.
3. Validate tests with `make test`.
4. Push and open a PR — CI must pass before merge.

## Code Standards

- Follow SOLID and separation-of-concerns.
- Type hints required for all functions.
- Avoid hard-coded paths, credentials, or network endpoints.

## Review

Each PR must pass:

- Lint (`make lint`)
- Typecheck (`mypy` or equivalent)
- Security (`gitleaks`, `trivy`)
- Unit tests (100% pass rate)
