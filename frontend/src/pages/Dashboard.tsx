import { useMemo, useCallback, useState, useEffect } from "react";
import { Row, Col, Card, Statistic, Table, Tag, Empty, Spin, Tabs } from "antd";
import {
  FundOutlined,
  BugOutlined,
  PercentageOutlined,
  DashboardOutlined,
} from "@ant-design/icons";
import Chart from "@/components/charts/Chart";
import { useDashboardStore } from "@/stores";
import { useRealtimeWS, usePolling } from "@/hooks/useRealtime";
import { echartsColors, severityColors } from "@/theme/dark-cyber";
import { dashboardAPI } from "@/services/api";
import type { AlertItem } from "@/services/api";

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // 只在客户端挂载后设置 mounted 状态
    if (typeof window !== "undefined") {
      setMounted(true);
    }
  }, []);

  // Hooks 必须在组件顶层调用，不能在条件语句中
  useRealtimeWS();

  const {
    totalToday,
    dgaHits,
    hitRate,
    p95Latency,
    qpsHistory,
    familyDist,
    realtimeAlerts,
    detectionAlerts,
  } = useDashboardStore();

  // dev polling — fetch real stats from API, fallback to mock tick
  const tick = useCallback(() => {
    if (!mounted) return;
    dashboardAPI
      .stats()
      .then((stats) => {
        const s = useDashboardStore.getState();
        s.setStats({
          totalToday: stats.total_today,
          dgaHits: stats.dga_hits,
          hitRate: stats.hit_rate,
          p95Latency: stats.p95_latency,
          qpsHistory: stats.qps_history?.length
            ? stats.qps_history
            : s.qpsHistory,
          familyDist: stats.family_dist?.length
            ? stats.family_dist
            : s.familyDist,
          realtimeAlerts: stats.recent_alerts?.length
            ? stats.recent_alerts
            : s.realtimeAlerts,
        });
      })
      .catch((err) => {
        console.error("Dashboard stats unavailable:", err);
      });
  }, [mounted]);

  usePolling(tick, 5000);

  /* --- chart options --- */
  const qpsOption = useMemo(() => {
    if (!mounted || qpsHistory.length === 0) {
      return {
        tooltip: { trigger: "axis" as const },
        xAxis: { type: "category" as const, data: [] },
        yAxis: [{ type: "value" as const }],
        series: [],
      };
    }
    return {
      tooltip: { trigger: "axis" as const },
      legend: { data: ["QPS", "DGA 命中"], textStyle: { color: "#8c8c8c" } },
      grid: { left: 40, right: 16, top: 36, bottom: 24 },
      xAxis: {
        type: "category" as const,
        data: qpsHistory.map((d) => d.time),
        axisLabel: { color: "#595959" },
      },
      yAxis: [
        {
          type: "value" as const,
          name: "QPS",
          axisLabel: { color: "#595959" },
        },
        {
          type: "value" as const,
          name: "命中",
          axisLabel: { color: "#595959" },
        },
      ],
      series: [
        {
          name: "QPS",
          type: "line",
          smooth: true,
          data: qpsHistory.map((d) => d.qps.toFixed(0)),
          itemStyle: { color: echartsColors[0] },
          areaStyle: { color: "rgba(22,104,220,0.15)" },
        },
        {
          name: "DGA 命中",
          type: "bar",
          yAxisIndex: 1,
          data: qpsHistory.map((d) => d.hits),
          itemStyle: { color: echartsColors[4] },
        },
      ],
    };
  }, [qpsHistory, mounted]);

  const pieOption = useMemo(() => {
    if (!mounted || familyDist.length === 0) {
      return {
        tooltip: { trigger: "item" as const },
        series: [{ type: "pie", data: [] }],
      };
    }
    return {
      tooltip: { trigger: "item" as const },
      legend: {
        orient: "vertical" as const,
        right: 8,
        top: "center",
        textStyle: { color: "#8c8c8c" },
      },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          center: ["40%", "50%"],
          data: familyDist,
          label: { color: "#8c8c8c" },
          itemStyle: { borderColor: "#141928", borderWidth: 2 },
        },
      ],
      color: echartsColors,
    };
  }, [familyDist, mounted]);

  const alertCols = [
    { title: "时间", dataIndex: "time", width: 90 },
    { title: "域名", dataIndex: "domain", ellipsis: true },
    {
      title: "分数",
      dataIndex: "score",
      width: 70,
      render: (v: number) => (
        <span style={{ color: v > 0.8 ? "#f5222d" : "#faad14" }}>
          {v?.toFixed(2)}
        </span>
      ),
    },
    {
      title: "严重度",
      dataIndex: "severity",
      width: 80,
      render: (v: string) => (
        <Tag color={severityColors[v] || "#595959"}>{v}</Tag>
      ),
    },
    { title: "家族", dataIndex: "family", width: 100 },
  ];

  // 使用固定值避免 hydration 错误
  const alertData: any[] = useMemo(() => {
    if (realtimeAlerts.length > 0) {
      return realtimeAlerts.map((a: AlertItem, i: number) => ({
        key: a.event_id || `rt-${i}`,
        time: a.timestamp?.slice(11, 19),
        ...a,
      }));
    }
    return [];
  }, [realtimeAlerts]);

  const detectionAlertData: any[] = useMemo(() => {
    if (detectionAlerts.length > 0) {
      return detectionAlerts.map((a: AlertItem, i: number) => ({
        key: a.event_id || `det-${i}`,
        time: a.timestamp?.slice(11, 19),
        ...a,
      }));
    }
    return [];
  }, [detectionAlerts]);

  const cardStyle = { borderColor: "#1f2937", background: "#141928" };

  // 如果未挂载，返回简单的加载状态，避免 hydration 不匹配
  if (!mounted) {
    return (
      <div
        style={{
          padding: "16px",
          minHeight: "100%",
          background: "#0a0e1a",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  // 确保组件始终渲染内容
  return (
    <div
      style={{
        padding: "16px",
        minHeight: "100%",
        background: "#0a0e1a",
        color: "#e8e8e8",
      }}
      suppressHydrationWarning
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card style={cardStyle}>
            <Statistic
              title="今日检测量"
              value={totalToday}
              prefix={<FundOutlined />}
              valueStyle={{ color: "#e8e8e8" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card style={cardStyle}>
            <Statistic
              title="DGA 命中"
              value={dgaHits}
              prefix={<BugOutlined />}
              valueStyle={{ color: "#f5222d" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card style={cardStyle}>
            <Statistic
              title="命中率"
              value={hitRate}
              suffix="%"
              prefix={<PercentageOutlined />}
              precision={2}
              valueStyle={{ color: "#e8e8e8" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card style={cardStyle}>
            <Statistic
              title="P95 延迟"
              value={p95Latency}
              suffix="ms"
              prefix={<DashboardOutlined />}
              valueStyle={{ color: "#e8e8e8" }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="检测 QPS & DGA 命中趋势" style={cardStyle}>
            {qpsHistory.length > 0 ? (
              <Chart option={qpsOption} style={{ height: 280 }} />
            ) : (
              <div
                style={{
                  height: 280,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Spin tip="加载中..." />
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="DGA 家族分布" style={cardStyle}>
            {familyDist.length > 0 ? (
              <Chart option={pieOption} style={{ height: 280 }} />
            ) : (
              <div
                style={{
                  height: 280,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Spin tip="加载中..." />
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Card
        title="实时告警流"
        style={{ marginTop: 16, ...cardStyle }}
        suppressHydrationWarning
      >
        <Tabs
          defaultActiveKey="realtime"
          items={[
            {
              key: "realtime",
              label: `实时告警 (${alertData.length})`,
              children:
                alertData.length === 0 ? (
                  <Empty description="暂无实时告警" />
                ) : (
                  <Table
                    columns={alertCols}
                    dataSource={alertData}
                    pagination={false}
                    size="small"
                    scroll={{ y: 260 }}
                  />
                ),
            },
            {
              key: "detection",
              label: `页面域名监测告警 (${detectionAlertData.length})`,
              children:
                detectionAlertData.length === 0 ? (
                  <Empty description="暂无域名监测告警" />
                ) : (
                  <Table
                    columns={alertCols}
                    dataSource={detectionAlertData}
                    pagination={false}
                    size="small"
                    scroll={{ y: 260 }}
                  />
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
