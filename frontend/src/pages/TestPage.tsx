export default function TestPage() {
  return (
    <div style={{ padding: '40px', background: '#fff', color: '#000', minHeight: '100vh' }}>
      <h1 style={{ color: 'red', fontSize: '24px' }}>测试页面 - 如果你看到这个，说明 React 正常工作</h1>
      <p>当前时间: {new Date().toLocaleString()}</p>
      <p>如果你看不到这个页面，说明 React 应用没有正确渲染。</p>
    </div>
  );
}
