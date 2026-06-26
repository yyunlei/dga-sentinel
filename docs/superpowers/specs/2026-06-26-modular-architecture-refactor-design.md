# DGA Sentinel 模块化架构重构设计

**日期:** 2026-06-26
**状态:** 设计已批准,待落实施计划
**分支:** `refactor/modular-architecture`

## 1. 背景与目标

DGA Sentinel 当前已按 `shared / gateway / scoring_service / dag_engine / agent_layer`
五个顶层包做了切分,大体对应"公共 / 业务 / AI / DAG"四个维度。但存在三类结构问题:

1. **根目录混入遗留产物** —— `app.py`、`predict.py`、`static/`、`templates/`、`statistics/`
   是 2025-01 的旧 FastAPI+Jinja 单体 demo,运行时无人引用,污染根目录。
2. **业务逻辑塞在 router 里(胖 router)** —— `gateway/routers/dag.py`(568 行)、
   `alerts.py`(555 行)等把 HTTP 路由、数据查询、业务规则、索引命名 hack 揉在一个文件,
   缺 service / repository 分层。
3. **AI 能力裂成两个平级包** —— scoring 与 agents 没有统一命名空间;且存在唯一的跨业务模块
   硬耦合 `dag_engine → scoring_service`。
4. **缺通用工具层** —— 全库无 util/helper 模块,工具逻辑(时间格式化、ES 兼容头等)内联散落。

**目标:** 引入 `src/` 顶层重组(common / business / ai / dag),叠加内部逻辑重构
(胖 router 抽 service 层、拆大文件、统一 AI 边界、新增工具层),并保证**8 大业务功能零回归**。

### 决策记录(brainstorming 已确认)

| 决策 | 选择 |
|---|---|
| 物理改动范围 | 引入 `src/` 顶层重组 |
| 重构深度 | 一次到位(物理搬迁 + 内部逻辑重构) |
| 验收标准 | 全量重建 + 全链路冲烟,改造前后端点快照对比 |
| 模块间耦合 | 尽量解耦,单向依赖,可被测试强制执行 |

### 环境约束(影响验证策略)

- **Intel Mac (x86_64)**:TensorFlow 无 Intel-Mac wheel,本地 `uv sync` 失败,scoring 无法本地跑,
  venv 内无 pytest。**唯一可靠验证 = Docker 重建 + 容器健康 + 端点冲烟**。
- **14 容器当前全部在线**:可作为活基线,改造前后对同一批端点冒烟对比。
- **无 CI workflow**:`.github/` 仅有 issue 模板,无 YAML 路径需要同步。

## 2. 目标顶层结构

采用 **"src 作为源根"** 方案(`pyproject.toml` 的 `package-dir={"":"src"}` +
Docker `PYTHONPATH=/app/src`),让模块名保持干净:`from common.config` 而非 `from src.common.config`。

```
src/
├── common/                  # 公共模块 (原 shared/)
│   ├── config.py  constants.py  observability.py  schemas.py
│   ├── features/            # 【下沉】特征提取原语 (原 scoring_service/features/)
│   │   └── lexical.py  entropy.py  ngram.py  nxdomain.py
│   └── utils/               # 【新增】通用工具类
│       ├── time.py          # 索引名/时间窗格式化 (收编 _events_index_today 等)
│       ├── es_compat.py     # ES8 兼容头 (收编 _ES_V8_HEADERS)
│       ├── ids.py           # 域名/事件 id、hash
│       └── retry.py         # 退避重试
├── business/                # 业务模块 (原 gateway/)
│   ├── main.py              # app 工厂
│   ├── api/                 # 原 routers/ —— 瘦身,只做 HTTP 编解码 + 依赖注入
│   ├── services/            # 【新增】业务逻辑编排,禁止 import FastAPI
│   ├── repositories/        # 【新增】数据访问 (ES/PG/StarRocks/scoring 客户端)
│   ├── middleware/          # 不变
│   └── schemas/             # API DTO
├── ai/                      # AI 模块 (统一命名空间,仍是 2 个独立可部署服务)
│   ├── scoring/             # 原 scoring_service/ (XGBoost + TF, gRPC+HTTP)
│   │   └── models/  proto/  drift.py  main.py  grpc_server.py
│   └── agents/              # 原 agent_layer/ (LangGraph 多智能体)
│       ├── __main__.py  consumer.py  orchestrator.py  base_agent.py
│       ├── intent_router.py  fc_bridge.py  fc_security.py  feedback_loop.py
│       └── agents/  a2a/  mcp/  rag/  text2sql/
└── dag/                     # DAG 编排 (原 dag_engine/)
    └── nodes/  pipelines/  engine.py  loader.py  runtime.py  checkpoint.py

research/                    # 【归档】statistics/ + dga_generate/ (纯研究,运行时不引用)
legacy/                      # 【归档】app.py predict.py static/ templates/ (旧 Flask 单体)
```

### 替用户做的判断

1. **AI 仍是 2 个独立容器** —— scoring 依赖 TF/XGBoost,agents 依赖 LangChain,依赖画像完全不同。
   `src/ai/` 只是源码归类,不合并部署单元。
2. **遗留文件归档不删** —— `predict.py` 是现 scoring 代码的血缘出处(多处 docstring 引用),
   移到 `legacy/` 保留可追溯,而非 `rm`。
3. **research/ 独立于 src/** —— `dga_generate`(40 个 DGA 家族)与 `statistics` 是训练/研究资产,
   不属于 4 大业务域,单独成目录。

## 3. 模块解耦规则与工具层

### 唯一跨模块耦合的消除

真实依赖矩阵(谁 import 谁):`shared` 不依赖任何包;`gateway/scoring/agents` 仅依赖 `shared`;
`dag_engine` 依赖 `shared` **+ `scoring_service`(2 处)** —— 全库唯一的跨业务模块硬耦合。

耦合真身:`dag/nodes/transform/feature_extractor.py` 直接
`from scoring_service.features.lexical/entropy import ...`。

**解法:下沉公共域。** 特征提取(lexical/entropy/ngram/nxdomain)是纯函数、无状态领域原语,
scoring 用它做推理特征,dag 用它做 transform——本不该归 scoring 私有。下沉到 `common/features/`,
dag→scoring 的硬依赖直接消失,`dag/Dockerfile` 不再 COPY scoring 包。

### 单向依赖铁律

```
                   common  (config / utils / features)   ← 地基,不依赖任何业务域
                  /    |    \
          business   ai(scoring/agents)   dag             ← 三大域只许依赖 common
                                                             彼此之间零 Python import
```

- `common` 不许 import 任何业务域(保持叶子)。
- `business / ai / dag` **只能** import `common`,彼此之间禁止 Python import。
- 跨服务运行时通信走**契约**而非 import:business→scoring(gRPC)、dag→scoring(HTTP `/score`)、
  dag→agents(Kafka alert topic)、agents(Redis pub/sub)。本就是部署级解耦。
- **架构守门测试** `tests/test_architecture.py`:静态扫描 import,断言无跨域依赖。
  纯静态,不受 Intel Mac+TF 限制,本地 pytest 可跑。

### 工具类分层判据(避免变成大杂烩)

- 跨域复用的纯函数 → `common/utils/`(时间、id、重试、ES 兼容头)。
- 只在单个模块内用的 → 留该模块的 `_helpers.py`,不上提。
- 领域能力(MCP 工具、agent 工具)→ 留 `ai/agents/mcp/tools/`,**不算**通用工具,不动。

## 4. business 三层分层与 8 大功能映射

### 功能 → 页面 → 端点 → 服务 映射表(也是验收矩阵)

| 业务功能 | 前端页面 | 端点组(**路径不变**) | 新 service | 数据源 |
|---|---|---|---|---|
| 实时监控 | Dashboard | `/dashboard` `/realtime`(WS) | `realtime_service` | ES, Redis |
| 域名检测 | Detection | `/score` `/query` | `detection_service` | scoring(gRPC), ES |
| 告警中心 | Alerts/Detail | `/alerts` `/explain` | `alert_service` | ES, agents |
| 模型管理 | Models | `/models` | `model_service` | scoring, PG |
| DAG 编排 | Pipeline | `/dag` `/node-configs` | `pipeline_service` | PG, dag-engine |
| 分析报表 | Reports | `/reports` | `report_service` | StarRocks, ES |
| Agent 监控 | AgentMonitor | `/agents` `/response` | `agent_monitor_service` | Redis, ES |
| 运营建议 | Recommendations | `/operations` | `operations_service` | StarRocks, ES |
| (支撑) | — | `/feedback` `/rag` `/healthz` `/readyz` | 各自轻量 service | — |

### business 内部三层

```
src/business/
├── main.py                  # app 工厂 (注册 api + 中间件)
├── api/                     # 瘦层:解析请求 → 调 service → 包装响应 → HTTP 异常
│                            # 文件名/URL 路径全部保持不变,前端零感知
├── services/                # 业务逻辑编排,按上表 8 功能切,禁止 import FastAPI
├── repositories/            # 数据访问,按数据源切
│   ├── es_repo.py           # 收编 alerts.py 里的 ES 查询 + 索引命名 + 兼容头
│   ├── pg_repo.py           # 原 db.py
│   ├── starrocks_repo.py    # 原 starrocks_client.py
│   └── scoring_client.py    # gRPC 调 ai/scoring 的契约客户端
├── middleware/  schemas/
```

### 铁约束

- **所有 URL 路径字节级不变** —— `/api/dashboard`、`/api/alerts` 等前端硬依赖,router 文件可改名但路径绝不动。
- 三层依赖单向:`api → services → repositories → common`。service 不碰 HTTP,repository 不碰业务规则。
- 拆分**优先做胖文件**(alerts 555、dag 568、node_configs 311、models 235、dashboard 222);
  已经很薄的(health)保持原样,不为分层而分层(YAGNI)。

## 5. ai 与 dag 内部整理

### ai/scoring(改动最小)

逻辑不动,仅改 import:`features/` 已下沉到 `common/features/`,scoring 改为 `from common.features import`。
`models/`、`proto/`、`drift.py`、`grpc_server.py`、`main.py` 保留。

### ai/agents(重点瘦入口)

`__main__.py`(448 行)把"启动 orchestrator + MCP server(uvicorn :8002)+ Kafka 消费循环"三件事揉在一起。
拆分:

- `__main__.py` 仅保留进程编排 `asyncio.gather(orchestrator, mcp_server, consumer)`,降到 ~60 行。
- Kafka alert 消费循环外移到 `consumer.py`(~200 行)。
- 子包(a2a / agents / mcp / rag / text2sql)结构已合理,不动。MCP 工具原样保留。

### dag(只搬迁 + 断耦合)

`engine.py`、`loader.py`、`runtime.py`、`checkpoint.py` 不动逻辑;4 个 YAML pipeline 不动。
唯一改动:`nodes/transform/feature_extractor.py` 的 import 从 `scoring_service.features` 改为
`common.features`。`dag/Dockerfile` 不再 COPY scoring 包。

## 6. Docker / pyproject / 验证流水线

### pyproject.toml

```toml
[tool.setuptools]
package-dir = {"" = "src"}
[tool.setuptools.packages.find]
where = ["src"]
include = ["common*", "business*", "ai*", "dag*"]
```

### 5 个 Dockerfile 重写

Dockerfile 随模块走,放进 `src/<域>/Dockerfile`;compose 的 `context: .` 不变,改 `dockerfile:` 路径。
每个 Dockerfile 加 `ENV PYTHONPATH=/app/src`,模块名保持干净。

| 服务 | COPY | CMD | 备注 |
|---|---|---|---|
| scoring | `src/common src/ai/scoring artifacts` | `uvicorn ai.scoring.main:app` | features 来自 common |
| gateway | `src/common src/business` | `uvicorn business.main:app` | URL 路径不变 |
| dag | `src/common src/dag` | `python -m dag.runtime` | **不再 COPY scoring** |
| agents | `src/common src/ai/agents` | `python -m ai.agents` | — |

注意保留 `docker-compose.yml` 现有的 `environment:` 容器地址覆盖块
(`kafka:9092` / `redis:6379` / `postgres:5432`),否则 `/api/readyz` 会报 `postgres: no_pool`。

### 验证流水线(全重建 + 全链路冲烟)

```
① 重构前: scripts/snapshot.sh  → curl 8 功能端点 + /readyz,存 baseline.json
② scripts/platform.sh up (全量重建 14 容器)
③ 健康门: 14 容器 healthy + /api/readyz 全绿
④ 冲烟: scripts/simulate_traffic.py 注入 DNS → 走完 Kafka→DAG→scoring→ES→alert→agent
⑤ 重构后: snapshot.sh → after.json,逐功能 diff baseline
⑥ 架构守门: pytest tests/test_architecture.py (纯静态)
```

## 7. 分阶段实施与回滚点

虽选"一次到位",但切成 6 个可独立验证的 commit,每个都是绿灯回滚点
(`git revert` 到上一绿点),在分支 `refactor/modular-architecture` 上做。

| 阶段 | 内容 | 验证 | 回滚点 |
|---|---|---|---|
| **P0** | 建分支;snapshot 基线;写 `test_architecture.py` | baseline.json 生成 | — |
| **P1** | **纯搬迁**:`git mv` 进 src/ + 脚本重写 238 处 import + pyproject + 5 Dockerfile + compose | 全重建→readyz→冲烟 = 基线一致 | **A** |
| **P2** | features 下沉 common/ + 断 dag→scoring 耦合 | 架构测试绿 + dag/scoring 重建 | **B** |
| **P3** | business 三层(api/services/repositories),优先胖文件 | 逐功能冲烟,8 项全绿 | **C** |
| **P4** | agents `__main__` 瘦身 + utils 收编内联 hack | agents 重建 + 监控页有数 | **D** |
| **P5** | legacy/ + research/ 归档,清根目录 | 全链路冲烟 vs 基线 | **E** |

**关键纪律:P1 用 `git mv` + 机械 import 重写,零逻辑改动。** 若冲烟挂了,一定是"搬错/import 错"
而非"逻辑改错",定位成本最低。逻辑重构(P3/P4)在搬迁验证通过后才做。

## 8. 影响面清单(必须同步改的产物)

- **238 处跨包 import**(被引用计数:agent_layer 124、shared 119、gateway 70、dag_engine 51、scoring_service 28)
- **5 个 Dockerfile** + **docker-compose.yml** 的 `dockerfile:` 路径
- **pyproject.toml** 的 `[tool.setuptools]` 包配置
- **tests/**:`from gateway.main import app`、`from scoring_service.main import app` 等测试导入
- **scripts/**:`scripts/test_feedback_loop.py` 等引用包的脚本
- **CLAUDE.md / README.md**:架构章节、目录树、命令示例的包名

## 9. 非目标(YAGNI)

- 不改任何 URL 端点路径、API 契约、数据库 schema。
- 不合并 scoring 与 agents 的部署单元。
- 不重构已经很薄、职责单一的 router(如 health)。
- 不动 4 个 DAG YAML pipeline 的语义。
- 不引入新框架/新依赖。
