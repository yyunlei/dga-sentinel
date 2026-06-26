import { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Table, Typography, Space, Tag, Spin, Segmented, Collapse } from 'antd';
import { SendOutlined, MessageOutlined, CloseOutlined, BookOutlined, DatabaseOutlined, BarChartOutlined, TableOutlined } from '@ant-design/icons';
import { queryAPI, ragAPI } from '@/services/api';
import type { RAGSource } from '@/services/api';
import Chart from '@/components/charts/Chart';

const { Text, Paragraph } = Typography;

type ChatMode = 'sql' | 'rag';

type ResultView = 'chart' | 'table';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'sql' | 'data' | 'rag';
  sql?: string;
  data?: Record<string, unknown>[];
  sources?: RAGSource[];
  loading?: boolean;
  view?: ResultView;
}

const welcomeMessages: Record<ChatMode, ChatMessage> = {
  sql: {
    role: 'assistant',
    content: '数据查询模式：输入自然语言，我会转换为 SQL 查询并返回结果。试试"查询今日高危告警"。',
    type: 'text',
  },
  rag: {
    role: 'assistant',
    content: '知识库模式：基于威胁情报知识库回答问题，支持来源引用。试试"什么是 DGA 域名"。',
    type: 'text',
  },
};

function renderDataTable(data: Record<string, unknown>[]) {
  if (!data.length) return null;
  const cols = Object.keys(data[0]).map((k) => ({ title: k, dataIndex: k, key: k, ellipsis: true }));
  return <Table columns={cols} dataSource={data.map((r, i) => ({ ...r, key: i }))} size="small" pagination={false} style={{ marginTop: 8 }} />;
}

// ──────────────────────────────────────────────────────────────────────
// Auto-detect chartable shape:
//   - exactly 2 columns where one is string-like (label) and one is numeric
//   - or N rows ≤ 50 with a "date/day/time/family/domain" column
// Returns [labels[], values[], labelKey, valueKey] or null.
// ──────────────────────────────────────────────────────────────────────
function detectChartable(
  data: Record<string, unknown>[],
): { labels: string[]; values: number[]; labelKey: string; valueKey: string } | null {
  if (!data.length || data.length > 100) return null;
  const cols = Object.keys(data[0]);
  if (cols.length < 2) return null;

  const numericCols = cols.filter((k) =>
    data.every((r) => r[k] === null || typeof r[k] === 'number' || (!isNaN(parseFloat(String(r[k]))) && isFinite(parseFloat(String(r[k]))))),
  );
  const stringCols = cols.filter((k) => !numericCols.includes(k));
  if (numericCols.length === 0 || stringCols.length === 0) return null;

  // Prefer date-like / category columns as label
  const labelKey =
    stringCols.find((k) => /date|day|time|family|domain|name|tenant|severity|hour/i.test(k)) ||
    stringCols[0];
  // Prefer count-like numeric column as value
  const valueKey =
    numericCols.find((k) => /count|cnt|total|hits|num|amount|sum|score/i.test(k)) ||
    numericCols[0];

  const labels = data.map((r) => String(r[labelKey] ?? ''));
  const values = data.map((r) => {
    const v = r[valueKey];
    return typeof v === 'number' ? v : parseFloat(String(v ?? 0)) || 0;
  });
  return { labels, values, labelKey, valueKey };
}

function renderChart(data: Record<string, unknown>[]) {
  const c = detectChartable(data);
  if (!c) return null;
  const isBar = c.labels.length <= 30;
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 50, right: 16, top: 24, bottom: 60 },
    xAxis: {
      type: 'category',
      data: c.labels,
      axisLabel: { color: '#a0a0a0', rotate: c.labels.length > 6 ? 30 : 0, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: c.valueKey,
      nameTextStyle: { color: '#8c8c8c', fontSize: 11 },
      axisLabel: { color: '#a0a0a0', fontSize: 11 },
      splitLine: { lineStyle: { color: '#1f2937' } },
    },
    series: [
      {
        type: isBar ? 'bar' : 'line',
        name: c.valueKey,
        data: c.values,
        itemStyle: { color: '#22d3ee' },
        smooth: true,
        showSymbol: c.labels.length <= 30,
      },
    ],
  };
  return <Chart option={option} style={{ width: '100%', height: 220, marginTop: 8 }} />;
}

function renderSources(sources: RAGSource[]) {
  if (!sources.length) return null;
  return (
    <Collapse
      size="small"
      style={{ marginTop: 8, background: '#0a0e1a', border: '1px solid #1f2937' }}
      items={[{
        key: 'sources',
        label: <Text style={{ color: '#8c8c8c', fontSize: 12 }}>来源引用 ({sources.length})</Text>,
        children: sources.map((s, i) => (
          <div key={i} style={{ marginBottom: 8, padding: '4px 0', borderBottom: i < sources.length - 1 ? '1px solid #1f2937' : 'none' }}>
            <Space size={4}>
              <Tag color="cyan" style={{ fontSize: 11 }}>{s.category}</Tag>
              <Text style={{ color: '#8c8c8c', fontSize: 11 }}>相关度: {(s.score * 100).toFixed(0)}%</Text>
            </Space>
            <Paragraph style={{ color: '#a0a0a0', fontSize: 12, margin: '4px 0 0', lineHeight: 1.4 }} ellipsis={{ rows: 3, expandable: true }}>
              {s.content}
            </Paragraph>
            <Text style={{ color: '#595959', fontSize: 11 }}>{s.source}</Text>
          </div>
        )),
      }]}
    />
  );
}

function MessageBubble({
  msg,
  onToggleView,
}: {
  msg: ChatMessage;
  onToggleView?: (next: ResultView) => void;
}) {
  const isUser = msg.role === 'user';
  const chartable = msg.data ? detectChartable(msg.data) !== null : false;
  const view: ResultView = msg.view ?? (chartable ? 'chart' : 'table');
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      <div style={{
        maxWidth: '95%',
        padding: '8px 12px',
        borderRadius: 8,
        background: isUser ? '#1668dc' : '#1a2035',
        color: '#e8e8e8',
      }}>
        {msg.loading ? (
          <Spin size="small" />
        ) : (
          <>
            <Text style={{ color: '#e8e8e8', whiteSpace: 'pre-wrap' }}>{msg.content}</Text>
            {msg.sql && (
              <div style={{ marginTop: 8, padding: '4px 8px', background: '#0a0e1a', borderRadius: 4 }}>
                <Tag color="blue" style={{ marginBottom: 4 }}>SQL</Tag>
                <Paragraph code style={{ margin: 0, fontSize: 12, color: '#8c8c8c' }}>{msg.sql}</Paragraph>
              </div>
            )}
            {msg.data && msg.data.length > 0 && (
              <>
                {chartable && onToggleView && (
                  <div style={{ marginTop: 8, marginBottom: 4 }}>
                    <Segmented
                      size="small"
                      value={view}
                      onChange={(v) => onToggleView(v as ResultView)}
                      options={[
                        { label: <Space size={4}><BarChartOutlined />图表</Space>, value: 'chart' },
                        { label: <Space size={4}><TableOutlined />表格</Space>, value: 'table' },
                      ]}
                    />
                  </div>
                )}
                {view === 'chart' && chartable ? renderChart(msg.data) : renderDataTable(msg.data)}
              </>
            )}
            {msg.sources && renderSources(msg.sources)}
          </>
        )}
      </div>
    </div>
  );
}

export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ChatMode>('sql');
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessages.sql]);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function handleModeChange(val: string | number) {
    const newMode = val as ChatMode;
    setMode(newMode);
    setMessages([welcomeMessages[newMode]]);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    setInput('');
    const userMsg: ChatMessage = { role: 'user', content: text, type: 'text' };
    const loadingMsg: ChatMessage = { role: 'assistant', content: '', loading: true };
    setMessages((prev) => [...prev, userMsg, loadingMsg]);

    try {
      if (mode === 'rag') {
        const resp = await ragAPI.query(text);
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: resp.answer || '未找到相关知识',
          type: 'rag',
          sources: resp.sources?.length ? resp.sources : undefined,
        };
        setMessages((prev) => [...prev.slice(0, -1), assistantMsg]);
      } else {
        const resp = await queryAPI.query(text);
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: resp.explanation || (resp.error ? `查询出错: ${resp.error}` : '查询完成'),
          type: resp.sql ? 'sql' : 'text',
          sql: resp.sql || undefined,
          data: resp.data?.length ? resp.data : undefined,
        };
        setMessages((prev) => [...prev.slice(0, -1), assistantMsg]);
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : '请求失败';
      setMessages((prev) => [...prev.slice(0, -1), { role: 'assistant', content: `请求失败: ${errMsg}`, type: 'text' }]);
    }
  }

  if (!open) {
    return (
      <Button type="primary" shape="circle" icon={<MessageOutlined />}
        style={{ position: 'fixed', right: 24, bottom: 24, width: 48, height: 48, zIndex: 1000 }}
        onClick={() => setOpen(true)} />
    );
  }

  return (
    <Card
      title={<Space><MessageOutlined />DGA 智能助手</Space>}
      extra={<CloseOutlined onClick={() => setOpen(false)} style={{ cursor: 'pointer' }} />}
      style={{ position: 'fixed', right: 24, bottom: 24, width: 560, height: 640, zIndex: 1000, display: 'flex', flexDirection: 'column', borderColor: '#1f2937' }}
      styles={{ body: { flex: 1, overflow: 'auto', padding: '12px' } }}
    >
      <div style={{ marginBottom: 8 }}>
        <Segmented
          block
          value={mode}
          onChange={handleModeChange}
          options={[
            { label: <Space size={4}><DatabaseOutlined />数据查询</Space>, value: 'sql' },
            { label: <Space size={4}><BookOutlined />知识库</Space>, value: 'rag' },
          ]}
          style={{ background: '#0a0e1a' }}
        />
      </div>
      <div style={{ height: 470, overflow: 'auto', marginBottom: 8 }}>
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            msg={m}
            onToggleView={(next) =>
              setMessages((prev) => prev.map((mm, j) => (j === i ? { ...mm, view: next } : mm)))
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
      <Input.Search
        placeholder={mode === 'rag' ? '输入安全知识问题...' : '输入数据查询问题...'}
        enterButton={<SendOutlined />}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onSearch={handleSend}
      />
    </Card>
  );
}
