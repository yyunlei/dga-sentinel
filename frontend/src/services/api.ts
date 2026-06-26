const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// --- Score ---
export interface ScoreResult {
  domain: string;
  score: number;
  is_dga: boolean;
  family: string | null;
  family_confidence: number | null;
  model_version: string;
  features?: Record<string, number>;
}

export interface ScoreResponse {
  results: ScoreResult[];
  trace_id: string;
  latency_ms: number;
}

export const scoreAPI = {
  score(domains: string[]) {
    return request<ScoreResponse>("/score", {
      method: "POST",
      body: JSON.stringify({ domains }),
    });
  },
};

// --- Explain ---
export interface ExplainResponse {
  domain: string;
  explanation: string;
  trace_id: string;
}

export const explainAPI = {
  explain(domain: string, score: number, family: string | null) {
    return request<ExplainResponse>("/explain", {
      method: "POST",
      body: JSON.stringify({ domain, score, family }),
    });
  },
};

// --- Alerts ---
export interface AlertItem {
  event_id: string;
  timestamp: string;
  domain: string;
  src_ip: string;
  score: number;
  severity: string;
  family: string | null;
  is_dga: boolean;
  acknowledged: boolean;
  pipeline_id?: string;
}

export interface AlertStats {
  total: number;
  pending: number;
  acknowledged: number;
  total_yesterday: number;
  by_severity: { name: string; value: number }[];
}

export interface DomainGroupItem {
  domain: string;
  alert_count: number;
  unique_src_ips: string[];
  unique_src_ip_count: number;
  max_severity: string;
  max_score: number;
  family: string | null;
  first_seen: string;
  last_seen: string;
  all_acknowledged: boolean;
}

export interface DomainGroupResponse {
  total_domains: number;
  groups: DomainGroupItem[];
}

export const alertsAPI = {
  list(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<{ alerts: AlertItem[]; total: number }>(`/alerts${qs}`);
  },
  /** 仅用于右上角角标：待处理（未确认）告警总数 */
  getUnacknowledgedCount(): Promise<number> {
    return request<{ total: number }>(
      `/alerts?acknowledged=false&limit=1`,
    ).then((r) => r.total ?? 0);
  },
  get(id: string) {
    return request<AlertItem>(`/alerts/${id}`);
  },
  acknowledge(id: string) {
    return request<{ ok: boolean }>(`/alerts/${id}/acknowledge`, {
      method: "POST",
    });
  },
  stats() {
    return request<AlertStats>("/alerts/stats");
  },
  listGrouped(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<DomainGroupResponse>(`/alerts/grouped${qs}`);
  },
  acknowledgeByDomain(domains: string[]) {
    return request<{ updated: number }>("/alerts/acknowledge-by-domain", {
      method: "POST",
      body: JSON.stringify({ domains }),
    });
  },
};

// --- Models ---
export interface ModelInfo {
  model_id: string;
  version: string;
  status: string;
  metrics: Record<string, number>;
  ab_weight: number;
  created_at: string;
  deployed_at: string | null;
}

export const modelsAPI = {
  list() {
    return request<{ models: ModelInfo[] }>("/models");
  },
  abTest(config: { model_a: string; model_b: string; weight_a: number }) {
    return request<{ ok: boolean }>("/models/ab-test", {
      method: "POST",
      body: JSON.stringify(config),
    });
  },
  rollback(modelId: string, version: string) {
    return request<{ ok: boolean; rolled_back_to?: string }>(
      `/models/${encodeURIComponent(modelId)}/rollback`,
      {
        method: "POST",
        body: JSON.stringify({ version }),
      },
    );
  },
  deploy(modelId: string, version: string) {
    return request<{ ok: boolean; deployed_version?: string }>(
      `/models/${encodeURIComponent(modelId)}/deploy`,
      {
        method: "POST",
        body: JSON.stringify({ version }),
      },
    );
  },
  offline(modelId: string) {
    return request<{ ok: boolean; status?: string }>(
      `/models/${encodeURIComponent(modelId)}/offline`,
      {
        method: "POST",
      },
    );
  },
  history(modelId: string) {
    return request<{
      history: {
        id: number;
        user_id: string;
        action: string;
        detail: Record<string, unknown>;
        created_at: string;
      }[];
    }>(`/models/${encodeURIComponent(modelId)}/history`);
  },
  versions(modelId: string) {
    return request<{
      versions: {
        version: string;
        status: string;
        created_at: string | null;
        deployed_at: string | null;
      }[];
    }>(`/models/${encodeURIComponent(modelId)}/versions`);
  },
};

// --- DAG ---
export interface PipelineInfo {
  pipeline_id: string;
  name: string;
  mode: string;
  status: string;
  version: string;
  created_at?: string;
}

export const dagAPI = {
  list() {
    return request<{ pipelines: PipelineInfo[] }>("/dag/pipelines");
  },
  start(pipelineId: string) {
    return request<{ ok: boolean; status: string }>(
      `/dag/pipelines/${encodeURIComponent(pipelineId)}/start`,
      {
        method: "POST",
      },
    );
  },
  stop(pipelineId: string) {
    return request<{ ok: boolean; status: string }>(
      `/dag/pipelines/${encodeURIComponent(pipelineId)}/stop`,
      {
        method: "POST",
      },
    );
  },
  replay(pipelineId: string, date: string, hour?: number) {
    return request<{ replay_id: string; status: string }>("/dag/replay", {
      method: "POST",
      body: JSON.stringify({
        pipeline: pipelineId,
        date,
        ...(hour != null && { hour }),
      }),
    });
  },
  status() {
    return request<Record<string, unknown>>("/dag/status");
  },
  history(pipelineId: string) {
    return request<{
      history: {
        id: number;
        operation: string;
        operator: string;
        status: string;
        detail: Record<string, unknown>;
        created_at: string;
      }[];
    }>(`/dag/pipelines/${encodeURIComponent(pipelineId)}/history`);
  },
  get(pipelineId: string) {
    return request<{
      pipeline_id: string;
      name: string;
      mode: string;
      status: string;
      version: string;
      yaml_content: string;
      nodes: {
        node_id: string;
        node_type: string;
        sub_type: string;
        label: string;
        config: Record<string, unknown>;
        position_x: number;
        position_y: number;
        sort_order: number;
      }[];
      edges: {
        source: string;
        target: string;
        edge_type: string;
        condition: string;
      }[];
    }>(`/dag/pipelines/${encodeURIComponent(pipelineId)}`);
  },
  save(pipelineId: string, yamlContent: string, name?: string, mode?: string) {
    return request<{ pipeline_id: string; version: number }>(
      `/dag/pipelines/${encodeURIComponent(pipelineId)}`,
      {
        method: "PUT",
        body: JSON.stringify({
          yaml_content: yamlContent,
          ...(name && { name }),
          ...(mode && { mode }),
        }),
      },
    );
  },
  create(name: string, mode: string, yamlContent: string) {
    return request<{
      pipeline_id: string;
      name: string;
      mode: string;
      status: string;
      version: number;
    }>("/dag/pipelines", {
      method: "POST",
      body: JSON.stringify({ name, mode, yaml_content: yamlContent }),
    });
  },
  delete(pipelineId: string) {
    return request<{ ok: boolean }>(
      `/dag/pipelines/${encodeURIComponent(pipelineId)}`,
      {
        method: "DELETE",
      },
    );
  },
  stats() {
    return request<{
      total: number;
      running: number;
      stopped: number;
      inactive: number;
      alert_rate: number;
      alerts_by_pipeline: {
        pipeline_id: string;
        name: string;
        count: number;
      }[];
      alerts_by_family: { name: string; value: number }[];
      alerts_by_severity: { name: string; value: number }[];
    }>("/dag/pipelines/stats");
  },
};

// --- Node Configs ---
export interface NodeConfigSchema {
  category: string;
  fields: {
    key: string;
    type: string;
    label: string;
    required?: boolean;
    default?: unknown;
    options?: string[];
  }[];
}

export interface NodeConfig {
  id: number;
  node_type: string;
  category: string;
  name: string;
  config: Record<string, unknown>;
  description: string;
  created_at?: string;
  updated_at?: string;
}

export const nodeConfigAPI = {
  schemas: () =>
    request<{ schemas: Record<string, NodeConfigSchema> }>(
      "/node-configs/schemas",
    ),
  schema: (nodeType: string) =>
    request<NodeConfigSchema & { node_type: string }>(
      `/node-configs/schemas/${nodeType}`,
    ),
  list: (params?: { node_type?: string; category?: string }) => {
    const qs = params
      ? "?" + new URLSearchParams(params as Record<string, string>).toString()
      : "";
    return request<{ configs: NodeConfig[] }>(`/node-configs${qs}`);
  },
  get: (id: number) => request<NodeConfig>(`/node-configs/${id}`),
  create: (data: {
    node_type: string;
    name: string;
    config: Record<string, unknown>;
    description?: string;
  }) =>
    request<NodeConfig>("/node-configs", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (
    id: number,
    data: {
      config?: Record<string, unknown>;
      name?: string;
      description?: string;
    },
  ) =>
    request<{ ok: boolean }>(`/node-configs/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (id: number) =>
    request<{ ok: boolean }>(`/node-configs/${id}`, { method: "DELETE" }),
};

// --- Query (Text2SQL / RAG) ---
export interface QueryResponse {
  sql: string;
  data: Record<string, unknown>[];
  explanation: string;
  error: string | null;
  trace_id: string;
}

export const queryAPI = {
  query(question: string, db_type: string = "starrocks") {
    return request<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify({ question, db_type }),
    });
  },
};

// --- Explain (Agent dispatch) ---
export interface ExplainDetailResponse {
  domain: string;
  explanation: string;
  dimensions: { title: string; content: string }[];
  confidence: number;
  trace_id: string;
}

export const explainDetailAPI = {
  explain(domain: string, score?: number, family?: string, src_ip?: string) {
    return request<ExplainDetailResponse>("/explain", {
      method: "POST",
      body: JSON.stringify({ domain, score, family, src_ip }),
    });
  },
};

// --- Agent Monitor ---
export interface AgentMetrics {
  name: string;
  status: "online" | "offline";
  execCount: number;
  avgLatency: number;
  errorRate: number;
}

export interface AgentExecRecord {
  timestamp: string;
  agent: string;
  action: string;
  duration_ms: number;
  status: "success" | "error" | "timeout";
  trace_id: string;
}

export interface A2AMessage {
  timestamp: string;
  from_agent: string;
  to_agent: string;
  message: string;
}

export const agentAPI = {
  metrics() {
    return request<{ agents: AgentMetrics[] }>("/agents/metrics");
  },
  execHistory(limit: number = 50) {
    return request<{ records: AgentExecRecord[] }>(
      `/agents/exec-history?limit=${limit}`,
    );
  },
  a2aMessages(limit: number = 20) {
    return request<{ messages: A2AMessage[] }>(
      `/agents/a2a-messages?limit=${limit}`,
    );
  },
};

// --- Response Agent ---
export interface ResponseAction {
  level: string;
  action: string;
}

export interface ResponseAgentResponse {
  recommendations: ResponseAction[];
  trace_id?: string;
}

export const responseAgentAPI = {
  getRecommendations(
    domain: string,
    score?: number,
    severity?: string,
    family?: string | null,
    src_ip?: string,
  ) {
    return request<ResponseAgentResponse>("/response", {
      method: "POST",
      body: JSON.stringify({ domain, score, severity, family, src_ip }),
    });
  },
};

// --- Dashboard ---
export interface DashboardStats {
  total_today: number;
  dga_hits: number;
  hit_rate: number;
  p95_latency: number;
  qps_history: { time: string; qps: number; hits: number }[];
  family_dist: { name: string; value: number }[];
  recent_alerts: AlertItem[];
}

export const dashboardAPI = {
  stats() {
    return request<DashboardStats>("/dashboard/stats");
  },
};

// --- Reports ---
export interface ReportStats {
  trend: { date: string; total: number; dga: number }[];
  topDomains: {
    rank: number;
    key: number;
    domain: string;
    count: number;
    family: string;
  }[];
  topHosts: {
    rank: number;
    key: number;
    src_ip: string;
    alerts: number;
    unique_domains: number;
  }[];
  heatmap: [number, number, number][];
}

export const reportsAPI = {
  stats(params?: { days?: number; start_date?: string; end_date?: string }) {
    const qs = new URLSearchParams();
    if (params?.start_date) qs.set("start_date", params.start_date);
    if (params?.end_date) qs.set("end_date", params.end_date);
    if (!params?.start_date && !params?.end_date)
      qs.set("days", String(params?.days ?? 30));
    return request<ReportStats>(`/reports/stats?${qs.toString()}`);
  },
};

// --- RAG Knowledge Base ---
export interface RAGSource {
  content: string;
  source: string;
  category: string;
  score: number;
}

export interface RAGResponse {
  answer: string;
  sources: RAGSource[];
  query: string;
  trace_id: string;
}

export const ragAPI = {
  query(question: string, top_k: number = 5) {
    return request<RAGResponse>("/rag/query", {
      method: "POST",
      body: JSON.stringify({ question, top_k }),
    });
  },
};

// --- Feedback (人工标注 → 反馈闭环) ---
export interface FeedbackRequest {
  event_id: string;
  domain: string;
  true_label: "dga" | "benign";
  predicted_label?: string;
  score?: number;
  family?: string | null;
  annotator?: string;
}

export interface FeedbackResponse {
  status: string;
  event_id: string;
  received_at: string;
}

export const feedbackAPI = {
  submit(req: FeedbackRequest) {
    return request<FeedbackResponse>("/feedback", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
};

// --- Operations / Recommendations ---
export interface OperationItem {
  id: number;
  pipeline_id: string;
  operation: string;
  operator: string;
  status: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface OperationsStats {
  by_status: Record<string, number>;
  by_operation_pending: Record<string, number>;
  pending_total: number;
}

export const operationsAPI = {
  listPending(opType?: string, limit: number = 100) {
    const qs = new URLSearchParams();
    if (opType) qs.set("op_type", opType);
    qs.set("limit", String(limit));
    return request<{ items: OperationItem[]; total: number }>(
      `/operations/pending?${qs.toString()}`,
    );
  },
  listRecent(limit: number = 100) {
    return request<{ items: OperationItem[]; total: number }>(
      `/operations/recent?limit=${limit}`,
    );
  },
  stats() {
    return request<OperationsStats>("/operations/stats");
  },
  acknowledge(id: number) {
    return request<{ id: number; status: string; by: string }>(
      `/operations/${id}/acknowledge`,
      { method: "POST" },
    );
  },
  dismiss(id: number) {
    return request<{ id: number; status: string; by: string }>(
      `/operations/${id}/dismiss`,
      { method: "POST" },
    );
  },
};

// --- Health ---
export const healthAPI = {
  healthz: () => request<{ status: string }>("/healthz"),
  readyz: () =>
    request<{ status: string; checks?: Record<string, string> }>("/readyz"),
};
