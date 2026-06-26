import { useEffect, useRef, useState } from 'react';
import { useDashboardStore } from '@/stores';

/**
 * WebSocket hook for realtime dashboard updates.
 * Falls back to mock data when WS is unavailable.
 */
export function useRealtimeWS() {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // 只在客户端执行
    if (typeof window === 'undefined') return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const url = `${protocol}://${host}/api/ws/realtime`;

    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let isConnecting = false;

    function connect() {
      if (isConnecting || ws?.readyState === WebSocket.OPEN) return;
      
      isConnecting = true;
      try {
        ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          isConnecting = false;
        };

        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            const { pushAlert, setStats } = useDashboardStore.getState();
            if (msg.type === 'alert') pushAlert(msg.data);
            if (msg.type === 'stats') setStats(msg.data);
          } catch { /* ignore bad frames */ }
        };

        ws.onerror = () => {
          isConnecting = false;
        };

        ws.onclose = () => {
          isConnecting = false;
          if (retryTimer) clearTimeout(retryTimer);
          retryTimer = setTimeout(connect, 3000);
        };
      } catch (error) {
        isConnecting = false;
        if (retryTimer) clearTimeout(retryTimer);
        retryTimer = setTimeout(connect, 3000);
      }
    }

    connect();

    return () => {
      if (retryTimer) clearTimeout(retryTimer);
      if (ws) {
        ws.close();
        ws = null;
      }
      wsRef.current = null;
    };
  }, []);
}

/**
 * Polling hook — fetches data at interval.
 */
export function usePolling(fn: () => void, intervalMs = 5000) {
  useEffect(() => {
    fn();
    const id = setInterval(fn, intervalMs);
    return () => clearInterval(id);
  }, [fn, intervalMs]);
}
