import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Select,
  Input,
  DatePicker,
  InputNumber,
  Row,
  Col,
  Drawer,
  Descriptions,
  Timeline,
  Statistic,
  Tabs,
  Tooltip,
  Spin,
  message,
  Empty,
  Badge,
  Flex,
  Popconfirm,
} from "antd";
import {
  SearchOutlined,
  ReloadOutlined,
  AlertOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  UnorderedListOutlined,
  ClusterOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { alertsAPI, dagAPI } from "@/services/api";
import { severityColors, echartsColors } from "@/theme/dark-cyber";
import Chart from "@/components/charts/Chart";
import type { AlertItem, AlertStats, DomainGroupItem } from "@/services/api";

const severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const families = [
  "qakbot",
  "necurs",
  "conficker",
  "suppobox",
  "ramnit",
  "matsnu",
];

export default function Alerts() {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<AlertItem | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  // Grouped view
  const [viewMode, setViewMode] = useState<"raw" | "grouped">("raw");
  const [domainGroups, setDomainGroups] = useState<DomainGroupItem[]>([]);
  const [expandedDomains, setExpandedDomains] = useState<
    Record<string, AlertItem[]>
  >({});
  const [expandLoading, setExpandLoading] = useState<Record<string, boolean>>(
    {},
  );
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<string[]>([]);

  // Stats
  const [alertStats, setAlertStats] = useState<AlertStats | null>(null);
  const [dagStats, setDagStats] = useState<{
    alerts_by_pipeline: { pipeline_id: string; name: string; count: number }[];
    alerts_by_family: { name: string; value: number }[];
  } | null>(null);

  // Filters
  const [severity, setSeverity] = useState<string | undefined>();
  const [family, setFamily] = useState<string | undefined>();
  const [domain, setDomain] = useState("");
  const [srcIp, setSrcIp] = useState("");
  const [scoreMin, setScoreMin] = useState<number | null>(null);
  const [scoreMax, setScoreMax] = useState<number | null>(null);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [status, setStatus] = useState<string | undefined>();
  const [source, setSource] = useState<string | undefined>();
  const [pipelineId, setPipelineId] = useState<string | undefined>();

  const sortByTimeDesc = (list: AlertItem[]) =>
    [...list].sort((a, b) =>
      (b.timestamp || "").localeCompare(a.timestamp || ""),
    );

  const buildFilterParams = useCallback(() => {
    const params: Record<string, string> = {};
    if (severity) params.severity = severity;
    if (family) params.family = family;
    if (domain) params.domain = domain;
    if (srcIp) params.src_ip = srcIp;
    if (scoreMin != null) params.score_min = String(scoreMin);
    if (scoreMax != null) params.score_max = String(scoreMax);
    if (startTime) params.start_time = startTime;
    if (endTime) params.end_time = endTime;
    if (status === "pending") params.acknowledged = "false";
    else if (status === "acknowledged") params.acknowledged = "true";
    if (source) params.source = source;
    if (pipelineId) params.pipeline_id = pipelineId;
    return params;
  }, [
    severity,
    family,
    domain,
    srcIp,
    scoreMin,
    scoreMax,
    startTime,
    endTime,
    status,
    source,
    pipelineId,
  ]);

  function doSearch() {
    setLoading(true);
    const params = buildFilterParams();

    if (viewMode === "grouped") {
      alertsAPI
        .listGrouped({ ...params, size: "2000" })
        .then((r) => {
          setDomainGroups(r.groups || []);
          setExpandedDomains({});
        })
        .catch(() => {
          setDomainGroups([]);
          message.error("加载分组告警失败");
        })
        .finally(() => setLoading(false));
    } else {
      alertsAPI
        .list(params)
        .then((r) => setAlerts(sortByTimeDesc(r.alerts || [])))
        .catch(() => {
          setAlerts([]);
          message.error("加载告警失败");
        })
        .finally(() => setLoading(false));
    }
  }

  useEffect(() => {
    doSearch();
    alertsAPI
      .stats()
      .then(setAlertStats)
      .catch(() => {});
    dagAPI
      .stats()
      .then((s) =>
        setDagStats({
          alerts_by_pipeline: s.alerts_by_pipeline,
          alerts_by_family: s.alerts_by_family,
        }),
      )
      .catch(() => {});
  }, []);

  // Re-search when view mode changes
  useEffect(() => {
    doSearch();
  }, [viewMode]);

  function handleReset() {
    setSeverity(undefined);
    setFamily(undefined);
    setDomain("");
    setSrcIp("");
    setScoreMin(null);
    setScoreMax(null);
    setStartTime("");
    setEndTime("");
    setStatus(undefined);
    setSource(undefined);
    setPipelineId(undefined);
  }

  // Reset triggers a new search
  useEffect(() => {
    if (
      !severity &&
      !family &&
      !domain &&
      !srcIp &&
      scoreMin == null &&
      scoreMax == null &&
      !startTime &&
      !endTime &&
      !status &&
      !source &&
      !pipelineId
    ) {
      doSearch();
    }
  }, [
    severity,
    family,
    domain,
    srcIp,
    scoreMin,
    scoreMax,
    startTime,
    endTime,
    status,
    source,
    pipelineId,
  ]);

  function handleAck(ids: string[]) {
    Promise.all(
      ids.map((id) => alertsAPI.acknowledge(id).catch(() => null)),
    ).then(() => {
      setAlerts((prev) =>
        prev.map((a) =>
          ids.includes(a.event_id) ? { ...a, acknowledged: true } : a,
        ),
      );
      setSelectedKeys([]);
      message.success(`已确认 ${ids.length} 条告警`);
      window.dispatchEvent(new CustomEvent("alerts-acknowledged"));
    });
  }

  function handleAckByDomain(domains: string[]) {
    alertsAPI.acknowledgeByDomain(domains).then((r) => {
      setDomainGroups((prev) =>
        prev.map((g) =>
          domains.includes(g.domain) ? { ...g, all_acknowledged: true } : g,
        ),
      );
      setExpandedDomains((prev) => {
        const next = { ...prev };
        domains.forEach((d) => delete next[d]);
        return next;
      });
      setSelectedGroupKeys([]);
      message.success(
        `已确认 ${domains.length} 个域名的所有告警 (${r.updated} 条)`,
      );
      window.dispatchEvent(new CustomEvent("alerts-acknowledged"));
    });
  }

  function loadDomainAlerts(domainName: string) {
    setExpandLoading((prev) => ({ ...prev, [domainName]: true }));
    alertsAPI
      .list({ domain: domainName, limit: "100" })
      .then((r) => {
        setExpandedDomains((prev) => ({
          ...prev,
          [domainName]: sortByTimeDesc(r.alerts || []),
        }));
      })
      .finally(() => {
        setExpandLoading((prev) => ({ ...prev, [domainName]: false }));
      });
  }

  const cols = [
    {
      title: "时间",
      dataIndex: "timestamp",
      width: 170,
      render: (v: string) => v?.replace("T", " ").slice(0, 19),
    },
    { title: "域名", dataIndex: "domain", ellipsis: true },
    { title: "源 IP", dataIndex: "src_ip", width: 140 },
    {
      title: "分数",
      dataIndex: "score",
      width: 70,
      render: (v: number) => (
        <span style={{ color: v > 0.8 ? "#f5222d" : "#faad14" }}>
          {v?.toFixed(3)}
        </span>
      ),
    },
    {
      title: "严重度",
      dataIndex: "severity",
      width: 90,
      render: (v: string) => <Tag color={severityColors[v]}>{v}</Tag>,
    },
    { title: "家族", dataIndex: "family", width: 100 },
    {
      title: "来源",
      dataIndex: "pipeline_id",
      width: 130,
      render: (v: string) => {
        if (!v || v === "gateway") return <Tag color="blue">手动评分</Tag>;
        return <Tag color="cyan">DAG 实时监测</Tag>;
      },
    },
    {
      title: "Pipeline",
      dataIndex: "pipeline_id",
      width: 180,
      render: (v: string) => {
        const nameMap: Record<string, string> = {
          gateway: "Gateway 域名评分",
          "dga-realtime-v1": "DGA 全链路检测 (真实场景)",
          "dga-batch-v1": "DGA 批量检测",
          "c2-realtime-v1": "C2 通信检测",
          "dns-tunnel-v1": "DNS 隧道检测",
        };
        return (
          <span style={{ color: "#8c8c8c" }}>{nameMap[v] || v || "-"}</span>
        );
      },
    },
    {
      title: "状态",
      dataIndex: "acknowledged",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="green">已确认</Tag> : <Tag color="orange">待处理</Tag>,
    },
    {
      title: "操作",
      width: 120,
      render: (_: unknown, r: AlertItem) => (
        <Space>
          <Button
            size="small"
            type="link"
            onClick={() => navigate(`/alerts/${r.event_id}`)}
          >
            详情
          </Button>
          {!r.acknowledged && (
            <Button
              size="small"
              type="link"
              onClick={() => handleAck([r.event_id])}
            >
              确认
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const groupedCols = [
    { title: "域名", dataIndex: "domain", ellipsis: true },
    {
      title: "告警数",
      dataIndex: "alert_count",
      width: 80,
      sorter: (a: DomainGroupItem, b: DomainGroupItem) =>
        a.alert_count - b.alert_count,
    },
    {
      title: "源 IP 数",
      dataIndex: "unique_src_ip_count",
      width: 90,
      render: (v: number, r: DomainGroupItem) => (
        <Tooltip title={r.unique_src_ips.slice(0, 10).join(", ") || "-"}>
          <span>{v}</span>
        </Tooltip>
      ),
    },
    {
      title: "最高严重度",
      dataIndex: "max_severity",
      width: 110,
      render: (v: string) => <Tag color={severityColors[v]}>{v}</Tag>,
    },
    {
      title: "最高分数",
      dataIndex: "max_score",
      width: 90,
      render: (v: number) => (
        <span style={{ color: v > 0.8 ? "#f5222d" : "#faad14" }}>
          {v?.toFixed(3)}
        </span>
      ),
    },
    { title: "家族", dataIndex: "family", width: 100 },
    {
      title: "首次发现",
      dataIndex: "first_seen",
      width: 170,
      render: (v: string) => v?.replace("T", " ").slice(0, 19),
    },
    {
      title: "最近发现",
      dataIndex: "last_seen",
      width: 170,
      render: (v: string) => v?.replace("T", " ").slice(0, 19),
    },
    {
      title: "状态",
      dataIndex: "all_acknowledged",
      width: 110,
      render: (v: boolean, r: DomainGroupItem) =>
        v ? (
          <Tag color="green">全部确认</Tag>
        ) : (
          <Popconfirm
            title="批量确认该域名所有未处理告警？"
            description={`将一次性确认 "${r.domain}" 下的所有 ${r.alert_count} 条告警`}
            onConfirm={(e) => {
              e?.stopPropagation();
              handleAckByDomain([r.domain]);
            }}
            onCancel={(e) => e?.stopPropagation()}
            okText="批量确认"
            cancelText="取消"
          >
            <Tag
              color="orange"
              style={{ cursor: "pointer", userSelect: "none" }}
              onClick={(e) => e.stopPropagation()}
            >
              待处理 →
            </Tag>
          </Popconfirm>
        ),
    },
  ];

  const cardStyle = { borderColor: "#1f2937" };

  const dayChange = alertStats
    ? alertStats.total - alertStats.total_yesterday
    : 0;
  const dayChangeRate =
    alertStats && alertStats.total_yesterday > 0
      ? ((dayChange / alertStats.total_yesterday) * 100).toFixed(1)
      : "0";

  return (
    <div>
      {/* Stats cards */}
      <Row gutter={[12, 12]}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="告警总数"
              value={alertStats?.total ?? 0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: "#e8e8e8" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="待处理"
              value={alertStats?.pending ?? 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: "#faad14" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="已确认"
              value={alertStats?.acknowledged ?? 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="较昨日"
              value={Math.abs(Number(dayChangeRate))}
              suffix="%"
              prefix={
                dayChange >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />
              }
              valueStyle={{ color: dayChange >= 0 ? "#f5222d" : "#52c41a" }}
            />
          </Card>
        </Col>
      </Row>

      {/* Charts */}
      <Row gutter={[12, 12]}>
        <Col xs={24} md={8}>
          <Card size="small" title="严重度分布" style={cardStyle}>
            <Chart
              style={{ height: 220 }}
              option={{
                tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
                legend: { bottom: 0, textStyle: { color: "#8c8c8c" } },
                series: [
                  {
                    type: "pie",
                    radius: ["35%", "65%"],
                    center: ["50%", "45%"],
                    label: { show: false },
                    emphasis: {
                      label: { show: true, fontSize: 13, fontWeight: "bold" },
                    },
                    data: (alertStats?.by_severity ?? []).map((s) => ({
                      name: s.name,
                      value: s.value,
                      itemStyle: { color: severityColors[s.name] || "#8c8c8c" },
                    })),
                  },
                ],
              }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title="家族告警 Top10" style={cardStyle}>
            <Chart
              style={{ height: 220 }}
              option={{
                tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
                legend: {
                  orient: "vertical",
                  right: 10,
                  top: "center",
                  textStyle: { color: "#8c8c8c" },
                },
                series: [
                  {
                    type: "pie",
                    radius: ["35%", "65%"],
                    center: ["35%", "50%"],
                    avoidLabelOverlap: true,
                    label: { show: false },
                    emphasis: {
                      label: { show: true, fontSize: 13, fontWeight: "bold" },
                    },
                    data: (dagStats?.alerts_by_family ?? []).map((f, i) => ({
                      name: f.name,
                      value: f.value,
                      itemStyle: {
                        color: echartsColors[i % echartsColors.length],
                      },
                    })),
                  },
                ],
              }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title="Pipeline 告警 Top10" style={cardStyle}>
            <Chart
              style={{ height: 220 }}
              option={{
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                grid: { left: 100, right: 16, top: 8, bottom: 8 },
                xAxis: { type: "value" },
                yAxis: {
                  type: "category",
                  data: [...(dagStats?.alerts_by_pipeline ?? [])]
                    .reverse()
                    .map((p) => p.name),
                  axisLabel: { width: 80, overflow: "truncate" },
                },
                series: [
                  {
                    type: "bar",
                    data: [...(dagStats?.alerts_by_pipeline ?? [])]
                      .reverse()
                      .map((p) => p.count),
                    itemStyle: {
                      color: echartsColors[0],
                      borderRadius: [0, 4, 4, 0],
                    },
                    barMaxWidth: 16,
                  },
                ],
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filter bar */}
      <Card
        size="small"
        style={{
          ...cardStyle,
          marginBottom: 0,
          borderBottom: "none",
          borderRadius: "8px 8px 0 0",
        }}
      >
        <Flex wrap gap={8} align="center">
          <DatePicker.RangePicker
            placeholder={["开始时间", "结束时间"]}
            style={{ width: 260 }}
            onChange={(_dates, dateStrings) => {
              setStartTime(dateStrings?.[0] ?? "");
              setEndTime(dateStrings?.[1] ?? "");
            }}
          />
          <Input
            placeholder="域名"
            allowClear
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            style={{ width: 150 }}
          />
          <Input
            placeholder="源 IP"
            allowClear
            value={srcIp}
            onChange={(e) => setSrcIp(e.target.value)}
            style={{ width: 130 }}
          />
          <InputNumber
            placeholder="分数 >="
            min={0}
            max={1}
            step={0.1}
            value={scoreMin}
            onChange={(v) => setScoreMin(v)}
            style={{ width: 95 }}
          />
          <InputNumber
            placeholder="分数 <="
            min={0}
            max={1}
            step={0.1}
            value={scoreMax}
            onChange={(v) => setScoreMax(v)}
            style={{ width: 95 }}
          />
          <Select
            placeholder="严重度"
            allowClear
            style={{ width: 100 }}
            value={severity}
            onChange={setSeverity}
            options={severities.map((s) => ({ label: s, value: s }))}
          />
          <Select
            placeholder="家族"
            allowClear
            style={{ width: 100 }}
            value={family}
            onChange={setFamily}
            options={families.map((f) => ({ label: f, value: f }))}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 90 }}
            value={status}
            onChange={setStatus}
            options={[
              { label: "待处理", value: "pending" },
              { label: "已确认", value: "acknowledged" },
            ]}
          />
          <Select
            placeholder="来源"
            allowClear
            style={{ width: 130 }}
            value={source}
            onChange={setSource}
            options={[
              { label: "手动评分", value: "manual" },
              { label: "DAG 实时监测", value: "dag" },
            ]}
          />
          <Select
            placeholder="Pipeline"
            allowClear
            style={{ width: 180 }}
            value={pipelineId}
            onChange={setPipelineId}
            options={[
              { label: "Gateway 域名评分", value: "gateway" },
              { label: "DGA 全链路检测", value: "dga-realtime-v1" },
              { label: "DGA 批量检测", value: "dga-batch-v1" },
              { label: "C2 通信检测", value: "c2-realtime-v1" },
              { label: "DNS 隧道检测", value: "dns-tunnel-v1" },
            ]}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={doSearch}>
            查询
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            重置
          </Button>
        </Flex>
      </Card>

      {/* Tabs card */}
      <Card
        style={{ ...cardStyle, borderRadius: "0 0 8px 8px" }}
        styles={{ body: { padding: 0 } }}
      >
        <Tabs
          activeKey={viewMode}
          onChange={(key) => {
            setViewMode(key as "raw" | "grouped");
            setSelectedKeys([]);
            setSelectedGroupKeys([]);
          }}
          tabBarStyle={{
            margin: 0,
            padding: "0 16px",
            background:
              "linear-gradient(180deg, rgba(22,104,220,0.06) 0%, transparent 100%)",
            borderBottom: "1px solid rgba(22,104,220,0.15)",
          }}
          tabBarExtraContent={
            (
              viewMode === "raw"
                ? selectedKeys.length > 0
                : selectedGroupKeys.length > 0
            ) ? (
              <Button
                type="primary"
                size="small"
                style={{ boxShadow: "0 0 12px rgba(22,104,220,0.4)" }}
                onClick={() =>
                  viewMode === "grouped"
                    ? handleAckByDomain(selectedGroupKeys)
                    : handleAck(selectedKeys)
                }
              >
                批量确认 (
                {viewMode === "raw"
                  ? selectedKeys.length
                  : selectedGroupKeys.length}
                )
              </Button>
            ) : null
          }
          items={[
            {
              key: "raw",
              label: (
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <UnorderedListOutlined />
                  原始告警
                  <Badge
                    count={alertStats?.total ?? 0}
                    overflowCount={9999}
                    style={{
                      backgroundColor: "#1668dc",
                      boxShadow: "0 0 8px rgba(22,104,220,0.5)",
                    }}
                  />
                </span>
              ),
              children: (
                <div style={{ padding: "12px 16px 16px" }}>
                  <Table
                    columns={cols}
                    dataSource={alerts.map((a) => ({ ...a, key: a.event_id }))}
                    loading={loading}
                    size="small"
                    pagination={{ pageSize: 15 }}
                    rowSelection={{
                      selectedRowKeys: selectedKeys,
                      onChange: (keys) => setSelectedKeys(keys as string[]),
                    }}
                    locale={{ emptyText: <Empty description="暂无告警数据" /> }}
                    onRow={(record) => ({
                      onClick: (e) => {
                        const target = e.target as HTMLElement;
                        if (
                          target.closest("button") ||
                          target.closest(".ant-btn") ||
                          target.closest(".ant-checkbox-wrapper")
                        )
                          return;
                        setSelected(record as AlertItem);
                      },
                      style: { cursor: "pointer" },
                    })}
                  />
                </div>
              ),
            },
            {
              key: "grouped",
              label: (
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <ClusterOutlined />
                  按域名聚合
                  {domainGroups.length > 0 && (
                    <Badge
                      count={domainGroups.length}
                      overflowCount={9999}
                      style={{
                        backgroundColor: "#13c2c2",
                        boxShadow: "0 0 8px rgba(19,194,194,0.5)",
                      }}
                    />
                  )}
                </span>
              ),
              children: (
                <div style={{ padding: "12px 16px 16px" }}>
                  <Table
                    columns={groupedCols}
                    dataSource={domainGroups.map((g) => ({
                      ...g,
                      key: g.domain,
                    }))}
                    loading={loading}
                    size="small"
                    pagination={{ pageSize: 15 }}
                    rowSelection={{
                      selectedRowKeys: selectedGroupKeys,
                      onChange: (keys) =>
                        setSelectedGroupKeys(keys as string[]),
                    }}
                    locale={{
                      emptyText: <Empty description="暂无聚合告警数据" />,
                    }}
                    expandable={{
                      expandedRowRender: (record: DomainGroupItem) => {
                        const domainAlerts = expandedDomains[record.domain];
                        if (expandLoading[record.domain])
                          return <Spin size="small" />;
                        if (!domainAlerts) return <Spin size="small" />;
                        return (
                          <Table
                            columns={cols}
                            dataSource={domainAlerts.map((a) => ({
                              ...a,
                              key: a.event_id,
                            }))}
                            size="small"
                            pagination={false}
                            style={{ margin: "-8px -8px -8px 0" }}
                          />
                        );
                      },
                      onExpand: (
                        expanded: boolean,
                        record: DomainGroupItem,
                      ) => {
                        if (expanded && !expandedDomains[record.domain])
                          loadDomainAlerts(record.domain);
                      },
                    }}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title="告警详情"
        open={!!selected}
        onClose={() => setSelected(null)}
        width={480}
        extra={
          selected && (
            <Button
              type="primary"
              size="small"
              onClick={() => {
                setSelected(null);
                navigate(`/alerts/${selected.event_id}`);
              }}
            >
              查看完整详情
            </Button>
          )
        }
      >
        {selected && (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="事件 ID">
                {selected.event_id}
              </Descriptions.Item>
              <Descriptions.Item label="域名">
                {selected.domain}
              </Descriptions.Item>
              <Descriptions.Item label="源 IP">
                {selected.src_ip}
              </Descriptions.Item>
              <Descriptions.Item label="风险分数">
                {selected.score}
              </Descriptions.Item>
              <Descriptions.Item label="严重度">
                <Tag color={severityColors[selected.severity]}>
                  {selected.severity}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="家族">
                {selected.family || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {!selected.pipeline_id || selected.pipeline_id === "gateway" ? (
                  <Tag color="blue">手动评分</Tag>
                ) : (
                  <Tag color="cyan">DAG 实时监测</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Pipeline">
                {(() => {
                  const nameMap: Record<string, string> = {
                    gateway: "Gateway 域名评分",
                    "dga-realtime-v1": "DGA 全链路检测 (真实场景)",
                    "dga-batch-v1": "DGA 批量检测",
                    "c2-realtime-v1": "C2 通信检测",
                    "dns-tunnel-v1": "DNS 隧道检测",
                  };
                  return (
                    nameMap[selected.pipeline_id || ""] ||
                    selected.pipeline_id ||
                    "-"
                  );
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="时间">
                {selected.timestamp}
              </Descriptions.Item>
            </Descriptions>
            <Card
              title="处置时间线"
              size="small"
              style={{ marginTop: 16, ...cardStyle }}
            >
              <Timeline
                items={[
                  {
                    color: "blue",
                    children: `${selected.timestamp?.replace("T", " ").slice(0, 19)} 检测到 DGA 域名，评分 ${selected.score?.toFixed(3)}`,
                  },
                  {
                    color: selected.is_dga ? "red" : "green",
                    children: selected.is_dga
                      ? `判定为 DGA 域名（家族: ${selected.family || "未知"}）`
                      : "判定为正常域名",
                  },
                  {
                    color: selected.acknowledged ? "green" : "gray",
                    children: selected.acknowledged ? "已确认处置" : "等待处置",
                  },
                ]}
              />
            </Card>
          </>
        )}
      </Drawer>
    </div>
  );
}
