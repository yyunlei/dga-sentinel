"""
YAML Pipeline 加载器 — 解析 YAML 配置并实例化节点
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dag_engine.nodes.base import BaseNode
from dag_engine.nodes.ingest.kafka_consumer import KafkaConsumerNode
from dag_engine.nodes.ingest.file_reader import FileReaderNode
from dag_engine.nodes.transform.dns_parser import DNSParserNode
from dag_engine.nodes.transform.feature_extractor import FeatureExtractorNode
from dag_engine.nodes.infer.scoring_client import ScoringClientNode
from dag_engine.nodes.filter.whitelist import WhitelistNode
from dag_engine.nodes.filter.threshold import ThresholdNode
from dag_engine.nodes.filter.blacklist import BlacklistNode
from dag_engine.nodes.sink.es_sink import ESSinkNode
from dag_engine.nodes.sink.kafka_sink import KafkaSinkNode
from dag_engine.nodes.sink.starrocks_sink import StarRocksSinkNode
from dag_engine.nodes.sink.fan_out import FanOutNode
from shared.observability import get_logger

logger = get_logger(__name__)

# 节点类型注册表
NODE_REGISTRY: dict[str, type[BaseNode]] = {
    "kafka_consumer": KafkaConsumerNode,
    "file_reader": FileReaderNode,
    "dns_parser": DNSParserNode,
    "feature_extractor": FeatureExtractorNode,
    "scoring_service": ScoringClientNode,
    "whitelist": WhitelistNode,
    "threshold": ThresholdNode,
    "blacklist": BlacklistNode,
    "rule_chain": ThresholdNode,  # rule_chain 默认用 threshold
    "es_sink": ESSinkNode,
    "kafka_sink": KafkaSinkNode,
    "starrocks_sink": StarRocksSinkNode,
    "fan_out": FanOutNode,
    "multi_sink": ESSinkNode,  # multi_sink 在 engine 中特殊处理
}


class PipelineDefinition:
    """解析后的 Pipeline 定义"""

    def __init__(self, name: str, mode: str, version: str, nodes: list[BaseNode], raw_config: dict):
        self.name = name
        self.pipeline_id = name
        self.mode = mode  # "stream" | "batch"
        self.version = version
        self.nodes = nodes
        self.raw_config = raw_config
        self.checkpoint_config = raw_config.get("checkpoint", {})

    def __repr__(self):
        return f"Pipeline({self.name}, mode={self.mode}, nodes={len(self.nodes)})"


def _infer_node_type(node_id: str) -> str:
    """根据 node_id 后缀推断节点类型（用于 conditional_edges 分支目标）"""
    for suffix in ("_sink", "_consumer", "_reader"):
        if node_id.endswith(suffix):
            return node_id.split("_", 1)[-1] if "_" in node_id else node_id
    # 常见映射
    if "alert" in node_id or "es" in node_id:
        return "es_sink"
    if "kafka" in node_id:
        return "kafka_sink"
    if "log" in node_id:
        return "es_sink"  # 默认 log sink 写 ES
    return "es_sink"


def load_pipeline(yaml_path: str | Path) -> PipelineDefinition:
    """从 YAML 文件加载 Pipeline 定义"""
    path = Path(yaml_path)
    with open(path) as f:
        config = yaml.safe_load(f)

    pipeline_cfg = config.get("pipeline", {})
    name = pipeline_cfg.get("name", path.stem)
    mode = pipeline_cfg.get("mode", "stream")
    version = pipeline_cfg.get("version", "1.0.0")

    nodes = []
    for node_cfg in config.get("nodes", []):
        node_id = node_cfg["id"]
        node_type = node_cfg["type"]
        node_config = node_cfg.get("config", {})

        cls = NODE_REGISTRY.get(node_type)
        if cls is None:
            logger.warning("unknown_node_type", node_type=node_type, node_id=node_id)
            continue

        # multi_sink 展开为多个 sink 节点
        if node_type == "multi_sink":
            for i, target in enumerate(node_config.get("targets", [])):
                sink_type = target.get("type", "es") + "_sink"
                sink_cls = NODE_REGISTRY.get(sink_type, ESSinkNode)
                nodes.append(sink_cls(
                    node_id=f"{node_id}_{target['type']}",
                    config=target,
                    pipeline_id=name,
                ))
        elif node_type == "fan_out":
            fan_out = FanOutNode(node_id=node_id, config=node_config, pipeline_id=name)
            for target in node_config.get("targets", []):
                sink_type = target.get("type", "es") + "_sink"
                sink_cls = NODE_REGISTRY.get(sink_type, ESSinkNode)
                child = sink_cls(
                    node_id=f"{node_id}_{target['type']}",
                    config=target,
                    pipeline_id=name,
                )
                fan_out.add_child(child)
            nodes.append(fan_out)
        else:
            nodes.append(cls(node_id=node_id, config=node_config, pipeline_id=name))

    logger.info("pipeline_loaded", name=name, mode=mode, node_count=len(nodes))

    # ---------- 解析 conditional_edges 中引用的额外节点 ----------
    existing_ids = {n.node_id for n in nodes}
    for ce in config.get("conditional_edges", []):
        for branch_key, target_id in ce.get("branches", {}).items():
            if target_id not in existing_ids:
                # 尝试根据 target_id 后缀推断节点类型
                inferred_type = _infer_node_type(target_id)
                cls = NODE_REGISTRY.get(inferred_type)
                if cls is not None:
                    nodes.append(cls(node_id=target_id, config={}, pipeline_id=name))
                    existing_ids.add(target_id)
                    logger.info("conditional_branch_node_created", node_id=target_id, type=inferred_type)
                else:
                    logger.warning("conditional_branch_node_unknown", target=target_id)

    return PipelineDefinition(name, mode, version, nodes, config)


def load_all_pipelines(directory: str | Path) -> list[PipelineDefinition]:
    """加载目录下所有 YAML pipeline"""
    path = Path(directory)
    pipelines = []
    for yaml_file in sorted(path.glob("*.yaml")):
        try:
            pipelines.append(load_pipeline(yaml_file))
        except Exception as e:
            logger.error("pipeline_load_error", file=str(yaml_file), error=str(e))
    return pipelines
