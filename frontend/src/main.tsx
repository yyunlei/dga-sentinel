import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found');
}

try {
  const root = ReactDOM.createRoot(rootElement);
  // 暂时禁用 StrictMode 以避免 hydration 错误
  root.render(<App />);
} catch (error) {
  console.error('Failed to render React app:', error);
  rootElement.innerHTML = `
    <div style="padding: 20px; color: red; font-family: Arial; background: white;">
      <h1>应用加载失败</h1>
      <p><strong>错误信息:</strong> ${error instanceof Error ? error.message : String(error)}</p>
      <p>请检查浏览器控制台获取更多信息。</p>
    </div>
  `;
}
