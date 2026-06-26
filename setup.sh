#!/usr/bin/env bash
# ============================================================
# dga-sentinel — First-time contributor setup
# Usage: ./setup.sh
# Idempotent: safe to run multiple times.
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn] ${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

echo ""
echo -e "${BOLD}=== dga-sentinel Setup ===${NC}"
echo ""

# ── 1. Prerequisite checks ────────────────────────────────────
step "Checking prerequisites"

MISSING=0

check_cmd() {
  local cmd="$1" hint="$2"
  if command -v "$cmd" &>/dev/null; then
    info "$cmd found: $(command -v "$cmd")"
  else
    error "$cmd is required but not installed. $hint"
    MISSING=$((MISSING + 1))
  fi
}

check_cmd docker    "Install Docker Desktop: https://docs.docker.com/get-docker/"
check_cmd python3   "Install Python 3.13+: https://www.python.org/downloads/"
check_cmd node      "Install Node.js 20+: https://nodejs.org/"
check_cmd npm       "npm is bundled with Node.js"

# Docker Compose V2
if docker compose version &>/dev/null 2>&1; then
  info "docker compose (v2) found"
else
  error "docker compose (v2) is required. Update Docker Desktop or install the plugin."
  MISSING=$((MISSING + 1))
fi

# Docker daemon running
if docker info &>/dev/null 2>&1; then
  info "Docker daemon is running"
else
  error "Docker daemon is not running. Start Docker Desktop first."
  MISSING=$((MISSING + 1))
fi

if [ "$MISSING" -gt 0 ]; then
  echo ""
  error "Setup aborted: $MISSING prerequisite(s) missing. Fix the errors above and re-run."
  exit 1
fi

# ── 2. Python version warning ─────────────────────────────────
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; }; then
  warn "Python $PYTHON_VERSION detected; dga-sentinel requires Python 3.12+. Some features may not work."
else
  info "Python $PYTHON_VERSION OK"
fi

# ── 3. Environment file ───────────────────────────────────────
step "Configuring environment"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  info "Created .env from .env.example"
  warn "IMPORTANT: Edit .env and set at least:"
  warn "  DEEPSEEK_API_KEY=<your-key>"
  warn "  JWT_SECRET=<random-secret-min-32-chars>"
  warn "  POSTGRES_PASSWORD / GRAFANA_ADMIN_PASSWORD"
  warn "Values marked 'change-me-in-production' MUST be changed before any network exposure."
else
  info ".env already exists — skipping (delete it and re-run to reset)"
fi

# ── 4. Data directories ───────────────────────────────────────
step "Creating persistent data directories"

DATA_DIRS=(
  "./data/kafka"
  "./data/elasticsearch"
  "./data/redis"
  "./data/postgres"
  "./data/starrocks/fe"
  "./data/starrocks/be"
  "./data/prometheus"
  "./data/grafana"
  "./data/jaeger"
  "./data/agent"
)

for d in "${DATA_DIRS[@]}"; do
  if [ ! -d "$d" ]; then
    mkdir -p "$d"
    info "Created $d"
  else
    info "$d already exists"
  fi
done

# ── 5. Python dependencies ────────────────────────────────────
step "Installing Python dependencies"

if command -v uv &>/dev/null; then
  info "uv found — running: uv sync"
  uv sync
  info "Python dependencies installed via uv into .venv"
else
  warn "uv not found. Falling back to python3 venv + pip."
  warn "Install uv for a faster, reproducible experience: https://docs.astral.sh/uv/"

  if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    python3 -m venv "$PROJECT_ROOT/.venv"
    info "Created .venv"
  fi

  # Activate for this script
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.venv/bin/activate"
  pip install --upgrade pip -q
  pip install -e ".[dev]" -q
  info "Python dependencies installed via pip into .venv"
fi

# TensorFlow / Intel Mac warning
if [[ "$(uname -s)" == "Darwin" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
  warn "Intel Mac detected: tensorflow >= 2.20.0 has no Intel-Mac wheel."
  warn "The scoring-service will fail to install locally. Use Docker for that service."
  warn "Gateway / DAG engine / agent work is not affected."
fi

# ── 6. Frontend dependencies (optional) ──────────────────────
step "Frontend dependencies"

if [ -d "$PROJECT_ROOT/frontend" ]; then
  if [ -t 0 ]; then
    # Interactive shell — ask
    read -rp "Install frontend npm dependencies now? [Y/n] " answer
    answer="${answer:-Y}"
  else
    # Non-interactive (piped) — default yes
    answer="Y"
  fi

  case "$answer" in
    [Yy]*)
      info "Running npm install in frontend/"
      cd "$PROJECT_ROOT/frontend"
      npm install --silent
      cd "$PROJECT_ROOT"
      info "Frontend dependencies installed"
      ;;
    *)
      warn "Skipped. Run manually: cd frontend && npm install"
      ;;
  esac
else
  warn "frontend/ directory not found — skipping npm install"
fi

# ── 7. Done ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}=== Setup complete! ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env and set DEEPSEEK_API_KEY, JWT_SECRET, and any other required values"
echo "  2. Run: scripts/platform.sh up"
echo "  3. Wait ~3-5 min for all 14 containers to become healthy"
echo "  4. Open: http://localhost:13001  (frontend)"
echo "           http://localhost:8000/docs  (API docs)"
echo "           http://localhost:3001  (Grafana, admin/admin)"
echo ""
echo "  Using Claude Code? CLAUDE.md has the full architecture and command reference."
echo "  Full deployment guide: docs/architecture-and-deployment.md"
echo ""
