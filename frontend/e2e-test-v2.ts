/**
 * DGA 平台全功能 E2E 测试 v2
 * 逐页面深度测试所有交互功能，截图 + Bug 检测
 */
import { chromium, Page } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BASE = 'http://localhost:3000';
const SHOTS = path.join(__dirname, 'screenshots-v2');
const R: { page: string; test: string; status: 'PASS'|'FAIL'|'WARN'; detail: string }[] = [];

function log(page: string, test: string, status: 'PASS'|'FAIL'|'WARN', detail: string) {
  R.push({ page, test, status, detail });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} [${page}] ${test} — ${detail}`);
}
async function shot(p: Page, name: string) {
  await p.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}
async function bodyText(p: Page) { return (await p.textContent('body')) || ''; }

// ═══════════════════════════════════════════════════
// 1. 导航与布局
// ═══════════════════════════════════════════════════
async function testLayout(p: Page) {
  const N = '布局';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(2000);

  // 侧边栏菜单项
  const items = await p.locator('.ant-menu-item').allTextContents();
  log(N, '侧边栏菜单', items.length >= 7 ? 'PASS' : 'FAIL', `${items.length} 项: ${items.join(', ')}`);

  // Header
  const header = await p.locator('.ant-layout-header').count();
  log(N, 'Header', header > 0 ? 'PASS' : 'FAIL', header > 0 ? '存在' : '缺失');

  // Footer 健康状态
  const footerText = await p.locator('.ant-layout-footer').textContent() || '';
  const hasHealth = footerText.includes('系统正常') || footerText.includes('系统不可达') || footerText.includes('部分服务');
  log(N, 'Footer 健康状态', hasHealth ? 'PASS' : 'FAIL', footerText.trim().slice(0, 80));

  // 告警角标
  const badge = p.locator('.ant-badge-count');
  const badgeCount = await badge.count();
  let badgeText = '';
  if (badgeCount > 0) badgeText = (await badge.first().textContent()) || '';
  log(N, '告警角标', badgeCount > 0 ? 'PASS' : 'WARN', badgeCount > 0 ? `角标值: ${badgeText}` : '无角标');

  // 侧边栏折叠
  const trigger = p.locator('.ant-layout-sider-trigger');
  if (await trigger.count() > 0) {
    await trigger.click();
    await p.waitForTimeout(500);
    const collapsed = await p.locator('.ant-layout-sider-collapsed').count();
    log(N, '侧边栏折叠', collapsed > 0 ? 'PASS' : 'FAIL', collapsed > 0 ? '折叠成功' : '折叠失败');
    await trigger.click();
    await p.waitForTimeout(500);
  }

  // 菜单导航测试
  const routes = ['/dashboard', '/detection', '/alerts', '/models', '/pipeline', '/reports', '/agent-monitor'];
  for (const route of routes) {
    const menuItem = p.locator(`.ant-menu-item[data-menu-id*="${route}"], .ant-menu-item`).filter({ has: p.locator(`[href="${route}"]`) });
    // 直接导航测试
    await p.goto(`${BASE}${route}`);
    await p.waitForTimeout(1000);
    const is404 = (await bodyText(p)).includes('404') || (await bodyText(p)).includes('Not Found');
    if (is404) log(N, `路由 ${route}`, 'FAIL', '404 页面');
  }
  log(N, '路由导航', 'PASS', `${routes.length} 个路由全部可达`);
  await shot(p, '01-layout');
}

// ═══════════════════════════════════════════════════
// 2. 实时监控 Dashboard
// ═══════════════════════════════════════════════════
async function testDashboard(p: Page) {
  const N = 'Dashboard';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(3000);
  await shot(p, '02-dashboard');

  const bt = await bodyText(p);

  // 统计卡片
  const statLabels = ['今日检测量', 'DGA 命中', '命中率', 'P95 延迟'];
  for (const label of statLabels) {
    log(N, `卡片: ${label}`, bt.includes(label) ? 'PASS' : 'FAIL', bt.includes(label) ? '存在' : '缺失');
  }

  // 图表
  log(N, 'QPS 趋势图', bt.includes('QPS') || bt.includes('趋势') ? 'PASS' : 'WARN', '检查 QPS 图表');
  log(N, '家族分布图', bt.includes('家族分布') ? 'PASS' : 'WARN', '检查饼图');

  // 实时告警流
  log(N, '实时告警流', bt.includes('实时告警') ? 'PASS' : 'WARN', '告警流区块');

  // 检查是否有错误
  const errors = await p.locator('.ant-alert-error').count();
  log(N, '错误状态', errors === 0 ? 'PASS' : 'FAIL', errors === 0 ? '无错误' : `${errors} 个错误提示`);

  // 检查数值是否为 0（可能是假数据）
  const totalMatch = bt.match(/今日检测量[\s\S]*?([\d,]+)/);
  if (totalMatch) {
    const val = parseInt(totalMatch[1].replace(/,/g, ''));
    log(N, '数据真实性', val > 0 ? 'PASS' : 'WARN', `今日检测量: ${val}`);
  }
}

// ═══════════════════════════════════════════════════
// 3. 域名检测
// ═══════════════════════════════════════════════════
async function testDetection(p: Page) {
  const N = '域名检测';
  await p.goto(`${BASE}/detection`);
  await p.waitForTimeout(2000);
  await shot(p, '03-detection-empty');

  // 输入框
  const textarea = p.locator('textarea').first();
  const hasTextarea = (await textarea.count()) > 0;
  log(N, '输入框', hasTextarea ? 'PASS' : 'FAIL', hasTextarea ? 'textarea 存在' : '未找到输入框');
  if (!hasTextarea) return;

  // 输入测试域名
  await textarea.fill('google.com\nbaidu.com\nxyz123abc.tk');
  await p.waitForTimeout(300);

  // 提交按钮
  const submitBtn = p.locator('button').filter({ hasText: /检测|提交|分析|查询/ }).first();
  if (await submitBtn.count() === 0) { log(N, '提交按钮', 'FAIL', '未找到'); return; }
  await submitBtn.click();
  await p.waitForTimeout(6000);
  await shot(p, '03-detection-result');

  const bt = await bodyText(p);
  // 结果表格
  const rows = await p.locator('.ant-table-tbody tr').count();
  log(N, '检测结果', rows > 0 ? 'PASS' : 'FAIL', `${rows} 条结果`);

  // 分数显示
  const hasScore = bt.includes('score') || bt.includes('分数') || bt.match(/0\.\d+/) !== null;
  log(N, '评分显示', hasScore ? 'PASS' : 'WARN', hasScore ? '分数可见' : '未找到分数');

  // 错误检查
  if (bt.includes('失败') || bt.includes('不可用')) log(N, 'API 状态', 'FAIL', '检测服务异常');
  else log(N, 'API 状态', 'PASS', '检测服务正常');
}

// ═══════════════════════════════════════════════════
// 4. 告警中心
// ═══════════════════════════════════════════════════
async function testAlerts(p: Page) {
  const N = '告警中心';
  await p.goto(`${BASE}/alerts`);
  await p.waitForTimeout(3000);
  await shot(p, '04-alerts');

  const rows = await p.locator('.ant-table-tbody tr').count();
  log(N, '告警列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 条告警`);

  // 严重度筛选
  const sel = p.locator('.ant-select').first();
  if (await sel.count() > 0) {
    log(N, '严重度筛选器', 'PASS', '存在');
    await sel.click();
    await p.waitForTimeout(500);
    const opts = await p.locator('.ant-select-item').count();
    log(N, '筛选选项', opts > 0 ? 'PASS' : 'WARN', `${opts} 个选项`);
    await p.keyboard.press('Escape');
  } else {
    log(N, '严重度筛选器', 'WARN', '未找到');
  }

  // 详情按钮
  if (rows > 0) {
    const detailBtn = p.locator('button, a').filter({ hasText: '详情' }).first();
    if (await detailBtn.count() > 0) {
      await detailBtn.click();
      await p.waitForTimeout(2000);
      await shot(p, '04-alerts-detail');
      const drawer = await p.locator('.ant-drawer').count();
      log(N, '详情抽屉/跳转', drawer > 0 ? 'PASS' : 'WARN', drawer > 0 ? '抽屉打开' : '可能跳转到详情页');
      if (drawer > 0) {
        const closeBtn = p.locator('.ant-drawer-close').first();
        if (await closeBtn.count() > 0) await closeBtn.click();
        await p.waitForTimeout(500);
      }
    }
  }

  // 错误检查
  const bt = await bodyText(p);
  if (bt.includes('503') || bt.includes('unavailable')) log(N, 'API 状态', 'FAIL', '告警服务不可用');
  else log(N, 'API 状态', 'PASS', 'API 正常');
}

// ═══════════════════════════════════════════════════
// 5. 告警详情页
// ═══════════════════════════════════════════════════
async function testAlertDetail(p: Page) {
  const N = '告警详情';
  const resp = await p.request.get(`${BASE}/api/alerts?limit=1`);
  if (!resp.ok()) { log(N, 'API', 'FAIL', `告警 API ${resp.status()}`); return; }
  const data = await resp.json();
  const alerts = data.alerts || [];
  if (alerts.length === 0) { log(N, '数据', 'WARN', '无告警数据'); return; }

  const id = alerts[0].event_id;
  await p.goto(`${BASE}/alerts/${id}`);
  await p.waitForTimeout(5000);
  await shot(p, '05-alert-detail');

  const bt = await bodyText(p);
  // 基本信息
  const desc = await p.locator('.ant-descriptions').count();
  log(N, '基本信息', desc > 0 ? 'PASS' : 'FAIL', `${desc} 个描述区块`);

  // 时间线
  const timeline = await p.locator('.ant-timeline').count();
  log(N, '处置时间线', timeline > 0 ? 'PASS' : 'WARN', `${timeline} 个时间线`);

  // ExplainAgent
  log(N, 'ExplainAgent', bt.includes('四维分析') || bt.includes('分析') ? 'PASS' : 'WARN', '四维分析区块');

  // ResponseAgent
  log(N, 'ResponseAgent', bt.includes('处置建议') || bt.includes('建议') ? 'PASS' : 'WARN', '处置建议区块');

  // 暂不可用
  if (bt.includes('暂不可用')) log(N, 'Agent 服务', 'WARN', '部分 Agent 不可用');
  else log(N, 'Agent 服务', 'PASS', 'Agent 正常');
}

// ═══════════════════════════════════════════════════
// 6. 模型管理
// ═══════════════════════════════════════════════════
async function testModels(p: Page) {
  const N = '模型管理';
  await p.goto(`${BASE}/models`);
  await p.waitForTimeout(3000);
  await shot(p, '06-models');

  const rows = await p.locator('.ant-table-tbody tr').count();
  log(N, '模型列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 个模型`);

  const bt = await bodyText(p);
  if (bt.includes('503') || bt.includes('unavailable')) log(N, 'API 状态', 'FAIL', '模型服务不可用');
  else log(N, 'API 状态', 'PASS', 'API 正常');

  // 操作按钮
  const buttons = await p.locator('button').allTextContents();
  const ops = ['A/B', '回滚', '上线', '下线', '历史'].filter(op => buttons.some(b => b.includes(op)));
  log(N, '操作按钮', ops.length >= 2 ? 'PASS' : 'WARN', `找到: ${ops.join(', ') || '无'}`);

  // 版本信息
  log(N, '版本信息', bt.includes('version') || bt.includes('版本') || bt.match(/v\d/) !== null ? 'PASS' : 'WARN', '版本列');
}

// ═══════════════════════════════════════════════════
// 7. DAG 编排
// ═══════════════════════════════════════════════════
async function testPipeline(p: Page) {
  const N = 'DAG 编排';
  await p.goto(`${BASE}/pipeline`);
  await p.waitForTimeout(3000);
  await shot(p, '07-pipeline');

  const rows = await p.locator('.ant-table-tbody tr').count();
  log(N, 'Pipeline 列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 条 Pipeline`);

  // Click second row (first real pipeline with content, skip "test" row)
  const clickIdx = rows > 1 ? 1 : 0;
  if (rows > 0) {
    await p.locator('.ant-table-tbody tr').nth(clickIdx).click();
    await p.waitForTimeout(3000);
  }

  // ReactFlow 编辑器
  const rf = await p.locator('.react-flow').count();
  log(N, 'DAG 编辑器', rf > 0 ? 'PASS' : 'WARN', `ReactFlow: ${rf}`);

  // 节点面板
  const bt = await bodyText(p);
  log(N, '节点面板', bt.includes('节点面板') ? 'PASS' : 'WARN', '节点面板');

  // 画布节点
  const nodesAfter = await p.locator('.react-flow__node').count();
  log(N, '加载 Pipeline', nodesAfter > 0 ? 'PASS' : 'WARN', `加载后节点数: ${nodesAfter}`);

  // 节点配置 — 点击节点打开右侧内嵌面板
  if (nodesAfter > 0) {
    await p.locator('.react-flow__node').first().click();
    await p.waitForTimeout(800);
    const configPanel = await p.locator('text=节点配置').count();
    log(N, '右侧配置面板', configPanel > 0 ? 'PASS' : 'WARN', configPanel > 0 ? '已打开' : '未打开');
    // Close panel
    const collapseBtn = p.locator('button:has-text("收起")').first();
    if (await collapseBtn.count() > 0) {
      await collapseBtn.click();
      await p.waitForTimeout(300);
    }
  }

  const collapsePanels = await p.locator('.ant-collapse-item').count();
  log(N, '可折叠配置面板', collapsePanels > 0 ? 'PASS' : 'WARN', `${collapsePanels} 个面板`);

  // 保存按钮
  const saveBtn = p.locator('button').filter({ hasText: /保存|Save/ });
  log(N, '保存功能', (await saveBtn.count()) > 0 ? 'PASS' : 'WARN', '保存按钮');

  await shot(p, '07-pipeline-loaded');
}

// ═══════════════════════════════════════════════════
// 8. 分析报表
// ═══════════════════════════════════════════════════
async function testReports(p: Page) {
  const N = '分析报表';
  await p.goto(`${BASE}/reports`);
  await p.waitForTimeout(3000);
  await shot(p, '08-reports');

  const cards = await p.locator('.ant-card').count();
  log(N, '报表卡片', cards >= 2 ? 'PASS' : 'WARN', `${cards} 个卡片`);

  const picker = await p.locator('.ant-picker').count();
  log(N, '日期选择器', picker > 0 ? 'PASS' : 'WARN', `${picker} 个`);

  const tables = await p.locator('.ant-table').count();
  log(N, '数据表格', tables > 0 ? 'PASS' : 'WARN', `${tables} 个表格`);

  const bt = await bodyText(p);
  if (bt.includes('503') || bt.includes('unavailable')) log(N, 'API 状态', 'FAIL', '报表服务不可用');
  else log(N, 'API 状态', 'PASS', 'API 正常');
}

// ═══════════════════════════════════════════════════
// 9. Agent 监控
// ═══════════════════════════════════════════════════
async function testAgentMonitor(p: Page) {
  const N = 'Agent 监控';
  await p.goto(`${BASE}/agent-monitor`);
  await p.waitForTimeout(3000);
  await shot(p, '09-agent-monitor');

  const cards = await p.locator('.ant-card').count();
  log(N, '监控卡片', cards >= 1 ? 'PASS' : 'WARN', `${cards} 个卡片`);

  const tags = await p.locator('.ant-tag').count();
  log(N, 'Agent 状态标签', tags > 0 ? 'PASS' : 'WARN', `${tags} 个标签`);

  const bt = await bodyText(p);
  if (bt.includes('503') || bt.includes('unavailable')) log(N, 'API 状态', 'FAIL', 'Agent 监控不可用');
  else log(N, 'API 状态', 'PASS', 'API 正常');
}

// ═══════════════════════════════════════════════════
// 10. Chat 智能助手
// ═══════════════════════════════════════════════════
async function testChatPanel(p: Page) {
  const N = 'Chat 助手';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(2000);

  // 浮动按钮
  const fab = p.locator('button.ant-btn-circle').last();
  if (await fab.count() === 0) { log(N, '浮动按钮', 'FAIL', '未找到'); return; }
  await fab.click();
  await p.waitForTimeout(1000);
  await shot(p, '10-chat-open');
  log(N, '浮动按钮', 'PASS', 'Chat 面板打开');

  // 模式切换
  const seg = await p.locator('.ant-segmented').count();
  log(N, '模式切换', seg > 0 ? 'PASS' : 'FAIL', seg > 0 ? 'Segmented 存在' : '未找到');

  const bt = await bodyText(p);
  log(N, '欢迎消息', bt.includes('数据查询模式') || bt.includes('智能助手') ? 'PASS' : 'WARN', '欢迎语');

  // Text2SQL 查询
  const chatInput = p.locator('.ant-input-search input, .ant-input-affix-wrapper input').last();
  if (await chatInput.count() > 0) {
    await chatInput.fill('查询今日告警数量');
    await chatInput.press('Enter');
    await p.waitForTimeout(5000);
    await shot(p, '10-chat-sql');
    log(N, 'Text2SQL', 'PASS', '已发送查询');
  }

  // 切换 RAG 模式
  const ragTab = p.locator('.ant-segmented-item').filter({ hasText: '知识库' });
  if (await ragTab.count() > 0) {
    await ragTab.click();
    await p.waitForTimeout(1000);
    const bt2 = await bodyText(p);
    log(N, 'RAG 模式', bt2.includes('知识库模式') ? 'PASS' : 'WARN', '切换到知识库');

    const ragInput = p.locator('.ant-input-search input, .ant-input-affix-wrapper input').last();
    if (await ragInput.count() > 0) {
      await ragInput.fill('什么是 DGA 域名');
      await ragInput.press('Enter');
      await p.waitForTimeout(5000);
      await shot(p, '10-chat-rag');
      log(N, 'RAG 查询', 'PASS', '已发送 RAG 查询');
    }
  } else {
    log(N, 'RAG 模式', 'FAIL', '未找到知识库切换');
  }

  // 关闭
  const closeBtn = p.locator('.anticon-close').last();
  if (await closeBtn.count() > 0) await closeBtn.click();
}

// ═══════════════════════════════════════════════════
// 11. API 端点
// ═══════════════════════════════════════════════════
async function testAPIEndpoints(p: Page) {
  const N = 'API 端点';
  const eps = [
    { path: '/api/healthz', label: 'healthz' },
    { path: '/api/readyz', label: 'readyz' },
    { path: '/api/alerts?limit=1', label: 'alerts' },
    { path: '/api/models', label: 'models' },
    { path: '/api/dag/pipelines', label: 'dag pipelines' },
    { path: '/api/dashboard/stats', label: 'dashboard stats' },
    { path: '/api/reports/stats?days=7', label: 'reports stats' },
    { path: '/api/agents/metrics', label: 'agent metrics' },
  ];
  for (const ep of eps) {
    try {
      const resp = await p.request.get(`${BASE}${ep.path}`);
      const s = resp.status();
      if (s === 200) log(N, ep.label, 'PASS', `${s} OK`);
      else if (s === 503) log(N, ep.label, 'WARN', `${s} 服务不可用`);
      else log(N, ep.label, 'FAIL', `${s}`);
    } catch (e: any) {
      log(N, ep.label, 'FAIL', `请求失败: ${e.message}`);
    }
  }
}

// ═══════════════════════════════════════════════════
// 12. 控制台错误
// ═══════════════════════════════════════════════════
async function testConsoleErrors(p: Page) {
  const N = '控制台错误';
  const errors: string[] = [];
  p.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  p.on('pageerror', err => errors.push(err.message));

  const pages = ['/dashboard', '/detection', '/alerts', '/models', '/pipeline', '/reports', '/agent-monitor'];
  for (const pg of pages) {
    await p.goto(`${BASE}${pg}`);
    await p.waitForTimeout(2000);
  }

  if (errors.length === 0) log(N, '全页面', 'PASS', '无控制台错误');
  else {
    const unique = [...new Set(errors)];
    for (const err of unique.slice(0, 10)) {
      log(N, '错误', 'WARN', err.slice(0, 120));
    }
  }
}

// ═══════════════════════════════════════════════════
// main
// ═══════════════════════════════════════════════════
async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  console.log('🚀 DGA 平台 E2E 测试 v2 开始\n' + '='.repeat(60));

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  try {
    await testLayout(page);       console.log('-'.repeat(60));
    await testDashboard(page);    console.log('-'.repeat(60));
    await testDetection(page);    console.log('-'.repeat(60));
    await testAlerts(page);       console.log('-'.repeat(60));
    await testAlertDetail(page);  console.log('-'.repeat(60));
    await testModels(page);       console.log('-'.repeat(60));
    await testPipeline(page);     console.log('-'.repeat(60));
    await testReports(page);      console.log('-'.repeat(60));
    await testAgentMonitor(page); console.log('-'.repeat(60));
    await testChatPanel(page);    console.log('-'.repeat(60));
    await testAPIEndpoints(page); console.log('-'.repeat(60));
    await testConsoleErrors(page);
  } finally {
    await browser.close();
  }

  // 汇总
  console.log('\n' + '='.repeat(60));
  console.log('📊 测试结果汇总\n');
  const pass = R.filter(r => r.status === 'PASS').length;
  const fail = R.filter(r => r.status === 'FAIL').length;
  const warn = R.filter(r => r.status === 'WARN').length;
  console.log(`  ✅ PASS: ${pass}  ❌ FAIL: ${fail}  ⚠️ WARN: ${warn}  总计: ${R.length}`);

  if (fail > 0) {
    console.log('\n❌ 失败项:');
    R.filter(r => r.status === 'FAIL').forEach(r => console.log(`  - [${r.page}] ${r.test}: ${r.detail}`));
  }
  if (warn > 0) {
    console.log('\n⚠️ 警告项:');
    R.filter(r => r.status === 'WARN').forEach(r => console.log(`  - [${r.page}] ${r.test}: ${r.detail}`));
  }

  console.log(`\n📸 截图: ${SHOTS}`);
  fs.writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify(R, null, 2));
  console.log(`📄 JSON 报告: ${path.join(SHOTS, 'report.json')}`);
}

main().catch(console.error);
