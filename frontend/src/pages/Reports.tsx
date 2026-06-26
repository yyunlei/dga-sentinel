import { useState, useEffect, useMemo } from 'react';
import { Card, Row, Col, Table, DatePicker, Spin, message, Empty, Button, Alert } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import Chart from '@/components/charts/Chart';
import { echartsColors } from '@/theme/dark-cyber';
import { reportsAPI, type ReportStats } from '@/services/api';
import type { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;

export default function Reports() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ReportStats | null>(null);
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function fetchData() {
    setLoading(true);
    setError(null);
    const params = dateRange
      ? { start_date: dateRange[0], end_date: dateRange[1] }
      : { days: 30 };
    reportsAPI.stats(params)
      .then(setData)
      .catch(() => { setData(null); setError('报表数据加载失败'); message.error('报表数据加载失败'); })
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchData(); }, [dateRange]);

  const trendDays = data?.trend ?? [];
  const topDomains = data?.topDomains ?? [];
  const topHosts = data?.topHosts ?? [];
  const heatmapData = data?.heatmap ?? [];

  const trendOption = useMemo(() => ({
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['总检测量', 'DGA 命中'], textStyle: { color: '#8c8c8c' } },
    grid: { left: 50, right: 16, top: 40, bottom: 24 },
    xAxis: { type: 'category' as const, data: trendDays.map((d) => d.date), axisLabel: { color: '#595959' } },
    yAxis: [
      { type: 'value' as const, name: '总量', axisLabel: { color: '#595959' } },
      { type: 'value' as const, name: 'DGA', axisLabel: { color: '#595959' } },
    ],
    series: [
      { name: '总检测量', type: 'line', smooth: true, data: trendDays.map((d) => d.total), itemStyle: { color: echartsColors[0] }, areaStyle: { color: 'rgba(22,104,220,0.1)' } },
      { name: 'DGA 命中', type: 'bar', yAxisIndex: 1, data: trendDays.map((d) => d.dga), itemStyle: { color: echartsColors[4] } },
    ],
  }), [trendDays]);

  const maxHeat = Math.max(1, ...heatmapData.map((d) => d[2]));
  const heatmapOption = useMemo(() => ({
    tooltip: { formatter: (p: { value: [number, number, number] }) => `${['周一','周二','周三','周四','周五','周六','周日'][p.value[1]]} ${p.value[0]}:00 — ${p.value[2]} 次告警` },
    grid: { left: 60, right: 40, top: 16, bottom: 40 },
    xAxis: { type: 'category' as const, data: Array.from({ length: 24 }, (_, i) => `${i}:00`), axisLabel: { color: '#595959', fontSize: 10 }, splitArea: { show: true } },
    yAxis: { type: 'category' as const, data: ['周一','周二','周三','周四','周五','周六','周日'], axisLabel: { color: '#595959' } },
    visualMap: { min: 0, max: maxHeat, calculable: true, orient: 'horizontal' as const, left: 'center', bottom: 0, inRange: { color: ['#0a0e1a', '#1668dc', '#f5222d'] }, textStyle: { color: '#8c8c8c' } },
    series: [{ type: 'heatmap', data: heatmapData, label: { show: false }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
  }), [heatmapData, maxHeat]);

  const domainCols = [
    { title: '#', dataIndex: 'rank', width: 40 },
    { title: '域名', dataIndex: 'domain', ellipsis: true },
    { title: '命中次数', dataIndex: 'count', width: 90 },
    { title: '家族', dataIndex: 'family', width: 100 },
  ];

  const hostCols = [
    { title: '#', dataIndex: 'rank', width: 40 },
    { title: '源 IP', dataIndex: 'src_ip', width: 150 },
    { title: '告警数', dataIndex: 'alerts', width: 80 },
    { title: '唯一域名', dataIndex: 'unique_domains', width: 90 },
  ];

  const cardStyle = { borderColor: '#1f2937' };

  if (loading) return <Spin size="large" tip="加载报表数据..." style={{ display: 'block', margin: '100px auto' }} />;
  if (error) return (
    <div style={{ textAlign: 'center', padding: '80px 0' }}>
      <Alert type="warning" message="服务暂不可用" description="报表服务暂不可用，可能是数据源未就绪，请稍后重试。" showIcon style={{ maxWidth: 480, margin: '0 auto 24px' }} />
      <Button icon={<ReloadOutlined />} onClick={fetchData}>重试</Button>
    </div>
  );

  return (
    <div>
      <Card title="趋势分析" style={cardStyle} extra={<RangePicker size="small" onChange={(dates) => {
          if (dates && dates[0] && dates[1]) {
            setDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]);
          } else {
            setDateRange(null);
          }
        }} />}>
        <Chart option={trendOption} style={{ height: 300 }} />
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Top DGA 域名" style={cardStyle}>
            <Table columns={domainCols} dataSource={topDomains} size="small" pagination={false} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Top 受影响主机" style={cardStyle}>
            <Table columns={hostCols} dataSource={topHosts} size="small" pagination={false} />
          </Card>
        </Col>
      </Row>

      <Card title="告警热力图（按小时/星期）" style={{ marginTop: 16, ...cardStyle }}>
        <Chart option={heatmapOption} style={{ height: 300 }} />
      </Card>
    </div>
  );
}
