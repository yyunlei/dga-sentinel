#!/usr/bin/env bash
# 用法: scripts/snapshot.sh <outfile>
# 抓取 gateway 的结构(openapi 路径集)与关键端点健康,作为重构前后对比基线。
set -euo pipefail
OUT="${1:?need outfile}"
BASE="http://localhost:8000"
{
  echo "### OPENAPI_PATHS"
  curl -fsS "$BASE/openapi.json" | python3 -c "import sys,json; [print(p) for p in sorted(json.load(sys.stdin)['paths'])]"
  echo "### READYZ"
  curl -fsS "$BASE/api/readyz" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('checks',d),sort_keys=True))"
  echo "### COUNTS"
  for ep in /api/models /api/dashboard/stats /api/operations/recommendations; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$ep" || echo ERR)
    echo "$ep -> $code"
  done
} > "$OUT"
echo "snapshot written: $OUT"
