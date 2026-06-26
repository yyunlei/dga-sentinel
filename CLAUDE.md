# dga-sentinel

**Version:** 0.1.0 | **Stack:** Python 3.13 + FastAPI + LangGraph + TensorFlow + React 19 | **Primary entry:** `scripts/platform.sh`

## What

Real-time DNS DGA detection and threat-hunting platform. Kafka-ingested DNS queries flow through a
LangGraph DAG pipeline, scored by XGBoost (binary) + CNN-Attention TensorFlow model (family
multi-class), then routed to a multi-agent layer (triage → threat-intel → explain → response) backed
by DeepSeek LLM. Full observability via Prometheus + Grafana + Jaeger.

## Quick Start

```bash
./setup.sh                          # prereq checks, .env, data dirs, uv sync
scripts/platform.sh up              # build + start 14 containers + health-check + seed
scripts/platform.sh status          # live status table
```

Docker Desktop requires >= 12 GB RAM allocation.

## Commands

```bash
# Platform lifecycle
scripts/platform.sh up              # full start (build + health + seed)
scripts/platform.sh up --no-build   # skip image rebuild (faster restart)
scripts/platform.sh up --skip-seed  # start without seeding data
scripts/platform.sh down            # stop all containers
scripts/platform.sh restart         # down + up
scripts/platform.sh status          # status table with ports
scripts/platform.sh check           # deep health + data validation
scripts/platform.sh seed            # re-run seed scripts only
scripts/platform.sh logs gateway    # tail logs for one service
scripts/platform.sh nuke            # destroy containers + volumes (irreversible)

# Python dev (requires uv)
uv sync                             # install all deps incl. dev extras
uv run pytest tests/unit/           # unit tests (no Docker needed)
uv run pytest tests/integration/    # integration tests (Docker stack required)
uv run pytest tests/e2e/test_full_pipeline_real.py  # e2e smoke test
uv run ruff check .                 # lint
uv run ruff format .                # format

# Backend dev server (without Docker)
PYTHONPATH=src uv run uvicorn business.main:app --reload --port 8000

# Other services (without Docker)
PYTHONPATH=src uv run uvicorn ai.scoring.main:app --reload --port 8001
PYTHONPATH=src uv run python -m dag.runtime
PYTHONPATH=src uv run python -m ai.agents

# Frontend dev
cd frontend && npm install && npm run dev   # Vite dev server → http://localhost:5173

# Hot-deploy frontend into running container (avoids full rebuild)
cd frontend && npm run build
docker cp dist/. dga-frontend:/usr/share/nginx/html

# Playwright e2e (frontend must be running)
cd frontend && npx playwright test
```

## Services & Ports

| Phase | Service | Container | Port |
|-------|---------|-----------|------|
| 1 | kafka | dga-kafka | 9092 (internal) / 9094 (host) |
| 1 | elasticsearch | dga-elasticsearch | 9200 |
| 1 | redis | dga-redis | 16379 |
| 1 | postgres | dga-postgres | 15432 |
| 1 | prometheus | dga-prometheus | 9090 |
| 1 | jaeger | dga-jaeger | 16686 |
| 1 | starrocks-fe | dga-starrocks-fe | 8030 |
| 2 | starrocks-be | dga-starrocks-be | 8040 |
| 2 | grafana | dga-grafana | 3001 |
| 3 | scoring-service | dga-scoring | 8001 |
| 3 | gateway | dga-gateway | 8000 |
| 3 | dag-engine | dga-dag-engine | — |
| 3 | agent-layer | dga-agent | — |
| 4 | frontend | dga-frontend | 13001 |

Full architecture and deployment diagrams: **docs/architecture-and-deployment.md** (8 Mermaid diagrams).

## Architecture

```
src/                All Python source (PYTHONPATH=src; pyproject package-dir=src)
  common/           (原 shared/) Config (pydantic-settings), constants, shared helpers
    config.py  constants.py  observability.py  schemas.py
    features/       (原 scoring_service/features/) lexical/entropy/ngram/nxdomain
    utils/          es_compat.py (ES8_HEADERS), time.py (index naming)
  business/         (原 gateway/) FastAPI REST/WS — JWT auth, rate-limit, scoring proxy, audit
    main.py         App factory, middleware wiring
    api/            (原 routers/) thin HTTP routers (score, explain, alerts, models, dag, query, rag, health)
    services/       Business orchestration (detection/alert/realtime/model/pipeline/report/agent_monitor/operations)
    repositories/   Data access (pg_repo/es_repo/starrocks_repo/scoring_client/model_repo/pipeline_repo/operations_repo/agent_client)
    middleware/     Auth, rate-limit, tracing, tenant, security
    schemas/        Pydantic request/response models
  ai/               AI module
    scoring/        (原 scoring_service/) XGBoost + TF CNN-Attention, gRPC + HTTP
      main.py       HTTP /readyz + /models + /score
      grpc_server.py  Protobuf service impl
      models/       ML models (binary, multi, ensemble, registry)
      drift.py      PSI-based model drift monitor
      proto/        Protobuf definitions and generated code
    agents/         (原 agent_layer/) LangGraph multi-agent
      __main__.py   Thin entry point
      orchestrator.py  Redis Pub/Sub A2A bus + agent lifecycle
      pipeline.py  consumer.py  mcp_app.py  fc_bridge.py  fc_security.py
      mcp/          MCP tool service (es_query, model_info, threat_intel)
  dag/              (原 dag_engine/) LangGraph StateGraph pipeline orchestrator
    engine.py       Graph builder, node registry
    loader.py       YAML → StateGraph compiler
    runtime.py      Kafka stream + file batch runtimes
    checkpoint.py   Redis-backed LangGraph checkpointer
    nodes/          Node impls (ingest/transform/infer/filter/sink)
    pipelines/      4 YAML pipeline definitions (see below)
frontend/           React 19 + TypeScript + Ant Design + Vite (nginx in container)
legacy/             Old Flask monolith (app.py, predict.py, static/, templates/)
research/           Training/research only (statistics/, dga_generate/ ~40 DGA family impls)
scripts/            platform.sh, seed_data.py, setup_pipelines.py, simulate_traffic.py
tests/
  unit/             No-Docker unit tests (pytest; pythonpath=["src"] in pyproject)
  integration/      Docker-stack integration tests
  e2e/              Full pipeline smoke (test_full_pipeline_real.py)
  playwright/       Browser automation tests
```

business (API gateway) → gRPC → ai/scoring (Scoring Service) for inference.
dag (DAG Engine) consumes Kafka, calls Scoring via HTTP, writes to ES + StarRocks + Kafka alerts.
ai/agents (Agent Layer) subscribes to the alert Kafka topic, runs LangGraph chains, publishes responses via Redis Pub/Sub.

## Key Files

```
src/business/main.py                         API entry point, all routers wired here
src/ai/scoring/main.py                       Model loading, /score HTTP + gRPC
src/dag/engine.py                            StateGraph builder and node dispatch
src/dag/loader.py                            YAML pipeline → LangGraph graph
src/dag/pipelines/dga_realtime.yaml          Production real-time pipeline
src/dag/pipelines/dga_batch.yaml             Batch scan pipeline
src/dag/pipelines/c2_realtime.yaml           C2 beacon detection pipeline
src/dag/pipelines/dns_tunnel.yaml            DNS tunneling detection pipeline
src/ai/agents/orchestrator.py                Multi-agent A2A bus orchestration
scripts/platform.sh                          One-command platform lifecycle
deploy/init-scripts/starrocks-tables.sql     StarRocks schema (CREATE IF NOT EXISTS)
```

## Configuration

All config via environment variables. Copy `.env.example` to `.env` before first run.

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPSEEK_API_KEY` | Yes | LLM API key (agent explain feature) |
| `JWT_SECRET` | Yes | Change from default before any network exposure |
| `PG_DSN` | Yes | PostgreSQL connection string |
| `POSTGRES_PASSWORD` | Yes | Must match password in PG_DSN |
| `KAFKA_BOOTSTRAP_SERVERS` | Yes | Kafka broker address |
| `ES_HOSTS` | Yes | Elasticsearch HTTP endpoint |
| `REDIS_URL` | Yes | Redis connection URL |
| `STARROCKS_HOST` | Yes | StarRocks FE host |
| `GRAFANA_ADMIN_PASSWORD` | Recommended | Change from `admin` |

## Conventions

- **Python 3.13** (pyproject.toml `requires-python = ">=3.12"`; CI targets 3.13)
- **Dependency management:** `uv` — use `uv sync` / `uv add` / `uv run`; never `pip install` directly
- **Linting/formatting:** `ruff` (configured in pyproject.toml) — run before every commit
- **Test layout:** `tests/{unit,integration,e2e,playwright}` — unit tests must not require Docker
- **Async:** asyncio throughout; use `asyncpg` for PG, `aiokafka` for Kafka
- **Frontend:** Prettier + TypeScript strict; `cd frontend && npm run build` must pass before PR

## Known Gotchas

> **Full troubleshooting playbook:** see [`docs/troubleshooting.md`](docs/troubleshooting.md).

- **`.env` host vs container address split.** `.env` ships with `localhost` URLs (so host scripts
  like `seed_data.py` work). Container apps (`gateway`, `dag-engine`, `agent-layer`) **must not**
  read those localhost values — `docker-compose.yml` overrides them with service names
  (`kafka:9092`, `redis:6379`, `postgres:5432`, etc.) per service. If you add a new app service,
  copy that `environment:` block, otherwise `/api/readyz` will report `postgres: no_pool`.
- **StarRocks BE auto-register:** BE never self-joins FE. `scripts/platform.sh up` calls
  `init_starrocks` which runs `ALTER SYSTEM ADD BACKEND` if needed. If you start via bare
  `docker compose up`, run `scripts/platform.sh seed` afterward.
- **StarRocks FE meta corruption:** Single-node FE can corrupt BDB journal on unclean shutdown
  (`role=FOLLOWER` written to `image/ROLE`). Wipe `data/starrocks/{fe,be}` and restart;
  `init_starrocks` will rebuild. Steps in **docs/troubleshooting.md §FE stuck in INIT**.
- **StarRocks BE disk watermark:** When the host disk is >95% full, BE refuses to create tablets
  (`empty store limit in request`). Add the `storage_flood_stage_*` overrides shown in
  **docs/troubleshooting.md §BE refuses tablet creation** to `be.conf` and restart BE.
- **Elasticsearch flood-stage on small disks:** ES auto-marks every index `read_only_allow_delete`
  when host disk crosses 95%. Mitigation in **docs/troubleshooting.md §ES indices red**.
- **`StarRocksSinkNode` is currently a stub** (`src/dag/nodes/sink/starrocks_sink.py`): it logs
  but does not actually write. Real-time pipelines do not populate StarRocks; only `seed_data.py`'s
  `seed_starrocks()` does. To enable streaming writes, implement Stream Load HTTP in that node.
- **`platform.sh seed` blocks on Gateway readyz check** even when Gateway is fine. If you hit
  "Gateway 未就绪", run `.venv/bin/python scripts/seed_data.py` directly.
- **Model artifacts not bundled:** `artifacts/binary/*.pkl` and `artifacts/multi/*.h5` are
  gitignored (large binaries). Drop them in before first `up`, or scoring crash-loops with
  `FileNotFoundError`. See `artifacts/README.md` for sourcing options.
- **DGA-DataSet not bundled:** `DGA-DataSet/dga_multi.csv` etc. are gitignored. Required only for
  `seed_data.py`. See `DGA-DataSet/README.md`.
- **TensorFlow on Intel Mac:** `tensorflow >= 2.20.0` has no Intel-Mac (x86_64 macOS) wheel.
  `uv sync` will fail on that platform. Workaround: install without TF extras or use Docker for
  scoring service. Does not block gateway/DAG/agent work.
- **ES vm.max_map_count:** Elasticsearch requires `vm.max_map_count >= 262144` on Linux hosts.
  macOS Docker Desktop handles this automatically.
- **First `up` time:** Full cold start (Kafka KRaft + ES + StarRocks) takes 3–5 minutes.
- **Hot frontend reload:** code changes need `cd frontend && npm run build` then
  `docker cp dist/. dga-sentinel-frontend:/usr/share/nginx/html` then nginx reload — `restart`
  alone won't pick up new bundles since the image bakes the dist at build time.
  `scripts/platform.sh up` polls each phase before proceeding.
- **Model artifacts:** `artifacts/binary/` and `artifacts/multi/` must contain trained model files
  before `scoring-service` can start. See `artifacts/README.md` for download/training instructions.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
