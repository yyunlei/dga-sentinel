import { useState, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Badge, Space, Typography } from "antd";
import {
  DashboardOutlined,
  SearchOutlined,
  AlertOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  BarChartOutlined,
  SafetyCertificateOutlined,
  RobotOutlined,
  BulbOutlined,
} from "@ant-design/icons";
import { alertsAPI, healthAPI } from "@/services/api";

const { Header, Sider, Content, Footer } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "实时监控" },
  { key: "/detection", icon: <SearchOutlined />, label: "域名检测" },
  { key: "/alerts", icon: <AlertOutlined />, label: "告警中心" },
  { key: "/models", icon: <ExperimentOutlined />, label: "模型管理" },
  { key: "/pipeline", icon: <ApartmentOutlined />, label: "DAG 编排" },
  { key: "/reports", icon: <BarChartOutlined />, label: "分析报表" },
  { key: "/agent-monitor", icon: <RobotOutlined />, label: "Agent 监控" },
  { key: "/recommendations", icon: <BulbOutlined />, label: "运营建议" },
];

const ALERTS_ACK_EVENT = "alerts-acknowledged";

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [unackCount, setUnackCount] = useState(0);
  const [healthStatus, setHealthStatus] = useState<string>("检查中...");
  const [healthChecks, setHealthChecks] = useState<Record<string, string>>({});
  const navigate = useNavigate();
  const location = useLocation();

  const fetchUnackCount = () => {
    alertsAPI
      .getUnacknowledgedCount()
      .then(setUnackCount)
      .catch(() => setUnackCount(0));
  };

  useEffect(() => {
    fetchUnackCount();
    const timer = setInterval(fetchUnackCount, 30_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (location.pathname === "/alerts") fetchUnackCount();
  }, [location.pathname]);

  useEffect(() => {
    const onAck = () => fetchUnackCount();
    window.addEventListener(ALERTS_ACK_EVENT, onAck);
    return () => window.removeEventListener(ALERTS_ACK_EVENT, onAck);
  }, []);

  useEffect(() => {
    const fetchHealth = () => {
      healthAPI
        .readyz()
        .then((r) => {
          setHealthStatus(r.status === "ready" ? "系统正常" : "部分服务异常");
          setHealthChecks(r.checks ?? {});
        })
        .catch(() => {
          setHealthStatus("系统不可达");
          setHealthChecks({});
        });
    };
    fetchHealth();
    const timer = setInterval(fetchHealth, 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <Layout style={{ minHeight: "100vh", background: "#0a0e1a" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{ borderRight: "1px solid #1f2937" }}
      >
        <div
          style={{
            height: 48,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid #1f2937",
          }}
        >
          <SafetyCertificateOutlined
            style={{ fontSize: 24, color: "#1668dc" }}
          />
          {!collapsed && (
            <Text
              strong
              style={{ marginLeft: 8, color: "#1668dc", fontSize: 16 }}
            >
              DGA 检测平台
            </Text>
          )}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => {
            navigate(key);
          }}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid #1f2937",
            background: "#0d1220",
          }}
        >
          <Text style={{ color: "#8c8c8c" }}>DGA 智能威胁检测平台</Text>
          <Space>
            <span
              role="button"
              tabIndex={0}
              onClick={() => navigate("/alerts")}
              onKeyDown={(e: React.KeyboardEvent) =>
                e.key === "Enter" && navigate("/alerts")
              }
              style={{
                cursor: "pointer",
                padding: "4px 8px",
                display: "inline-flex",
                alignItems: "center",
                position: "relative",
              }}
              title="告警中心"
            >
              <Badge count={unackCount} overflowCount={9999} size="small">
                <AlertOutlined style={{ fontSize: 18, color: "#8c8c8c" }} />
              </Badge>
            </span>
          </Space>
        </Header>
        <Content
          style={{
            margin: 16,
            overflow: "auto",
            background: "#0a0e1a",
            minHeight: "calc(100vh - 120px)",
            position: "relative",
            zIndex: 1,
          }}
          suppressHydrationWarning
        >
          <Outlet />
        </Content>
        <Footer
          style={{
            textAlign: "center",
            padding: "8px 16px",
            borderTop: "1px solid #1f2937",
            background: "#0d1220",
            fontSize: 12,
            color: "#595959",
          }}
        >
          <Space split={<span style={{ color: "#1f2937" }}>|</span>}>
            <Text
              type="secondary"
              style={{
                color: healthStatus === "系统正常" ? "#52c41a" : "#faad14",
              }}
            >
              {healthStatus}
            </Text>
            {Object.entries(healthChecks)
              .slice(0, 3)
              .map(([k, v]) => (
                <Text
                  key={k}
                  type="secondary"
                  style={{ color: v.startsWith("ok") ? undefined : "#f5222d" }}
                >
                  {k}: {v.startsWith("ok") ? "ok" : "fail"}
                </Text>
              ))}
          </Space>
        </Footer>
      </Layout>
    </Layout>
  );
}
