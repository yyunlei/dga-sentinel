import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Select,
  message,
  Popconfirm,
  Statistic,
  Row,
  Col,
  Empty,
  Typography,
  Tooltip,
} from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  BulbOutlined,
} from "@ant-design/icons";
import { operationsAPI } from "@/services/api";
import type { OperationItem, OperationsStats } from "@/services/api";
import Chart from "@/components/charts/Chart";
import { echartsColors } from "@/theme/dark-cyber";

const { Text } = Typography;

const cardStyle = { borderColor: "#1f2937" };

const opTypeMeta: Record<string, { color: string; label: string; desc: string }> = {
  threshold_recommendation: {
    color: "orange",
    label: "阈值调整建议",
    desc: "某 family FP 率超过 20% — 建议调高检测阈值",
  },
  drift_alert: {
    color: "red",
    label: "数据漂移告警",
    desc: "PSI ≥ 0.25 — 特征分布显著偏离基线，建议重训练或重设基线",
  },
  auto_whitelist_promote: {
    color: "green",
    label: "白名单自动加入",
    desc: "≥ 5 次 FP 反馈 → 已加入 whitelist:auto",
  },
  auto_whitelist_demote: {
    color: "default",
    label: "白名单自动移除",
    desc: "FP 信号过期，已从 whitelist:auto 移除",
  },
  auto_blacklist_promote: {
    color: "volcano",
    label: "黑名单自动加入",
    desc: "≥ 3 次 TP 反馈 → 已加入 blacklist:auto",
  },
  auto_blacklist_demote: {
    color: "default",
    label: "黑名单自动移除",
    desc: "TP 信号过期，已从 blacklist:auto 移除",
  },
};

function meta(op: string) {
  return opTypeMeta[op] || { color: "blue", label: op, desc: "" };
}

const statusColor: Record<string, string> = {
  pending: "gold",
  acknowledged: "green",
  dismissed: "default",
  success: "green",
  error: "red",
};

// detail 字段中文标签 + 单位
const detailMeta: Record<string, { label: string; unit?: string }> = {
  psi: { label: "PSI 漂移指数" },
  feature: { label: "漂移特征" },
  threshold: { label: "告警阈值" },
  window_size: { label: "样本窗口", unit: " 条" },
  fp_rate: { label: "误报率" },
  fp_count: { label: "FP 次数", unit: " 次" },
  tp_count: { label: "TP 次数", unit: " 次" },
  domain: { label: "域名" },
  family: { label: "家族" },
  current_threshold: { label: "当前阈值" },
  recommended_threshold: { label: "建议阈值" },
  reason: { label: "原因" },
};

function fmtVal(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4);
  return String(v);
}

/** 把 pending_operations.detail(任意结构)渲染成带标签的紧凑卡片，而非原始 JSON */
function renderDetail(d: Record<string, unknown>) {
  if (!d || typeof d !== "object") return <Text type="secondary">—</Text>;
  const action = d.suggested_action as string | undefined;
  const entries = Object.entries(d).filter(([k]) => k !== "suggested_action");
  return (
    <div style={{ maxWidth: 520 }}>
      <Space size={[6, 6]} wrap>
        {entries.map(([k, v]) => {
          const m = detailMeta[k] || { label: k };
          // PSI 按严重度着色：≥1 极严重(红) / ≥阈值 显著(橙) / 否则稳定(绿)
          let color: string | undefined;
          if (k === "psi") {
            const n = Number(v);
            const th = Number((d.threshold as number) ?? 0.25);
            color = n >= 1 ? "red" : n >= th ? "orange" : "green";
          }
          return (
            <Tag key={k} color={color} style={{ marginInlineEnd: 0 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>{m.label}</Text>
              <Text strong style={{ fontSize: 12, marginLeft: 4 }}>
                {fmtVal(v)}{m.unit || ""}
              </Text>
            </Tag>
          );
        })}
      </Space>
      {action && (
        <div
          style={{
            marginTop: 8,
            padding: "6px 10px",
            background: "rgba(96,165,250,0.08)",
            borderLeft: "3px solid #60a5fa",
            borderRadius: 4,
            fontSize: 12,
            color: "#bfdbfe",
            lineHeight: 1.5,
          }}
        >
          <BulbOutlined style={{ color: "#60a5fa", marginRight: 6 }} />
          {action}
        </div>
      )}
    </div>
  );
}

export default function Recommendations() {
  const [items, setItems] = useState<OperationItem[]>([]);
  const [stats, setStats] = useState<OperationsStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [actingId, setActingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const op_type = filter === "all" ? undefined : filter;
      const [list, st] = await Promise.all([
        operationsAPI.listPending(op_type, 200),
        operationsAPI.stats(),
      ]);
      setItems(list.items);
      setStats(st);
    } catch {
      message.error("加载推荐列表失败 — 检查 Gateway 是否在线");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAck(id: number) {
    setActingId(id);
    try {
      await operationsAPI.acknowledge(id);
      message.success("已确认 — 请按建议手动跟进");
      await load();
    } catch {
      message.error("操作失败");
    } finally {
      setActingId(null);
    }
  }

  async function handleDismiss(id: number) {
    setActingId(id);
    try {
      await operationsAPI.dismiss(id);
      message.success("已忽略");
      await load();
    } catch {
      message.error("操作失败");
    } finally {
      setActingId(null);
    }
  }

  const columns = [
    { title: "ID", dataIndex: "id", width: 70 },
    {
      title: "类型",
      dataIndex: "operation",
      width: 160,
      render: (op: string) => {
        const m = meta(op);
        return (
          <Tooltip title={m.desc}>
            <Tag color={m.color}>{m.label}</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: "Pipeline",
      dataIndex: "pipeline_id",
      width: 120,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: "来源",
      dataIndex: "operator",
      width: 160,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: "详情",
      dataIndex: "detail",
      render: (d: Record<string, unknown>) => renderDetail(d),
    },
    {
      title: "时间",
      dataIndex: "created_at",
      width: 165,
      render: (t: string) => (
        <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 12, color: "#9ca3af" }}>
          {t?.replace("T", " ").slice(0, 19)}
        </span>
      ),
    },
    {
      title: "操作",
      width: 195,
      fixed: "right" as const,
      render: (_: unknown, row: OperationItem) => (
        <Space size={4}>
          <Popconfirm
            title="确认这条推荐？"
            description="状态会改为 acknowledged，请记得手动执行对应动作"
            onConfirm={() => handleAck(row.id)}
            okText="确认"
            cancelText="取消"
          >
            <Button
              size="small"
              type="primary"
              icon={<CheckOutlined />}
              loading={actingId === row.id}
            >
              确认
            </Button>
          </Popconfirm>
          <Popconfirm
            title="忽略这条推荐？"
            description="状态会改为 dismissed，不会再出现在 pending 列表"
            onConfirm={() => handleDismiss(row.id)}
            okText="忽略"
            cancelText="取消"
          >
            <Button
              size="small"
              danger
              icon={<CloseOutlined />}
              loading={actingId === row.id}
            >
              忽略
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const pendingByOp = stats?.by_operation_pending || {};

  // 漂移特征 PSI 排行(取 drift_alert，按 feature 取最大 PSI，升序便于横向柱自下而上)
  const psiByFeature = useMemo(() => {
    const m: Record<string, number> = {};
    items.forEach((i) => {
      if (i.operation !== "drift_alert") return;
      const f = String(i.detail?.feature ?? "未知");
      const psi = Number(i.detail?.psi ?? 0);
      if (!Number.isNaN(psi)) m[f] = Math.max(m[f] ?? 0, psi);
    });
    return Object.entries(m).sort((a, b) => a[1] - b[1]);
  }, [items]);

  // 建议类型分布(按 operation 计数)
  const opCounts = useMemo(() => {
    const m: Record<string, number> = {};
    items.forEach((i) => {
      m[i.operation] = (m[i.operation] ?? 0) + 1;
    });
    return Object.entries(m);
  }, [items]);

  const psiOption = {
    grid: { left: 96, right: 56, top: 12, bottom: 24 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (ps: { name: string; value: number }[]) =>
        `${ps[0].name}<br/>PSI 漂移指数：<b>${ps[0].value}</b>`,
    },
    xAxis: {
      type: "value",
      axisLabel: { color: "#8c8c8c" },
      splitLine: { lineStyle: { color: "#1f2937" } },
    },
    yAxis: {
      type: "category",
      data: psiByFeature.map(([f]) => f),
      axisLabel: { color: "#cbd5e1" },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 22,
        data: psiByFeature.map(([, v]) => ({
          value: Number(v.toFixed(3)),
          itemStyle: {
            color: v >= 1 ? "#f5222d" : v >= 0.25 ? "#fa8c16" : "#52c41a",
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: { show: true, position: "right", color: "#e8e8e8", fontSize: 11, formatter: "{c}" },
        markLine: {
          symbol: "none",
          data: [{ xAxis: 0.25 }],
          lineStyle: { color: "#faad14", type: "dashed" },
          label: { formatter: "阈值 0.25", color: "#faad14", position: "insideEndTop", fontSize: 11 },
        },
      },
    ],
  };

  const typeOption = {
    tooltip: { trigger: "item", formatter: "{b}：{c} 条 ({d}%)" },
    legend: { bottom: 0, textStyle: { color: "#8c8c8c", fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["46%", "70%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#0b1220", borderWidth: 2 },
        label: { color: "#cbd5e1", fontSize: 11, formatter: "{b}\n{c}" },
        data: opCounts.map(([k, v], idx) => ({
          name: meta(k).label,
          value: v,
          itemStyle: { color: echartsColors[idx % echartsColors.length] },
        })),
      },
    ],
  };

  return (
    <div>
      {/* 顶部统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={6}>
          <Card style={cardStyle}>
            <Statistic
              title="待处理推荐"
              value={stats?.pending_total ?? 0}
              prefix={<BulbOutlined />}
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card style={cardStyle}>
            <Statistic
              title="阈值建议"
              value={pendingByOp.threshold_recommendation || 0}
              valueStyle={{ color: "#fa8c16", fontSize: 22 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card style={cardStyle}>
            <Statistic
              title="漂移告警"
              value={pendingByOp.drift_alert || 0}
              valueStyle={{ color: "#f5222d", fontSize: 22 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card style={cardStyle}>
            <Statistic
              title="累计已确认"
              value={stats?.by_status?.acknowledged ?? 0}
              valueStyle={{ color: "#52c41a", fontSize: 22 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 可视化图表 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            style={cardStyle}
            title={
              <Space>
                <BulbOutlined style={{ color: "#fa8c16" }} />
                <span>漂移特征 PSI 排行</span>
                <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  红=极严重(≥1) · 橙=显著(≥0.25) · 绿=稳定
                </Text>
              </Space>
            }
          >
            {psiByFeature.length ? (
              <Chart option={psiOption} style={{ height: 260 }} />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="当前无漂移告警数据"
                style={{ padding: "72px 0" }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card style={cardStyle} title="建议类型分布">
            {opCounts.length ? (
              <Chart option={typeOption} style={{ height: 260 }} />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无 pending 建议"
                style={{ padding: "72px 0" }}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 主表 */}
      <Card
        style={cardStyle}
        title={
          <Space>
            <BulbOutlined style={{ color: "#fa8c16" }} />
            <span>运营建议（pending 状态，需要分析师决策）</span>
          </Space>
        }
        extra={
          <Space>
            <Select
              value={filter}
              onChange={setFilter}
              style={{ width: 200 }}
              options={[
                { value: "all", label: "全部类型" },
                { value: "threshold_recommendation", label: "阈值建议" },
                { value: "drift_alert", label: "漂移告警" },
                { value: "auto_whitelist_promote", label: "白名单加入" },
                { value: "auto_blacklist_promote", label: "黑名单加入" },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table<OperationItem>
          columns={columns}
          dataSource={items.map((i) => ({ ...i, key: i.id }))}
          loading={loading}
          size="small"
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 15, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  filter === "all"
                    ? "暂无待处理推荐 — 闭环跑得很稳 🎉"
                    : "该类型暂无 pending 推荐"
                }
              />
            ),
          }}
        />
        <div
          style={{
            marginTop: 12,
            padding: "8px 12px",
            background: "#0f172a",
            borderRadius: 4,
            fontSize: 12,
            color: "#9ca3af",
          }}
        >
          <Text strong style={{ color: "#60a5fa" }}>说明：</Text>{" "}
          点击"确认"会把 status 改为 <Tag color={statusColor.acknowledged}>acknowledged</Tag>，
          表示分析师认可建议（**需要手动跟进**实际动作，平台不直接改 pipeline 配置）。
          点击"忽略"会改为 <Tag color={statusColor.dismissed}>dismissed</Tag>。
          所有动作写入 <Text code>audit_log</Text> 表。
        </div>
      </Card>
    </div>
  );
}
