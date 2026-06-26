import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  BackgroundVariant,
  NodeToolbar,
  useReactFlow,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button, Tooltip } from "antd";
import { EditOutlined, DeleteOutlined, CopyOutlined } from "@ant-design/icons";

const NODE_COLORS: Record<string, string> = {
  ingest: "#1677ff",
  transform: "#52c41a",
  infer: "#722ed1",
  filter: "#fa8c16",
  sink: "#f5222d",
};

/** 选中态：每类节点不同颜色的边框光影（主色 + 辅色渐变光晕） */
const SELECTED_GLOW: Record<
  string,
  { border: string; shadow: string; secondary?: string }
> = {
  ingest: {
    border: "#36cfc9",
    secondary: "#1677ff",
    shadow:
      "0 0 0 2px rgba(54, 207, 201, 0.6), 0 0 16px rgba(54, 207, 201, 0.5), 0 0 32px rgba(22, 119, 255, 0.25)",
  },
  transform: {
    border: "#73d13d",
    secondary: "#95de64",
    shadow:
      "0 0 0 2px rgba(115, 209, 61, 0.6), 0 0 16px rgba(115, 209, 61, 0.5), 0 0 32px rgba(82, 196, 26, 0.25)",
  },
  infer: {
    border: "#b37feb",
    secondary: "#36cfc9",
    shadow:
      "0 0 0 2px rgba(179, 127, 235, 0.7), 0 0 20px rgba(179, 127, 235, 0.5), 0 0 40px rgba(54, 207, 201, 0.3)",
  },
  filter: {
    border: "#ffc53d",
    secondary: "#ff9c6b",
    shadow:
      "0 0 0 2px rgba(255, 197, 61, 0.6), 0 0 16px rgba(255, 197, 61, 0.5), 0 0 32px rgba(250, 140, 22, 0.25)",
  },
  sink: {
    border: "#ff7875",
    secondary: "#ff4d4f",
    shadow:
      "0 0 0 2px rgba(255, 120, 117, 0.6), 0 0 16px rgba(255, 120, 117, 0.5), 0 0 32px rgba(245, 34, 45, 0.3)",
  },
};

const CATEGORY_LABELS: Record<string, string> = {
  ingest: "数据接入",
  transform: "数据转换",
  infer: "模型推理",
  filter: "过滤规则",
  sink: "数据输出",
};

interface ReactFlowEditorProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
  onNodeClick?: (node: Node) => void;
  onPaneClick?: () => void;
  selectedNodeId?: string | null;
  onNodeEdit?: (nodeId: string) => void;
  onNodeDelete?: (nodeId: string) => void;
  onNodeDuplicate?: (nodeId: string) => void;
  onDropNode?: (
    position: { x: number; y: number },
    nodeType: string,
    subType: string,
  ) => void;
  /** 弹窗内可设为 false，避免小地图遮挡画布 */
  showMinimap?: boolean;
}

function CustomNode({
  data,
  selected,
  id,
}: {
  data: Record<string, unknown>;
  selected?: boolean;
  id: string;
}) {
  const nodeType = (data.nodeType as string) || "ingest";
  const color = NODE_COLORS[nodeType] || "#1677ff";
  const glow = SELECTED_GLOW[nodeType] || SELECTED_GLOW.ingest;
  const catLabel = CATEGORY_LABELS[nodeType] || nodeType;
  const configKeys = Object.keys(
    (data.config as Record<string, unknown>) || {},
  );
  const onEdit = data.onEdit as ((id: string) => void) | undefined;
  const onDelete = data.onDelete as ((id: string) => void) | undefined;
  const onDuplicate = data.onDuplicate as ((id: string) => void) | undefined;

  return (
    <>
      <NodeToolbar
        isVisible={selected || undefined}
        position={Position.Top}
        offset={8}
        style={{
          display: "flex",
          gap: 4,
          background: "#1a1f2e",
          borderRadius: 6,
          padding: "4px 6px",
          border: "1px solid #2d3748",
        }}
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
        }}
      >
        <Tooltip title="编辑配置">
          <Button
            size="small"
            type="primary"
            ghost
            icon={<EditOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onEdit?.(id);
            }}
            style={{ borderColor: color, color }}
          />
        </Tooltip>
        <Tooltip title="复制节点">
          <Button
            size="small"
            ghost
            icon={<CopyOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onDuplicate?.(id);
            }}
            style={{ borderColor: "#8c8c8c", color: "#8c8c8c" }}
          />
        </Tooltip>
        <Tooltip title="删除节点">
          <Button
            size="small"
            danger
            ghost
            icon={<DeleteOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              if (typeof onDelete === "function") onDelete(id);
            }}
          />
        </Tooltip>
      </NodeToolbar>

      <div
        style={{
          padding: "10px 16px",
          borderRadius: 12,
          border: selected ? `2px solid ${glow.border}` : `2px solid ${color}`,
          outline: selected ? `1px solid ${glow.secondary ?? glow.border}` : "none",
          outlineOffset: selected ? 2 : 0,
          background: selected
            ? `linear-gradient(145deg, ${color}22 0%, ${color}08 100%)`
            : `${color}18`,
          color: "#e8e8e8",
          fontWeight: 600,
          fontSize: 13,
          textAlign: "center",
          minWidth: 130,
          boxShadow: selected
            ? `${glow.shadow}, inset 0 1px 0 rgba(255,255,255,0.06)`
            : "0 2px 8px rgba(0,0,0,0.3)",
          transition: "border 0.2s, box-shadow 0.25s, outline 0.2s, background 0.2s",
        }}
      >
        <Handle
          type="target"
          position={Position.Left}
          style={{ background: color, width: 8, height: 8 }}
        />
        <div style={{ fontSize: 10, color, marginBottom: 2, fontWeight: 400 }}>
          {catLabel}
        </div>
        <div style={{ color, fontSize: 14, fontWeight: 700 }}>
          {data.label as string}
        </div>
        {configKeys.length > 0 && (
          <div style={{ fontSize: 10, color: "#8c8c8c", marginTop: 4 }}>
            {configKeys.length} 项配置
          </div>
        )}
        <Handle
          type="source"
          position={Position.Right}
          style={{ background: color, width: 8, height: 8 }}
        />
      </div>
    </>
  );
}

const nodeTypes: NodeTypes = { custom: CustomNode };

export default function ReactFlowEditor({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onPaneClick,
  selectedNodeId,
  onNodeEdit,
  onNodeDelete,
  onNodeDuplicate,
  onDropNode,
  showMinimap = true,
}: ReactFlowEditorProps) {
  const { screenToFlowPosition, fitView } = useReactFlow();

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeClick?.(node),
    [onNodeClick],
  );
  const handlePaneClick = useCallback(() => onPaneClick?.(), [onPaneClick]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const nodeType = e.dataTransfer.getData("application/reactflow-type");
      const subType = e.dataTransfer.getData("application/reactflow-subtype");
      if (!nodeType || !subType) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      onDropNode?.(position, nodeType, subType);
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
    },
    [screenToFlowPosition, fitView, onDropNode],
  );

  const miniMapNodeColor = useCallback((node: Node) => {
    const nt = (node.data?.nodeType as string) || "ingest";
    return NODE_COLORS[nt] || "#1677ff";
  }, []);

  const styledNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        type: "custom",
        selected: n.id === selectedNodeId,
        data: {
          ...n.data,
          onEdit: onNodeEdit,
          onDelete: onNodeDelete,
          onDuplicate: onNodeDuplicate,
        },
      })),
    [nodes, selectedNodeId, onNodeEdit, onNodeDelete, onNodeDuplicate],
  );

  const styledEdges = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        animated: true,
        style: { stroke: "#4a5568", strokeWidth: 2 },
      })),
    [edges],
  );

  return (
    <div style={{ width: "100%", height: "100%" }} className="react-flow-editor-with-controls">
      <style>{`
        .react-flow__node:hover .react-flow__node-toolbar {
          opacity: 1 !important;
          visibility: visible !important;
        }
        /* 画布缩放控件更醒目：蓝色图标与边框 */
        .react-flow-editor-with-controls .react-flow__controls {
          box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          border: 1px solid #1677ff !important;
          border-radius: 8px;
          overflow: hidden;
        }
        .react-flow-editor-with-controls .react-flow__controls-button {
          background: #1e3a5f !important;
          color: #60a5fa !important;
          border-color: #2563eb !important;
          fill: #60a5fa !important;
        }
        .react-flow-editor-with-controls .react-flow__controls-button:hover {
          background: #2563eb !important;
          color: #fff !important;
          fill: #fff !important;
        }
        .react-flow-editor-with-controls .react-flow__controls-button svg {
          fill: currentColor;
        }
        /* 隐藏 React Flow 署名/水印 */
        .react-flow__attribution,
        .react-flow__panel a[href*="reactflow"],
        .react-flow__panel a[href*="xyflow"] {
          display: none !important;
        }
      `}</style>
      <ReactFlow
        nodes={styledNodes}
        edges={styledEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        defaultEdgeOptions={{
          animated: true,
          style: { stroke: "#4a5568", strokeWidth: 2 },
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#1f2937"
        />
        <Controls
          style={{
            background: "#1e3a5f",
            border: "1px solid #2563eb",
            borderRadius: 8,
          }}
        />
        {showMinimap && (
          <MiniMap
            nodeColor={miniMapNodeColor}
            zoomable
            pannable
            style={{ background: "#0a0e1a", borderColor: "#1f2937" }}
          />
        )}
      </ReactFlow>
    </div>
  );
}
