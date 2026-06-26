import { create } from 'zustand';
import type { Node, Edge, OnNodesChange, OnEdgesChange, Connection } from '@xyflow/react';
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react';
import yaml from 'js-yaml';

interface DagState {
  nodes: Node[];
  edges: Edge[];
  selectedNode: Node | null;
  configDrawerOpen: boolean;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  addNode: (node: Node) => void;
  removeNode: (nodeId: string) => void;
  /** 重命名节点 ID，并更新所有相关边；若 newId 已被其他节点占用则返回 false */
  renameNode: (oldId: string, newId: string) => boolean;
  setSelectedNode: (node: Node | null) => void;
  openConfigDrawer: (nodeId?: string) => void;
  closeConfigDrawer: () => void;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (connection: Connection) => void;
  toYAML: () => string;
  fromYAML: (yamlStr: string) => void;
}

interface PipelineStage {
  id: string;
  type: string;
  subType: string;
  config?: Record<string, unknown>;
}

interface PipelineConfig {
  stages?: PipelineStage[];
  connections?: { source: string; target: string }[];
  // Real pipeline YAML format
  nodes?: { id: string; type: string; config?: Record<string, unknown> }[];
}

/** Map real node type → editor category */
const TYPE_TO_CATEGORY: Record<string, string> = {
  kafka_consumer: 'ingest',
  file_reader: 'ingest',
  es_source: 'ingest',
  dns_parser: 'transform',
  feature_extractor: 'transform',
  severity_tag: 'transform',
  threat_intel_enrich: 'transform',
  geoip_lookup: 'transform',
  risk_aggregate: 'transform',
  scoring_service: 'infer',
  family_classify: 'infer',
  whitelist: 'filter',
  threshold: 'filter',
  blacklist: 'filter',
  es_sink: 'sink',
  kafka_sink: 'sink',
  starrocks_sink: 'sink',
  fan_out: 'sink',
  multi_sink: 'sink',
};

export const useDagStore = create<DagState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNode: null,
  configDrawerOpen: false,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  addNode: (node) => set((s) => ({ nodes: [...s.nodes, node] })),

  removeNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNode: s.selectedNode?.id === nodeId ? null : s.selectedNode,
      configDrawerOpen: s.selectedNode?.id === nodeId ? false : s.configDrawerOpen,
    })),

  renameNode: (oldId, newId) => {
    const { nodes, edges, selectedNode } = get();
    const trimmed = (newId ?? '').trim();
    if (!trimmed || trimmed === oldId) return true;
    const exists = nodes.some((n) => n.id === trimmed);
    if (exists) return false;
    const newNodes = nodes.map((n) =>
      n.id === oldId ? { ...n, id: trimmed } : n,
    );
    const newEdges = edges.map((e) => ({
      ...e,
      source: e.source === oldId ? trimmed : e.source,
      target: e.target === oldId ? trimmed : e.target,
    }));
    const newSelected =
      selectedNode?.id === oldId
        ? { ...selectedNode, id: trimmed }
        : selectedNode;
    set({ nodes: newNodes, edges: newEdges, selectedNode: newSelected });
    return true;
  },

  setSelectedNode: (node) => set({ selectedNode: node }),

  openConfigDrawer: (nodeId) => {
    if (nodeId) {
      const node = get().nodes.find((n) => n.id === nodeId);
      if (node) set({ selectedNode: node, configDrawerOpen: true });
      else set({ configDrawerOpen: true });
    } else {
      set({ configDrawerOpen: true });
    }
  },

  closeConfigDrawer: () => set({ configDrawerOpen: false }),

  onNodesChange: (changes) =>
    set((s) => ({ nodes: applyNodeChanges(changes, s.nodes) })),

  onEdgesChange: (changes) =>
    set((s) => ({ edges: applyEdgeChanges(changes, s.edges) })),

  onConnect: (connection) =>
    set((s) => ({ edges: addEdge(connection, s.edges) })),

  toYAML: () => {
    const { nodes, edges } = get();
    const config = {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: (n.data?.subType as string) || (n.data?.nodeType as string) || 'unknown',
        ...(n.data?.config && Object.keys(n.data.config as object).length > 0
          ? { config: n.data.config as Record<string, unknown> }
          : {}),
      })),
      connections: edges.map((e) => ({ source: e.source, target: e.target })),
    };
    return yaml.dump(config, { indent: 2 });
  },

  fromYAML: (yamlStr) => {
    try {
      const config = yaml.load(yamlStr) as PipelineConfig;
      if (!config) return;

      let parsedNodes: Node[] = [];
      let parsedEdges: Edge[] = [];

      if (config.stages && config.stages.length > 0) {
        // Editor's own format: stages with type/subType
        parsedNodes = config.stages.map((stage, i) => ({
          id: stage.id,
          type: 'custom',
          position: { x: 250 * (i % 5), y: 120 * Math.floor(i / 5) },
          data: {
            label: stage.subType || stage.id,
            nodeType: stage.type,
            subType: stage.subType,
            config: stage.config || {},
          },
        }));
        parsedEdges = (config.connections || []).map((conn, i) => ({
          id: `e-${i}`,
          source: conn.source,
          target: conn.target,
        }));
      } else if (config.nodes && config.nodes.length > 0) {
        // Real pipeline YAML format: nodes with type being the actual node type
        parsedNodes = config.nodes.map((node, i) => {
          const category = TYPE_TO_CATEGORY[node.type] || 'transform';
          return {
            id: node.id,
            type: 'custom',
            position: { x: 250 * (i % 5), y: 120 * Math.floor(i / 5) },
            data: {
              label: node.type,
              nodeType: category,
              subType: node.type,
              config: node.config || {},
            },
          };
        });
        // Use explicit connections if present, otherwise infer sequential
        if (config.connections && config.connections.length > 0) {
          parsedEdges = config.connections.map((conn, i) => ({
            id: `e-${i}`,
            source: conn.source,
            target: conn.target,
          }));
        } else {
          // Infer sequential connections from node order
          parsedEdges = config.nodes.slice(0, -1).map((node, i) => ({
            id: `e-${i}`,
            source: node.id,
            target: config.nodes![i + 1].id,
          }));
        }
      } else {
        // Empty or unrecognized format
        set({ nodes: [], edges: [], selectedNode: null });
        return;
      }

      set({ nodes: parsedNodes, edges: parsedEdges, selectedNode: null });
    } catch {
      console.error('Failed to parse YAML pipeline config');
    }
  },
}));
