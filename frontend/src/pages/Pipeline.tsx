import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Row,
  Col,
  Input,
  App,
  Drawer,
  Timeline,
  Modal,
  Empty,
  Collapse,
  Form,
  InputNumber,
  Switch,
  Select,
  Tooltip,
  Badge,
  DatePicker,
  Statistic,
} from "antd";
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CodeOutlined,
  HistoryOutlined,
  SettingOutlined,
  SaveOutlined,
  DeleteOutlined,
  PlusOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  AppstoreOutlined,
  EditOutlined,
  SearchOutlined,
  ReloadOutlined,
  FundOutlined,
  ThunderboltOutlined,
  StopOutlined,
  AlertOutlined,
} from "@ant-design/icons";
import {
  ReactFlowEditor,
  NodePalette,
  CreatePipelineModal,
  NodeConfigForm,
} from "@/components/dag-editor";
import {
  getSchemaForNode,
  type NodeConfigFieldSchema,
} from "@/components/dag-editor/nodeConfigSchemas";
import { useDagStore } from "@/stores/dagStore";
import { usePipelineStore } from "@/stores";
import { dagAPI } from "@/services/api";
import { useDebounce } from "@/hooks/useDebounce";
import type { PipelineInfo } from "@/services/api";
import type { Node } from "@xyflow/react";
import { ReactFlowProvider } from "@xyflow/react";

const { TextArea } = Input;

let nodeIdCounter = 0;

/** Render a config field based on schema type */
function renderConfigField(field: NodeConfigFieldSchema) {
  switch (field.type) {
    case "number":
      return (
        <InputNumber
          style={{ width: "100%" }}
          placeholder={field.placeholder}
        />
      );
    case "boolean":
      return <Switch />;
    case "enum":
      return (
        <Select
          allowClear
          placeholder={field.placeholder}
          options={field.options}
          style={{ width: "100%" }}
        />
      );
    case "array":
      return (
        <Select
          mode="tags"
          style={{ width: "100%" }}
          placeholder={field.placeholder || "输入后回车添加"}
          tokenSeparators={[",", " "]}
        />
      );
    default:
      return <Input placeholder={field.placeholder} />;
  }
}

function PipelineInner() {
  const { modal, message } = App.useApp();
  const { pipelines, setPipelines } = usePipelineStore();
  const {
    nodes,
    edges,
    selectedNode,
    configDrawerOpen,
    onNodesChange,
    onEdgesChange,
    onConnect,
    setSelectedNode,
    addNode,
    removeNode,
    renameNode,
    fromYAML,
    toYAML,
    openConfigDrawer,
    closeConfigDrawer,
  } = useDagStore();
  const [yaml, setYaml] = useState("");
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(
    null,
  );
  const [selectedPipelineName, setSelectedPipelineName] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [replayDate, setReplayDate] = useState("");
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // History drawer
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPipelineId, setHistoryPipelineId] = useState("");
  const [historyData, setHistoryData] = useState<
    {
      id: number;
      operation: string;
      operator: string;
      status: string;
      detail: Record<string, unknown>;
      created_at: string;
    }[]
  >([]);

  // Create pipeline modal
  const [createOpen, setCreateOpen] = useState(false);

  // Edit pipeline modal
  const [editOpen, setEditOpen] = useState(false);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [editPipeline, setEditPipeline] = useState<{
    pipeline_id: string;
    name: string;
    mode: string;
    description?: string;
  } | null>(null);

  // DAG editor modal
  const [editorOpen, setEditorOpen] = useState(false);

  // Pipeline stats
  const [pipelineStats, setPipelineStats] = useState<{
    total: number;
    running: number;
    stopped: number;
    inactive: number;
    alert_rate: number;
    alerts_by_pipeline: { pipeline_id: string; name: string; count: number }[];
    alerts_by_family: { name: string; value: number }[];
    alerts_by_severity: { name: string; value: number }[];
  } | null>(null);

  // Card body width for modal sizing
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardBodyWidth, setCardBodyWidth] = useState<number>(0);
  useEffect(() => {
    function measure() {
      const el = cardRef.current?.querySelector<HTMLElement>(".ant-card-body");
      if (el) setCardBodyWidth(el.clientWidth);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Search filters
  const [filterName, setFilterName] = useState("");
  const [filterStatus, setFilterStatus] = useState<string | undefined>(
    undefined,
  );
  const [filterDateRange, setFilterDateRange] = useState<
    [string, string] | null
  >(null);

  useEffect(() => {
    dagAPI
      .list()
      .then((r) => setPipelines(r.pipelines))
      .catch(() => {
        setPipelines([]);
        message.error("加载 Pipeline 列表失败");
      });
    dagAPI
      .stats()
      .then(setPipelineStats)
      .catch(() => {});
  }, [setPipelines]);

  // Mark dirty when nodes/edges change (after initial load)
  const prevNodesLen = useRef(0);
  useEffect(() => {
    if (selectedPipelineId && prevNodesLen.current > 0) setDirty(true);
    prevNodesLen.current = nodes.length;
  }, [nodes, edges, selectedPipelineId]);

  const debouncedFilterName = useDebounce(filterName, 300);

  const data = pipelines.filter((p) => {
    if (
      debouncedFilterName &&
      !p.name.toLowerCase().includes(debouncedFilterName.toLowerCase())
    )
      return false;
    if (filterStatus && p.status !== filterStatus) return false;
    if (filterDateRange && p.created_at) {
      const ct = new Date(p.created_at).getTime();
      const [start, end] = filterDateRange;
      if (start && ct < new Date(start).getTime()) return false;
      if (end && ct > new Date(end + "T23:59:59").getTime()) return false;
    }
    return true;
  });

  /** 只有 stopped 状态才允许编辑和删除 */
  function canEditOrDelete(status: string) {
    return status === "stopped" || status === "inactive";
  }

  function updatePipelineStatus(pipelineId: string, status: string) {
    setPipelines(
      pipelines.map((p) =>
        p.pipeline_id === pipelineId ? { ...p, status } : p,
      ),
    );
  }

  function handleStart(pipelineId: string) {
    setLoadingId(pipelineId);
    dagAPI
      .start(pipelineId)
      .then(() => {
        updatePipelineStatus(pipelineId, "running");
        message.success("Pipeline 已启动");
      })
      .catch(() => message.error("启动失败"))
      .finally(() => setLoadingId(null));
  }

  function handleStop(pipelineId: string) {
    setLoadingId(pipelineId);
    dagAPI
      .stop(pipelineId)
      .then(() => {
        updatePipelineStatus(pipelineId, "stopped");
        message.success("Pipeline 已停止");
      })
      .catch(() => message.error("停止失败"))
      .finally(() => setLoadingId(null));
  }

  function handleReplay(pipelineId: string) {
    if (!replayDate) {
      message.warning("请选择回放日期");
      return;
    }
    setLoadingId(pipelineId);
    dagAPI
      .replay(pipelineId, replayDate)
      .then((res) => message.success(`回放已提交：${res.replay_id}`))
      .catch(() => message.error("回放提交失败"))
      .finally(() => setLoadingId(null));
  }

  function handleShowHistory(pipelineId: string) {
    setHistoryPipelineId(pipelineId);
    setHistoryOpen(true);
    dagAPI
      .history(pipelineId)
      .then((r) => setHistoryData(r.history))
      .catch(() => setHistoryData([]));
  }

  function handleLoadPipeline(pipelineId: string, name: string) {
    doLoadPipeline(pipelineId, name);
  }

  function doLoadPipeline(pipelineId: string, name: string) {
    setSelectedPipelineId(pipelineId);
    setSelectedPipelineName(name);
    setDirty(false);
    prevNodesLen.current = 0;
    closeConfigDrawer();
    dagAPI
      .get(pipelineId)
      .then((r) => {
        if (r.yaml_content) {
          setYaml(r.yaml_content);
          fromYAML(r.yaml_content);
          message.success(`已加载: ${name}`);
        } else {
          fromYAML("nodes: []");
          message.info("该 Pipeline 暂无配置");
        }
        setEditorOpen(true);
      })
      .catch(() => message.error("加载 Pipeline 配置失败"));
  }

  function handleSavePipeline() {
    if (!selectedPipelineId) {
      message.warning("请先选择一个 Pipeline");
      return;
    }
    modal.confirm({
      title: "确认保存",
      icon: <ExclamationCircleOutlined />,
      content: `确定要保存 Pipeline「${selectedPipelineName}」的配置吗？将创建新版本。`,
      okText: "确认保存",
      cancelText: "取消",
      onOk: () => {
        setSaving(true);
        const exported = toYAML();
        const pipeline = data.find((p) => p.pipeline_id === selectedPipelineId);
        const fullYaml = pipeline
          ? `pipeline:\n  name: ${selectedPipelineId}\n  mode: ${pipeline.mode}\n  version: "${pipeline.version}"\n\n${exported}`
          : exported;
        dagAPI
          .save(selectedPipelineId!, fullYaml)
          .then((res) => {
            message.success({
              content: `保存成功！新版本: v${res.version}`,
              icon: <CheckCircleOutlined style={{ color: "#52c41a" }} />,
            });
            setDirty(false);
            dagAPI
              .list()
              .then((r) => setPipelines(r.pipelines))
              .catch(() => {});
          })
          .catch(() => message.error("保存失败，请稍后重试"))
          .finally(() => setSaving(false));
      },
    });
  }

  // --- Node config change handler ---
  const handleConfigChange = useCallback(
    (nodeId: string, key: string, value: unknown) => {
      const { nodes: currentNodes, setNodes } = useDagStore.getState();
      setNodes(
        currentNodes.map((n) => {
          if (n.id !== nodeId) return n;
          const oldConfig = (n.data?.config as Record<string, unknown>) || {};
          return {
            ...n,
            data: { ...n.data, config: { ...oldConfig, [key]: value } },
          };
        }),
      );
    },
    [],
  );

  // --- Node click → open config drawer ---
  const handleNodeClick = useCallback(
    (node: Node) => {
      setSelectedNode(node);
      openConfigDrawer(node.id);
    },
    [setSelectedNode, openConfigDrawer],
  );

  // --- Node toolbar callbacks ---
  const handleNodeEdit = useCallback(
    (nodeId: string) => {
      openConfigDrawer(nodeId);
    },
    [openConfigDrawer],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      modal.confirm({
        title: "删除节点",
        content: `确定要删除节点「${nodeId}」吗？`,
        okText: "删除",
        okType: "danger",
        cancelText: "取消",
        onOk: () => removeNode(nodeId),
      });
    },
    [removeNode, modal],
  );

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const source = nodes.find((n) => n.id === nodeId);
      if (!source) return;
      nodeIdCounter += 1;
      const newNode: Node = {
        id: `${source.data?.subType || "node"}_${nodeIdCounter}`,
        type: "custom",
        position: { x: source.position.x + 40, y: source.position.y + 40 },
        data: {
          ...source.data,
          config: {
            ...((source.data?.config as Record<string, unknown>) || {}),
          },
        },
      };
      addNode(newNode);
      message.success(`已复制节点: ${newNode.id}`);
    },
    [nodes, addNode],
  );

  // --- Drop handler (coordinates come from ReactFlowEditor) ---
  const handleCanvasDrop = useCallback(
    (position: { x: number; y: number }, nodeType: string, subType: string) => {
      nodeIdCounter += 1;
      const newNode: Node = {
        id: `${subType}_${nodeIdCounter}`,
        type: "custom",
        position,
        data: { label: subType, nodeType, subType, config: {} },
      };
      addNode(newNode);
    },
    [addNode],
  );

  // --- YAML drawer ---
  function handleExportYaml() {
    const exported = toYAML();
    setYaml(exported);
    setDrawerOpen(true);
  }

  function handleImportYaml() {
    if (!yaml.trim()) {
      message.warning("YAML 内容为空");
      return;
    }
    fromYAML(yaml);
    setDrawerOpen(false);
    message.success("YAML 已导入到编辑器");
  }

  // --- Delete pipeline ---
  function handleDeletePipeline(pipelineId: string, name: string) {
    modal.confirm({
      title: "删除 Pipeline",
      icon: <ExclamationCircleOutlined />,
      content: `确定要删除 Pipeline「${name}」吗？此操作不可恢复。`,
      okText: "确认删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => {
        dagAPI
          .delete(pipelineId)
          .then(() => {
            message.success(`已删除: ${name}`);
            // If deleted the currently selected pipeline, clear editor
            if (selectedPipelineId === pipelineId) {
              setSelectedPipelineId(null);
              setSelectedPipelineName("");
              fromYAML("nodes: []");
              closeConfigDrawer();
            }
            dagAPI
              .list()
              .then((r) => setPipelines(r.pipelines))
              .catch(() => {});
          })
          .catch(() => message.error("删除失败"));
      },
    });
  }

  // --- Table columns ---
  const columns = [
    {
      title: "Pipeline",
      dataIndex: "name",
      key: "name",
      render: (text: string, record: PipelineInfo) => (
        <a onClick={() => handleLoadPipeline(record.pipeline_id, text)}>
          {text}
        </a>
      ),
    },
    {
      title: "模式",
      dataIndex: "mode",
      key: "mode",
      render: (m: string) => (
        <Tag color={m === "realtime" ? "blue" : "orange"}>{m}</Tag>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => (
        <Tag
          color={
            s === "running" ? "green" : s === "stopped" ? "red" : "default"
          }
        >
          {s}
        </Tag>
      ),
    },
    { title: "版本", dataIndex: "version", key: "version" },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (t: string | undefined) =>
        t ? new Date(t).toLocaleString("zh-CN") : "-",
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, record: PipelineInfo) => {
        const editable = canEditOrDelete(record.status);
        return (
          <div onClick={(e) => e.stopPropagation()}>
            <Space size="small">
              {record.status !== "running" ? (
                <Tooltip title="启动">
                  <Button
                    type="text"
                    size="small"
                    icon={<PlayCircleOutlined />}
                    loading={loadingId === record.pipeline_id}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStart(record.pipeline_id);
                    }}
                  />
                </Tooltip>
              ) : (
                <Tooltip title="停止">
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<PauseCircleOutlined />}
                    loading={loadingId === record.pipeline_id}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStop(record.pipeline_id);
                    }}
                  />
                </Tooltip>
              )}
              <Tooltip title={editable ? "编辑" : "运行中不可编辑"}>
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  disabled={!editable}
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditPipeline({
                      pipeline_id: record.pipeline_id,
                      name: record.name,
                      mode: record.mode,
                    });
                    setEditOpen(true);
                  }}
                />
              </Tooltip>
              <Tooltip title="操作历史">
                <Button
                  type="text"
                  size="small"
                  icon={<HistoryOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleShowHistory(record.pipeline_id);
                  }}
                />
              </Tooltip>
              <Tooltip title={editable ? "删除" : "运行中不可删除"}>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={!editable}
                  data-row-action
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    if (editable)
                      handleDeletePipeline(record.pipeline_id, record.name);
                  }}
                />
              </Tooltip>
            </Space>
          </div>
        );
      },
    },
  ];

  // --- Build collapsible config items for right drawer（与新建弹窗一致：可编辑节点名称、点击名字聚焦）---
  const collapseItems = nodes.map((node) => {
    const subType = (node.data?.subType as string) || "";
    const schema = getSchemaForNode(subType);
    const nodeType = (node.data?.nodeType as string) || "transform";
    const colorMap: Record<string, string> = {
      ingest: "#1677ff",
      transform: "#52c41a",
      infer: "#722ed1",
      filter: "#fa8c16",
      sink: "#f5222d",
    };
    const color = colorMap[nodeType] || "#1677ff";

    return {
      key: node.id,
      label: (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Tag color={color} style={{ margin: 0 }}>
            {subType}
          </Tag>
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              setSelectedNode(node);
              openConfigDrawer(node.id);
              setFocusNodeId(node.id);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.stopPropagation();
                setSelectedNode(node);
                openConfigDrawer(node.id);
                setFocusNodeId(node.id);
              }
            }}
            style={{
              color: "#d1d5db",
              fontSize: 12,
              cursor: "pointer",
              textDecoration: "underline",
              textUnderlineOffset: 2,
            }}
          >
            {node.id}
          </span>
        </div>
      ),
      extra: (
        <Tooltip title="删除节点">
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              handleDeleteNode(node.id);
            }}
          />
        </Tooltip>
      ),
      children: (
        <NodeConfigForm
          key={node.id}
          node={node}
          schema={schema}
          onConfigChange={handleConfigChange}
          onRenameNode={renameNode}
          onDeleteNode={handleDeleteNode}
          renderConfigField={renderConfigField}
          focusNodeId={focusNodeId}
          onFocusNodeNameDone={() => setFocusNodeId(null)}
        />
      ),
    };
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        gap: 12,
      }}
    >
      {/* Stats cards */}
      <Row gutter={[12, 12]}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ borderColor: "#1f2937" }}>
            <Statistic
              title="Pipeline 总数"
              value={pipelineStats?.total ?? 0}
              prefix={<AppstoreOutlined />}
              valueStyle={{ color: "#e8e8e8" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ borderColor: "#1f2937" }}>
            <Statistic
              title="运行中"
              value={pipelineStats?.running ?? 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ borderColor: "#1f2937" }}>
            <Statistic
              title="已停止 / 未激活"
              value={
                (pipelineStats?.stopped ?? 0) + (pipelineStats?.inactive ?? 0)
              }
              prefix={<StopOutlined />}
              valueStyle={{ color: "#8c8c8c" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ borderColor: "#1f2937" }}>
            <Statistic
              title="告警 Pipeline 占比"
              value={pipelineStats?.alert_rate ?? 0}
              suffix="%"
              prefix={<AlertOutlined />}
              valueStyle={{ color: "#faad14" }}
            />
          </Card>
        </Col>
      </Row>

      {/* Top: Pipeline list */}
      <div ref={cardRef}>
        <Card
          size="small"
          title="Pipeline 列表"
          extra={
            <Button
              type="primary"
              icon={<PlusOutlined />}
              size="small"
              onClick={() => setCreateOpen(true)}
            >
              新建 Pipeline
            </Button>
          }
        >
          {/* Search filters */}
          <Row gutter={12} style={{ marginBottom: 12 }}>
            <Col span={6}>
              <Input
                placeholder="Pipeline 名称"
                prefix={<SearchOutlined />}
                allowClear
                value={filterName}
                onChange={(e) => setFilterName(e.target.value)}
              />
            </Col>
            <Col span={4}>
              <Select
                placeholder="状态"
                allowClear
                style={{ width: "100%" }}
                value={filterStatus}
                onChange={(v) => setFilterStatus(v)}
                options={[
                  { label: "运行中", value: "running" },
                  { label: "已停止", value: "stopped" },
                  { label: "未激活", value: "inactive" },
                ]}
              />
            </Col>
            <Col span={5}>
              <DatePicker
                placeholder="开始时间"
                style={{ width: "100%" }}
                onChange={(_d, ds) => {
                  const s = typeof ds === "string" ? ds : "";
                  setFilterDateRange((prev) => [s, prev?.[1] ?? ""]);
                }}
              />
            </Col>
            <Col span={5}>
              <DatePicker
                placeholder="结束时间"
                style={{ width: "100%" }}
                onChange={(_d, ds) => {
                  const s = typeof ds === "string" ? ds : "";
                  setFilterDateRange((prev) => [prev?.[0] ?? "", s]);
                }}
              />
            </Col>
            <Col span={4}>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  setFilterName("");
                  setFilterStatus(undefined);
                  setFilterDateRange(null);
                }}
              >
                重置
              </Button>
            </Col>
          </Row>
          <Table
            dataSource={data}
            columns={columns}
            rowKey="pipeline_id"
            size="small"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        </Card>
      </div>
      <Modal
        open={editorOpen}
        onCancel={() => {
          setEditorOpen(false);
          closeConfigDrawer();
        }}
        footer={null}
        width={
          cardBodyWidth && cardBodyWidth > 100
            ? Math.min(cardBodyWidth - 40, 1200)
            : "75vw"
        }
        style={{ minWidth: 760, maxWidth: 1200, top: 60 }}
        styles={{
          body: {
            padding: 0,
            overflow: "hidden",
            minHeight: 380,
            height: "min(calc(100vh - 200px), 660px)",
            maxHeight: "80vh",
            display: "flex",
            flexDirection: "column",
          },
        }}
        title={
          <Space>
            <span>DAG 可视化编排</span>
            <Tag color="blue">{selectedPipelineName}</Tag>
          </Space>
        }
        destroyOnClose
      >
        {/* Toolbar */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            padding: "8px 12px",
            borderBottom: "1px solid #1f2937",
          }}
        >
          <Space>
            <Button
              icon={<CodeOutlined />}
              size="small"
              onClick={handleExportYaml}
            >
              YAML
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              size="small"
              loading={saving}
              onClick={handleSavePipeline}
              disabled={!dirty}
            >
              保存
            </Button>
          </Space>
        </div>
        {/* Editor body：与新建第二步窗口同高、同布局，节点列 248px 避免遮挡 */}
        <Row style={{ flex: 1, minHeight: 0, height: "100%" }}>
          <Col
            flex="0 0 248px"
            style={{
              height: "100%",
              width: 248,
              minWidth: 248,
              maxWidth: 248,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: "auto",
                overflowX: "hidden",
                scrollbarGutter: "stable",
              }}
            >
              <NodePalette />
            </div>
          </Col>
          <Col flex="auto" style={{ position: "relative", height: "100%" }}>
            <ReactFlowEditor
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={handleNodeClick}
              onPaneClick={() => {
                setSelectedNode(null);
                closeConfigDrawer();
              }}
              selectedNodeId={selectedNode?.id}
              onNodeEdit={handleNodeEdit}
              onNodeDelete={handleDeleteNode}
              onNodeDuplicate={handleDuplicateNode}
              onDropNode={handleCanvasDrop}
              showMinimap={false}
            />
          </Col>
          {/* Right: config panel */}
          {configDrawerOpen && (
            <Col
              flex="380px"
              style={{
                borderLeft: "1px solid #1f2937",
                background: "#0d1117",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "10px 12px",
                  borderBottom: "1px solid #1f2937",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Space>
                  <SettingOutlined style={{ color: "#e8e8e8" }} />
                  <span
                    style={{ color: "#e8e8e8", fontWeight: 600, fontSize: 13 }}
                  >
                    节点配置
                  </span>
                  {nodes.length > 0 && <Tag>{nodes.length} 个节点</Tag>}
                </Space>
                <Button
                  type="text"
                  size="small"
                  onClick={() => setSelectedNode(null)}
                  style={{ color: "#8c8c8c" }}
                >
                  收起全部
                </Button>
              </div>
              <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
                {nodes.length === 0 ? (
                  <Empty description="画布中暂无节点" />
                ) : (
                  <Collapse
                    accordion
                    activeKey={selectedNode?.id ? [selectedNode.id] : undefined}
                    onChange={(keys) => {
                      const key = Array.isArray(keys) ? keys[0] : keys;
                      if (key) {
                        const node = nodes.find((n) => n.id === key);
                        if (node) setSelectedNode(node);
                      } else {
                        setSelectedNode(null);
                      }
                    }}
                    items={collapseItems}
                  />
                )}
              </div>
            </Col>
          )}
        </Row>
      </Modal>

      {/* YAML Drawer */}
      <Drawer
        title="YAML 编辑"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={520}
        extra={
          <Button type="primary" size="small" onClick={handleImportYaml}>
            导入到编辑器
          </Button>
        }
      >
        <TextArea
          value={yaml}
          onChange={(e) => setYaml(e.target.value)}
          rows={24}
          style={{ fontFamily: "monospace", fontSize: 12 }}
        />
      </Drawer>

      {/* History Drawer */}
      <Drawer
        title={`操作历史 — ${historyPipelineId}`}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        width={420}
      >
        {historyData.length === 0 ? (
          <Empty description="暂无操作记录" />
        ) : (
          <Timeline
            items={historyData.map((h) => ({
              color:
                h.status === "success"
                  ? "green"
                  : h.status === "failed"
                    ? "red"
                    : "blue",
              children: (
                <div>
                  <div>
                    <strong>{h.operation}</strong> — {h.operator}
                  </div>
                  <div style={{ fontSize: 12, color: "#888" }}>
                    {h.created_at}
                  </div>
                  {h.detail && Object.keys(h.detail).length > 0 && (
                    <pre
                      style={{ fontSize: 11, color: "#aaa", margin: "4px 0 0" }}
                    >
                      {JSON.stringify(h.detail, null, 2)}
                    </pre>
                  )}
                </div>
              ),
            }))}
          />
        )}
      </Drawer>

      {/* Create Pipeline Modal */}
      <CreatePipelineModal
        open={createOpen}
        containerWidth={cardBodyWidth}
        onCancel={() => setCreateOpen(false)}
        onCreated={(pipelineId, name, yamlContent) => {
          setCreateOpen(false);
          message.success(`创建成功: ${name}`);
          dagAPI
            .list()
            .then((r) => {
              setPipelines(r.pipelines);
              setSelectedPipelineId(pipelineId);
              setSelectedPipelineName(name);
              setDirty(false);
              prevNodesLen.current = 0;
              fromYAML(yamlContent);
            })
            .catch(() => {});
        }}
      />

      {/* Edit Pipeline Modal */}
      {editPipeline && (
        <CreatePipelineModal
          open={editOpen}
          containerWidth={cardBodyWidth}
          editMode
          editPipeline={editPipeline}
          onCancel={() => {
            setEditOpen(false);
            setEditPipeline(null);
          }}
          onCreated={() => {}}
          onSaved={(pipelineId, name) => {
            setEditOpen(false);
            setEditPipeline(null);
            message.success(`保存成功: ${name}`);
            dagAPI
              .list()
              .then((r) => setPipelines(r.pipelines))
              .catch(() => {});
          }}
        />
      )}
    </div>
  );
}

export default function Pipeline() {
  return (
    <ReactFlowProvider>
      <PipelineInner />
    </ReactFlowProvider>
  );
}
