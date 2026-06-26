import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type FocusEvent,
  type ReactNode,
} from "react";
import {
  Modal,
  Steps,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Button,
  Space,
  Row,
  Col,
  Tag,
  Typography,
  Collapse,
  Tooltip,
  Empty,
  message,
} from "antd";
import {
  SettingOutlined,
  DeleteOutlined,
  SaveOutlined,
  ArrowLeftOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import { ReactFlowProvider } from "@xyflow/react";
import type { Node } from "@xyflow/react";
import { dagAPI } from "@/services/api";
import {
  getSchemaForNode,
  type NodeConfigFieldSchema,
} from "./nodeConfigSchemas";
import { useDagStore } from "@/stores/dagStore";
import ReactFlowEditor from "./ReactFlowEditor";
import NodePalette from "./NodePalette";

const { TextArea } = Input;
const { Text } = Typography;

interface CreatePipelineModalProps {
  open: boolean;
  containerWidth?: number;
  onCancel: () => void;
  onCreated: (pipelineId: string, name: string, yamlContent: string) => void;
  /** 编辑模式 */
  editMode?: boolean;
  editPipeline?: {
    pipeline_id: string;
    name: string;
    mode: string;
    description?: string;
  };
  onSaved?: (pipelineId: string, name: string) => void;
}

const colorMap: Record<string, string> = {
  ingest: "#1677ff",
  transform: "#52c41a",
  infer: "#722ed1",
  filter: "#fa8c16",
  sink: "#f5222d",
};

let nodeIdCounter = 100;

function renderConfigField(field: NodeConfigFieldSchema) {
  switch (field.type) {
    case "number":
      return (
        <InputNumber
          style={{ width: "100%" }}
          placeholder={field.placeholder}
          step={
            field.placeholder && parseFloat(field.placeholder) < 1 ? 0.01 : 1
          }
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

interface EditorContentProps {
  onSave: () => void;
  onBack: () => void;
  saving: boolean;
  editMode?: boolean;
}

const NODE_ID_PATTERN = /^[a-zA-Z0-9_]+$/;

/** 单节点配置表单：持有一个 Form 实例，节点名称在 onBlur 时提交；不校验唯一性，仅保证格式与入库不乱。供 CreatePipelineModal 与 Pipeline 页共用。 */
export function NodeConfigForm({
  node,
  schema,
  onConfigChange,
  onRenameNode,
  onDeleteNode,
  renderConfigField,
  focusNodeId,
  onFocusNodeNameDone,
}: {
  node: Node;
  schema: ReturnType<typeof getSchemaForNode>;
  onConfigChange: (nodeId: string, key: string, value: unknown) => void;
  onRenameNode: (oldId: string, newId: string) => boolean;
  onDeleteNode: (nodeId: string) => void;
  renderConfigField: (field: NodeConfigFieldSchema) => ReactNode;
  focusNodeId?: string | null;
  onFocusNodeNameDone?: () => void;
}) {
  const [form] = Form.useForm();
  const nodeNameInputRef = useRef<HTMLInputElement | null>(null);
  const config = (node.data?.config as Record<string, unknown>) || {};
  const currentNodeId = node.id;

  const handleNodeNameBlur = useCallback(
    (e: FocusEvent<HTMLInputElement>) => {
      const v = (e.target.value ?? "").trim();
      if (!v || v === currentNodeId) return;
      if (!NODE_ID_PATTERN.test(v)) {
        form.setFieldsValue({ _nodeId: currentNodeId });
        return;
      }
      const ok = onRenameNode(currentNodeId, v);
      if (!ok) form.setFieldsValue({ _nodeId: currentNodeId });
    },
    [currentNodeId, onRenameNode, form],
  );

  useEffect(() => {
    if (focusNodeId === node.id) {
      nodeNameInputRef.current?.focus();
      onFocusNodeNameDone?.();
    }
  }, [focusNodeId, node.id, onFocusNodeNameDone]);

  return (
    <Form
      form={form}
      layout="vertical"
      size="small"
      initialValues={{ _nodeId: node.id, ...config }}
      onValuesChange={(changed) => {
        if ("_nodeId" in changed) return;
        Object.entries(changed).forEach(([k, v]) =>
          onConfigChange(node.id, k, v),
        );
      }}
    >
      <Form.Item
        label="节点名称"
        name="_nodeId"
        rules={[
          { required: true, message: "请输入节点名称" },
          {
            pattern: NODE_ID_PATTERN,
            message: "仅允许字母、数字和下划线",
          },
        ]}
      >
        <Input
          ref={nodeNameInputRef as never}
          placeholder="例如：whitelist_101"
          onBlur={handleNodeNameBlur}
        />
      </Form.Item>
      {schema ? (
        schema.fields.map((field) => (
          <Form.Item
            key={field.key}
            label={
              <span>
                {field.label}
                {field.placeholder && field.type !== "boolean" && (
                  <Tooltip title={field.placeholder}>
                    <QuestionCircleOutlined
                      style={{
                        marginLeft: 4,
                        color: "#595959",
                        fontSize: 11,
                      }}
                    />
                  </Tooltip>
                )}
              </span>
            }
            name={field.key}
            valuePropName={field.type === "boolean" ? "checked" : "value"}
            rules={
              field.required
                ? [{ required: true, message: `请填写 ${field.label}` }]
                : []
            }
          >
            {renderConfigField(field)}
          </Form.Item>
        ))
      ) : (
        <Text type="secondary">该节点类型暂无配置项</Text>
      )}
    </Form>
  );
}

function EditorContent({
  onSave,
  onBack,
  saving,
  editMode,
}: EditorContentProps) {
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
    openConfigDrawer,
    closeConfigDrawer,
  } = useDagStore();

  const handleNodeClick = useCallback(
    (node: Node) => {
      setSelectedNode(node);
      openConfigDrawer(node.id);
    },
    [setSelectedNode, openConfigDrawer],
  );

  const handleNodeEdit = useCallback(
    (nodeId: string) => {
      openConfigDrawer(nodeId);
    },
    [openConfigDrawer],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      removeNode(nodeId);
    },
    [removeNode],
  );

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const source = nodes.find((n) => n.id === nodeId);
      if (!source) return;
      nodeIdCounter += 1;
      addNode({
        id: `${source.data?.subType || "node"}_${nodeIdCounter}`,
        type: "custom",
        position: { x: source.position.x + 40, y: source.position.y + 40 },
        data: {
          ...source.data,
          config: {
            ...((source.data?.config as Record<string, unknown>) || {}),
          },
        },
      });
    },
    [nodes, addNode],
  );

  const handleCanvasDrop = useCallback(
    (position: { x: number; y: number }, nodeType: string, subType: string) => {
      nodeIdCounter += 1;
      addNode({
        id: `${subType}_${nodeIdCounter}`,
        type: "custom",
        position,
        data: { label: subType, nodeType, subType, config: {} },
      });
    },
    [addNode],
  );

  const handleConfigChange = useCallback(
    (nodeId: string, key: string, value: unknown) => {
      const { nodes: cur, setNodes } = useDagStore.getState();
      setNodes(
        cur.map((n) => {
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

  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  const collapseItems = nodes.map((node) => {
    const subType = (node.data?.subType as string) || "";
    const schema = getSchemaForNode(subType);
    const nodeType = (node.data?.nodeType as string) || "transform";
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
        height: "100%",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <Row style={{ flex: 1, minHeight: 0, height: "100%" }}>
        <Col
          flex="0 0 280px"
          style={{
            height: "100%",
            width: 280,
            minWidth: 280,
            maxWidth: 280,
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
              overflow: "auto",
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
        {configDrawerOpen && (
          <Col
            flex="0 0 280px"
            style={{
              borderLeft: "1px solid rgba(255,255,255,0.06)",
              background: "#0d1117",
              display: "flex",
              flexDirection: "column",
              height: "100%",
              width: 280,
              minWidth: 280,
              maxWidth: 280,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "10px 12px",
                borderBottom: "1px solid rgba(255,255,255,0.06)",
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
            <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
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
                    } else setSelectedNode(null);
                  }}
                  items={collapseItems}
                />
              )}
            </div>
          </Col>
        )}
      </Row>
      {/* Bottom action bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 16px",
          borderTop: "1px solid rgba(255,255,255,0.08)",
          background: "rgba(255,255,255,0.03)",
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
          上一步
        </Button>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={onSave}
        >
          {editMode ? "保存" : "保存并创建"}
        </Button>
      </div>
    </div>
  );
}

export default function CreatePipelineModal({
  open,
  containerWidth,
  onCancel,
  onCreated,
  editMode,
  editPipeline,
  onSaved,
}: CreatePipelineModalProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();
  const [creating, setCreating] = useState(false);
  const savedState = useRef<{ nodes: Node[]; edges: unknown[] } | null>(null);
  const formValues = useRef<{
    name: string;
    mode: string;
    description?: string;
  }>({ name: "", mode: "stream" });
  const { fromYAML, toYAML } = useDagStore();

  useEffect(() => {
    if (open) {
      const state = useDagStore.getState();
      savedState.current = { nodes: [...state.nodes], edges: [...state.edges] };
      setCreating(false);

      if (editMode && editPipeline) {
        // Edit mode: pre-fill form, load existing YAML, go directly to editor
        formValues.current = {
          name: editPipeline.name,
          mode: editPipeline.mode,
          description: editPipeline.description,
        };
        form.setFieldsValue({
          name: editPipeline.name,
          mode: editPipeline.mode,
          description: editPipeline.description,
        });
        setCurrentStep(1);
        // Load existing pipeline YAML
        dagAPI
          .get(editPipeline.pipeline_id)
          .then((r) => {
            if (r.yaml_content) fromYAML(r.yaml_content);
            else fromYAML("nodes: []");
          })
          .catch(() => fromYAML("nodes: []"));
      } else {
        // Create mode: reset everything
        setCurrentStep(0);
        form.resetFields();
        formValues.current = { name: "", mode: "stream" };
        fromYAML("nodes: []");
      }
    } else if (savedState.current) {
      const store = useDagStore.getState();
      store.setNodes(savedState.current.nodes as Node[]);
      store.setEdges(savedState.current.edges as never[]);
      savedState.current = null;
    }
  }, [open, form, fromYAML, editMode, editPipeline]);

  function handleNext() {
    if (currentStep === 0) {
      form.validateFields().then((values) => {
        formValues.current = values;
        setCurrentStep(1);
      });
    }
  }

  function handleSubmit() {
    const { name, mode } = formValues.current;
    if (!name) {
      message.warning("Pipeline 名称不能为空");
      return;
    }
    const yamlContent = toYAML();
    setCreating(true);

    if (editMode && editPipeline) {
      // Edit mode: save existing pipeline
      dagAPI
        .save(editPipeline.pipeline_id, yamlContent, name.trim(), mode)
        .then((res) => {
          onSaved?.(res.pipeline_id, name.trim());
        })
        .catch((err) => {
          message.error(`保存失败: ${err.message || "未知错误"}`);
        })
        .finally(() => setCreating(false));
    } else {
      // Create mode
      dagAPI
        .create(name.trim(), mode, yamlContent)
        .then((res) => onCreated(res.pipeline_id, res.name, yamlContent))
        .catch((err) => {
          message.error(`创建失败: ${err.message || "未知错误"}`);
        })
        .finally(() => setCreating(false));
    }
  }

  const fullWidth =
    containerWidth && containerWidth > 100
      ? Math.min(containerWidth - 40, 1200)
      : "75vw";

  return (
    <Modal
      title={null}
      open={open}
      onCancel={onCancel}
      width={fullWidth}
      style={{ minWidth: 760, maxWidth: 1200, top: 60 }}
      destroyOnClose
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
      footer={null}
    >
      {/* Header */}
      <div
        style={{
          textAlign: "center",
          padding: "16px 0 4px",
        }}
      >
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            letterSpacing: 1,
          }}
        >
          {editMode ? "编辑 Pipeline" : "新建 Pipeline"}
        </div>
        <div style={{ color: "#8c8c8c", fontSize: 12, marginTop: 2 }}>
          {editMode
            ? "修改基本信息或通过可视化编排调整检测流水线"
            : "配置基本信息并通过可视化编排构建检测流水线"}
        </div>
      </div>

      <div style={{ padding: "0 32px" }}>
        <Steps
          current={currentStep}
          size="small"
          style={{ marginBottom: 16 }}
          items={[{ title: "基本信息" }, { title: "可视化编排" }]}
        />
      </div>

      {/* Content area */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          padding: "0 24px 16px",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {currentStep === 0 && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "flex-start",
              paddingTop: 32,
              flex: 1,
              minHeight: 0,
            }}
          >
            <div style={{ width: 480 }}>
              <Form
                form={form}
                layout="vertical"
                initialValues={{ mode: "stream" }}
                size="large"
              >
                <Form.Item
                  label="Pipeline 名称"
                  name="name"
                  rules={[{ required: true, message: "请输入 Pipeline 名称" }]}
                >
                  <Input placeholder="例如：DGA 实时检测流水线" />
                </Form.Item>
                <Form.Item label="运行模式" name="mode">
                  <Select
                    options={[
                      { label: "实时流 (stream)", value: "stream" },
                      { label: "批处理 (batch)", value: "batch" },
                    ]}
                  />
                </Form.Item>
                <Form.Item label="描述" name="description">
                  <TextArea rows={4} placeholder="可选：描述该流水线的用途" />
                </Form.Item>
                <Form.Item
                  style={{ textAlign: "center", marginBottom: 0, marginTop: 8 }}
                >
                  <Button
                    type="primary"
                    size="large"
                    onClick={handleNext}
                    style={{ minWidth: 200 }}
                  >
                    下一步
                  </Button>
                </Form.Item>
              </Form>
            </div>
          </div>
        )}

        {currentStep === 1 && (
          <div
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <ReactFlowProvider>
              <EditorContent
                onSave={handleSubmit}
                onBack={() => setCurrentStep(0)}
                saving={creating}
                editMode={editMode}
              />
            </ReactFlowProvider>
          </div>
        )}
      </div>
    </Modal>
  );
}
