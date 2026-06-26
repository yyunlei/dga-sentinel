import React, { useCallback, useState } from "react";
import { Typography, Tag, Tooltip, Collapse } from "antd";
import {
  CloudDownloadOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  FilterOutlined,
  ExportOutlined,
} from "@ant-design/icons";

const { Text } = Typography;

interface NodeCategory {
  name: string;
  label: string;
  color: string;
  nodeType: string;
  icon: React.ReactNode;
  items: { type: string; label: string; desc: string }[];
}

const CATEGORIES: NodeCategory[] = [
  {
    name: "Ingest",
    label: "数据接入",
    color: "#1677ff",
    nodeType: "ingest",
    icon: <CloudDownloadOutlined />,
    items: [
      {
        type: "kafka_consumer",
        label: "Kafka 消费者",
        desc: "从 Kafka Topic 消费 DNS 日志",
      },
      {
        type: "file_reader",
        label: "文件读取",
        desc: "读取本地 JSON/CSV 文件",
      },
      {
        type: "es_source",
        label: "ES 数据源",
        desc: "从 Elasticsearch 索引读取数据",
      },
    ],
  },
  {
    name: "Transform",
    label: "数据转换",
    color: "#52c41a",
    nodeType: "transform",
    icon: <SwapOutlined />,
    items: [
      { type: "dns_parser", label: "DNS 解析", desc: "解析 DNS 查询字段" },
      {
        type: "feature_extractor",
        label: "特征提取",
        desc: "提取词法/熵值特征",
      },
      {
        type: "severity_tag",
        label: "严重度标记",
        desc: "按分数阈值标记严重等级",
      },
      {
        type: "threat_intel_enrich",
        label: "威胁情报富化",
        desc: "查询外部威胁情报源",
      },
      {
        type: "geoip_lookup",
        label: "GeoIP 定位",
        desc: "IP 地理位置查询",
      },
      {
        type: "risk_aggregate",
        label: "风险聚合",
        desc: "多维度风险评分聚合",
      },
    ],
  },
  {
    name: "Infer",
    label: "模型推理",
    color: "#722ed1",
    nodeType: "infer",
    icon: <ThunderboltOutlined />,
    items: [
      { type: "scoring_service", label: "评分服务", desc: "DGA 模型评分推理" },
      {
        type: "family_classify",
        label: "家族分类",
        desc: "DGA 家族多分类推理",
      },
    ],
  },
  {
    name: "Filter",
    label: "过滤规则",
    color: "#fa8c16",
    nodeType: "filter",
    icon: <FilterOutlined />,
    items: [
      { type: "whitelist", label: "白名单", desc: "过滤已知安全域名" },
      { type: "threshold", label: "阈值过滤", desc: "按分数阈值过滤" },
      { type: "blacklist", label: "黑名单", desc: "匹配已知恶意域名" },
    ],
  },
  {
    name: "Sink",
    label: "数据输出",
    color: "#f5222d",
    nodeType: "sink",
    icon: <ExportOutlined />,
    items: [
      { type: "es_sink", label: "ES 输出", desc: "写入 Elasticsearch" },
      { type: "kafka_sink", label: "Kafka 输出", desc: "写入 Kafka Topic" },
      {
        type: "starrocks_sink",
        label: "StarRocks 输出",
        desc: "写入 StarRocks 表",
      },
      { type: "multi_sink", label: "多路输出", desc: "同时写入多个目标" },
      { type: "fan_out", label: "扇出", desc: "分发到多个下游节点" },
    ],
  },
];

export default function NodePalette() {
  const [activeKeys, setActiveKeys] = useState<string[]>(
    CATEGORIES.map((c) => c.name),
  );

  const onDragStart = useCallback(
    (e: React.DragEvent, nodeType: string, subType: string) => {
      e.dataTransfer.setData("application/reactflow-type", nodeType);
      e.dataTransfer.setData("application/reactflow-subtype", subType);
      e.dataTransfer.effectAllowed = "move";
    },
    [],
  );

  const collapseItems = CATEGORIES.map((cat) => ({
    key: cat.name,
    label: (
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ color: cat.color, fontSize: 14 }}>{cat.icon}</span>
        <span style={{ color: "#e8e8e8", fontSize: 12, fontWeight: 500 }}>
          {cat.label}
        </span>
        <Tag
          style={{
            marginLeft: "auto",
            fontSize: 10,
            lineHeight: "16px",
            padding: "0 4px",
          }}
        >
          {cat.items.length}
        </Tag>
      </div>
    ),
    children: (
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {cat.items.map((item) => (
          <Tooltip key={item.type} title={item.desc} placement="right">
            <div
              draggable
              onDragStart={(e) => onDragStart(e, cat.nodeType, item.type)}
              style={{
                padding: "6px 10px",
                borderRadius: 6,
                border: `1px solid ${cat.color}33`,
                background: `${cat.color}08`,
                cursor: "grab",
                fontSize: 12,
                color: "#d1d5db",
                transition: "all 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = `${cat.color}20`;
                e.currentTarget.style.borderColor = `${cat.color}66`;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = `${cat.color}08`;
                e.currentTarget.style.borderColor = `${cat.color}33`;
              }}
            >
              {item.label}
            </div>
          </Tooltip>
        ))}
      </div>
    ),
  }));

  return (
    <div
      style={{
        width: "100%",
        maxWidth: 264,
        minWidth: 200,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid #1f2937",
        background: "#0d1117",
        boxSizing: "border-box",
        paddingRight: 4,
      }}
    >
      <div style={{ padding: "12px 10px 8px" }}>
        <Text
          strong
          style={{ fontSize: 13, color: "#e8e8e8", display: "block" }}
        >
          节点面板
        </Text>
        <Text
          type="secondary"
          style={{ fontSize: 11, display: "block", marginTop: 4 }}
        >
          拖拽节点到画布
        </Text>
      </div>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
          padding: "0 4px 12px 16px",
        }}
      >
        <Collapse
          ghost
          size="small"
          activeKey={activeKeys}
          onChange={(keys) => setActiveKeys(keys as string[])}
          items={collapseItems}
        />
      </div>
    </div>
  );
}
