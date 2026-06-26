"""
PipelineService 单测：fake repo，秒级运行，无需 Docker/PG。

覆盖：
  1. _save_nodes_edges — YAML 解析 + 节点类型映射（含 scoring_service → infer）
  2. create_pipeline — 生成 UUID pipeline_id，调用 repo.create_pipeline
  3. list_schemas — 返回全部 NODE_CONFIG_SCHEMAS（含 scoring_service 键）
  4. get_schema — 已知类型返回 schema；未知类型 raise NodeTypeUnknownError
  5. start_pipeline — 调用 repo.set_redis_pipeline_status + repo.set_pipeline_status
  6. pipeline_history — 格式化 detail 字段（str→dict / dict 原样）
  7. delete_pipeline — "DELETE 0" 时 raise PipelineNotFoundError
  8. update_node_config — None 参数保留原值，调用 repo.update_node_config
"""
from __future__ import annotations

import json
import pytest

from business.services.pipeline_service import (
    PipelineService,
    PipelineNotFoundError,
    DatabaseUnavailableError,
    NodeTypeUnknownError,
    NodeConfigNotFoundError,
)
from business.services.node_schemas import NODE_CONFIG_SCHEMAS


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakePipelineRepo:
    """记录所有调用，返回可控结果，不做真实 IO。"""

    def __init__(self, *, has_pg: bool = True) -> None:
        self.calls: dict[str, list] = {}
        self._has_pg = has_pg
        # 可控返回值
        self._list_pipelines_result = []
        self._get_pipeline_result = None
        self._get_pipeline_meta_result = None
        self._get_pipeline_version_result = None
        self._get_node_config_result = None
        self._delete_result = "DELETE 1"
        self._delete_node_config_result = "DELETE 1"
        self._create_node_config_result = None

    def _record(self, method: str, *args) -> None:
        self.calls.setdefault(method, []).append(args)

    def has_pg(self) -> bool:
        return self._has_pg

    # pipeline queries
    async def list_pipelines(self):
        self._record("list_pipelines")
        return self._list_pipelines_result if self._has_pg else None

    async def get_pipeline(self, pipeline_id):
        self._record("get_pipeline", pipeline_id)
        return self._get_pipeline_result

    async def get_pipeline_meta(self, pipeline_id):
        self._record("get_pipeline_meta", pipeline_id)
        return self._get_pipeline_meta_result

    async def get_pipeline_version(self, pipeline_id):
        self._record("get_pipeline_version", pipeline_id)
        return self._get_pipeline_version_result

    async def count_pipeline_statuses(self):
        self._record("count_pipeline_statuses")
        return []

    # pipeline writes
    async def create_pipeline(self, pipeline_id, name, mode, yaml_content, status, version):
        self._record("create_pipeline", pipeline_id, name, mode, yaml_content, status, version)

    async def delete_pipeline(self, pipeline_id):
        self._record("delete_pipeline", pipeline_id)
        return self._delete_result

    async def update_pipeline(self, pipeline_id, name, mode, yaml_content, version):
        self._record("update_pipeline", pipeline_id, name, mode, yaml_content, version)

    async def set_pipeline_status(self, pipeline_id, status):
        self._record("set_pipeline_status", pipeline_id, status)

    # operations history
    async def record_operation(self, pipeline_id, operation, operator="system", status="success", detail=None):
        self._record("record_operation", pipeline_id, operation, operator, status, detail)

    async def get_pipeline_history(self, pipeline_id, limit=50):
        self._record("get_pipeline_history", pipeline_id, limit)
        return getattr(self, "_history_result", [])

    # nodes / edges
    async def clear_nodes(self, pipeline_id):
        self._record("clear_nodes", pipeline_id)

    async def clear_edges(self, pipeline_id):
        self._record("clear_edges", pipeline_id)

    async def upsert_node(self, pipeline_id, node_id, node_type, sub_type, label, config_json, pos_x, pos_y, sort_order):
        self._record("upsert_node", pipeline_id, node_id, node_type, sub_type, label, config_json, pos_x, pos_y, sort_order)

    async def insert_edge(self, pipeline_id, source, target, edge_type, condition):
        self._record("insert_edge", pipeline_id, source, target, edge_type, condition)

    async def load_nodes(self, pipeline_id):
        self._record("load_nodes", pipeline_id)
        return []

    async def load_edges(self, pipeline_id):
        self._record("load_edges", pipeline_id)
        return []

    # replay / redis / es
    async def create_replay_job(self, replay_id, pipeline, date, hour):
        self._record("create_replay_job", replay_id, pipeline, date, hour)

    async def set_redis_pipeline_status(self, pipeline_id, status):
        self._record("set_redis_pipeline_status", pipeline_id, status)

    async def get_active_pipeline_count(self):
        self._record("get_active_pipeline_count")
        return 0

    async def get_es_pipeline_stats(self, index, body):
        self._record("get_es_pipeline_stats")
        return None

    # filesystem
    def list_pipeline_files(self, pipeline_dir):
        self._record("list_pipeline_files", pipeline_dir)
        return []

    def read_pipeline_file(self, pipeline_dir, pipeline_id):
        self._record("read_pipeline_file", pipeline_dir, pipeline_id)
        return None

    # node config
    async def list_node_configs(self, node_type=None, category=None):
        self._record("list_node_configs", node_type, category)
        return []

    async def create_node_config(self, node_type, category, name, config_json, description):
        self._record("create_node_config", node_type, category, name, config_json, description)
        return self._create_node_config_result

    async def get_node_config(self, config_id):
        self._record("get_node_config", config_id)
        return self._get_node_config_result

    async def update_node_config(self, config_id, name, config_json, description):
        self._record("update_node_config", config_id, name, config_json, description)

    async def delete_node_config(self, config_id):
        self._record("delete_node_config", config_id)
        return self._delete_node_config_result


def _make_svc(*, has_pg: bool = True) -> tuple[PipelineService, FakePipelineRepo]:
    repo = FakePipelineRepo(has_pg=has_pg)
    return PipelineService(repo=repo), repo


# ---------------------------------------------------------------------------
# Test 1: _save_nodes_edges — YAML 解析 + 节点类型映射
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_nodes_edges_parses_yaml_and_maps_node_types():
    """
    _save_nodes_edges 应正确解析 YAML，提取 nodes 和 connections，
    并用 _NODE_TYPE_MAP 将 sub_type 映射到 node_type 大类。
    重点验证 scoring_service → infer，kafka_consumer → ingest，未知类型 → transform。
    """
    svc, repo = _make_svc()
    yaml_content = """
nodes:
  - id: node_a
    type: kafka_consumer
    label: "Kafka Input"
    config:
      topic: dns-query-logs
  - id: node_b
    type: scoring_service
    label: "Scoring"
    config:
      endpoint: "scoring-service:50051"
  - id: node_c
    type: unknown_type
    label: "Unknown"
connections:
  - source: node_a
    target: node_b
    edge_type: default
    condition: ""
"""
    await svc._save_nodes_edges("pipe-001", yaml_content)

    # clear_nodes / clear_edges 各调用一次
    assert repo.calls.get("clear_nodes") == [("pipe-001",)]
    assert repo.calls.get("clear_edges") == [("pipe-001",)]

    # 3 个 upsert_node 调用
    node_calls = repo.calls.get("upsert_node", [])
    assert len(node_calls) == 3

    # 按 node_id 索引
    by_node_id = {c[1]: c for c in node_calls}

    # kafka_consumer → ingest
    assert by_node_id["node_a"][2] == "ingest"
    assert by_node_id["node_a"][3] == "kafka_consumer"

    # scoring_service → infer（关键数据值雷点验证）
    assert by_node_id["node_b"][2] == "infer"
    assert by_node_id["node_b"][3] == "scoring_service"

    # unknown_type → transform（默认值）
    assert by_node_id["node_c"][2] == "transform"

    # 1 条边
    edge_calls = repo.calls.get("insert_edge", [])
    assert len(edge_calls) == 1
    assert edge_calls[0][1] == "node_a"  # source
    assert edge_calls[0][2] == "node_b"  # target


# ---------------------------------------------------------------------------
# Test 2: create_pipeline — 生成 UUID，调用 repo.create_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_pipeline_generates_uuid_and_calls_repo():
    """
    create_pipeline 应生成有效 UUID pipeline_id，
    调用 repo.create_pipeline(pipeline_id, name, mode, yaml, 'inactive', '1')
    并返回包含正确字段的 dict。
    """
    svc, repo = _make_svc()
    result = await svc.create_pipeline(
        name="test-pipe", mode="stream", yaml_content="nodes: []"
    )

    assert result["name"] == "test-pipe"
    assert result["mode"] == "stream"
    assert result["status"] == "inactive"
    assert result["version"] == 1
    assert len(result["pipeline_id"]) == 36  # UUID 格式

    create_calls = repo.calls.get("create_pipeline", [])
    assert len(create_calls) == 1
    call = create_calls[0]
    assert call[0] == result["pipeline_id"]   # pipeline_id
    assert call[1] == "test-pipe"             # name
    assert call[2] == "stream"                # mode
    assert call[4] == "inactive"              # status
    assert call[5] == "1"                     # version str


@pytest.mark.asyncio
async def test_create_pipeline_raises_when_no_pg():
    """DB 不可用时 create_pipeline 应 raise DatabaseUnavailableError。"""
    svc, _ = _make_svc(has_pg=False)
    with pytest.raises(DatabaseUnavailableError):
        await svc.create_pipeline("name", "stream", "nodes: []")


# ---------------------------------------------------------------------------
# Test 3: list_schemas / get_schema — NODE_CONFIG_SCHEMAS 保留
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_schemas_returns_all_schemas():
    """
    list_schemas 应返回 {"schemas": NODE_CONFIG_SCHEMAS}，
    验证 scoring_service 键存在且 category 为 infer。
    """
    svc, _ = _make_svc()
    result = svc.list_schemas()

    assert "schemas" in result
    schemas = result["schemas"]
    # scoring_service 键原样保留
    assert "scoring_service" in schemas
    assert schemas["scoring_service"]["category"] == "infer"
    # 至少 19 种节点类型
    assert len(schemas) >= 19


@pytest.mark.asyncio
async def test_get_schema_returns_correct_schema():
    """get_schema('kafka_consumer') 应返回含 category='ingest' 的 schema。"""
    svc, _ = _make_svc()
    result = svc.get_schema("kafka_consumer")

    assert result["node_type"] == "kafka_consumer"
    assert result["category"] == "ingest"
    assert "fields" in result


@pytest.mark.asyncio
async def test_get_schema_raises_for_unknown_type():
    """get_schema 对不存在的 node_type 应 raise NodeTypeUnknownError。"""
    svc, _ = _make_svc()
    with pytest.raises(NodeTypeUnknownError) as exc_info:
        svc.get_schema("totally_unknown_node_xyz")
    assert "totally_unknown_node_xyz" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 4: start_pipeline / stop_pipeline — Redis + PG 状态写入
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_pipeline_calls_redis_and_pg():
    """
    start_pipeline 应依次调用：
      repo.set_redis_pipeline_status(pid, 'running')
      repo.set_pipeline_status(pid, 'running')
      repo.record_operation(pid, 'start')
    并返回 {"ok": True, "status": "running"}。
    """
    svc, repo = _make_svc()
    result = await svc.start_pipeline("pipe-abc")

    assert result == {"ok": True, "status": "running"}

    redis_calls = repo.calls.get("set_redis_pipeline_status", [])
    assert len(redis_calls) == 1
    assert redis_calls[0] == ("pipe-abc", "running")

    pg_calls = repo.calls.get("set_pipeline_status", [])
    assert len(pg_calls) == 1
    assert pg_calls[0] == ("pipe-abc", "running")

    op_calls = repo.calls.get("record_operation", [])
    assert any(c[1] == "start" for c in op_calls)


@pytest.mark.asyncio
async def test_stop_pipeline_sets_stopped_status():
    """stop_pipeline 写入 'stopped' 状态。"""
    svc, repo = _make_svc()
    result = await svc.stop_pipeline("pipe-abc")

    assert result == {"ok": True, "status": "stopped"}
    redis_calls = repo.calls.get("set_redis_pipeline_status", [])
    assert redis_calls[0] == ("pipe-abc", "stopped")


# ---------------------------------------------------------------------------
# Test 5: pipeline_history — detail 字段 str→dict 转换
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_history_formats_detail_correctly():
    """
    pipeline_history 应将 detail 为 str 时 json.loads，
    为 dict 时 dict() 原样，为 None/空时返回 {}。
    """
    svc, repo = _make_svc()

    class FakeRow(dict):
        pass

    detail_str = json.dumps({"version": 2})
    detail_dict = {"action": "start"}

    repo._history_result = [
        FakeRow({"id": 1, "operation": "save", "operator": "admin", "status": "success", "detail": detail_str, "created_at": "2026-01-01"}),
        FakeRow({"id": 2, "operation": "start", "operator": "system", "status": "success", "detail": detail_dict, "created_at": "2026-01-02"}),
        FakeRow({"id": 3, "operation": "stop", "operator": "system", "status": "success", "detail": None, "created_at": "2026-01-03"}),
    ]

    result = await svc.pipeline_history("pipe-001", limit=10)
    history = result["history"]

    assert len(history) == 3
    # str detail → dict via json.loads
    assert history[0]["detail"] == {"version": 2}
    # dict detail → dict directly
    assert history[1]["detail"] == {"action": "start"}
    # None detail → {}
    assert history[2]["detail"] == {}


# ---------------------------------------------------------------------------
# Test 6: delete_pipeline — "DELETE 0" → PipelineNotFoundError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_pipeline_raises_not_found_when_no_rows():
    """repo.delete_pipeline 返回 'DELETE 0' 时，服务应 raise PipelineNotFoundError。"""
    svc, repo = _make_svc()
    repo._delete_result = "DELETE 0"

    with pytest.raises(PipelineNotFoundError):
        await svc.delete_pipeline("nonexistent-pipe")


@pytest.mark.asyncio
async def test_delete_pipeline_succeeds_when_row_found():
    """正常删除（'DELETE 1'）返回 {"ok": True}。"""
    svc, repo = _make_svc()
    repo._delete_result = "DELETE 1"

    result = await svc.delete_pipeline("pipe-xyz")
    assert result == {"ok": True}


# ---------------------------------------------------------------------------
# Test 7: create_node_config — 未知类型 → NodeTypeUnknownError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_node_config_raises_for_unknown_type():
    """create_node_config 对不在 NODE_CONFIG_SCHEMAS 中的 node_type 应 raise NodeTypeUnknownError。"""
    svc, _ = _make_svc()
    with pytest.raises(NodeTypeUnknownError):
        await svc.create_node_config("bad_type", "my-config", {}, "desc")


@pytest.mark.asyncio
async def test_create_node_config_sets_category_from_schema():
    """
    create_node_config 应从 NODE_CONFIG_SCHEMAS 取 category，
    调用 repo.create_node_config(node_type, category, name, config_json, description)。
    """
    svc, repo = _make_svc()

    class FakeConfigRow(dict):
        pass

    repo._create_node_config_result = FakeConfigRow({
        "id": 42, "node_type": "kafka_consumer", "category": "ingest",
        "name": "my-kafka", "config": "{}", "description": "",
    })

    result = await svc.create_node_config("kafka_consumer", "my-kafka", {"topic": "dns"}, "")

    cc = repo.calls.get("create_node_config", [])
    assert len(cc) == 1
    assert cc[0][0] == "kafka_consumer"   # node_type
    assert cc[0][1] == "ingest"            # category from schema
    assert cc[0][2] == "my-kafka"          # name
    assert result["id"] == 42


# ---------------------------------------------------------------------------
# Test 8: update_node_config — None 参数保留原值
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_node_config_preserves_original_values_when_none():
    """
    update_node_config(config_id, name=None, config=None, description=None)
    应从 repo.get_node_config 取原值，调用 repo.update_node_config 保持不变。
    """
    svc, repo = _make_svc()

    class FakeRow(dict):
        pass

    original_config = json.dumps({"topic": "dns"})
    repo._get_node_config_result = FakeRow({
        "id": 7, "node_type": "kafka_consumer", "category": "ingest",
        "name": "original-name", "config": original_config, "description": "orig-desc",
        "created_at": "2026-01-01", "updated_at": "2026-01-01",
    })

    result = await svc.update_node_config(7)  # all None

    assert result == {"ok": True, "id": 7}

    uc = repo.calls.get("update_node_config", [])
    assert len(uc) == 1
    call = uc[0]
    assert call[0] == 7                    # config_id
    assert call[1] == "original-name"      # name preserved
    assert call[2] == original_config      # config preserved (str)
    assert call[3] == "orig-desc"          # description preserved
