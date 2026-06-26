#!/bin/bash
# ============================================================
# DGA 平台端到端验证脚本
# 用法: bash tests/e2e/test_e2e.sh
# ============================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}[PASS]${NC} $desc"
        ((PASS++))
    else
        echo -e "${RED}[FAIL]${NC} $desc"
        ((FAIL++))
    fi
}

echo "=== DGA Platform E2E Test ==="
echo ""

# 1. 基础设施健康检查
echo "--- Infrastructure ---"
check "Kafka reachable" "docker exec dga-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list"
check "Elasticsearch reachable" "curl -sf http://localhost:9200/_cluster/health"
check "Redis reachable" "docker exec dga-redis redis-cli ping"
check "PostgreSQL reachable" "docker exec dga-postgres pg_isready -U dga"
check "Prometheus reachable" "curl -sf http://localhost:9090/-/healthy"
check "Grafana reachable" "curl -sf http://localhost:3001/api/health"
check "Jaeger reachable" "curl -sf http://localhost:16686/"

echo ""
echo "--- API Gateway ---"
check "Gateway /healthz" "curl -sf http://localhost:8000/healthz"
check "Gateway /readyz" "curl -sf http://localhost:8000/readyz"

echo ""
echo "--- Scoring Service ---"
check "Scoring /healthz" "curl -sf http://localhost:8001/healthz"
check "Scoring /metrics" "curl -sf http://localhost:8001/metrics | grep dga_score"

echo ""
echo "--- Score API ---"
check "POST /score" "curl -sf -X POST http://localhost:8000/api/v1/score -H 'Content-Type: application/json' -d '{\"domains\":[\"test123.xyz\"]}'"

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
