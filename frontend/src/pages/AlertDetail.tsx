import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import {
  Card,
  Descriptions,
  Timeline,
  Table,
  Tag,
  Tooltip,
  Alert,
  Typography,
  Row,
  Col,
  Space,
  Spin,
  message,
  Button,
} from "antd";
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { severityColors } from "@/theme/dark-cyber";
import {
  alertsAPI,
  explainDetailAPI,
  feedbackAPI,
  responseAgentAPI,
} from "@/services/api";

const { Title, Paragraph, Text } = Typography;

interface AlertData {
  event_id: string;
  domain: string;
  score: number;
  severity: string;
  family: string | null;
  src_ip: string;
  timestamp: string;
}

interface Dimension {
  title: string;
  content: string;
}

const relatedCols = [
  {
    title: "事件 ID",
    dataIndex: "event_id",
    width: 110,
    render: (v: string) =>
      v ? (
        <Tooltip title={v} placement="topLeft">
          <Text code style={{ fontSize: 12 }}>
            {v.slice(0, 8)}…
          </Text>
        </Tooltip>
      ) : (
        "—"
      ),
  },
  {
    title: "域名",
    dataIndex: "domain",
    ellipsis: { showTitle: false },
    render: (v: string) => (
      <Tooltip title={v} placement="topLeft">
        <span>{v}</span>
      </Tooltip>
    ),
  },
  {
    title: "分数",
    dataIndex: "score",
    width: 90,
    align: "right" as const,
    render: (v: number) => (
      <span
        style={{
          color: v > 0.8 ? "#f5222d" : v > 0.5 ? "#faad14" : "#52c41a",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {v?.toFixed(3)}
      </span>
    ),
  },
  {
    title: "严重度",
    dataIndex: "severity",
    width: 100,
    align: "center" as const,
    render: (v: string) => (
      <Tag color={severityColors[v]} style={{ margin: 0 }}>
        {v}
      </Tag>
    ),
  },
  {
    title: "时间",
    dataIndex: "timestamp",
    width: 170,
    render: (v: string) => (
      <span style={{ fontVariantNumeric: "tabular-nums", color: "#9ca3af" }}>
        {v?.replace("T", " ").slice(0, 19)}
      </span>
    ),
  },
];

const levelColor: Record<string, string> = {
  urgent: "red",
  high: "orange",
  medium: "blue",
};
const levelLabel: Record<string, string> = {
  urgent: "紧急",
  high: "高",
  medium: "中",
};
const cardStyle = { borderColor: "#1f2937" };

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [alert, setAlert] = useState<AlertData | null>(null);
  const [loading, setLoading] = useState(true);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [explanation, setExplanation] = useState("");
  const [relatedAlerts, setRelatedAlerts] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<
    { color: string; children: string }[]
  >([]);
  const [recommendations, setRecommendations] = useState<
    { level: string; action: string }[]
  >([]);
  const [recError, setRecError] = useState(false);
  const [dimError, setDimError] = useState(false);
  const [recLoading, setRecLoading] = useState(true);
  const [dimLoading, setDimLoading] = useState(true);
  const [fbLoading, setFbLoading] = useState<"dga" | "benign" | null>(null);
  const [fbSubmitted, setFbSubmitted] = useState<"dga" | "benign" | null>(null);

  async function submitFeedback(label: "dga" | "benign") {
    if (!alert) return;
    setFbLoading(label);
    try {
      await feedbackAPI.submit({
        event_id: alert.event_id,
        domain: alert.domain,
        true_label: label,
        predicted_label: "dga",
        score: alert.score,
        family: alert.family,
      });
      setFbSubmitted(label);
      message.success(
        label === "benign"
          ? "已提交：误报标注（5 次后自动加白名单）"
          : "已提交：DGA 确认（3 次后自动加黑名单）",
      );
    } catch {
      message.error("反馈提交失败，请重试");
    } finally {
      setFbLoading(null);
    }
  }

  useEffect(() => {
    if (!id) return;
    loadAlertDetail(id);
  }, [id]);

  async function loadAlertDetail(eventId: string) {
    setLoading(true);
    setRecLoading(true);
    setDimLoading(true);

    // Step 1: 主告警必须先到位，页面才能 render
    let data: AlertData;
    try {
      data = (await alertsAPI.get(eventId)) as unknown as AlertData;
      setAlert(data);
      setLoading(false); // 关键：主数据 50ms 就到，立即解锁页面渲染
    } catch {
      message.error("加载告警详情失败");
      setLoading(false);
      return; // 没有主数据无从渲染
    }

    const ts = data.timestamp?.replace("T", " ").slice(11, 19) || "00:00:00";
    setTimeline([
      {
        color: "blue",
        children: `${ts} — 检测阶段：模型评分 ${data.score?.toFixed(3)}，判定为 DGA 域名`,
      },
      {
        color: "orange",
        children: `${ts} — TriageAgent：关联源 IP ${data.src_ip} 历史告警，评估严重度为 ${data.severity}`,
      },
      {
        color: "green",
        children: `${ts} — ExplainAgent：完成四维分析，确认 ${data.family || "未知"} 家族特征`,
      },
      { color: "red", children: `${ts} — ResponseAgent：生成处置建议` },
    ]);

    // Step 2-4: 三个子调用并行 fire-and-forget — 各自的局部 loader 控制 UI
    // 并行而非串行，总耗时 = max(三者) 而非 sum，整页不再被 LLM 长调用阻塞

    // ResponseAgent (~5-10s)
    responseAgentAPI
      .getRecommendations(
        data.domain,
        data.score,
        data.severity,
        data.family,
        data.src_ip,
      )
      .then((respActions) => {
        if (respActions.recommendations?.length) {
          setRecommendations(respActions.recommendations);
        } else {
          setRecError(true);
        }
      })
      .catch(() => {
        setRecError(true);
        message.warning("处置建议服务暂不可用");
      })
      .finally(() => setRecLoading(false));

    // ExplainAgent (~20s — DeepSeek LLM)
    explainDetailAPI
      .explain(data.domain, data.score, data.family || undefined, data.src_ip)
      .then((explainResp) => {
        if (explainResp.explanation) setExplanation(explainResp.explanation);
        if (explainResp.dimensions?.length)
          setDimensions(explainResp.dimensions);
      })
      .catch(() => setDimError(true))
      .finally(() => setDimLoading(false));

    // Related alerts (空 src_ip 跳过查询，否则会拉全表)
    if (data.src_ip) {
      alertsAPI
        .list({ limit: "5", src_ip: data.src_ip })
        .then((related) => {
          setRelatedAlerts(
            related.alerts
              .filter((a) => a.event_id !== eventId)
              .slice(0, 5)
              .map((a, i) => ({ key: i, ...a })),
          );
        })
        .catch(() => {
          /* empty */
        });
    }
  }

  if (loading || !alert) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <Spin size="large" tip="加载告警详情..." />
      </div>
    );
  }

  const severityIcon =
    alert.severity === "CRITICAL" || alert.severity === "HIGH" ? (
      <WarningOutlined style={{ color: "#f5222d" }} />
    ) : (
      <CheckCircleOutlined style={{ color: "#52c41a" }} />
    );

  return (
    <div>
      {/* 顶部导航 + 基本信息 */}
      <Card style={cardStyle}>
        <Row align="middle" justify="space-between" style={{ marginBottom: 12 }}>
          <Col>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate("/alerts")}
            >
              返回告警列表
            </Button>
          </Col>
          <Col>
            <Space size={8}>
              <Text type="secondary" style={{ fontSize: 13 }}>
                分析师标注：
              </Text>
              <Button
                size="small"
                icon={<CloseCircleOutlined />}
                danger
                loading={fbLoading === "benign"}
                disabled={!!fbSubmitted}
                onClick={() => submitFeedback("benign")}
              >
                {fbSubmitted === "benign" ? "已标记误报" : "标记为误报"}
              </Button>
              <Button
                size="small"
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={fbLoading === "dga"}
                disabled={!!fbSubmitted}
                onClick={() => submitFeedback("dga")}
              >
                {fbSubmitted === "dga" ? "已确认 DGA" : "确认为 DGA"}
              </Button>
            </Space>
          </Col>
        </Row>
        <Descriptions
          title={
            <Space>
              {severityIcon}
              <Title level={4} style={{ margin: 0 }}>
                告警详情
              </Title>
              <Tag color={severityColors[alert.severity]}>{alert.severity}</Tag>
            </Space>
          }
          column={{ xs: 1, sm: 2, lg: 3 }}
          bordered
          size="small"
        >
          <Descriptions.Item label="事件 ID">
            {alert.event_id}
          </Descriptions.Item>
          <Descriptions.Item label="域名">
            <Text copyable>{alert.domain}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="风险分数">
            <span style={{ color: "#f5222d", fontWeight: 600 }}>
              {alert.score?.toFixed(3)}
            </span>
          </Descriptions.Item>
          <Descriptions.Item label="家族">
            <Tag color="volcano">{alert.family || "未知"}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="源 IP">
            <Text copyable>{alert.src_ip}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="时间">
            {alert.timestamp?.replace("T", " ").slice(0, 19)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 第一行：时间线 + 处置建议 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card title="处置时间线" style={{ ...cardStyle, height: "100%" }}>
            <Timeline items={timeline} />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title="ResponseAgent 处置建议"
            style={{ ...cardStyle, height: "100%" }}
          >
            {recLoading ? (
              <div style={{ textAlign: "center", padding: 24 }}>
                <Spin tip="生成建议中..." />
              </div>
            ) : recError ? (
              <Alert
                type="warning"
                message="处置建议服务暂不可用，请检查 Agent Layer 服务状态"
                showIcon
              />
            ) : (
              <>
                <Alert
                  type="warning"
                  message="该告警需要立即处置"
                  showIcon
                  style={{ marginBottom: 12 }}
                />
                {recommendations.map((r, i) => (
                  <div
                    key={i}
                    style={{
                      marginBottom: 10,
                      padding: "8px 12px",
                      background: "#111827",
                      borderRadius: 6,
                      borderLeft: `3px solid ${levelColor[r.level] || "#1890ff"}`,
                    }}
                  >
                    <Tag color={levelColor[r.level] || "blue"}>
                      {levelLabel[r.level] || r.level.toUpperCase()}
                    </Tag>
                    <Text>{r.action}</Text>
                  </div>
                ))}
              </>
            )}
          </Card>
        </Col>
      </Row>

      {/* 第二行：四维分析（全宽） */}
      <Card
        title="ExplainAgent 四维分析"
        style={{ ...cardStyle, marginTop: 16 }}
      >
        {dimLoading ? (
          <div style={{ textAlign: "center", padding: 24 }}>
            <Spin tip="分析中..." />
          </div>
        ) : dimError ? (
          <Alert
            type="warning"
            message="分析服务暂不可用，请检查 Agent Layer 服务状态"
            showIcon
          />
        ) : dimensions.length === 0 ? (
          <Alert type="info" message="暂无四维分析数据" showIcon />
        ) : (
          <>
            <Row gutter={[16, 16]}>
              {dimensions.map((d) => (
                <Col xs={24} sm={12} key={d.title}>
                  <Card
                    size="small"
                    style={{
                      background: "#111827",
                      borderColor: "#1f2937",
                      height: "100%",
                    }}
                  >
                    <Text strong style={{ color: "#60a5fa" }}>
                      {d.title}
                    </Text>
                    <Paragraph type="secondary" style={{ margin: "8px 0 0" }}>
                      {d.content}
                    </Paragraph>
                  </Card>
                </Col>
              ))}
            </Row>
          </>
        )}
      </Card>

      {/* 第三行：关联告警（全宽） */}
      <Card
        title={
          <Space size={6} align="center">
            <span>关联告警</span>
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              同源 IP
            </Text>
            <Tag
              color="red"
              style={{
                fontSize: 13,
                fontWeight: 600,
                margin: 0,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {alert.src_ip || "未知"}
            </Tag>
            <Text type="secondary" style={{ fontSize: 13 }}>
              · {relatedAlerts.length} 条
            </Text>
          </Space>
        }
        style={{ ...cardStyle, marginTop: 16 }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          columns={relatedCols}
          dataSource={relatedAlerts}
          rowKey="event_id"
          size="small"
          pagination={
            relatedAlerts.length > 10
              ? { pageSize: 10, size: "small", showSizeChanger: false }
              : false
          }
          scroll={{ x: 720 }}
          locale={{ emptyText: "暂无同源 IP 关联告警" }}
        />
      </Card>
    </div>
  );
}
