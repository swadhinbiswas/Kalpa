# Contributing to Kalpa

## Development Setup

```bash
git clone https://github.com/swadhinbiswas/kalpa
cd kalpa

# Create virtual environment
uv venv
source .venv/bin/activate

# Install with dev dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Code Quality

- **Linting**: `ruff check kalpa/ tests/`
- **Formatting**: `ruff format kalpa/ tests/`
- **Type checking**: `mypy kalpa/ --ignore-missing-imports`
- **Security**: `bandit -r kalpa/ -x kalpa/tests -ll`
- **Tests**: `pytest tests/ -v --cov=kalpa`

All checks must pass before merging.

## Pull Request Process

1. Open an issue for feature discussion before implementing
2. Fork the repo and create a branch from `main`
3. Write tests for new functionality
4. Ensure all CI checks pass
5. Update CHANGELOG.md with your changes
6. Submit the PR with a clear description

## Commit Messages

Follow conventional commits format:

- `feat:` — new feature
- `fix:` — bug fix
- `refactor:` — code change without feature/fix
- `test:` — test additions/changes
- `docs:` — documentation
- `ci:` — CI/CD changes

## Code Style

- Target Python 3.12+
- Use type hints for all function signatures
- Prefer dataclasses over dictionaries for structured data
- Keep functions focused and small
- Write docstrings for public APIs
- No cloud, no network, no telemetry
