export default function DashboardSimple() {
  return (
    <div style={{ 
      padding: '40px', 
      background: '#fff', 
      color: '#000', 
      minHeight: '100vh',
      fontSize: '18px'
    }}>
      <h1 style={{ color: 'red', fontSize: '24px', marginBottom: '20px' }}>
        Dashboard 简化版 - 如果你看到这个，说明路由和组件都正常
      </h1>
      <p>当前时间: {new Date().toLocaleString()}</p>
      <p>如果你能看到这个页面，说明 Dashboard 路由和 MainLayout 都正常工作。</p>
      <p>如果还是空白，可能是原 Dashboard 组件有问题。</p>
    </div>
  );
}
