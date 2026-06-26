"""
DAG 编排引擎 — 基于 LangGraph StateGraph
将 YAML 定义的节点串联为有向无环图执行
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, END

from dag.loader import PipelineDefinition
from dag.checkpoint import CheckpointManager
from common.observability import get_logger, ACTIVE_PIPELINES

logger = get_logger(__name__)


class PipelineState(TypedDict, total=False):
    """DAG Pipeline 的状态定义"""
    # 元数据
    trace_id: str
    event_id: str
    pipeline_id: str
    tenant_id: str
    # 数据流
    raw_message: Any
    raw_data: Any
    source: str
    topic: str
    # 解析后
    domain: str
    src_ip: str
    query_type: str
    event_timestamp: str
    parsed: dict
    # 特征
    features: dict
    # 推理结果
    score: float
    is_dga: bool
    family: str | None
    family_confidence: float | None
    model_version: str
    threshold: float
    severity: str
    # 规则
    rules_applied: list[str]
    # 输出
    sinks_written: list[str]
    errors: list[dict]
    # 运行时注入的客户端（不序列化）
    _es_client: Any
    _kafka_producer: Any
    _starrocks_client: Any


class DAGEngine:
    """
    DAG 编排引擎
    将 PipelineDefinition 的节点列表编译为 LangGraph StateGraph
    """

    def __init__(self, pipeline: PipelineDefinition, checkpoint_mgr: CheckpointManager | None = None):
        self.pipeline = pipeline
        self.checkpoint = checkpoint_mgr or CheckpointManager()
        self._graph = self._build_graph()
        self._compiled = self._graph.compile()

    # ------------------------------------------------------------------
    # Conditional-edge helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_score_router(threshold: float, high_branch: str, low_branch: str):
        """Return a routing function that compares state['score'] to *threshold*.

        Returns *high_branch* when score >= threshold, *low_branch* otherwise.
        """

        def _router(state: dict) -> str:
            score = state.get("score", 0.0)
            if score >= threshold:
                return high_branch
            return low_branch

        return _router

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        """将节点列表构建为 LangGraph StateGraph（支持条件分支）"""
        graph = StateGraph(PipelineState)

        nodes = self.pipeline.nodes
        if not nodes:
            raise ValueError(f"Pipeline {self.pipeline.name} has no nodes")

        # 注册所有节点
        node_ids = set()
        for node in nodes:
            graph.add_node(node.node_id, node.safe_process)
            node_ids.add(node.node_id)

        # 设置入口
        graph.set_entry_point(nodes[0].node_id)

        # ---------- 解析 conditional_edges 配置 ----------
        raw_cfg = self.pipeline.raw_config or {}
        cond_edges_cfg = raw_cfg.get("conditional_edges", [])

        # 索引: from_node -> conditional edge config
        cond_map: dict[str, dict] = {}
        for ce in cond_edges_cfg:
            cond_map[ce["from"]] = ce

        # 确保分支目标节点已注册（可能是额外 sink 节点）
        for ce in cond_edges_cfg:
            for branch_target in ce.get("branches", {}).values():
                if branch_target not in node_ids:
                    # 尝试从 pipeline 节点列表中查找（已注册则跳过）
                    logger.warning(
                        "conditional_branch_target_missing",
                        target=branch_target,
                        pipeline=self.pipeline.name,
                    )

        # ---------- 连接边 ----------
        # 收集有条件出边的节点，跳过它们的线性连接
        cond_from_nodes = set(cond_map.keys())

        for i in range(len(nodes) - 1):
            src = nodes[i].node_id
            dst = nodes[i + 1].node_id

            if src in cond_from_nodes:
                ce = cond_map[src]
                condition_type = ce.get("condition", "score_threshold")
                branches = ce.get("branches", {})

                if condition_type == "score_threshold":
                    threshold = float(ce.get("threshold", 0.5))
                    high_key = "high"
                    low_key = "low"
                    high_target = branches.get(high_key, dst)
                    low_target = branches.get(low_key, dst)

                    router = self._make_score_router(threshold, high_key, low_key)
                    branch_map = {high_key: high_target, low_key: low_target}
                    graph.add_conditional_edges(src, router, branch_map)
                else:
                    # 未知条件类型，回退到线性边
                    logger.warning("unknown_condition_type", condition=condition_type)
                    graph.add_edge(src, dst)
            else:
                graph.add_edge(src, dst)

        # 最后一个节点 → END（如果它不是条件出边源）
        last_id = nodes[-1].node_id
        if last_id not in cond_from_nodes:
            graph.add_edge(last_id, END)
        else:
            # 条件分支的所有目标都需要连接到 END
            ce = cond_map[last_id]
            for target in ce.get("branches", {}).values():
                if target in node_ids:
                    graph.add_edge(target, END)

        logger.info(
            "dag_built",
            pipeline=self.pipeline.name,
            nodes=[n.node_id for n in nodes],
            conditional_edges=len(cond_edges_cfg),
        )
        return graph

    async def run(self, message: Any, **context) -> PipelineState:
        """
        执行一次 DAG pipeline
        message: 输入消息（Kafka 消息体 / 文件行）
        context: 运行时上下文（es_client, kafka_producer 等）
        """
        event_id = uuid4().hex
        trace_id = context.get("trace_id", uuid4().hex)

        # 幂等检查
        if await self.checkpoint.is_processed(event_id):
            logger.debug("event_already_processed", event_id=event_id)
            return PipelineState(event_id=event_id, trace_id=trace_id)

        initial_state: PipelineState = {
            "trace_id": trace_id,
            "event_id": event_id,
            "pipeline_id": self.pipeline.pipeline_id,
            "tenant_id": context.get("tenant_id", "default"),
            "raw_message": message,
            "errors": [],
            "rules_applied": [],
            "sinks_written": [],
            # 注入运行时客户端
            "_es_client": context.get("es_client"),
            "_kafka_producer": context.get("kafka_producer"),
            "_starrocks_client": context.get("starrocks_client"),
        }

        # 执行 DAG
        result = await self._compiled.ainvoke(initial_state)

        # 标记已处理
        await self.checkpoint.mark_processed(event_id)

        return result
