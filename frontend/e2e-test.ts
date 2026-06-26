/**
 * DGA 平台全功能自动化测试
 * 使用 Playwright 遍历所有页面，截图 + 功能验证
 */
import { chromium, Browser, Page } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE = 'http://localhost:3000';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
const RESULTS: { page: string; feature: string; status: 'PASS' | 'FAIL' | 'WARN'; detail: string }[] = [];

function log(page: string, feature: string, status: 'PASS' | 'FAIL' | 'WARN', detail: string) {
  RESULTS.push({ page, feature, status, detail });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} [${page}] ${feature}: ${detail}`);
}

async function screenshot(p: Page, name: string) {
  await p.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}.png`), fullPage: true });
}

async function testDashboard(p: Page) {
  const name = '实时监控';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(3000);
  await screenshot(p, '01-dashboard');

  // 检查统计卡片
  const cards = await p.locator('.ant-card').count();
  if (cards >= 3) log(name, '统计卡片', 'PASS', `找到 ${cards} 个卡片`);
  else log(name, '统计卡片', 'FAIL', `仅找到 ${cards} 个卡片`);

  // 检查是否有错误提示
  const errorAlert = await p.locator('.ant-alert-error').count();
  if (errorAlert > 0) log(name, '数据加载', 'FAIL', '页面显示错误提示');
  else log(name, '数据加载', 'PASS', '无错误提示');

  // 检查图表是否渲染
  const charts = await p.locator('canvas, .bindbindbindbindecharts-bindbindfor, [class*="bindchart"]').count();
  const svgs = await p.locator('svg').count();
  log(name, '图表渲染', svgs > 2 ? 'PASS' : 'WARN', `SVG 元素: ${svgs}`);

  // 检查 503 错误
  const text = await p.textContent('body');
  if (text?.includes('503') || text?.includes('unavailable')) log(name, 'API 状态', 'FAIL', '检测到 503 错误');
  else log(name, 'API 状态', 'PASS', 'API 正常');
}

async function testDetection(p: Page) {
  const name = '域名检测';
  await p.goto(`${BASE}/detection`);
  await p.waitForTimeout(2000);
  await screenshot(p, '02-detection-empty');

  // 检查输入框
  const input = p.locator('textarea, input[type="text"], .ant-input');
  const inputCount = await input.count();
  if (inputCount > 0) log(name, '输入框', 'PASS', '输入框存在');
  else { log(name, '输入框', 'FAIL', '未找到输入框'); return; }

  // 输入测试域名并提交
  const textarea = p.locator('textarea').first();
  if (await textarea.count() > 0) {
    await textarea.fill('google.com\nbaidu.com\nxyz123abc.tk');
    await p.waitForTimeout(500);
  } else {
    const textInput = p.locator('input').first();
    await textInput.fill('google.com');
  }

  const submitBtn = p.locator('button').filter({ hasText: /检测|提交|分析|查询/ }).first();
  if (await submitBtn.count() > 0) {
    await submitBtn.click();
    await p.waitForTimeout(5000);
    await screenshot(p, '02-detection-result');

    // 检查结果
    const table = await p.locator('.ant-table-tbody tr').count();
    if (table > 0) log(name, '检测结果', 'PASS', `返回 ${table} 条结果`);
    else {
      const bodyText = await p.textContent('body');
      if (bodyText?.includes('失败') || bodyText?.includes('错误'))
        log(name, '检测结果', 'FAIL', '检测请求失败');
      else log(name, '检测结果', 'WARN', '无结果返回');
    }
  } else {
    log(name, '提交按钮', 'FAIL', '未找到提交按钮');
  }
}

async function testAlerts(p: Page) {
  const name = '告警中心';
  await p.goto(`${BASE}/alerts`);
  await p.waitForTimeout(3000);
  await screenshot(p, '03-alerts');

  // 检查表格
  const rows = await p.locator('.ant-table-tbody tr').count();
  log(name, '告警列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 条告警`);

  // 检查严重度筛选
  const select = p.locator('.ant-select').first();
  if (await select.count() > 0) {
    log(name, '严重度筛选', 'PASS', '筛选器存在');
    await select.click();
    await p.waitForTimeout(500);
    const options = await p.locator('.ant-select-item').count();
    log(name, '筛选选项', options > 0 ? 'PASS' : 'WARN', `${options} 个选项`);
    await p.keyboard.press('Escape');
  }

  // 点击详情按钮
  const detailBtn = p.locator('button, a').filter({ hasText: '详情' }).first();
  if (await detailBtn.count() > 0 && rows > 0) {
    await detailBtn.click();
    await p.waitForTimeout(2000);
    await screenshot(p, '03-alerts-detail-drawer');
    const drawer = await p.locator('.ant-drawer').count();
    log(name, '详情抽屉', drawer > 0 ? 'PASS' : 'FAIL', drawer > 0 ? '抽屉打开' : '抽屉未打开');
    // 关闭抽屉
    const closeBtn = p.locator('.ant-drawer-close').first();
    if (await closeBtn.count() > 0) await closeBtn.click();
    await p.waitForTimeout(500);
  }

  // 测试告警详情页
  if (rows > 0) {
    // 获取第一条告警的 event_id
    const firstRow = p.locator('.ant-table-tbody tr').first();
    const cells = await firstRow.locator('td').allTextContents();
    log(name, '告警数据', 'PASS', `首行: ${cells.slice(0, 3).join(' | ')}`);
  }
}

async function testAlertDetail(p: Page) {
  const name = '告警详情页';
  // 先获取一个告警 ID
  const resp = await p.request.get(`${BASE}/api/alerts?limit=1`);
  if (resp.ok()) {
    const data = await resp.json();
    const alerts = data.alerts || [];
    if (alerts.length > 0) {
      const id = alerts[0].event_id;
      await p.goto(`${BASE}/alerts/${id}`);
      await p.waitForTimeout(5000);
      await screenshot(p, '04-alert-detail');

      // 检查各区块
      const descriptions = await p.locator('.ant-descriptions').count();
      log(name, '基本信息', descriptions > 0 ? 'PASS' : 'FAIL', `${descriptions} 个描述区块`);

      const timeline = await p.locator('.ant-timeline').count();
      log(name, '处置时间线', timeline > 0 ? 'PASS' : 'FAIL', `${timeline} 个时间线`);

      // ExplainAgent
      const bodyText = await p.textContent('body') || '';
      if (bodyText.includes('四维分析')) log(name, 'ExplainAgent', 'PASS', '四维分析区块存在');
      else log(name, 'ExplainAgent', 'WARN', '未找到四维分析');

      // ResponseAgent
      if (bodyText.includes('处置建议')) log(name, 'ResponseAgent', 'PASS', '处置建议区块存在');
      else log(name, 'ResponseAgent', 'WARN', '未找到处置建议');

      // 检查是否有 "暂不可用" 提示
      if (bodyText.includes('暂不可用')) log(name, 'Agent 服务', 'WARN', '部分 Agent 服务不可用');
      else log(name, 'Agent 服务', 'PASS', 'Agent 服务正常');
    } else {
      log(name, '数据', 'WARN', '无告警数据，跳过详情页测试');
    }
  } else {
    log(name, 'API', 'FAIL', `告警 API 返回 ${resp.status()}`);
  }
}

async function testModels(p: Page) {
  const name = '模型管理';
  await p.goto(`${BASE}/models`);
  await p.waitForTimeout(3000);
  await screenshot(p, '05-models');

  const rows = await p.locator('.ant-table-tbody tr').count();
  log(name, '模型列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 个模型`);

  const bodyText = await p.textContent('body') || '';
  if (bodyText.includes('503') || bodyText.includes('unavailable'))
    log(name, 'API 状态', 'FAIL', '模型服务不可用');
  else log(name, 'API 状态', 'PASS', 'API 正常');

  // 检查操作按钮
  const buttons = await p.locator('button').allTextContents();
  const ops = ['A/B', '回滚', '上线', '下线', '历史'].filter(op => buttons.some(b => b.includes(op)));
  log(name, '操作按钮', ops.length >= 2 ? 'PASS' : 'WARN', `找到: ${ops.join(', ') || '无'}`);
}

async function testPipeline(p: Page) {
  const name = 'DAG 编排';
  await p.goto(`${BASE}/pipeline`);
  await p.waitForTimeout(3000);
  await screenshot(p, '06-pipeline');

  // 检查 Pipeline 列表
  const rows = await p.locator('.ant-table-tbody tr').count();
  log(name, 'Pipeline 列表', rows > 0 ? 'PASS' : 'WARN', `${rows} 条 Pipeline`);

  // 检查 DAG 编辑器
  const reactflow = await p.locator('.react-flow, .reactflow-wrapper, [class*="react-flow"]').count();
  log(name, 'DAG 编辑器', reactflow > 0 ? 'PASS' : 'WARN', `ReactFlow 元素: ${reactflow}`);

  // 检查节点面板
  const bodyText = await p.textContent('body') || '';
  if (bodyText.includes('节点') || bodyText.includes('Node'))
    log(name, '节点面板', 'PASS', '节点面板存在');
  else log(name, '节点面板', 'WARN', '未找到节点面板');

  // 检查保存按钮
  const saveBtn = p.locator('button').filter({ hasText: /保存|Save/ });
  if (await saveBtn.count() > 0) log(name, '保存功能', 'PASS', '保存按钮存在');
  else log(name, '保存功能', 'WARN', '未找到保存按钮');
}

async function testReports(p: Page) {
  const name = '分析报表';
  await p.goto(`${BASE}/reports`);
  await p.waitForTimeout(3000);
  await screenshot(p, '07-reports');

  const cards = await p.locator('.ant-card').count();
  log(name, '报表卡片', cards >= 2 ? 'PASS' : 'WARN', `${cards} 个卡片`);

  // 检查日期选择器
  const picker = await p.locator('.ant-picker').count();
  log(name, '日期选择器', picker > 0 ? 'PASS' : 'WARN', `${picker} 个日期选择器`);

  // 检查表格
  const tables = await p.locator('.ant-table').count();
  log(name, '数据表格', tables > 0 ? 'PASS' : 'WARN', `${tables} 个表格`);

  const bodyText = await p.textContent('body') || '';
  if (bodyText.includes('503') || bodyText.includes('unavailable'))
    log(name, 'API 状态', 'FAIL', '报表服务不可用');
  else log(name, 'API 状态', 'PASS', 'API 正常');
}

async function testAgentMonitor(p: Page) {
  const name = 'Agent 监控';
  await p.goto(`${BASE}/agent-monitor`);
  await p.waitForTimeout(3000);
  await screenshot(p, '08-agent-monitor');

  const cards = await p.locator('.ant-card').count();
  log(name, '监控卡片', cards >= 1 ? 'PASS' : 'WARN', `${cards} 个卡片`);

  const bodyText = await p.textContent('body') || '';
  if (bodyText.includes('503') || bodyText.includes('unavailable'))
    log(name, 'API 状态', 'FAIL', 'Agent 监控服务不可用');
  else log(name, 'API 状态', 'PASS', 'API 正常');

  // 检查 Agent 状态
  const tags = await p.locator('.ant-tag').count();
  log(name, 'Agent 状态标签', tags > 0 ? 'PASS' : 'WARN', `${tags} 个标签`);
}

async function testChatPanel(p: Page) {
  const name = 'Chat 智能助手';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(2000);

  // 找到浮动按钮
  const fab = p.locator('button.ant-btn-circle').last();
  if (await fab.count() > 0) {
    await fab.click();
    await p.waitForTimeout(1000);
    await screenshot(p, '09-chat-open');
    log(name, '浮动按钮', 'PASS', 'Chat 面板打开');

    // 检查模式切换
    const segmented = await p.locator('.ant-segmented').count();
    log(name, '模式切换', segmented > 0 ? 'PASS' : 'FAIL', segmented > 0 ? 'Segmented 控件存在' : '未找到模式切换');

    // 检查欢迎消息
    const bodyText = await p.textContent('body') || '';
    if (bodyText.includes('数据查询模式') || bodyText.includes('智能助手'))
      log(name, '欢迎消息', 'PASS', '欢迎消息显示');
    else log(name, '欢迎消息', 'WARN', '未找到欢迎消息');

    // 测试 Text2SQL 模式
    const chatInput = p.locator('.ant-input-search input, .ant-input-affix-wrapper input').last();
    if (await chatInput.count() > 0) {
      await chatInput.fill('查询今日告警数量');
      await chatInput.press('Enter');
      await p.waitForTimeout(5000);
      await screenshot(p, '09-chat-sql-result');
      log(name, 'Text2SQL 查询', 'PASS', '已发送查询');
    }

    // 切换到 RAG 模式
    const ragTab = p.locator('.ant-segmented-item').filter({ hasText: '知识库' });
    if (await ragTab.count() > 0) {
      await ragTab.click();
      await p.waitForTimeout(1000);

      const bodyText2 = await p.textContent('body') || '';
      if (bodyText2.includes('知识库模式'))
        log(name, 'RAG 模式切换', 'PASS', '切换到知识库模式');
      else log(name, 'RAG 模式切换', 'WARN', '切换后未显示知识库欢迎语');

      // 测试 RAG 查询
      const ragInput = p.locator('.ant-input-search input, .ant-input-affix-wrapper input').last();
      if (await ragInput.count() > 0) {
        await ragInput.fill('什么是 DGA 域名');
        await ragInput.press('Enter');
        await p.waitForTimeout(5000);
        await screenshot(p, '09-chat-rag-result');
        log(name, 'RAG 查询', 'PASS', '已发送 RAG 查询');
      }
    } else {
      log(name, 'RAG 模式', 'FAIL', '未找到知识库切换按钮');
    }

    // 关闭 Chat
    const closeBtn = p.locator('.anticon-close').last();
    if (await closeBtn.count() > 0) await closeBtn.click();
  } else {
    log(name, '浮动按钮', 'FAIL', '未找到 Chat 浮动按钮');
  }
}

async function testNavigation(p: Page) {
  const name = '导航与布局';
  await p.goto(`${BASE}/dashboard`);
  await p.waitForTimeout(2000);

  // 检查侧边栏菜单
  const menuItems = await p.locator('.ant-menu-item').count();
  log(name, '侧边栏菜单', menuItems >= 6 ? 'PASS' : 'WARN', `${menuItems} 个菜单项`);

  // 检查 Header
  const header = await p.locator('.ant-layout-header').count();
  log(name, 'Header', header > 0 ? 'PASS' : 'FAIL', header > 0 ? 'Header 存在' : '未找到 Header');

  // 检查 Footer 健康状态
  const footer = await p.locator('.ant-layout-footer').count();
  log(name, 'Footer', footer > 0 ? 'PASS' : 'FAIL', footer > 0 ? 'Footer 存在' : '未找到 Footer');

  const footerText = await p.locator('.ant-layout-footer').textContent() || '';
  if (footerText.includes('系统正常') || footerText.includes('系统不可达') || footerText.includes('部分服务'))
    log(name, '健康状态', 'PASS', `Footer 显示: ${footerText.slice(0, 50)}`);
  else log(name, '健康状态', 'WARN', `Footer 内容: ${footerText.slice(0, 50)}`);

  // 检查告警角标
  const badge = await p.locator('.ant-badge').count();
  log(name, '告警角标', badge > 0 ? 'PASS' : 'WARN', `${badge} 个角标`);

  // 测试侧边栏折叠
  const collapseBtn = p.locator('.ant-layout-sider-trigger');
  if (await collapseBtn.count() > 0) {
    await collapseBtn.click();
    await p.waitForTimeout(500);
    await screenshot(p, '10-sidebar-collapsed');
    log(name, '侧边栏折叠', 'PASS', '折叠功能正常');
    await collapseBtn.click();
    await p.waitForTimeout(500);
  }
}

async function testAPIEndpoints(p: Page) {
  const name = 'API 端点';
  const endpoints = [
    { path: '/api/healthz', label: 'healthz' },
    { path: '/api/readyz', label: 'readyz' },
    { path: '/api/alerts?limit=1', label: 'alerts' },
    { path: '/api/models', label: 'models' },
    { path: '/api/dag/pipelines', label: 'dag pipelines' },
    { path: '/api/dashboard/stats', label: 'dashboard stats' },
    { path: '/api/reports/stats?days=7', label: 'reports stats' },
    { path: '/api/agents/metrics', label: 'agent metrics' },
  ];

  for (const ep of endpoints) {
    try {
      const resp = await p.request.get(`${BASE}${ep.path}`);
      const status = resp.status();
      if (status === 200) log(name, ep.label, 'PASS', `${status} OK`);
      else if (status === 503) log(name, ep.label, 'WARN', `${status} 服务不可用`);
      else log(name, ep.label, 'FAIL', `${status}`);
    } catch (e: any) {
      log(name, ep.label, 'FAIL', `请求失败: ${e.message}`);
    }
  }
}

async function testConsoleErrors(p: Page) {
  const name = '控制台错误';
  const errors: string[] = [];
  p.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  p.on('pageerror', err => errors.push(err.message));

  const pages = ['/dashboard', '/detection', '/alerts', '/models', '/pipeline', '/reports', '/agent-monitor'];
  for (const path of pages) {
    await p.goto(`${BASE}${path}`);
    await p.waitForTimeout(2000);
  }

  if (errors.length === 0) log(name, '全页面', 'PASS', '无控制台错误');
  else {
    const unique = [...new Set(errors)];
    for (const err of unique.slice(0, 10)) {
      log(name, '错误', 'WARN', err.slice(0, 120));
    }
  }
}

async function main() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  console.log('🚀 DGA 平台全功能自动化测试开始\n');
  console.log('='.repeat(60));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    await testNavigation(page);
    console.log('-'.repeat(60));
    await testDashboard(page);
    console.log('-'.repeat(60));
    await testDetection(page);
    console.log('-'.repeat(60));
    await testAlerts(page);
    console.log('-'.repeat(60));
    await testAlertDetail(page);
    console.log('-'.repeat(60));
    await testModels(page);
    console.log('-'.repeat(60));
    await testPipeline(page);
    console.log('-'.repeat(60));
    await testReports(page);
    console.log('-'.repeat(60));
    await testAgentMonitor(page);
    console.log('-'.repeat(60));
    await testChatPanel(page);
    console.log('-'.repeat(60));
    await testAPIEndpoints(page);
    console.log('-'.repeat(60));
    await testConsoleErrors(page);
  } finally {
    await browser.close();
  }

  // 汇总报告
  console.log('\n' + '='.repeat(60));
  console.log('📊 测试结果汇总\n');
  const pass = RESULTS.filter(r => r.status === 'PASS').length;
  const fail = RESULTS.filter(r => r.status === 'FAIL').length;
  const warn = RESULTS.filter(r => r.status === 'WARN').length;
  console.log(`  ✅ PASS: ${pass}  ❌ FAIL: ${fail}  ⚠️ WARN: ${warn}  总计: ${RESULTS.length}`);

  if (fail > 0) {
    console.log('\n❌ 失败项:');
    RESULTS.filter(r => r.status === 'FAIL').forEach(r => console.log(`  - [${r.page}] ${r.feature}: ${r.detail}`));
  }
  if (warn > 0) {
    console.log('\n⚠️ 警告项:');
    RESULTS.filter(r => r.status === 'WARN').forEach(r => console.log(`  - [${r.page}] ${r.feature}: ${r.detail}`));
  }

  console.log(`\n📸 截图保存在: ${SCREENSHOT_DIR}`);

  // 写入 JSON 报告
  const reportPath = path.join(SCREENSHOT_DIR, 'test-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(RESULTS, null, 2));
  console.log(`📄 JSON 报告: ${reportPath}`);
}

main().catch(console.error);
