# Contributing to dga-sentinel

Thank you for your interest in contributing. This is a volunteer/community project — response time
is best-effort. All contributions are welcome: bug fixes, features, documentation, and tests.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Please read it before
participating.

## Development Setup

### 1. Clone and bootstrap

```bash
git clone https://github.com/yyunlei/dga-sentinel.git
cd dga-sentinel
./setup.sh
```

`setup.sh` will:
- Verify prerequisites (Docker, Python 3.13+, Node 20+)
- Copy `.env.example` to `.env`
- Create `./data/` subdirectories for Docker volumes
- Install Python dependencies via `uv sync` (falls back to pip + venv)
- Optionally install frontend npm dependencies

### 2. Configure `.env`

At minimum, set:

```
DEEPSEEK_API_KEY=<your-key>    # required for the agent explain feature
JWT_SECRET=<random-secret>     # change from default before any network exposure
```

### 3. Start the stack

```bash
scripts/platform.sh up
```

For iterative backend development you can start only the infrastructure and run the gateway locally:

```bash
docker compose up -d kafka elasticsearch redis postgres
uv run uvicorn gateway.main:app --reload --port 8000
```

### 4. Frontend development

```bash
cd frontend
npm install
npm run dev          # Vite dev server at http://localhost:5173
```

To test your frontend changes against the running Docker stack, hot-deploy into the container:

```bash
cd frontend && npm run build
docker cp dist/. dga-frontend:/usr/share/nginx/html
```

## Code Style

### Python

- **Formatter / linter:** `ruff` (configured in `pyproject.toml`)
- **Type checker:** `mypy`
- Run before every commit:

  ```bash
  uv run ruff check .
  uv run ruff format .
  uv run mypy gateway/ scoring_service/
  ```

- Follow existing async patterns: `asyncpg` for PostgreSQL, `aiokafka` for Kafka, `asyncio`
  throughout.
- Add type annotations to all new functions.

### TypeScript / Frontend

- **Formatter:** Prettier (project config in `frontend/`)
- **Type checking:** `tsc --noEmit` (enforced via `npm run build`)
- Ant Design component conventions — match the existing page/component structure in `frontend/src/`.

## Testing

All pull requests must pass the unit test suite. Integration and e2e tests are optional but
strongly encouraged for changes that touch the pipeline or agent layer.

```bash
# Unit tests — no Docker required
uv run pytest tests/unit/ -v

# Integration tests — Docker stack must be running
uv run pytest tests/integration/ -v

# E2E smoke test — full stack required
python tests/e2e/test_full_pipeline_real.py

# With coverage
uv run pytest tests/unit/ tests/integration/ \
    --cov=gateway --cov=scoring_service --cov=dag_engine --cov=agent_layer \
    --cov-report=term-missing

# Playwright UI tests
cd frontend && npx playwright install chromium
uv run pytest tests/playwright/test_pipeline_full.py -v
```

> If you add a new DAG node type or agent, add corresponding unit tests under `tests/unit/` and at
> least one integration test.

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`:

   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** — keep commits focused and atomic.

3. **Run checks locally** before pushing:

   ```bash
   uv run ruff check . && uv run ruff format .
   uv run pytest tests/unit/ -q
   ```

4. **Open a PR** against `main` with:
   - A clear title and description of *what* changed and *why*
   - Reference to any related issues (`Closes #123`)
   - Notes on testing performed (unit, integration, manual)
   - Screenshots for UI changes

5. A maintainer will review and respond. Given the volunteer nature of this project, please allow
   several days for a review.

### Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<description>` | `feat/add-dns-tunnel-detection` |
| Bug fix | `fix/<description>` | `fix/starrocks-be-registration` |
| Docs | `docs/<description>` | `docs/update-deployment-guide` |
| Refactor | `refactor/<description>` | `refactor/dag-engine-loader` |

## Reporting Issues

Use the GitHub issue templates:

- **Bug report** — include Docker version, OS, `scripts/platform.sh status` output, and relevant
  logs (`scripts/platform.sh logs <service>`)
- **Feature request** — describe the use case, expected behavior, and any relevant alternatives

## Using Claude Code

This project includes a `CLAUDE.md` with full architecture context, commands, and gotchas. If you
use Claude Code:

```bash
claude    # starts Claude Code; CLAUDE.md is read automatically
```

Claude Code is particularly useful for:
- Understanding the DAG pipeline node registry (`dag_engine/engine.py`)
- Adding new pipeline YAML configurations (`dag_engine/pipelines/`)
- Navigating the agent orchestration layer (`agent_layer/orchestrator.py`)

## Questions

Open a GitHub Discussion or issue. This is a community project — there are no official support
channels or guaranteed response times.
