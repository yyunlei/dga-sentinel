import { useState } from "react";
import {
  Card,
  Input,
  Button,
  Upload,
  Row,
  Col,
  Space,
  Typography,
  Table,
  Tag,
  message,
  Empty,
} from "antd";
import {
  SearchOutlined,
  UploadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import Chart from "@/components/charts/Chart";
import { useDetectionStore, useDashboardStore } from "@/stores";
import { scoreAPI, explainAPI } from "@/services/api";
import { echartsColors, severityColors } from "@/theme/dark-cyber";
import type { ScoreResult } from "@/services/api";

const { TextArea } = Input;
const { Text } = Typography;

export default function Detection() {
  const [input, setInput] = useState("");
  const [error, setError] = useState(false);
  const {
    loading,
    results,
    explanation,
    setLoading,
    setResults,
    setExplanation,
  } = useDetectionStore();

  async function handleDetect() {
    const domains = input
      .split(/[\n,;\s]+/)
      .map((d) => d.trim())
      .filter(Boolean);
    if (!domains.length) return;
    setLoading(true);
    setExplanation("");
    setError(false);
    try {
      const resp = await scoreAPI.score(domains);
      setResults(resp.results);
      // Push DGA-positive results to dashboard detection alerts
      const { pushDetectionAlert } = useDashboardStore.getState();
      resp.results
        .filter((r) => r.is_dga)
        .forEach((r) => {
          pushDetectionAlert({
            event_id: `det-${Date.now()}-${r.domain}`,
            timestamp: new Date().toISOString(),
            domain: r.domain,
            src_ip: "",
            score: r.score,
            severity:
              r.score > 0.9 ? "CRITICAL" : r.score > 0.7 ? "HIGH" : "MEDIUM",
            family: r.family,
            is_dga: true,
            acknowledged: false,
          });
        });
    } catch {
      message.error("评分服务不可用");
      setResults([]);
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  /** 若后端返回了原始 API 错误文案（401、api key 等），不展示给用户 */
  function sanitizeExplanation(text: string, r: ScoreResult): string {
    const lower = text.toLowerCase();
    if (
      lower.includes("authentication fails") ||
      (lower.includes("api key") && lower.includes("invalid")) ||
      (lower.includes("解释生成失败") &&
        (lower.includes("401") || lower.includes("api key")))
    ) {
      return `DeepSeek API 认证失败，请检查服务端环境变量 DEEPSEEK_API_KEY 是否已配置且有效。`;
    }
    return text;
  }

  async function handleExplain(r: ScoreResult) {
    setExplanation("正在生成解释...");
    try {
      const resp = await explainAPI.explain(r.domain, r.score, r.family);
      setExplanation(sanitizeExplanation(resp.explanation, r));
    } catch {
      message.error("解释服务不可用");
      setExplanation("");
    }
  }
  const selected = results[0];

  const gaugeOption = selected
    ? {
        series: [
          {
            type: "gauge",
            startAngle: 200,
            endAngle: -20,
            min: 0,
            max: 1,
            splitNumber: 5,
            pointer: { show: true, length: "60%" },
            axisLine: {
              lineStyle: {
                width: 20,
                color: [
                  [0.3, "#52c41a"],
                  [0.7, "#faad14"],
                  [1, "#f5222d"],
                ],
              },
            },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { color: "#8c8c8c", fontSize: 10 },
            detail: {
              valueAnimation: true,
              fontSize: 28,
              color: "#e8e8e8",
              offsetCenter: [0, "70%"],
              formatter: "{value}",
            },
            data: [{ value: selected.score.toFixed(3) }],
          },
        ],
      }
    : {};

  const radarOption = selected?.features
    ? {
        radar: {
          indicator: Object.keys(selected.features)
            .slice(0, 6)
            .map((k) => ({ name: k, max: 1 })),
          axisName: { color: "#8c8c8c", fontSize: 10 },
        },
        series: [
          {
            type: "radar",
            data: [
              {
                value: Object.values(selected.features).slice(0, 6),
                areaStyle: { color: "rgba(22,104,220,0.3)" },
              },
            ],
            itemStyle: { color: echartsColors[0] },
          },
        ],
      }
    : null;

  const cols = [
    { title: "域名", dataIndex: "domain", ellipsis: true },
    {
      title: "分数",
      dataIndex: "score",
      width: 80,
      render: (v: number) => (
        <span
          style={{
            color: v > 0.7 ? "#f5222d" : v > 0.3 ? "#faad14" : "#52c41a",
          }}
        >
          {v?.toFixed(3)}
        </span>
      ),
    },
    {
      title: "DGA",
      dataIndex: "is_dga",
      width: 70,
      render: (v: boolean) =>
        v ? <Tag color="red">是</Tag> : <Tag color="green">否</Tag>,
    },
    {
      title: "家族",
      dataIndex: "family",
      width: 100,
      render: (v: string | null) => v || "-",
    },
    {
      title: "置信度",
      dataIndex: "family_confidence",
      width: 80,
      render: (v: number | null) =>
        v != null ? (v * 100).toFixed(1) + "%" : "-",
    },
    {
      title: "操作",
      width: 80,
      render: (_: unknown, r: ScoreResult) => (
        <Button size="small" type="link" onClick={() => handleExplain(r)}>
          解释
        </Button>
      ),
    },
  ];

  const cardStyle = { borderColor: "#1f2937" };

  return (
    <div>
      <Card title="域名检测" style={cardStyle}>
        <Row gutter={16}>
          <Col flex="auto">
            <TextArea
              rows={3}
              placeholder="输入域名（每行一个，或逗号分隔）"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
          </Col>
          <Col>
            <Space direction="vertical">
              <Button
                type="primary"
                icon={<SearchOutlined />}
                loading={loading}
                onClick={handleDetect}
              >
                检测
              </Button>
              <Upload
                accept=".txt,.csv"
                showUploadList={false}
                beforeUpload={(file) => {
                  file.text().then((t) => setInput(t));
                  return false;
                }}
              >
                <Button icon={<UploadOutlined />}>上传文件</Button>
              </Upload>
            </Space>
          </Col>
        </Row>
      </Card>

      {error && results.length === 0 && (
        <Card style={{ marginTop: 16, ...cardStyle, textAlign: "center" }}>
          <Empty description="评分服务不可用" />
          <Button
            icon={<ReloadOutlined />}
            onClick={handleDetect}
            style={{ marginTop: 12 }}
          >
            重试
          </Button>
        </Card>
      )}

      {results.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={8}>
            <Card title="风险评分" style={cardStyle}>
              <Chart option={gaugeOption} style={{ height: 220 }} />
              {selected && (
                <div style={{ textAlign: "center" }}>
                  <Tag
                    color={
                      selected.is_dga ? severityColors.HIGH : severityColors.LOW
                    }
                  >
                    {selected.is_dga ? "DGA 域名" : "正常域名"}
                  </Tag>
                </div>
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            {radarOption && (
              <Card title="特征雷达" style={cardStyle}>
                <Chart option={radarOption} style={{ height: 250 }} />
              </Card>
            )}
            {!radarOption && (
              <Card title="家族概率" style={cardStyle}>
                <Chart
                  option={{
                    tooltip: {
                      formatter: (p: { name: string; value: number }) =>
                        `${p.name}：${(p.value * 100).toFixed(1)}%`,
                    },
                    grid: { left: 48, right: 16, top: 24, bottom: 24 },
                    xAxis: {
                      type: "category",
                      data: results
                        .filter((r) => r.family)
                        .map((r) => r.family!),
                      axisLabel: { color: "#8c8c8c" },
                    },
                    yAxis: {
                      type: "value",
                      min: 0,
                      max: 1,
                      axisLabel: {
                        color: "#8c8c8c",
                        formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
                      },
                    },
                    series: [
                      {
                        type: "bar",
                        barMaxWidth: 64,
                        data: results
                          .filter((r) => r.family)
                          .map((r) => r.family_confidence),
                        label: {
                          show: true,
                          position: "top",
                          color: "#e8e8e8",
                          formatter: (p: { value: number }) =>
                            `${(p.value * 100).toFixed(1)}%`,
                        },
                        itemStyle: { color: echartsColors[0] },
                      },
                    ],
                  }}
                  style={{ height: 250 }}
                />
              </Card>
            )}
          </Col>
          <Col xs={24} lg={8}>
            <Card
              title="AI 解释"
              style={cardStyle}
              styles={{ body: { minHeight: 250 } }}
            >
              {explanation ? (
                <Text style={{ whiteSpace: "pre-wrap" }}>{explanation}</Text>
              ) : (
                <Text type="secondary">点击结果行的"解释"按钮获取 AI 分析</Text>
              )}
            </Card>
          </Col>
        </Row>
      )}

      {results.length > 0 && (
        <Card title="检测结果" style={{ marginTop: 16, ...cardStyle }}>
          <Table
            columns={cols}
            dataSource={results.map((r, i) => ({ ...r, key: i }))}
            size="small"
            pagination={{ pageSize: 20 }}
          />
        </Card>
      )}
    </div>
  );
}
