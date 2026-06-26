# 📦 Release Notes — DGA 智能威胁检测平台 v1.0.0

> 发布日期：2026-06-26
> 一套以 **AI 为核心** 的企业级 DNS 安全分析平台，实现从「实时检测 → 智能研判 → 自动处置 → 数据闭环」的全链路安全运营。

---

## 🎯 版本说明

**DGA 智能威胁检测平台 v1.0.0** 是首个完整功能版本。平台聚焦 DGA（Domain Generation Algorithm，域名生成算法）恶意域名检测——这类域名是僵尸网络与 C2（命令控制）通道的隐蔽通信基础设施。

本版本将 **机器学习推理**、**流式 Pipeline 编排** 与 **LLM 多 Agent 协作** 深度融合，让安全分析师不仅能「看到告警」，更能「理解告警、处置告警、并让系统自我进化」。

---

## ✨ 核心功能

| 模块 | 功能 |
|------|------|
| **实时监控仪表盘** | 今日检测量 / DGA 命中率 / QPS 趋势 / 家族分布 / 实时告警流 |
| **域名检测** | 单条 / 批量域名评分 + 恶意家族识别 + LLM 解释 |
| **告警中心** | 多维筛选 / 严重度·家族·Pipeline 分布 / 按域名聚合 / 告警详情抽屉 |
| **DAG 编排** | 可视化拖拽式 Pipeline 编辑器，YAML 双向同步，stream / batch 双模式，版本管理与回放 |
| **模型管理** | 多版本注册 + A/B 灰度发布 + 性能对比 + 一键上线 / 回滚 |
| **分析报表** | 30 天趋势 / Top DGA 域名·受影响主机 / 告警热力图（小时 × 星期）|
| **Agent 监控** | 多 Agent 调用指标 / 执行历史 / A2A 消息流可视化 |
| **运营建议** | 漂移特征 PSI 排行 + 建议类型分布 / 阈值·漂移·黑白名单建议 / 分析师确认·忽略闭环 |
| **问数 & 知识库** | 自然语言查询数据（NL2SQL）+ 安全知识库 RAG 问答 |
| **多租户 & 安全** | JWT 认证 + RBAC 三角色 + 租户级阈值 + 速率限制 + 审计日志 |

---

## 🌟 平台特点

- **🧩 前后端解耦** — Frontend（React 19）与 API 独立迭代，发布更灵活
- **🔀 流式处理闭环** — Kafka + LangGraph DAG 贯通采集、解析、评分、落库
- **🗄️ 多引擎分工（CQRS）** — Elasticsearch 检索、Redis 缓存、StarRocks OLAP 分析各司其职，读写分离
- **🧱 微服务架构** — Gateway / Scoring / DAG / Agent 独立容器，职责清晰、独立扩展
- **📊 全链路可观测** — Prometheus 指标 + Grafana 仪表盘 + Jaeger 分布式追踪 + structlog 结构化日志
- **🚀 一键部署** — `scripts/platform.sh` 编排 14 容器 / 4 阶段健康检查启动
- **🎨 现代化界面** — Ant Design 5 深色主题 + ECharts 数据可视化

---

## 🤖 AI 能力重点 ⭐

> 本平台的核心竞争力在于 **AI 全栈赋能**——从底层模型推理，到中层智能编排，再到上层 LLM 交互，构成完整的「检测 → 研判 → 处置 → 自进化」智能闭环。

### 1. 多模型融合检测引擎

- **二分类**：XGBoost 高精度判定「是否 DGA」（毫秒级推理）
- **家族多分类**：TensorFlow **CNN-Attention** 深度模型识别 **40+ 恶意家族**（gameover、conficker、bamital 等）
- **特征工程**：熵值（Shannon entropy）、n-gram、字符长度、辅音堆叠、nxdomain 比率等 14 维特征
- **可解释性**：SHAP 输出每个预测的特征贡献度，让「黑盒」可审计

### 2. LangGraph 智能 Pipeline 编排

- 基于 **LangGraph StateGraph** 的有向无环图编排，可视化拖拽节点（接入 / 转换 / 推理 / 过滤 / 输出）
- 支持 **stream（实时流）/ batch（批量回放）** 双运行时
- Redis Checkpoint 实现 Pipeline 状态持久化与断点续跑

### 3. A2A 多 Agent 协作研判 🧠

四类智能体经 **Redis Pub/Sub 消息总线（A2A Bus）** 协同，对每条高危告警自动完成深度研判：

| Agent | 职责 |
|-------|------|
| **Triage** | 告警分诊：关联源 IP 历史、评估严重度 |
| **ThreatIntel** | 威胁情报富化：查询 IOC、关联已知威胁 |
| **Explain** | 四维深度解释：字符特征 / 熵值 / DGA 家族模式 / 网络行为 |
| **Response** | 处置建议：DNS 封禁、主机隔离、SOC 工单、SIEM 记录 |

### 4. LLM 驱动的智能交互

- **告警解释（DeepSeek LLM）** — 把模型评分转化为分析师可读的自然语言研判报告
- **问数 / NL2SQL** — 用自然语言提问（如「统计最近 24 小时的告警总数」），自动生成 StarRocks SQL，返回数据 + 图表 + AI 解读，**零 SQL 门槛**
- **安全知识库 RAG** — 检索增强问答，结合 MITRE ATT&CK 等知识库给出 **带来源引用** 的安全解答

### 5. MCP 工具服务

通过 **Model Context Protocol** 为 Agent 提供统一工具接口（ES 查询、模型信息、威胁情报），实现 AI 与平台能力的标准化对接。

### 6. 数据漂移自治闭环 ♻️

- **PSI（群体稳定性指数）** 实时监控特征分布偏移
- PSI ≥ 阈值时自动产出运营建议（触发重训练 / 重设基线）
- 结合分析师 TP/FP 反馈，自动更新黑白名单与检测阈值，形成 **detect → feedback → retrain → detect** 的模型自进化闭环

---

## 📋 本次发布变更摘要

**新增**
- 运营建议页：结构化漂移详情卡片 + PSI 排行 / 建议类型分布双图表可视化
- 界面预览扩展至 13 个业务页面截图（含问数、RAG、DAG 编辑器、运营建议等）

**优化**
- 域名检测页家族概率图（0~1 标准化刻度）与风险仪表盘（刻度去重叠）
- README 重构为标准开源文档结构（简介 / 特性 / 架构 / 快速开始 / API / 运维）

**稳定性**
- 全栈 14 容器一键编排与分阶段健康检查
- 服务依赖顺序与资源占用优化

---

## 🚀 快速体验

```bash
git clone https://github.com/yyunlei/dga-sentinel.git && cd dga-sentinel
cp .env.example .env          # 填入 DEEPSEEK_API_KEY
scripts/platform.sh up        # 一键启动
```

启动后访问 http://localhost:3000 进入控制台。详见 [README](README.md)。

---

<div align="center">

**DGA 智能威胁检测平台 v1.0.0** · AI 让 DNS 安全分析更智能、更高效

</div>
