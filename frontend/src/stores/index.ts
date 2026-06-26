import { create } from "zustand";
import type {
  AlertItem,
  ScoreResult,
  ModelInfo,
  PipelineInfo,
} from "@/services/api";

// --- Dashboard Store ---
interface DashboardState {
  totalToday: number;
  dgaHits: number;
  hitRate: number;
  p95Latency: number;
  qpsHistory: { time: string; qps: number; hits: number }[];
  familyDist: { name: string; value: number }[];
  realtimeAlerts: AlertItem[];
  detectionAlerts: AlertItem[];
  pushAlert: (a: AlertItem) => void;
  pushDetectionAlert: (a: AlertItem) => void;
  setStats: (s: Partial<DashboardState>) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  totalToday: 0,
  dgaHits: 0,
  hitRate: 0,
  p95Latency: 0,
  qpsHistory: [],
  familyDist: [],
  realtimeAlerts: [],
  detectionAlerts: [],
  pushAlert: (a) =>
    set((s) => ({ realtimeAlerts: [a, ...s.realtimeAlerts].slice(0, 100) })),
  pushDetectionAlert: (a) =>
    set((s) => ({ detectionAlerts: [a, ...s.detectionAlerts].slice(0, 100) })),
  setStats: (partial) => set(partial),
}));

// --- Detection Store ---
interface DetectionState {
  loading: boolean;
  results: ScoreResult[];
  explanation: string;
  setLoading: (v: boolean) => void;
  setResults: (r: ScoreResult[]) => void;
  setExplanation: (e: string) => void;
}

export const useDetectionStore = create<DetectionState>((set) => ({
  loading: false,
  results: [],
  explanation: "",
  setLoading: (loading) => set({ loading }),
  setResults: (results) => set({ results }),
  setExplanation: (explanation) => set({ explanation }),
}));

// --- Models Store ---
interface ModelsState {
  models: ModelInfo[];
  setModels: (m: ModelInfo[]) => void;
}

export const useModelsStore = create<ModelsState>((set) => ({
  models: [],
  setModels: (models) => set({ models }),
}));

// --- Pipeline Store ---
interface PipelineState {
  pipelines: PipelineInfo[];
  setPipelines: (p: PipelineInfo[]) => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  pipelines: [],
  setPipelines: (pipelines) => set({ pipelines }),
}));
