import { useState, useEffect, useMemo } from "react";
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Row,
  Col,
  Slider,
  InputNumber,
  App,
  Modal,
  Select,
  Drawer,
  Timeline,
  Empty,
} from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import Chart from "@/components/charts/Chart";
import { useModelsStore } from "@/stores";
import { modelsAPI } from "@/services/api";
import { echartsColors } from "@/theme/dark-cyber";
import type { ModelInfo } from "@/services/api";

function normalizeModel(m: ModelInfo): ModelInfo {
  return {
    ...m,
    metrics: m.metrics || {},
    ab_weight: m.ab_weight ?? 1,
    created_at: m.created_at ?? "",
    deployed_at: m.deployed_at ?? null,
  };
}

export default function Models() {
  const { modal, message } = App.useApp();
  const { models, setModels } = useModelsStore();
  const [abWeight, setAbWeight] = useState(50);
  const [loading, setLoading] = useState<string | null>(null);

  // History drawer
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyModelId, setHistoryModelId] = useState("");
  const [historyData, setHistoryData] = useState<
    {
      id: number;
      user_id: string;
      action: string;
      detail: Record<string, unknown>;
      created_at: string;
    }[]
  >([]);

  // Rollback version selector
  const [rollbackModalOpen, setRollbackModalOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<ModelInfo | null>(null);
  const [rollbackVersions, setRollbackVersions] = useState<
    { version: string; status: string }[]
  >([]);
  const [selectedRollbackVersion, setSelectedRollbackVersion] = useState<
    string | null
  >(null);

  function loadModels() {
    modelsAPI
      .list()
      .then((r) => {
        setModels(r.models.map(normalizeModel));
      })
      .catch(() => {
        message.error("加载模型列表失败");
        setModels([]);
      });
  }

  useEffect(() => {
    loadModels();
  }, [setModels]);

  const data = models;

  function handleABTest() {
    const staging = data.find((m) => m.status === "staging");
    const prod = data.find((m) => m.status === "production");
    if (!staging || !prod) {
      message.warning(
        "需要同时存在 production 与 staging 版本才能配置 A/B 测试",
      );
      return;
    }
    setLoading("ab");
    modelsAPI
      .abTest({
        model_a: prod.version,
        model_b: staging.version,
        weight_a: abWeight / 100,
      })
      .then(() => {
        message.success("A/B 测试配置已更新");
        loadModels();
      })
      .catch(() => {
        message.error("A/B 测试配置失败");
      })
      .finally(() => setLoading(null));
  }

  function handleRollback(r: ModelInfo) {
    setRollbackTarget(r);
    setSelectedRollbackVersion(null);
    modelsAPI
      .versions(r.model_id)
      .then((res) =>
        setRollbackVersions(
          res.versions.filter((v) => v.version !== r.version),
        ),
      )
      .catch(() => {
        const fallback = data.filter(
          (m) => m.model_id === r.model_id && m.version !== r.version,
        );
        setRollbackVersions(
          fallback.map((m) => ({ version: m.version, status: m.status })),
        );
      });
    setRollbackModalOpen(true);
  }

  function confirmRollback() {
    if (!rollbackTarget || !selectedRollbackVersion) {
      message.warning("请选择回滚目标版本");
      return;
    }
    setLoading(rollbackTarget.model_id + rollbackTarget.version);
    setRollbackModalOpen(false);
    modelsAPI
      .rollback(rollbackTarget.model_id, selectedRollbackVersion)
      .then(() => {
        message.success(`已回滚至 ${selectedRollbackVersion}`);
        loadModels();
      })
      .catch(() => {
        message.error("回滚失败");
      })
      .finally(() => setLoading(null));
  }

  function handleDeploy(r: ModelInfo) {
    modal.confirm({
      title: "确认上线",
      content: `确定要将 ${r.model_id} 版本 ${r.version} 上线为 production 吗？当前 production 版本将变为 staging。`,
      okText: "确认上线",
      cancelText: "取消",
      onOk: () => {
        setLoading(r.model_id + r.version);
        modelsAPI
          .deploy(r.model_id, r.version)
          .then(() => {
            message.success(`版本 ${r.version} 已上线`);
            loadModels();
          })
          .catch(() => {
            message.error("上线失败");
          })
          .finally(() => setLoading(null));
      },
    });
  }

  function handleOffline(r: ModelInfo) {
    modal.confirm({
      title: "确认下线",
      content: `确定要将 ${r.model_id} 当前 production 版本下线吗？下线后状态将变为 staging。`,
      okText: "确认下线",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () => {
        setLoading(r.model_id + r.version);
        modelsAPI
          .offline(r.model_id)
          .then(() => {
            message.success(`模型 ${r.model_id} 已下线`);
            loadModels();
          })
          .catch(() => {
            message.error("下线失败");
          })
          .finally(() => setLoading(null));
      },
    });
  }

  function handleShowHistory(modelId: string) {
    setHistoryModelId(modelId);
    setHistoryOpen(true);
    modelsAPI
      .history(modelId)
      .then((r) => setHistoryData(r.history))
      .catch(() => setHistoryData([]));
  }

  const compareOption = useMemo(() => {
    const metricNames = ["accuracy", "f1", "precision", "recall"];
    const versions = [...new Set(data.map((m) => m.version))];
    return {
      tooltip: { trigger: "axis" as const },
      legend: { data: versions, textStyle: { color: "#8c8c8c" } },
      grid: { left: 50, right: 16, top: 40, bottom: 24 },
      xAxis: {
        type: "category" as const,
        data: metricNames,
        axisLabel: { color: "#8c8c8c" },
      },
      yAxis: {
        type: "value" as const,
        min: 0,
        max: 1,
        axisLabel: { color: "#8c8c8c" },
      },
      series: versions.map((v, i) => {
        const model = data.find((m) => m.version === v);
        return {
          name: v,
          type: "bar",
          data: metricNames.map((k) => model?.metrics?.[k] ?? 0),
          itemStyle: { color: echartsColors[i % echartsColors.length] },
        };
      }),
    };
  }, [data]);

  const cols = [
    { title: "模型 ID", dataIndex: "model_id", width: 180 },
    { title: "版本", dataIndex: "version", width: 100 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (v: string) => (
        <Tag
          color={
            v === "production"
              ? "green"
              : v === "staging"
                ? "orange"
                : "default"
          }
        >
          {v}
        </Tag>
      ),
    },
    {
      title: "Accuracy",
      width: 90,
      render: (_: unknown, r: ModelInfo) =>
        r.metrics?.accuracy != null
          ? (r.metrics.accuracy * 100).toFixed(1) + "%"
          : "NaN%",
    },
    {
      title: "F1",
      width: 80,
      render: (_: unknown, r: ModelInfo) =>
        r.metrics?.f1 != null ? (r.metrics.f1 * 100).toFixed(1) + "%" : "NaN%",
    },
    {
      title: "AUC",
      width: 80,
      render: (_: unknown, r: ModelInfo) =>
        r.metrics?.auc != null ? r.metrics.auc.toFixed(3) : "-",
    },
    {
      title: "A/B 权重",
      dataIndex: "ab_weight",
      width: 90,
      render: (v: number) => (v != null ? (v * 100).toFixed(0) + "%" : "-"),
    },
    {
      title: "上线时间",
      dataIndex: "deployed_at",
      width: 170,
      render: (v: string | null) =>
        v ? v.replace("T", " ").slice(0, 19) : "-",
    },
    {
      title: "操作",
      width: 240,
      render: (_: unknown, r: ModelInfo) => {
        const busy = loading === r.model_id + r.version;
        return (
          <Space size="small">
            {r.status === "production" && (
              <>
                <Button
                  size="small"
                  type="link"
                  loading={busy}
                  onClick={() => handleRollback(r)}
                >
                  回滚
                </Button>
                <Button
                  size="small"
                  type="link"
                  danger
                  loading={busy}
                  onClick={() => handleOffline(r)}
                >
                  下线
                </Button>
              </>
            )}
            {r.status === "staging" && (
              <Button
                size="small"
                type="link"
                loading={busy}
                onClick={() => handleDeploy(r)}
              >
                上线
              </Button>
            )}
            <Button
              size="small"
              type="link"
              icon={<HistoryOutlined />}
              onClick={() => handleShowHistory(r.model_id)}
            >
              历史
            </Button>
          </Space>
        );
      },
    },
  ];

  const cardStyle = { borderColor: "#1f2937" };

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="模型版本列表" style={cardStyle}>
            <Table
              columns={cols}
              dataSource={data.map((m, i) => ({ ...m, key: i }))}
              size="small"
              pagination={false}
              locale={{ emptyText: <Empty description="暂无模型数据" /> }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="性能对比" style={cardStyle}>
            <Chart option={compareOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>

      <Card title="A/B 测试配置" style={{ marginTop: 16, ...cardStyle }}>
        <Space align="center" wrap>
          <span style={{ color: "#8c8c8c" }}>Production 权重:</span>
          <Slider
            style={{ width: 200 }}
            min={0}
            max={100}
            value={abWeight}
            onChange={setAbWeight}
          />
          <InputNumber
            min={0}
            max={100}
            value={abWeight}
            onChange={(v) => setAbWeight(v ?? 50)}
          />
          <span style={{ color: "#8c8c8c" }}>%</span>
          <Button
            type="primary"
            loading={loading === "ab"}
            onClick={handleABTest}
          >
            应用
          </Button>
        </Space>
      </Card>

      {/* 回滚版本选择 */}
      <Modal
        title={`回滚 ${rollbackTarget?.model_id || ""}`}
        open={rollbackModalOpen}
        onCancel={() => setRollbackModalOpen(false)}
        onOk={confirmRollback}
        okText="确认回滚"
        cancelText="取消"
      >
        <p>请选择要回滚到的目标版本：</p>
        <Select
          style={{ width: "100%" }}
          placeholder="选择版本"
          value={selectedRollbackVersion}
          onChange={setSelectedRollbackVersion}
          options={rollbackVersions.map((v) => ({
            label: `${v.version} (${v.status})`,
            value: v.version,
          }))}
        />
      </Modal>

      {/* 模型操作历史 */}
      <Drawer
        title={`操作历史 — ${historyModelId}`}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        width={480}
      >
        {historyData.length === 0 ? (
          <div style={{ color: "#8c8c8c", textAlign: "center", padding: 40 }}>
            暂无操作记录
          </div>
        ) : (
          <Timeline
            items={historyData.map((h) => ({
              children: (
                <div key={h.id}>
                  <Tag color="blue">{h.action}</Tag>
                  <span
                    style={{ color: "#8c8c8c", fontSize: 12, marginLeft: 8 }}
                  >
                    {h.created_at?.replace("T", " ").slice(0, 19)}
                  </span>
                  <div style={{ fontSize: 12, color: "#8c8c8c", marginTop: 4 }}>
                    操作人: {h.user_id}
                  </div>
                  {h.detail && Object.keys(h.detail).length > 0 && (
                    <div
                      style={{ fontSize: 12, color: "#595959", marginTop: 2 }}
                    >
                      {JSON.stringify(h.detail)}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        )}
      </Drawer>
    </div>
  );
}
