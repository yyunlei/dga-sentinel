import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { darkCyberTheme } from '@/theme/dark-cyber';
import MainLayout from '@/components/common/MainLayout';
import Dashboard from '@/pages/Dashboard';
import DashboardSimple from '@/pages/DashboardSimple';
import Detection from '@/pages/Detection';
import Alerts from '@/pages/Alerts';
import AlertDetail from '@/pages/AlertDetail';
import Models from '@/pages/Models';
import Pipeline from '@/pages/Pipeline';
import Reports from '@/pages/Reports';
import AgentMonitor from '@/pages/AgentMonitor';
import Recommendations from '@/pages/Recommendations';
import TestPage from '@/pages/TestPage';
import ChatPanel from '@/components/chat/ChatPanel';

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        ...darkCyberTheme,
        algorithm: theme.darkAlgorithm,
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/test" element={<TestPage />} />
            <Route element={<MainLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/detection" element={<Detection />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/alerts/:id" element={<AlertDetail />} />
              <Route path="/models" element={<Models />} />
              <Route path="/pipeline" element={<Pipeline />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/agent-monitor" element={<AgentMonitor />} />
              <Route path="/recommendations" element={<Recommendations />} />
            </Route>
          </Routes>
          <ChatPanel />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

// 添加全局错误处理
window.addEventListener('error', (event) => {
  console.error('Global error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
});

export default App;
