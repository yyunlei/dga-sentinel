# 模块化架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 DGA Sentinel 五个平级包重组为 `src/{common,business,ai,dag}` 四大域,叠加 business 三层分层、特征下沉解耦、agents 入口瘦身、通用工具层,保证 8 大业务功能零回归。

**Architecture:** "src 作为源根"(`package-dir={"":"src"}` + Docker `PYTHONPATH=/app/src`),模块名保持干净(`common`/`business`/`ai.scoring`/`ai.agents`/`dag`)。单向依赖铁律:业务三大域只许依赖 `common`,彼此零 Python import,跨服务走 gRPC/HTTP/Kafka/Redis 契约。分 6 阶段(P0–P5),每阶段一个绿灯回滚 commit。

**Tech Stack:** Python 3.13 · FastAPI · LangGraph · gRPC · TensorFlow/XGBoost · Docker Compose(14 容器)· React 19 前端(不改)。

## Global Constraints

- **Python `requires-python = ">=3.12"`**,CI/运行时为 3.13。
- **依赖管理用 `uv`**,禁止 `pip install` 直接装(Docker 内除外,沿用现有 Dockerfile 的 `pip install .`)。
- **所有 HTTP URL 路径字节级不变** —— 全部挂在 `/api` 前缀,前端硬依赖,router 文件可改名但路径绝不动。
- **单向依赖铁律** —— `common` 不 import 任何业务域;`business/ai/dag` 只 import `common`,彼此禁止 Python import。
- **验证只能靠 Docker**(Intel Mac x86_64,TF 无 wheel,本地无法跑 scoring/pytest-full);唯一例外是纯静态的 `tests/test_architecture.py`,本地可跑。
- **保留 `docker-compose.yml` 的 `environment:` 容器地址覆盖块**(`kafka:9092`/`redis:6379`/`postgres:5432`),否则 `/api/readyz` 报 `postgres: no_pool`。
- **每阶段结束必须**:`scripts/platform.sh up` 全量重建 → 14 容器 healthy → `/api/readyz` 全绿 → 端点快照 diff 基线一致 → 再 commit。
- 模型产物 `artifacts/binary/*.pkl`、`artifacts/multi/*.h5` 是 gitignored 大文件,**已在位**(14 容器在线即证明),搬迁不动 `artifacts/`。

### 包名重写映射(贯穿全程)

| 旧包 | 新模块 | 阶段 |
|---|---|---|
| `shared` | `common` | P1 |
| `gateway` | `business` | P1 |
| `scoring_service` | `ai.scoring` | P1 |
| `agent_layer` | `ai.agents` | P1 |
| `dag_engine` | `dag` | P1 |
| `ai.scoring.features` | `common.features` | P2(解耦) |

---

## Phase P0:基线快照 + 架构守门测试

**目的:** 建立"改造前"客观基线和静态守门,后续每阶段都对它验证。本阶段不动任何业务代码。

### Task 0.1:建分支 + 快照脚本

**Files:**
- Create: `scripts/snapshot.sh`

**Interfaces:**
- Produces: `scripts/snapshot.sh <outfile>` —— 抓 `/openapi.json` 路径清单 + `/api/readyz` + 代表性 GET 端点,写入 `<outfile>`。

- [ ] **Step 1: 建专用分支**

```bash
cd /Users/yyunlei/Projects/dga-sentinel
git checkout -b refactor/modular-architecture
git status   # 应在新分支,工作区干净
```

- [ ] **Step 2: 写 snapshot.sh**

`/openapi.json` 的路径集合是结构不变量——改造前后必须完全一致,证明没有端点消失。

```bash
cat > scripts/snapshot.sh <<'EOF'
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
EOF
chmod +x scripts/snapshot.sh
```

- [ ] **Step 3: 抓取改造前基线**

Run:
```bash
scripts/snapshot.sh /tmp/baseline.txt && cp /tmp/baseline.txt docs/superpowers/plans/baseline-pre-refactor.txt
cat docs/superpowers/plans/baseline-pre-refactor.txt
```
Expected: `### OPENAPI_PATHS` 下有一长串 `/api/...` 路径;`### READYZ` 显示各依赖 ok;COUNTS 各端点返回 200。**若 gateway 未在线先 `scripts/platform.sh up`。**

- [ ] **Step 4: Commit 基线**

```bash
git add scripts/snapshot.sh docs/superpowers/plans/baseline-pre-refactor.txt
git commit -m "test: add endpoint snapshot script + pre-refactor baseline"
```

### Task 0.2:架构守门测试(test-first,真正的 TDD)

**Files:**
- Create: `tests/test_architecture.py`

**Interfaces:**
- Produces: `tests/test_architecture.py` —— 静态扫描 `src/` 下 import,断言 `common` 不依赖业务域、业务三大域互不 import。P0 时它对**旧结构会失败**(预期),P1 搬迁后转绿。

- [ ] **Step 1: 写架构测试(此刻预期失败,因为 src/ 还不存在)**

```python
# tests/test_architecture.py
"""架构守门:验证单向依赖铁律,纯静态,无需 Docker/TF。"""
from __future__ import annotations
import ast, pathlib, pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
DOMAINS = {"common", "business", "ai", "dag"}
# 允许的依赖:任何域可依赖 common;common 谁都不依赖;业务域之间禁止
FORBIDDEN = {
    "common": {"business", "ai", "dag"},
    "business": {"ai", "dag"},
    "ai": {"business", "dag"},
    "dag": {"business", "ai"},
}

def _domain_of(path: pathlib.Path) -> str:
    return path.relative_to(SRC).parts[0]

def _imported_top_modules(tree: ast.AST) -> set[str]:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return mods

@pytest.mark.skipif(not SRC.exists(), reason="src/ 尚未建立(P1 之前)")
def test_no_cross_domain_imports():
    violations = []
    for py in SRC.rglob("*.py"):
        dom = _domain_of(py)
        imported = _imported_top_modules(ast.parse(py.read_text(encoding="utf-8")))
        for bad in FORBIDDEN.get(dom, set()) & imported & DOMAINS:
            violations.append(f"{py.relative_to(SRC)} ({dom}) 不应 import {bad}")
    assert not violations, "跨域依赖违规:\n" + "\n".join(violations)
```

- [ ] **Step 2: 跑测试,确认当前 skip(src/ 不存在)**

Run: `.venv/bin/python -m pip install pytest -q && .venv/bin/python -m pytest tests/test_architecture.py -v`
Expected: `1 skipped`(`src/ 尚未建立`)。**这证明测试本身可运行**;真正转绿在 P1 之后。

- [ ] **Step 3: Commit**

```bash
git add tests/test_architecture.py
git commit -m "test: add architecture guard for one-way domain dependencies"
```

---

## Phase P1:纯物理搬迁(零逻辑改动)

**目的:** 仅移动文件位置 + 重写 238 处 import + pyproject + 5 Dockerfile + compose + tests/scripts 引用。**绝不改任何业务逻辑**——若验证挂,一定是搬错/import 错。

### Task 1.1:`git mv` 建立 src/ 骨架

**Files:**
- Move: `shared/`→`src/common/`,`gateway/`→`src/business/`,`scoring_service/`→`src/ai/scoring/`,`agent_layer/`→`src/ai/agents/`,`dag_engine/`→`src/dag/`

**Interfaces:**
- Produces: `src/` 下五个目录就位,内部文件名不变(features 仍在 `src/ai/scoring/features/`,P2 才下沉)。

- [ ] **Step 1: 用 git mv 搬迁(保留历史)**

```bash
cd /Users/yyunlei/Projects/dga-sentinel
mkdir -p src/ai
git mv shared          src/common
git mv gateway         src/business
git mv dag_engine      src/dag
git mv scoring_service src/ai/scoring
git mv agent_layer     src/ai/agents
# 建命名空间标记(ai 是普通包)
touch src/ai/__init__.py && git add src/ai/__init__.py
ls -R src | head -40
```
Expected: `src/common`、`src/business`、`src/dag`、`src/ai/scoring`、`src/ai/agents` 就位。

- [ ] **Step 2: Commit 纯移动(此刻 import 全断,先固化移动)**

```bash
git add -A
git commit -m "refactor(P1): git mv five packages into src/ (imports not yet rewritten)"
```

### Task 1.2:批量重写 import

**Files:**
- Modify: `src/**/*.py`、`tests/**/*.py`、`scripts/**/*.py`(238 处跨包 import)

**Interfaces:**
- Consumes: 包名重写映射表(见 Global Constraints)。
- Produces: 全库 import 指向新模块名;`ai.scoring.features` 仍存在(P2 才改 `common.features`)。

- [ ] **Step 1: 写一次性重写脚本**

顺序关键:先把 `from agent_layer` → `from ai.agents`、`scoring_service` → `ai.scoring` 这类长前缀,再处理裸包名。

```bash
cat > /tmp/rewrite_imports.py <<'EOF'
import pathlib, re
ROOTS = ["src", "tests", "scripts"]
# (正则, 替换) —— 覆盖 `from X` / `import X` / `X.` 限定引用
MAP = [
    (r'\bagent_layer\b',     'ai.agents'),
    (r'\bscoring_service\b', 'ai.scoring'),
    (r'\bdag_engine\b',      'dag'),
    (r'\bgateway\b',         'business'),
    (r'\bshared\b',          'common'),
]
files = [p for r in ROOTS for p in pathlib.Path(r).rglob("*.py")]
changed = 0
for p in files:
    s = p.read_text(encoding="utf-8"); o = s
    for pat, repl in MAP:
        s = re.sub(pat, repl, s)
    if s != o:
        p.write_text(s, encoding="utf-8"); changed += 1
print(f"rewrote {changed} files")
EOF
.venv/bin/python /tmp/rewrite_imports.py
```

- [ ] **Step 2: 核查无残留旧包名**

Run:
```bash
grep -rEn '\b(shared|gateway|scoring_service|dag_engine|agent_layer)\b' --include='*.py' src tests scripts \
  | grep -E '^\S+:(from|import|\s)' | grep -vE '#|"""|文档|注释' | head
```
Expected: **空**(或仅 docstring/注释里的历史说明)。若有 `from gateway` 等真实 import 残留,手动修。

> ⚠️ 注意误伤:`shared` 作为英文单词可能出现在字符串/注释里。重写后人工 diff review `git diff` 确认只动了 import 与模块限定名,没改字符串字面量(如日志文案)。如有误伤手动回改。

- [ ] **Step 3: 本地编译检查(纯语法,不跑 TF)**

Run:
```bash
.venv/bin/python -m compileall -q src/common src/business src/dag src/ai/agents && echo "syntax OK (非 scoring)"
```
Expected: `syntax OK`。**scoring 含 TF import,本地跳过**,靠 Docker 验证。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(P1): rewrite 238 cross-package imports to new module names"
```

### Task 1.3:pyproject + Dockerfile + compose 改路径

**Files:**
- Modify: `pyproject.toml:69-70`
- Move+Modify: 5 个 Dockerfile → `src/<域>/Dockerfile`
- Modify: `docker-compose.yml`(`dockerfile:` 路径)

**Interfaces:**
- Produces: 镜像构建用新包配置;每个容器 `PYTHONPATH=/app/src` + 干净模块名 CMD。

- [ ] **Step 1: 改 pyproject 包发现**

替换 `pyproject.toml` 末尾的 `[tool.setuptools.packages.find]` 段为:

```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["common*", "business*", "ai*", "dag*"]
```

- [ ] **Step 2: 重写 gateway→business Dockerfile**

```bash
git mv gateway/Dockerfile src/business/Dockerfile 2>/dev/null || git mv src/business/Dockerfile src/business/Dockerfile
cat > src/business/Dockerfile <<'EOF'
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
COPY src/common   src/common
COPY src/business src/business
EXPOSE 8000
CMD ["uvicorn", "business.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
```

- [ ] **Step 3: 重写 scoring Dockerfile**

```bash
cat > src/ai/scoring/Dockerfile <<'EOF'
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -U pip setuptools wheel && pip install .
COPY src/common     src/common
COPY src/ai/scoring src/ai/scoring
COPY artifacts/     artifacts/
EXPOSE 8001
CMD ["uvicorn", "ai.scoring.main:app", "--host", "0.0.0.0", "--port", "8001"]
EOF
```

- [ ] **Step 4: 重写 dag Dockerfile(P1 仍 COPY scoring,因 features 尚未下沉)**

```bash
cat > src/dag/Dockerfile <<'EOF'
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
COPY src/common     src/common
COPY src/ai/scoring src/ai/scoring
COPY src/dag        src/dag
CMD ["python", "-m", "dag.runtime"]
EOF
```

- [ ] **Step 5: 重写 agents Dockerfile**

```bash
cat > src/ai/agents/Dockerfile <<'EOF'
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
COPY src/common    src/common
COPY src/ai/agents src/ai/agents
CMD ["python", "-m", "ai.agents"]
EOF
git add -A && rm -f gateway/Dockerfile scoring_service/Dockerfile dag_engine/Dockerfile agent_layer/Dockerfile 2>/dev/null || true
```

- [ ] **Step 6: 改 docker-compose.yml 的 dockerfile 路径**

将四处 `dockerfile:` 改为新位置(`context: .` 不变):

```yaml
# scoring:   dockerfile: src/ai/scoring/Dockerfile
# gateway:   dockerfile: src/business/Dockerfile
# dag-engine: dockerfile: src/dag/Dockerfile
# agent-layer: dockerfile: src/ai/agents/Dockerfile
```

Run 核对:
```bash
grep -nE 'dockerfile:' docker-compose.yml
```
Expected: 四行指向 `src/...`,frontend 那行不变。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(P1): point pyproject/Dockerfiles/compose at src/ layout"
```

### Task 1.4:P1 验证门(全量重建 + 冲烟 = 基线一致)

- [ ] **Step 1: 全量重建**

Run: `scripts/platform.sh up`
Expected: 构建 4 个 app 镜像成功,各阶段健康检查通过。冷启动 3–5 分钟。**若某容器 crash-loop,看 `scripts/platform.sh logs <svc>` 定位 import 错。**

- [ ] **Step 2: 容器健康门**

Run: `docker ps --format '{{.Names}}\t{{.Status}}' | grep dga | wc -l && curl -fsS localhost:8000/api/readyz`
Expected: 14 个容器;readyz 各依赖 ok。

- [ ] **Step 3: 架构守门测试转绿**

Run: `.venv/bin/python -m pytest tests/test_architecture.py -v`
Expected: **此刻仍会 FAIL** —— 因 `src/dag/nodes/transform/feature_extractor.py` 仍 `from ai.scoring.features import`(dag→ai 跨域)。这是预期的,P2 修复。**记录该失败为唯一违规项。**

- [ ] **Step 4: 端点结构 + 数据冲烟,对比基线**

Run:
```bash
scripts/snapshot.sh /tmp/after-p1.txt
diff <(sed -n '/OPENAPI_PATHS/,/READYZ/p' docs/superpowers/plans/baseline-pre-refactor.txt) \
     <(sed -n '/OPENAPI_PATHS/,/READYZ/p' /tmp/after-p1.txt) && echo "端点集合一致 ✓"
scripts/simulate_traffic.py 2>/dev/null || .venv/bin/python scripts/simulate_traffic.py
```
Expected: openapi 路径集合 **零 diff**(没有端点消失);simulate_traffic 注入后,`curl localhost:8000/api/dashboard/stats` 有数据。

- [ ] **Step 5: Commit 验证产物**

```bash
cp /tmp/after-p1.txt docs/superpowers/plans/after-p1.txt
git add docs/superpowers/plans/after-p1.txt
git commit -m "test(P1): verify endpoint parity + full-stack smoke after src/ move [回滚点 A]"
```

---

## Phase P2:特征下沉 common/ + 断 dag→scoring 耦合

**目的:** 把 `ai/scoring/features/` 提到 `common/features/`,消除全库唯一的跨业务域硬耦合,架构守门测试转全绿。

### Task 2.1:下沉 features 到 common

**Files:**
- Move: `src/ai/scoring/features/`→`src/common/features/`
- Modify: scoring 与 dag 中所有 `from ai.scoring.features` → `from common.features`
- Modify: `src/dag/Dockerfile`(去掉 `COPY src/ai/scoring`)

**Interfaces:**
- Consumes: `common.features.lexical.extract_lexical_features`、`common.features.entropy.extract_entropy_features` 等(签名不变,仅位置变)。
- Produces: dag 不再依赖 ai;架构测试断言通过。

- [ ] **Step 1: git mv features 上提**

```bash
git mv src/ai/scoring/features src/common/features
```

- [ ] **Step 2: 重写 features 引用**

```bash
cat > /tmp/rewrite_features.py <<'EOF'
import pathlib, re
for p in pathlib.Path("src").rglob("*.py"):
    s = p.read_text(encoding="utf-8")
    n = re.sub(r'\bai\.scoring\.features\b', 'common.features', s)
    if n != s: p.write_text(n, encoding="utf-8"); print("fixed", p)
EOF
.venv/bin/python /tmp/rewrite_features.py
grep -rn 'ai\.scoring\.features' src && echo "!! 仍有残留" || echo "无残留 ✓"
```
Expected: `feature_extractor.py` 与 scoring 内部引用都改为 `common.features`;无残留。

- [ ] **Step 3: dag Dockerfile 去掉 scoring COPY**

把 `src/dag/Dockerfile` 中的 `COPY src/ai/scoring src/ai/scoring` 行删除(dag 不再需要它)。

```bash
grep -n 'ai/scoring' src/dag/Dockerfile && echo "!! 还在,删掉这行" || echo "dag 已不依赖 scoring ✓"
```

- [ ] **Step 4: 语法检查**

Run: `.venv/bin/python -m compileall -q src/common/features src/dag && echo OK`
Expected: `OK`。

- [ ] **Step 5: 架构守门测试转全绿**

Run: `.venv/bin/python -m pytest tests/test_architecture.py -v`
Expected: **PASS**(`test_no_cross_domain_imports` 通过)—— 这是解耦完成的客观证据。

- [ ] **Step 6: 重建 dag + scoring 验证**

Run:
```bash
scripts/platform.sh up --no-build && docker compose build scoring-service dag-engine && scripts/platform.sh up
curl -fsS localhost:8000/api/readyz
```
Expected: scoring 与 dag 容器正常起、readyz 绿。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(P2): lift features into common/, remove dag->scoring coupling [回滚点 B]"
```

---

## Phase P3:business 三层(api / services / repositories)

**目的:** 把胖 router 拆成 `api → services → repositories → common`。**优先胖文件**;已薄的(health/feedback/rag)只搬目录不强拆。每个功能独立可验证。

### Task 3.1:建三层骨架 + repository 基座

**Files:**
- Create: `src/business/services/__init__.py`、`src/business/repositories/__init__.py`
- Move: `src/business/routers/`→`src/business/api/`(目录改名,URL 不变)
- Move: `src/business/db.py`→`src/business/repositories/pg_repo.py`、`src/business/starrocks_client.py`→`src/business/repositories/starrocks_repo.py`
- Create: `src/business/repositories/es_repo.py`、`src/business/utils`(若需)

**Interfaces:**
- Produces: `api` 包(原 routers,路径不变)、空的 `services`/`repositories` 包、`pg_repo`/`starrocks_repo` 在新位置。

- [ ] **Step 1: routers 改名为 api,搬数据访问件**

```bash
git mv src/business/routers src/business/api
git mv src/business/db.py src/business/repositories  2>/dev/null; mkdir -p src/business/repositories
git mv src/business/db.py src/business/repositories/pg_repo.py 2>/dev/null || true
git mv src/business/starrocks_client.py src/business/repositories/starrocks_repo.py
touch src/business/services/__init__.py src/business/repositories/__init__.py
```

- [ ] **Step 2: 重写 business 内部对 routers/db/starrocks_client 的 import**

```bash
cat > /tmp/rewrite_business.py <<'EOF'
import pathlib, re
MAP = [
    (r'\bbusiness\.routers\b', 'business.api'),
    (r'\bbusiness\.db\b', 'business.repositories.pg_repo'),
    (r'\bbusiness\.starrocks_client\b', 'business.repositories.starrocks_repo'),
]
for p in pathlib.Path("src/business").rglob("*.py"):
    s = p.read_text(encoding="utf-8"); o = s
    for a, b in MAP: s = re.sub(a, b, s)
    if s != o: p.write_text(s, encoding="utf-8"); print("fixed", p)
EOF
.venv/bin/python /tmp/rewrite_business.py
# main.py 里 include_router 的模块引用也会被覆盖到
grep -rn 'business\.routers\|business\.db\b\|starrocks_client' src/business && echo "!! 残留" || echo "无残留 ✓"
```

- [ ] **Step 3: 同步 tests 里对 routers/db 的引用**

```bash
grep -rln 'gateway\.routers\|business\.routers\|business\.db\b' tests | while read f; do
  sed -i '' -E 's/business\.routers/business.api/g; s/business\.db\b/business.repositories.pg_repo/g' "$f"
done; echo done
```

- [ ] **Step 4: 语法检查 + 重建 gateway 验证未破坏**

Run: `.venv/bin/python -m compileall -q src/business && docker compose build gateway && scripts/platform.sh up && curl -fsS localhost:8000/api/readyz`
Expected: 编译 OK、gateway 重建起、readyz 绿。

- [ ] **Step 5: 端点结构不变**

Run: `scripts/snapshot.sh /tmp/after-p3-skel.txt && diff <(grep '^/' docs/superpowers/plans/baseline-pre-refactor.txt) <(grep '^/' /tmp/after-p3-skel.txt) && echo "路径集合一致 ✓"`
Expected: 零 diff。

- [ ] **Step 6: Commit 骨架**

```bash
git add -A
git commit -m "refactor(P3): rename routers->api, move db/starrocks into repositories"
```

### Task 3.2:抽取 alert_service(胖文件样板,告警中心)

> **这是三层抽取的"标准样板"。** 其余功能(3.3+)严格照此模式做,故此处给完整代码;后续任务只列出"源文件→目标文件"清单 + 该功能的冲烟端点,不重复样板。

**Files:**
- Create: `src/business/repositories/es_repo.py`(告警相关 ES 查询)
- Create: `src/business/services/alert_service.py`
- Modify: `src/business/api/alerts.py`(瘦身为 HTTP 层)
- Test: `tests/unit/test_alert_service.py`

**Interfaces:**
- Consumes: `common.utils.time.events_index_today()`、`common.utils.es_compat.ES8_HEADERS`(P4 建;此任务先就地放 `repositories/es_repo.py` 顶部常量,P4 再收编)。
- Produces: `AlertService.list_alerts(...)`、`AlertService.get_alert(alert_id)` 等;`api/alerts.py` 仅调用 service。

- [ ] **Step 1: 读现状,定位 alerts.py 的查询逻辑**

Run: `wc -l src/business/api/alerts.py && grep -nE 'def |async def |\.search\(|_es' src/business/api/alerts.py | head -40`
目的:列出哪些是 HTTP handler、哪些是 ES 查询/业务规则(后者下沉)。

- [ ] **Step 2: 写 service 单测(test-first,纯逻辑用 fake repo)**

service 不碰 FastAPI,可用假 repository 单测——**这条本地能跑,不需 Docker/TF**。

```python
# tests/unit/test_alert_service.py
import pytest
from business.services.alert_service import AlertService

class FakeAlertRepo:
    async def search_alerts(self, *, severity=None, limit=50, **kw):
        return [{"id": "a1", "severity": "HIGH", "domain": "x.com"}]
    async def get_by_id(self, alert_id):
        return {"id": alert_id, "severity": "HIGH"} if alert_id == "a1" else None

@pytest.mark.asyncio
async def test_list_alerts_passthrough():
    svc = AlertService(repo=FakeAlertRepo())
    out = await svc.list_alerts(severity="HIGH", limit=10)
    assert out[0]["id"] == "a1"

@pytest.mark.asyncio
async def test_get_alert_missing_returns_none():
    svc = AlertService(repo=FakeAlertRepo())
    assert await svc.get_alert("nope") is None
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/python -m pip install pytest pytest-asyncio -q && .venv/bin/python -m pytest tests/unit/test_alert_service.py -v`
Expected: FAIL(`ModuleNotFoundError: business.services.alert_service`)。

- [ ] **Step 4: 写 es_repo(把 alerts.py 的 ES 查询搬进来)**

```python
# src/business/repositories/es_repo.py
"""告警/事件 ES 数据访问。封装索引命名、ES8 兼容头、查询构造。"""
from __future__ import annotations
from datetime import datetime, timezone
from common.constants import ES_INDEX_EVENTS

ES8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}

def events_index_wildcard() -> str:
    return f"{ES_INDEX_EVENTS}-*"

class AlertRepo:
    def __init__(self, es):
        self._es = es

    async def search_alerts(self, *, severity=None, limit=50, **filters):
        query = {"bool": {"filter": []}}
        if severity:
            query["bool"]["filter"].append({"term": {"severity": severity}})
        # 把 alerts.py 原有 filter 构造逻辑原样搬入(family/tld/时间窗等)
        resp = await self._es.search(
            index=events_index_wildcard(), headers=ES8_HEADERS,
            body={"query": query, "size": limit, "sort": [{"@timestamp": "desc"}]},
        )
        return [h["_source"] | {"id": h["_id"]} for h in resp["hits"]["hits"]]

    async def get_by_id(self, alert_id):
        resp = await self._es.search(
            index=events_index_wildcard(), headers=ES8_HEADERS,
            body={"query": {"ids": {"values": [alert_id]}}, "size": 1},
        )
        hits = resp["hits"]["hits"]
        return (hits[0]["_source"] | {"id": hits[0]["_id"]}) if hits else None
```

> 实施者注:`search_alerts` 的 filter 构造、聚合、分组(grouped view)等业务细节,**逐段从原 `alerts.py` 搬入对应方法**,保持查询语义不变。本块给的是骨架与签名。

- [ ] **Step 5: 写 service(纯业务编排,无 FastAPI)**

```python
# src/business/services/alert_service.py
"""告警中心业务逻辑:不依赖 FastAPI,只依赖 repository。"""
from __future__ import annotations

class AlertService:
    def __init__(self, repo):
        self._repo = repo

    async def list_alerts(self, *, severity=None, limit=50, **filters):
        return await self._repo.search_alerts(severity=severity, limit=limit, **filters)

    async def get_alert(self, alert_id):
        return await self._repo.get_by_id(alert_id)
```

- [ ] **Step 6: 跑 service 单测转绿**

Run: `.venv/bin/python -m pytest tests/unit/test_alert_service.py -v`
Expected: PASS(2 passed)。

- [ ] **Step 7: 瘦身 api/alerts.py —— 只做 HTTP**

router 改为构造依赖(es client)→ 建 repo/service → 调 service → 返回。**URL 路径与查询参数签名一字不改。**

```python
# src/business/api/alerts.py (瘦身后骨架)
from fastapi import APIRouter, Depends, HTTPException, Query
from business.repositories.es_repo import AlertRepo
from business.repositories.pg_repo import get_es_client
from business.services.alert_service import AlertService
from business.middleware.rbac import require_analyst

router = APIRouter()

def _service(es=Depends(get_es_client)) -> AlertService:
    return AlertService(repo=AlertRepo(es))

@router.get("/alerts")
async def list_alerts(severity: str | None = Query(None), limit: int = Query(50),
                      svc: AlertService = Depends(_service), _=Depends(require_analyst)):
    return await svc.list_alerts(severity=severity, limit=limit)

@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str, svc: AlertService = Depends(_service),
                    _=Depends(require_analyst)):
    out = await svc.get_alert(alert_id)
    if out is None:
        raise HTTPException(404, "alert not found")
    return out
```

> 实施者注:原 `alerts.py` 里**所有现存端点**(含 grouped、acknowledge、incidents 等)都要保留,逐个改成"调 service"。对照 P0 的 openapi 基线确保一个都不少。

- [ ] **Step 8: 重建 gateway,验证告警中心端到端**

Run:
```bash
docker compose build gateway && scripts/platform.sh up
scripts/snapshot.sh /tmp/after-alerts.txt
diff <(grep '^/api/alert' docs/superpowers/plans/baseline-pre-refactor.txt) <(grep '^/api/alert' /tmp/after-alerts.txt) && echo "告警端点一致 ✓"
curl -fsS 'localhost:8000/api/alerts?limit=5' | head -c 300
```
Expected: 告警相关端点零 diff;`/api/alerts` 返回 JSON 数组。前端 `/alerts` 页可正常加载(可选浏览器核对)。

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(P3): extract alert_service + AlertRepo, slim api/alerts.py"
```

### Task 3.3:抽取其余胖功能(照 3.2 样板)

> 对每个功能重复 3.2 的 Step 1–9(读现状 → service 单测 → repo → service → 瘦 api → 重建冲烟 → commit)。**每个功能单独 commit + 单独冲烟**,失败只回滚该功能。

**逐功能清单(源 → 目标 → 冲烟端点):**

- [ ] **3.3a 域名检测**:`api/score.py`+`api/query.py` → `services/detection_service.py` + `repositories/scoring_client.py`(gRPC 客户端)。冲烟:`POST /api/score`(单域名)返回 label/score;`/api/query`。单测:detection_service 用 fake scoring client。Commit。
- [ ] **3.3b 实时监控**:`api/dashboard.py`+`api/realtime.py` → `services/realtime_service.py`(收编多级 fallback 窗口逻辑)+ `es_repo` 复用。冲烟:`/api/dashboard/stats` 有 qps_history/family_dist。Commit。
- [ ] **3.3c 模型管理**:`api/models.py` → `services/model_service.py` + `scoring_client`/`pg_repo`。冲烟:`/api/models` 列出 binary+multi 模型。Commit。
- [ ] **3.3d DAG 编排**:`api/dag.py`(568 行,最胖)+`api/node_configs.py` → `services/pipeline_service.py` + `pg_repo`。冲烟:`/api/dag/pipelines` 列出 4 条 pipeline;`/api/node-configs`。Commit。
- [ ] **3.3e 分析报表**:`api/reports.py` → `services/report_service.py` + `starrocks_repo`/`es_repo`。冲烟:`/api/reports` 返回报表数据。Commit。
- [ ] **3.3f Agent 监控**:`api/agents.py` → `services/agent_monitor_service.py` + Redis 访问(`repositories/redis_repo.py`)。冲烟:`/api/agents` 返回 4 个 agent 状态/历史。Commit。
- [ ] **3.3g 运营建议**:`api/operations.py` → `services/operations_service.py` + `starrocks_repo`/`es_repo`。冲烟:`/api/operations/recommendations` 有数据。Commit。

**保持原样不强拆(YAGNI):** `api/health.py`、`api/feedback.py`、`api/rag.py`、`api/explain.py` —— 已薄/职责单一,仅随目录改名,不抽 service。

- [ ] **3.3h P3 总验证门**:全量 `scripts/platform.sh up` → 14 容器 healthy → openapi 路径集 vs 基线**零 diff** → simulate_traffic 注入 → 8 功能逐一 curl 有数据 → 架构测试绿。Commit:`test(P3): all 8 features green after layering [回滚点 C]`。

---

## Phase P4:agents 入口瘦身 + utils 收编

**目的:** `ai/agents/__main__.py`(448 行)拆出 Kafka 消费循环到 `consumer.py`;把散落内联工具收编进 `common/utils/`。

### Task 4.1:抽 consumer.py

**Files:**
- Create: `src/ai/agents/consumer.py`
- Modify: `src/ai/agents/__main__.py`(瘦身到 ~60 行)

**Interfaces:**
- Consumes: `ai.agents.orchestrator`(DispatchRequest 等,签名不变)。
- Produces: `consumer.run_alert_consumer(orchestrator)` 协程;`__main__` 仅 `asyncio.gather(orchestrator, mcp_server, consumer)`。

- [ ] **Step 1: 读 __main__.py,标出三块边界**

Run: `grep -nE 'async def |def |asyncio\.|uvicorn|Kafka|consumer|gather' src/ai/agents/__main__.py`
目的:定位"orchestrator 启动 / MCP server / Kafka 消费循环"三段。

- [ ] **Step 2: 把 Kafka 消费循环整段移到 consumer.py**

```python
# src/ai/agents/consumer.py
"""Kafka alert 消费循环:订阅 dga-alerts,每条告警跑一次 pipeline。"""
from __future__ import annotations
import asyncio, json
from common.observability import get_logger
logger = get_logger(__name__)

async def run_alert_consumer(orchestrator, *, topic="dga-alerts"):
    # 把 __main__.py 中原 Kafka 订阅 + 逐条 dispatch 的循环原样搬入此函数。
    # 仅迁移,不改逻辑;依赖通过参数注入 orchestrator。
    ...
```

> 实施者注:把 `__main__.py` 里 Kafka consumer 的建连、订阅、`async for msg` 循环、错误处理**逐行搬入** `run_alert_consumer`,把对全局 `_orchestrator` 的引用改为入参。

- [ ] **Step 3: 瘦身 __main__.py**

```python
# src/ai/agents/__main__.py (瘦身后)
from __future__ import annotations
import asyncio
from ai.agents.orchestrator import AgentOrchestrator   # 按实际类名
from ai.agents.consumer import run_alert_consumer
from common.observability import setup_logging, get_logger

logger = get_logger(__name__)

async def main():
    setup_logging()
    orch = AgentOrchestrator()
    await orch.start()
    await asyncio.gather(
        orch.serve_a2a(),               # Redis Pub/Sub A2A 监听
        _serve_mcp(orch),               # uvicorn :8002(保留原 MCP 启动)
        run_alert_consumer(orch),       # Kafka alert 消费
    )

if __name__ == "__main__":
    asyncio.run(main())
```

> 实施者注:`_serve_mcp` / orchestrator 的真实方法名以现有代码为准;此步只重组结构,**不改 MCP server 与 orchestrator 内部行为**。

- [ ] **Step 4: 语法检查 + 重建 agents**

Run: `.venv/bin/python -m compileall -q src/ai/agents && docker compose build agent-layer && scripts/platform.sh up && curl -fsS localhost:8000/api/agents | head -c 200`
Expected: 编译 OK;agent 容器起;`/api/agents` 返回 agent 状态(证明 orchestrator + 监控数据流未破坏)。

- [ ] **Step 5: 冲烟 — 告警驱动 agent**

Run: `.venv/bin/python scripts/simulate_traffic.py && sleep 10 && curl -fsS localhost:8000/api/agents | python3 -c "import sys,json;d=json.load(sys.stdin);print('run_history len:', len(d.get('history',d)))"`
Expected: 注入流量后 agent 有新执行历史(consumer 正常消费 alert)。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(P4): split Kafka consumer out of agents __main__ (448->~60 lines)"
```

### Task 4.2:收编内联工具到 common/utils

**Files:**
- Create: `src/common/utils/__init__.py`、`time.py`、`es_compat.py`、`ids.py`、`retry.py`
- Modify: 引用方改为 `from common.utils...`

**Interfaces:**
- Produces: `common.utils.time.events_index_today()`、`common.utils.es_compat.ES8_HEADERS` 等;P3 的 `es_repo.py` 顶部就地常量改为 import 自此。

- [ ] **Step 1: 建 utils 模块(把 es_repo/各处的内联 hack 提炼)**

```python
# src/common/utils/time.py
from datetime import datetime, timezone
from common.constants import ES_INDEX_EVENTS
def events_index_today() -> str:
    return f"{ES_INDEX_EVENTS}-{datetime.now(timezone.utc):%Y.%m.%d}"
def events_index_wildcard() -> str:
    return f"{ES_INDEX_EVENTS}-*"
```
```python
# src/common/utils/es_compat.py
ES8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}
```
(`ids.py`/`retry.py`:仅在确有 ≥2 处重复时才建;无重复则不建——YAGNI。)

- [ ] **Step 2: 单测 utils(本地可跑)**

```python
# tests/unit/test_common_utils.py
from common.utils.time import events_index_today, events_index_wildcard
from common.utils.es_compat import ES8_HEADERS
def test_index_names():
    assert events_index_wildcard().endswith("-*")
    assert events_index_today().count("-") >= 1
def test_es8_headers_compat():
    assert "compatible-with=8" in ES8_HEADERS["Accept"]
```
Run: `.venv/bin/python -m pytest tests/unit/test_common_utils.py -v` → PASS。

- [ ] **Step 3: 把 es_repo 等改为引用 common.utils**

将 P3 `es_repo.py` 顶部就地的 `ES8_HEADERS`、`events_index_*` 删除,改 `from common.utils.es_compat import ES8_HEADERS` / `from common.utils.time import events_index_wildcard`。grep 确保无重复定义残留:
```bash
grep -rn 'compatible-with=8' src/business && echo "!! 仍有内联,应改 import" || echo "已收编 ✓"
```

- [ ] **Step 4: 重建 gateway 验证**

Run: `docker compose build gateway && scripts/platform.sh up && curl -fsS 'localhost:8000/api/alerts?limit=3' | head -c 200`
Expected: 告警端点仍正常(证明收编未改行为)。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(P4): collect inline helpers into common/utils [回滚点 D]"
```

---

## Phase P5:遗留归档 + 根目录清理 + 文档同步

**目的:** 把旧 Flask 单体与研究脚本移出根目录,更新 CLAUDE.md/README 的目录树与命令。

### Task 5.1:归档 legacy/ 与 research/

**Files:**
- Move: `app.py`、`predict.py`、`static/`、`templates/` → `legacy/`
- Move: `statistics/`、`dga_generate/` → `research/`

- [ ] **Step 1: 再次确认无运行时引用(双保险)**

Run:
```bash
grep -rEn 'from predict|import predict|from app |templates/|static/' --include='*.py' src tests scripts | grep -vE '#|"""|legacy/' | head
```
Expected: **空**(`scoring` 内 docstring 提到 predict.py 的血缘说明不算引用)。

- [ ] **Step 2: 归档**

```bash
mkdir -p legacy research
git mv app.py predict.py legacy/
git mv static templates legacy/
git mv statistics dga_generate research/
echo "旧 FastAPI+Jinja 单体 demo,已被 src/ai/scoring 取代,仅留作血缘参考。" > legacy/README.md
echo "DGA 家族生成器与统计脚本,训练/研究用,运行时不引用。" > research/README.md
git add legacy/README.md research/README.md
```

- [ ] **Step 3: 全链路冲烟(确认归档无副作用)**

Run: `scripts/platform.sh up && curl -fsS localhost:8000/api/readyz && scripts/snapshot.sh /tmp/after-p5.txt && diff <(grep '^/' docs/superpowers/plans/baseline-pre-refactor.txt) <(grep '^/' /tmp/after-p5.txt) && echo "端点集合 vs 基线 零 diff ✓"`
Expected: 14 容器健康、readyz 绿、openapi 路径集合零 diff。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(P5): archive legacy monolith -> legacy/, research scripts -> research/"
```

### Task 5.2:同步 CLAUDE.md / README 架构文档

**Files:**
- Modify: `CLAUDE.md`(架构章节、目录树、命令示例的包名)
- Modify: `README.md`(同上)

- [ ] **Step 1: 更新 CLAUDE.md 的 Architecture 目录树与 Key Files**

把 `gateway/` → `src/business/`、`scoring_service/` → `src/ai/scoring/`、`dag_engine/` → `src/dag/`、`agent_layer/` → `src/ai/agents/`、`shared/` → `src/common/`;新增 `services/`、`repositories/`、`common/features`、`common/utils` 说明;更新"Known Gotchas"里 `StarRocksSinkNode` 路径为 `src/dag/nodes/sink/starrocks_sink.py`。

- [ ] **Step 2: 更新命令示例**

`uvicorn gateway.main:app` → `uvicorn business.main:app`(注明需 `PYTHONPATH=src`);`python -m dag_engine.runtime` → `python -m dag.runtime` 等。

- [ ] **Step 3: 核对文档无旧包名残留**

Run: `grep -nE '\b(gateway|scoring_service|dag_engine|agent_layer)/\b|gateway\.main|dag_engine\.' CLAUDE.md README.md | head`
Expected: 仅剩历史变更记录(如有)说明,无误导性现行指令。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs(P5): update architecture tree and commands for src/ layout [回滚点 E]"
```

---

## Phase 终:收尾验证 + 合并

- [ ] **Step 1: 终极全链路冲烟 vs 基线**

Run:
```bash
scripts/platform.sh up
docker ps --format '{{.Names}}' | grep dga | wc -l        # 期望 14
curl -fsS localhost:8000/api/readyz
.venv/bin/python -m pytest tests/test_architecture.py tests/unit/ -v   # 架构 + 单测全绿
.venv/bin/python scripts/simulate_traffic.py
scripts/snapshot.sh /tmp/final.txt
diff <(grep '^/' docs/superpowers/plans/baseline-pre-refactor.txt) <(grep '^/' /tmp/final.txt) && echo "✅ 端点集合 vs 基线 零 diff"
```
逐一核对 8 功能页(浏览器或 curl):实时监控/域名检测/告警中心/模型管理/DAG 编排/分析报表/Agent 监控/运营建议——全部有数据。

- [ ] **Step 2: 用 superpowers:finishing-a-development-branch 决定合并/PR**

调用该 skill,基于"全部绿灯"决定 merge 到 main 或开 PR。

---

## Self-Review(已执行)

- **Spec 覆盖:** §2 结构→P1;§3 解耦/utils→P2+P4.2;§4 business 三层+8 功能→P3;§5 ai/dag 整理→P2/P4.1;§6 Docker/验证→P1.3+各阶段验证门;§7 分阶段→P0–P5+终;§8 影响面→P1.2/P1.3/P3.1/P5.2 逐项覆盖;§9 非目标→各任务"不强拆"约束。无缺口。
- **占位符:** P3.3 用"照样板"列清单是有意压缩(样板在 3.2 给全),非占位;`ids.py/retry.py` 标注"确有重复才建"是 YAGNI 决策,非 TODO。
- **类型一致:** `AlertService(repo=...)`、`AlertRepo(es)`、`run_alert_consumer(orchestrator)` 在定义与调用处签名一致;`events_index_wildcard()` 在 es_repo(P3)与 common.utils(P4)同名,P4 明确为"删就地、改 import",非冲突。
- **依赖映射:** P1 重写顺序(长前缀先于裸名)与 P2 features 二次重写已分阶段,避免 `scoring_service.features` 被错误一步改写。
