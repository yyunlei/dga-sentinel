#!/usr/bin/env bash
# ============================================================
# DGA 智能威胁检测平台 — 一键启动 & 健康检查脚本
# 用法: scripts/platform.sh <command> [options]
# 兼容 macOS bash 3.x（不使用 declare -A）
# ============================================================
set -o pipefail

# ── 项目根目录 ──────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
POLL_INTERVAL=5

# ── 颜色 & 符号 ────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
PASS="${GREEN}✓${NC}"; FAIL="${RED}✗${NC}"; WARN="${YELLOW}⚠${NC}"

# ── 选项默认值 ──────────────────────────────────────────────
NO_BUILD=0; SKIP_SEED=0; VERBOSE=0

# ── 服务分阶段定义 ──────────────────────────────────────────
PHASE1="kafka elasticsearch redis postgres prometheus jaeger starrocks-fe"
PHASE2="starrocks-be grafana"
PHASE3="scoring-service gateway dag-engine agent-layer"
PHASE4="frontend"
ALL_SERVICES="$PHASE1 $PHASE2 $PHASE3 $PHASE4"

# ── 查表函数（兼容 bash 3.x）────────────────────────────────
get_container() {
  case "$1" in
    kafka) echo "dga-sentinel-kafka" ;; elasticsearch) echo "dga-sentinel-elasticsearch" ;;
    redis) echo "dga-sentinel-redis" ;; postgres) echo "dga-sentinel-postgres" ;;
    prometheus) echo "dga-sentinel-prometheus" ;; jaeger) echo "dga-sentinel-jaeger" ;;
    starrocks-fe) echo "dga-sentinel-starrocks-fe" ;; starrocks-be) echo "dga-sentinel-starrocks-be" ;;
    grafana) echo "dga-sentinel-grafana" ;; scoring-service) echo "dga-sentinel-scoring" ;;
    gateway) echo "dga-sentinel-gateway" ;; dag-engine) echo "dga-sentinel-dag-engine" ;;
    agent-layer) echo "dga-sentinel-agent" ;; frontend) echo "dga-sentinel-frontend" ;;
    *) echo "unknown" ;;
  esac
}

get_port() {
  case "$1" in
    kafka) echo "9092" ;; elasticsearch) echo "9200" ;;
    redis) echo "16379" ;; postgres) echo "15432" ;;
    prometheus) echo "9090" ;; jaeger) echo "16686" ;;
    starrocks-fe) echo "8030" ;; starrocks-be) echo "8040" ;;
    grafana) echo "3001" ;; scoring-service) echo "8001" ;;
    gateway) echo "8000" ;; dag-engine) echo "N/A" ;;
    agent-layer) echo "N/A" ;; frontend) echo "13001" ;;
    *) echo "N/A" ;;
  esac
}

get_timeout() {
  case "$1" in
    kafka) echo "150" ;; elasticsearch) echo "120" ;;
    redis) echo "60" ;; postgres) echo "60" ;;
    prometheus) echo "60" ;; jaeger) echo "60" ;;
    starrocks-fe) echo "120" ;; starrocks-be) echo "90" ;;
    grafana) echo "60" ;; scoring-service) echo "120" ;;
    gateway) echo "90" ;; dag-engine) echo "60" ;;
    agent-layer) echo "60" ;; frontend) echo "30" ;;
    *) echo "60" ;;
  esac
}

# ── 输出辅助 ────────────────────────────────────────────────
print_header()  { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}"; }
print_phase()   { echo -e "\n  ${BOLD}$1${NC}"; }
print_ok()      { echo -e "  ${PASS}  $1"; }
print_fail()    { echo -e "  ${FAIL}  $1"; }
print_warn()    { echo -e "  ${WARN}  $1"; }
print_step()    { echo -e "  ${DIM}→${NC} $1"; }

# ════════════════════════════════════════════════════════════
#  前置检查
# ════════════════════════════════════════════════════════════
check_prerequisites() {
  local ok=1
  for cmd in docker curl; do
    if ! command -v "$cmd" &>/dev/null; then
      print_fail "$cmd 未安装"; ok=0
    fi
  done
  if ! docker compose version &>/dev/null; then
    print_fail "docker compose (v2) 不可用"; ok=0
  fi
  if ! docker info &>/dev/null; then
    print_fail "Docker daemon 未运行"; ok=0
  fi
  if [ ! -f "$COMPOSE_FILE" ]; then
    print_fail "docker-compose.yml 不存在: $COMPOSE_FILE"; ok=0
  fi
  if [ ! -f "$PROJECT_ROOT/.env" ]; then
    print_warn ".env 文件不存在，部分服务可能无法启动"
  fi
  if [ $ok -eq 0 ]; then
    echo -e "\n${RED}前置检查失败，请修复后重试${NC}"; exit 1
  fi
}

# ════════════════════════════════════════════════════════════
#  Docker Compose 生命周期
# ════════════════════════════════════════════════════════════
compose_up() {
  local build_flag="--build"
  [ "$NO_BUILD" -eq 1 ] && build_flag=""
  print_header "启动 DGA 平台"
  cd "$PROJECT_ROOT"
  if docker compose -f "$COMPOSE_FILE" up -d $build_flag 2>&1; then
    print_ok "所有容器已启动"
  else
    print_fail "docker compose up 失败"
    exit 1
  fi
}

compose_down() {
  print_header "停止 DGA 平台"
  cd "$PROJECT_ROOT"
  docker compose -f "$COMPOSE_FILE" down 2>&1
  print_ok "所有容器已停止"
}

compose_nuke() {
  echo -e "${RED}${BOLD}警告: 将删除所有容器和数据卷，数据不可恢复！${NC}"
  read -rp "确认继续? [y/N] " confirm
  case "$confirm" in
    [Yy]*) ;;
    *) echo "已取消"; exit 0 ;;
  esac
  cd "$PROJECT_ROOT"
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>&1
  print_ok "所有容器和卷已删除"
}

# ════════════════════════════════════════════════════════════
#  各服务健康检查函数
# ════════════════════════════════════════════════════════════
check_kafka() {
  docker exec dga-kafka bash -c \
    '(command -v kafka-topics.sh && kafka-topics.sh --bootstrap-server localhost:9092 --list) || /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list' \
    &>/dev/null
}
check_elasticsearch() {
  local resp
  resp=$(curl -sf http://localhost:9200/_cluster/health 2>/dev/null) || return 1
  echo "$resp" | grep -qv '"status":"red"'
}
check_redis() {
  docker exec dga-redis redis-cli ping 2>/dev/null | grep -q PONG
}
check_postgres() {
  docker exec dga-postgres pg_isready -U dga -d dga_platform &>/dev/null
}
check_prometheus() {
  curl -sf http://localhost:9090/-/ready &>/dev/null
}
check_jaeger() {
  curl -sf http://localhost:16686/ &>/dev/null
}
check_starrocks_fe() {
  curl -sf http://localhost:8030/api/health &>/dev/null
}
check_starrocks_be() {
  docker inspect --format='{{.State.Running}}' dga-starrocks-be 2>/dev/null | grep -q true
}
check_grafana() {
  curl -sf http://localhost:3001/api/health &>/dev/null
}
check_scoring_service() {
  curl -sf http://localhost:8001/readyz 2>/dev/null | grep -q '"status":"ready"'
}
check_gateway() {
  curl -sf http://localhost:8000/api/readyz 2>/dev/null | grep -q '"status":"ready"'
}
check_dag_engine() {
  docker inspect --format='{{.State.Running}}' dga-dag-engine 2>/dev/null | grep -q true
}
check_agent_layer() {
  docker inspect --format='{{.State.Running}}' dga-agent 2>/dev/null | grep -q true
}
check_frontend() {
  curl -sf -o /dev/null http://localhost:13001/
}

# 根据服务名调用对应检查函数
run_check_for() {
  local svc="$1"
  local fn="check_$(echo "$svc" | tr '-' '_')"
  $fn 2>/dev/null
}

# ════════════════════════════════════════════════════════════
#  轮询等待 & 分阶段健康检查
# ════════════════════════════════════════════════════════════
wait_for_service() {
  local name="$1" timeout="$2"
  local elapsed=0
  while [ $elapsed -lt "$timeout" ]; do
    if run_check_for "$name"; then return 0; fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
    [ "$VERBOSE" -eq 1 ] && printf "    ${DIM}%s: %ds / %ds${NC}\r" "$name" "$elapsed" "$timeout"
  done
  return 1
}

check_phase() {
  local phase_name="$1"; shift
  local phase_failed=0

  print_phase "$phase_name"
  for svc in $@; do
    local container
    container=$(get_container "$svc")
    local timeout
    timeout=$(get_timeout "$svc")

    if ! docker inspect "$container" &>/dev/null; then
      printf "  ${FAIL}  %-20s 容器不存在\n" "$svc"
      phase_failed=$((phase_failed + 1))
      continue
    fi

    if wait_for_service "$svc" "$timeout"; then
      printf "  ${PASS}  %-20s ready\n" "$svc"
    else
      printf "  ${FAIL}  %-20s 超时 (${timeout}s)\n" "$svc"
      print_failure_diagnostics "$svc"
      phase_failed=$((phase_failed + 1))
    fi
  done
  return $phase_failed
}

run_phased_healthcheck() {
  local total_failed=0

  print_header "分阶段健康检查"

  if ! check_phase "Phase 1: 基础设施" $PHASE1; then
    total_failed=$?
    print_fail "基础设施未就绪 (${total_failed} 个失败)，跳过后续阶段"
    return $total_failed
  fi

  check_phase "Phase 2: 数据层" $PHASE2 || total_failed=$((total_failed + $?))
  check_phase "Phase 3: 应用服务" $PHASE3 || total_failed=$((total_failed + $?))
  check_phase "Phase 4: 前端" $PHASE4 || total_failed=$((total_failed + $?))

  echo ""
  if [ $total_failed -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}全部服务就绪${NC}"
  else
    echo -e "  ${RED}${BOLD}${total_failed} 个服务未就绪${NC}"
  fi
  return $total_failed
}

# ════════════════════════════════════════════════════════════
#  失败诊断
# ════════════════════════════════════════════════════════════
print_failure_diagnostics() {
  local svc="$1"
  local container
  container=$(get_container "$svc")

  local state
  state=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
  printf "    ${DIM}状态: %s${NC}\n" "$state"

  if [ "$state" = "exited" ]; then
    local exit_code
    exit_code=$(docker inspect --format='{{.State.ExitCode}}' "$container" 2>/dev/null)
    printf "    ${DIM}退出码: %s${NC}\n" "$exit_code"
  fi

  printf "    ${DIM}最近日志:${NC}\n"
  docker logs --tail=10 "$container" 2>&1 | sed 's/^/      /'

  case "$svc" in
    elasticsearch)
      echo "    提示: 检查 vm.max_map_count >= 262144" ;;
    kafka)
      echo "    提示: Kafka KRaft 需要 120s+ 启动时间" ;;
    postgres)
      echo "    提示: 检查端口 5432 是否被占用" ;;
    scoring-service)
      echo "    提示: 检查 artifacts/ 目录下模型文件" ;;
    gateway)
      echo "    提示: 先确认 redis/postgres/es/scoring 正常" ;;
  esac
}

# ════════════════════════════════════════════════════════════
#  数据验证
# ════════════════════════════════════════════════════════════
run_data_checks() {
  print_header "数据验证"

  # PostgreSQL
  print_phase "PostgreSQL"
  for tbl in model_versions pipeline_configs tenant_configs node_configs feedback audit_log; do
    local count
    count=$(docker exec dga-postgres psql -U dga -d dga_platform -t -c \
      "SELECT count(*) FROM $tbl;" 2>/dev/null | tr -d ' ')
    if [ -z "$count" ] || [ "$count" = "0" ]; then
      printf "  ${WARN}  %-25s  空表 (0 行)\n" "$tbl"
    else
      printf "  ${PASS}  %-25s  %s 行\n" "$tbl" "$count"
    fi
  done

  # Elasticsearch
  print_phase "Elasticsearch"
  local indices
  indices=$(curl -sf 'http://localhost:9200/_cat/indices/dga-*?h=index,docs.count' 2>/dev/null)
  if [ -z "$indices" ]; then
    print_warn "未找到 dga-* 索引 (运行 seed 命令播种)"
  else
    echo "$indices" | while IFS= read -r line; do
      local idx cnt
      idx=$(echo "$line" | awk '{print $1}')
      cnt=$(echo "$line" | awk '{print $2}')
      printf "  ${PASS}  %-35s  %s docs\n" "$idx" "$cnt"
    done
  fi

  # Redis
  print_phase "Redis"
  local dbsize
  dbsize=$(docker exec dga-redis redis-cli DBSIZE 2>/dev/null | awk '{print $2}')
  printf "  %-30s  %s\n" "键总数" "${dbsize:-0}"
  local has_stats
  has_stats=$(docker exec dga-redis redis-cli EXISTS dashboard:stats 2>/dev/null)
  if [ "$has_stats" = "1" ]; then
    print_ok "dashboard:stats 缓存存在"
  else
    print_warn "dashboard:stats 缓存不存在 (运行 seed 命令)"
  fi

  # Kafka Topics
  print_phase "Kafka Topics"
  local topics
  topics=$(docker exec dga-kafka bash -c \
    '(kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null) || (/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null)' 2>/dev/null)
  for t in dns-query-logs dga-alerts; do
    if echo "$topics" | grep -q "^${t}$"; then
      printf "  ${PASS}  %s\n" "$t"
    else
      printf "  ${WARN}  %s (未找到)\n" "$t"
    fi
  done

  # Scoring 模型
  print_phase "Scoring Service"
  local models_resp
  models_resp=$(curl -sf http://localhost:8001/models 2>/dev/null)
  if [ -n "$models_resp" ]; then
    print_ok "模型服务可达"
    if command -v python3 &>/dev/null; then
      echo "$models_resp" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = data if isinstance(data, list) else data.get('models', [])
    for m in models:
        mid = m.get('model_id', m.get('name', '?'))
        ver = m.get('version', '?')
        print(f'  \033[0;32m✓\033[0m  {mid} (v{ver})')
except: print('  模型信息解析失败')
" 2>/dev/null
    fi
  else
    print_fail "模型服务不可达"
  fi

  # Gateway readyz 详情
  print_phase "Gateway 依赖检查"
  local readyz
  readyz=$(curl -sf http://localhost:8000/api/readyz 2>/dev/null)
  if [ -n "$readyz" ] && command -v python3 &>/dev/null; then
    echo "$readyz" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for k, v in data.get('checks', {}).items():
        sym = '\033[0;32m✓\033[0m' if 'ok' in str(v).lower() else '\033[0;31m✗\033[0m'
        print(f'  {sym}  gateway -> {k:20s}  {v}')
except: print('  readyz 解析失败')
" 2>/dev/null
  elif [ -n "$readyz" ]; then
    print_ok "Gateway readyz 正常"
  else
    print_fail "Gateway readyz 不可达"
  fi
}

# ════════════════════════════════════════════════════════════
#  数据播种
# ════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════
#  StarRocks 初始化：注册 BE + 建库建表（幂等）
# ════════════════════════════════════════════════════════════
init_starrocks() {
  print_header "StarRocks 初始化"

  local fe_container be_container
  fe_container=$(get_container starrocks-fe)
  be_container=$(get_container starrocks-be)

  if ! docker inspect "$fe_container" &>/dev/null; then
    print_warn "$fe_container 不存在，跳过"
    return 0
  fi
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$fe_container" 2>/dev/null)" != "healthy" ]; then
    print_fail "$fe_container 未健康，跳过初始化"
    return 1
  fi

  # 1) 注册 BE（官方 start_be.sh 不会自动 join FE，必须手动 ADD BACKEND）
  print_step "检查 BE 注册状态 ..."
  local backend_count
  backend_count=$(docker exec "$fe_container" bash -lc \
    'mysql -h127.0.0.1 -P9030 -uroot -N -B -e "SHOW BACKENDS"' 2>/dev/null | wc -l | tr -d ' ')

  if [ "$backend_count" = "0" ]; then
    print_step "BE 未注册，执行 ALTER SYSTEM ADD BACKEND ..."
    if docker exec "$fe_container" bash -lc \
        'mysql -h127.0.0.1 -P9030 -uroot -e "ALTER SYSTEM ADD BACKEND \"starrocks-be:9050\";"' 2>&1; then
      print_ok "BE 已注册（starrocks-be:9050）"
    else
      print_fail "BE 注册失败"
      return 1
    fi
  else
    print_ok "BE 已注册（${backend_count} 个）"
  fi

  # 2) 等 BE alive=true（注册后 BE 需要心跳上报，否则 schema 创建会因
  #    "Current alive backend is []" 失败）
  print_step "等待 BE 心跳到达 (Alive=true) ..."
  local waited=0 max_wait=60 alive=0
  while [ $waited -lt $max_wait ]; do
    if docker exec "$fe_container" bash -lc \
        'mysql -h127.0.0.1 -P9030 -uroot -N -B -e "SHOW BACKENDS"' 2>/dev/null \
        | awk -F'\t' '{print $9}' | grep -q "true"; then
      alive=1
      break
    fi
    sleep 3
    waited=$((waited + 3))
  done
  if [ $alive -eq 1 ]; then
    print_ok "BE Alive=true（等待 ${waited}s）"
  else
    print_warn "BE 心跳超时 ${max_wait}s，schema 创建可能失败"
  fi

  # 3) 建库建表（CREATE ... IF NOT EXISTS，幂等）
  local schema_file="$PROJECT_ROOT/deploy/init-scripts/starrocks-tables.sql"
  if [ ! -f "$schema_file" ]; then
    print_warn "$schema_file 不存在，跳过 schema 初始化"
    return 0
  fi

  print_step "应用 schema: deploy/init-scripts/starrocks-tables.sql ..."
  # BE 刚 alive 时 schema 偶发失败（"alive backend is []"），重试一次
  local attempt=0 ok=0
  while [ $attempt -lt 3 ] && [ $ok -eq 0 ]; do
    if docker exec -i "$fe_container" bash -lc 'mysql -h127.0.0.1 -P9030 -uroot' < "$schema_file" 2>/dev/null; then
      ok=1
    else
      attempt=$((attempt + 1))
      sleep 5
    fi
  done
  if [ $ok -eq 1 ]; then
    local tables
    tables=$(docker exec "$fe_container" bash -lc \
      'mysql -h127.0.0.1 -P9030 -uroot -N -B -e "USE dga_analytics; SHOW TABLES;"' 2>/dev/null | tr '\n' ' ')
    print_ok "schema 就绪（dga_analytics: ${tables}）"
  else
    print_fail "schema 应用失败（已重试 3 次）"
    return 1
  fi
}

run_seed() {
  print_header "数据播种"
  if ! check_gateway; then
    print_fail "Gateway 未就绪，无法播种"
    return 1
  fi
  # 优先使用项目 venv 里的 python（包含 asyncpg / httpx / redis 等种子脚本依赖）
  local PY
  if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PY="$PROJECT_ROOT/.venv/bin/python"
  elif command -v python3 &>/dev/null; then
    PY="python3"
  else
    print_fail "未找到可用 python（.venv 或系统 python3 都缺失）"
    return 1
  fi
  cd "$PROJECT_ROOT"
  if [ -f scripts/seed_data.py ]; then
    print_step "运行 seed_data.py ($PY) ..."
    if "$PY" scripts/seed_data.py 2>&1; then
      print_ok "seed_data.py 完成"
    else
      print_fail "seed_data.py 失败"
    fi
  else
    print_warn "scripts/seed_data.py 不存在，跳过"
  fi
  if [ -f scripts/setup_pipelines.py ]; then
    print_step "运行 setup_pipelines.py ($PY) ..."
    if "$PY" scripts/setup_pipelines.py 2>&1; then
      print_ok "setup_pipelines.py 完成"
    else
      print_warn "setup_pipelines.py 部分失败 (非致命)"
    fi
  else
    print_warn "scripts/setup_pipelines.py 不存在，跳过"
  fi
}

# ════════════════════════════════════════════════════════════
#  状态报告
# ════════════════════════════════════════════════════════════
print_summary_report() {
  local healthy=0 unhealthy=0 starting=0 total=0

  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║         DGA 平台状态报告  $(date '+%Y-%m-%d %H:%M:%S')            ║${NC}"
  echo -e "${BOLD}╠══════════════════════════════════════════════════════════════╣${NC}"
  printf "${BOLD}║  %-18s  %-12s  %-6s  %-16s  ║${NC}\n" "SERVICE" "STATUS" "PORT" "CONTAINER"
  echo -e "${BOLD}║──────────────────────────────────────────────────────────────║${NC}"

  for svc in $ALL_SERVICES; do
    total=$((total + 1))
    local port container status_str
    port=$(get_port "$svc")
    container=$(get_container "$svc")

    if run_check_for "$svc"; then
      status_str="${GREEN}HEALTHY${NC} "
      healthy=$((healthy + 1))
    else
      local running
      running=$(docker inspect --format='{{.State.Running}}' "$container" 2>/dev/null)
      if [ "$running" = "true" ]; then
        status_str="${YELLOW}STARTING${NC}"
        starting=$((starting + 1))
      else
        status_str="${RED}DOWN${NC}    "
        unhealthy=$((unhealthy + 1))
      fi
    fi
    printf "║  %-18s  %-22b  %-6s  %-16s  ║\n" "$svc" "$status_str" "$port" "$container"
  done

  echo -e "${BOLD}╠══════════════════════════════════════════════════════════════╣${NC}"
  printf "║  总计: %-3d  " "$total"
  printf "${GREEN}健康: %-3d${NC}  " "$healthy"
  [ $starting -gt 0 ] && printf "${YELLOW}启动中: %-3d${NC}  " "$starting"
  [ $unhealthy -gt 0 ] && printf "${RED}异常: %-3d${NC}  " "$unhealthy"
  echo "                    ║"
  echo -e "${BOLD}╠══════════════════════════════════════════════════════════════╣${NC}"
  echo "║  访问地址:                                                   ║"
  echo "║    前端:        http://localhost:13001                       ║"
  echo "║    Gateway:     http://localhost:8000/api/readyz             ║"
  echo "║    Scoring:     http://localhost:8001/readyz                 ║"
  echo "║    Grafana:     http://localhost:3001  (admin/admin)         ║"
  echo "║    Jaeger:      http://localhost:16686                       ║"
  echo "║    Prometheus:  http://localhost:9090                        ║"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
}

# ════════════════════════════════════════════════════════════
#  帮助信息
# ════════════════════════════════════════════════════════════
print_usage() {
  cat <<'USAGE'
DGA 智能威胁检测平台 — 运维脚本

用法: scripts/platform.sh <command> [options]

命令:
  up          一键启动所有服务 (构建 + 启动 + 健康检查 + 播种)
  down        停止所有服务
  restart     重启所有服务 (down + up)
  status      查看所有服务状态
  check       深度检查 (健康 + 数据验证)
  seed        运行数据播种脚本
  logs [svc]  查看日志 (指定服务名或查看全部)
  nuke        销毁所有容器和数据卷 (不可恢复!)
  help        显示此帮助

选项:
  --no-build    跳过 docker compose --build
  --skip-seed   跳过自动数据播种
  --verbose     显示详细轮询进度

示例:
  scripts/platform.sh up                    # 一键启动 (含构建和播种)
  scripts/platform.sh up --no-build         # 快速启动 (不重新构建)
  scripts/platform.sh up --skip-seed        # 启动但不播种数据
  scripts/platform.sh check                 # 深度健康 + 数据检查
  scripts/platform.sh logs gateway          # 查看 gateway 日志
  scripts/platform.sh restart --no-build    # 快速重启
USAGE
}

# ════════════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════════════
main() {
  local cmd="${1:-help}"
  shift || true

  while [ $# -gt 0 ]; do
    case "$1" in
      --no-build)   NO_BUILD=1; shift ;;
      --skip-seed)  SKIP_SEED=1; shift ;;
      --verbose)    VERBOSE=1; shift ;;
      *)            break ;;
    esac
  done

  case "$cmd" in
    up)
      check_prerequisites
      compose_up
      run_phased_healthcheck || true
      init_starrocks || true
      if [ "$SKIP_SEED" -eq 0 ]; then
        run_seed || true
      fi
      print_summary_report
      ;;
    down)
      compose_down
      ;;
    restart)
      compose_down
      sleep 3
      compose_up
      run_phased_healthcheck || true
      init_starrocks || true
      if [ "$SKIP_SEED" -eq 0 ]; then
        run_seed || true
      fi
      print_summary_report
      ;;
    status)
      print_summary_report
      ;;
    check)
      run_phased_healthcheck || true
      run_data_checks
      print_summary_report
      ;;
    seed)
      run_seed
      ;;
    logs)
      local target="${1:-}"
      cd "$PROJECT_ROOT"
      if [ -n "$target" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f --tail=100 "$target"
      else
        docker compose -f "$COMPOSE_FILE" logs -f --tail=50
      fi
      ;;
    nuke)
      compose_nuke
      ;;
    help|*)
      print_usage
      ;;
  esac
}

main "$@"
