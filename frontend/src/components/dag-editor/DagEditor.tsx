import { useState } from 'react';
import { Tag } from 'antd';

export interface DagNode {
  id: string;
  label: string;
  type: string;
  color: string;
  config?: Record<string, unknown>;
}

export interface DagEditorProps {
  nodes: DagNode[];
  onNodeClick?: (node: DagNode) => void;
}

const NODE_WIDTH = 120;
const NODE_HEIGHT = 56;
const GAP = 48;
const ARROW_SIZE = 8;

export default function DagEditor({ nodes, onNodeClick }: DagEditorProps) {
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const totalWidth = nodes.length * (NODE_WIDTH + GAP) - GAP;
  const svgHeight = NODE_HEIGHT + 40;

  function handleClick(node: DagNode) {
    setActiveNode(node.id === activeNode ? null : node.id);
    onNodeClick?.(node);
  }

  return (
    <div style={{ overflowX: 'auto', padding: '16px 0' }}>
      <svg
        width={Math.max(totalWidth + 40, 200)}
        height={svgHeight}
        viewBox={`0 0 ${Math.max(totalWidth + 40, 200)} ${svgHeight}`}
        style={{ display: 'block', margin: '0 auto' }}
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth={ARROW_SIZE}
            markerHeight={ARROW_SIZE}
            refX={ARROW_SIZE}
            refY={ARROW_SIZE / 2}
            orient="auto"
          >
            <polygon
              points={`0 0, ${ARROW_SIZE} ${ARROW_SIZE / 2}, 0 ${ARROW_SIZE}`}
              fill="#595959"
            />
          </marker>
        </defs>

        {nodes.map((node, i) => {
          const x = 20 + i * (NODE_WIDTH + GAP);
          const y = 20;
          const isActive = activeNode === node.id;

          return (
            <g key={node.id}>
              {/* Connection arrow */}
              {i < nodes.length - 1 && (
                <line
                  x1={x + NODE_WIDTH}
                  y1={y + NODE_HEIGHT / 2}
                  x2={x + NODE_WIDTH + GAP - 4}
                  y2={y + NODE_HEIGHT / 2}
                  stroke="#595959"
                  strokeWidth={2}
                  markerEnd="url(#arrowhead)"
                />
              )}

              {/* Node box */}
              <rect
                x={x}
                y={y}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={8}
                fill={isActive ? `${node.color}33` : `${node.color}18`}
                stroke={node.color}
                strokeWidth={isActive ? 2.5 : 1.5}
                style={{ cursor: 'pointer', transition: 'all 0.2s' }}
                onClick={() => handleClick(node)}
              />

              {/* Node label */}
              <text
                x={x + NODE_WIDTH / 2}
                y={y + NODE_HEIGHT / 2 - 6}
                textAnchor="middle"
                fill={node.color}
                fontSize={13}
                fontWeight={600}
                fontFamily="Inter, sans-serif"
                style={{ pointerEvents: 'none' }}
              >
                {node.label}
              </text>

              {/* Node type */}
              <text
                x={x + NODE_WIDTH / 2}
                y={y + NODE_HEIGHT / 2 + 12}
                textAnchor="middle"
                fill="#8c8c8c"
                fontSize={10}
                fontFamily="JetBrains Mono, monospace"
                style={{ pointerEvents: 'none' }}
              >
                {node.type}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Active node config display */}
      {activeNode && (() => {
        const node = nodes.find(n => n.id === activeNode);
        if (!node?.config) return null;
        return (
          <div style={{
            marginTop: 12,
            padding: '12px 16px',
            background: '#141928',
            border: `1px solid ${node.color}44`,
            borderRadius: 8,
          }}>
            <Tag color={node.color} style={{ marginBottom: 8 }}>{node.label}</Tag>
            <pre style={{
              margin: 0,
              fontSize: 12,
              color: '#e8e8e8',
              fontFamily: 'JetBrains Mono, monospace',
              whiteSpace: 'pre-wrap',
            }}>
              {JSON.stringify(node.config, null, 2)}
            </pre>
          </div>
        );
      })()}
    </div>
  );
}
