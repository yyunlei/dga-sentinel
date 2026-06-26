import { useState, useEffect, useCallback } from 'react';
import { Row, Col, Card, Statistic, Badge, Table, Timeline, Tag, Space, Spin, message, Empty, Button, Alert } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { agentAPI } from '@/services/api';
import type { AgentMetrics, AgentExecRecord, A2AMessage } from '@/services/api';

const statusColorMap = { success: 'green', error: 'red', timeout: 'orange' } as const;
const a2aColorMap: Record<string, string> = { TriageAgent: 'blue', ExplainAgent: 'green', ThreatIntelAgent: 'orange', ResponseAgent: 'red' };

const columns = [
  { title: '时间', dataIndex: 'timestamp', width: 160 },
  { title: 'Agent', dataIndex: 'agent', width: 140, render: (v: string) => <Tag color="blue">{v}</Tag> },
  { title: '动作', dataIndex: 'action', width: 100 },
  { title: '耗时(ms)', dataIndex: 'duration_ms', width: 90, sorter: (a: AgentExecRecord, b: AgentExecRecord) => a.duration_ms - b.duration_ms },
  { title: '状态', dataIndex: 'status', width: 80, render: (v: 'success' | 'error' | 'timeout') => <Tag color={statusColorMap[v]}>{v}</Tag> },
  { title: 'Trace ID', dataIndex: 'trace_id', width: 140, render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span> },
];

const cardStyle = { borderColor: '#1f2937' };

export default function AgentMonitor() {
  const [agents, setAgents] = useState<AgentMetrics[]>([]);
  const [execHistory, setExecHistory] = useState<(AgentExecRecord & { key: string })[]>([]);
  const [a2aMessages, setA2aMessages] = useState<{ color: string; children: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [metricsResp, historyResp, msgResp] = await Promise.all([
        agentAPI.metrics(),
        agentAPI.execHistory(30),
        agentAPI.a2aMessages(10),
      ]);
      setAgents(metricsResp.agents || []);
      setExecHistory((historyResp.records || []).map((r, i) => ({ ...r, key: `exec-${i}` })));
      setA2aMessages((msgResp.messages || []).map((m) => ({
        color: a2aColorMap[m.from_agent] || 'blue',
        children: `${m.from_agent} → ${m.to_agent}: ${m.message} (${m.timestamp?.slice(11, 19) || ''})`,
      })));
    } catch (err) {
      setError('Agent 监控数据加载失败');
      message.error('Agent 监控数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading && agents.length === 0) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
  }

  if (error && agents.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 0' }}>
        <Alert type="warning" message="服务暂不可用" description="Agent 监控服务暂不可用，请稍后重试。" showIcon style={{ maxWidth: 480, margin: '0 auto 24px' }} />
        <Button icon={<ReloadOutlined />} onClick={loadData}>重试</Button>
      </div>
    );
  }

  return (
    <div>
      <Row gutter={[16, 16]}>
        {agents.map((a) => (
          <Col xs={24} sm={12} lg={6} key={a.name}>
            <Card style={cardStyle} title={<Space><Badge status={a.status === 'online' ? 'success' : 'error'} />{a.name}</Space>}>
              <Statistic title="执行次数" value={a.execCount} />
              <Row gutter={16} style={{ marginTop: 8 }}>
                <Col span={12}><Statistic title="平均延迟" value={a.avgLatency} suffix="ms" valueStyle={{ fontSize: 16 }} /></Col>
                <Col span={12}><Statistic title="错误率" value={a.errorRate} suffix="%" valueStyle={{ fontSize: 16, color: a.errorRate > 1.5 ? '#f5222d' : '#52c41a' }} /></Col>
              </Row>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="执行历史" style={cardStyle} extra={
            <ReloadOutlined style={{ cursor: 'pointer' }} onClick={loadData} />
          }>
            <Table columns={columns} dataSource={execHistory} size="small" pagination={{ pageSize: 8 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="A2A 消息流" style={cardStyle}>
            <Timeline items={a2aMessages} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
