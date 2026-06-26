import { chromium, type Page, type Browser } from 'playwright';

const BASE = 'http://localhost:3000';
const results: { page: string; test: string; status: 'PASS' | 'FAIL' | 'WARN'; detail: string }[] = [];

function log(page: string, test: string, status: 'PASS' | 'FAIL' | 'WARN', detail: string) {
  results.push({ page, test, status, detail });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} [${page}] ${test}: ${detail}`);
}

async function waitForPageReady(page: Page) {
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1000);
}

async function getConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });
  return errors;
}

// ─── 1. Dashboard ───
async function testDashboard(page: Page) {
  const name = 'Dashboard';
  await page.goto(`${BASE}/dashboard`);
  await waitForPageReady(page);

  // Check page loads
  const title = await page.title();
  log(name, '页面加载', title ? 'PASS' : 'FAIL', `Title: ${title}`);

  // Check key stats cards
  const cards = await page.locator('.ant-card').count();
  log(name, '统计卡片', cards >= 2 ? 'PASS' : 'WARN', `找到 ${cards} 个卡片`);

  // Check for charts
  const charts = await page.locator('canvas, .recharts-wrapper, svg.recharts-surface, [class*="chart"]').count();
  log(name, '图表渲染', charts >= 1 ? 'PASS' : 'WARN', `找到 ${charts} 个图表元素`);

  // Screenshot
  await page.screenshot({ path: 'frontend/screenshots-v2/dashboard.png', fullPage: true });
  log(name, '截图', 'PASS', 'dashboard.png');
}

// ─── 2. Detection ───
async function testDetection(page: Page) {
  const name = 'Detection';
  await page.goto(`${BASE}/detection`);
  await waitForPageReady(page);

  // Check page loads
  const hasInput = await page.locator('textarea, input[type="text"], .ant-input').first().isVisible().catch(() => false);
  log(name, '输入框', hasInput ? 'PASS' : 'FAIL', hasInput ? '检测输入框可见' : '未找到输入框');

  // Try submitting a domain
  const textarea = page.locator('textarea, .ant-input').first();
  if (await textarea.isVisible().catch(() => false)) {
    await textarea.fill('google.com\nexample.com\nasdkjqwekjh.xyz');
    const submitBtn = page.locator('button').filter({ hasText: /检测|分析|提交|Score/i }).first();
    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(3000);
      // Check results
      const resultTable = await page.locator('.ant-table-tbody tr, .ant-list-item').count();
      log(name, '检测提交', resultTable > 0 ? 'PASS' : 'WARN', `结果行数: ${resultTable}`);
    } else {
      log(name, '检测提交', 'WARN', '未找到提交按钮');
    }
  }

  await page.screenshot({ path: 'frontend/screenshots-v2/detection.png', fullPage: true });
  log(name, '截图', 'PASS', 'detection.png');
}

// ─── 3. Alerts ───
async function testAlerts(page: Page) {
  const name = 'Alerts';
  await page.goto(`${BASE}/alerts`);
  await waitForPageReady(page);

  const table = await page.locator('.ant-table').first().isVisible().catch(() => false);
  log(name, '告警列表', table ? 'PASS' : 'WARN', table ? '表格可见' : '未找到表格或无数据');

  // Check filter area
  const filters = await page.locator('.ant-select, .ant-picker, .ant-input').count();
  log(name, '筛选区域', filters >= 1 ? 'PASS' : 'WARN', `找到 ${filters} 个筛选组件`);

  // Check pagination
  const pagination = await page.locator('.ant-pagination').isVisible().catch(() => false);
  log(name, '分页', pagination ? 'PASS' : 'WARN', pagination ? '分页可见' : '无分页');

  // Try clicking first alert row for detail
  const firstRow = page.locator('.ant-table-tbody tr').first();
  if (await firstRow.isVisible().catch(() => false)) {
    await firstRow.click();
    await page.waitForTimeout(2000);
    const url = page.url();
    log(name, '告警详情跳转', url.includes('/alerts/') ? 'PASS' : 'WARN', `URL: ${url}`);
    await page.goBack();
    await waitForPageReady(page);
  }

  await page.screenshot({ path: 'frontend/screenshots-v2/alerts.png', fullPage: true });
  log(name, '截图', 'PASS', 'alerts.png');
}

// ─── 4. Models ───
async function testModels(page: Page) {
  const name = 'Models';
  await page.goto(`${BASE}/models`);
  await waitForPageReady(page);

  const cards = await page.locator('.ant-card').count();
  log(name, '模型卡片', cards >= 1 ? 'PASS' : 'WARN', `找到 ${cards} 个卡片`);

  const table = await page.locator('.ant-table').first().isVisible().catch(() => false);
  log(name, '模型列表', table ? 'PASS' : 'WARN', table ? '表格可见' : '未找到表格');

  // Check action buttons
  const btns = await page.locator('button').filter({ hasText: /部署|回滚|A\/B|下线/i }).count();
  log(name, '操作按钮', btns >= 1 ? 'PASS' : 'WARN', `找到 ${btns} 个操作按钮`);

  await page.screenshot({ path: 'frontend/screenshots-v2/models.png', fullPage: true });
  log(name, '截图', 'PASS', 'models.png');
}

// ─── 5. Pipeline ───
async function testPipeline(page: Page) {
  const name = 'Pipeline';
  await page.goto(`${BASE}/pipeline`);
  await waitForPageReady(page);

  // Check table
  const table = await page.locator('.ant-table').first().isVisible().catch(() => false);
  log(name, 'Pipeline列表', table ? 'PASS' : 'WARN', table ? '表格可见' : '未找到表格');

  // Check search filters
  const searchInput = await page.locator('input[placeholder*="Pipeline"], input[placeholder*="名称"]').isVisible().catch(() => false);
  const statusSelect = await page.locator('.ant-select').count().then(c => c >= 1).catch(() => false);
  const datePicker = await page.locator('.ant-picker').count().then(c => c >= 1).catch(() => false);
  log(name, '搜索筛选区', searchInput || statusSelect || datePicker ? 'PASS' : 'WARN',
    `名称搜索:${searchInput} 状态筛选:${statusSelect} 日期:${datePicker}`);

  // Check create button
  const createBtn = page.locator('button').filter({ hasText: /新建/i }).first();
  const hasCreate = await createBtn.isVisible().catch(() => false);
  log(name, '新建按钮', hasCreate ? 'PASS' : 'FAIL', hasCreate ? '新建按钮可见' : '未找到新建按钮');

  // Test create pipeline
  if (hasCreate) {
    await createBtn.click();
    await page.waitForTimeout(1000);
    const modal = await page.locator('.ant-modal-content').isVisible().catch(() => false);
    log(name, '新建弹窗', modal ? 'PASS' : 'FAIL', modal ? '弹窗已打开' : '弹窗未打开');
    if (modal) {
      // Use the modal's cancel/close button
      const cancelBtn = page.locator('.ant-modal-content').locator('button').filter({ hasText: /取消|Cancel/i }).first();
      const closeBtn = page.locator('.ant-modal-close').first();
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click();
      } else if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
      } else {
        await page.keyboard.press('Escape');
      }
      await page.waitForTimeout(500);
    }
  }

  // Check action buttons (start/stop, edit, delete, history)
  const actionBtns = await page.locator('.ant-table-tbody button').count();
  log(name, '操作按钮', actionBtns >= 1 ? 'PASS' : 'WARN', `找到 ${actionBtns} 个操作按钮`);

  // Check disabled state for running pipelines
  const rows = await page.locator('.ant-table-tbody tr').count();
  if (rows > 0) {
    // Click first row to load into editor
    const firstRowName = page.locator('.ant-table-tbody tr').first().locator('a').first();
    if (await firstRowName.isVisible().catch(() => false)) {
      await firstRowName.click();
      await page.waitForTimeout(2000);
      // Check DAG editor loaded
      const dagEditor = await page.locator('.react-flow, [class*="reactflow"]').isVisible().catch(() => false);
      log(name, 'DAG编辑器', dagEditor ? 'PASS' : 'WARN', dagEditor ? '编辑器已加载' : '编辑器未加载');
    }
  }

  await page.screenshot({ path: 'frontend/screenshots-v2/pipeline.png', fullPage: true });
  log(name, '截图', 'PASS', 'pipeline.png');
}

// ─── 6. Reports ───
async function testReports(page: Page) {
  const name = 'Reports';
  await page.goto(`${BASE}/reports`);
  await waitForPageReady(page);

  const cards = await page.locator('.ant-card').count();
  log(name, '报告卡片', cards >= 1 ? 'PASS' : 'WARN', `找到 ${cards} 个卡片`);

  const charts = await page.locator('canvas, .recharts-wrapper, svg.recharts-surface').count();
  log(name, '图表', charts >= 1 ? 'PASS' : 'WARN', `找到 ${charts} 个图表`);

  await page.screenshot({ path: 'frontend/screenshots-v2/reports.png', fullPage: true });
  log(name, '截图', 'PASS', 'reports.png');
}

// ─── 7. Agent Monitor ───
async function testAgentMonitor(page: Page) {
  const name = 'AgentMonitor';
  await page.goto(`${BASE}/agent-monitor`);
  await waitForPageReady(page);

  const cards = await page.locator('.ant-card').count();
  log(name, '页面加载', cards >= 1 ? 'PASS' : 'WARN', `找到 ${cards} 个卡片`);

  await page.screenshot({ path: 'frontend/screenshots-v2/agent-monitor.png', fullPage: true });
  log(name, '截图', 'PASS', 'agent-monitor.png');
}

// ─── 8. Navigation & Layout ───
async function testNavigation(page: Page) {
  const name = 'Navigation';
  await page.goto(`${BASE}/dashboard`);
  await waitForPageReady(page);

  // Check sidebar menu
  const menuItems = await page.locator('.ant-menu-item, .ant-menu-submenu').count();
  log(name, '侧边栏菜单', menuItems >= 5 ? 'PASS' : 'WARN', `找到 ${menuItems} 个菜单项`);

  // Navigate through all pages via menu
  const routes = [
    { text: /仪表盘|Dashboard/i, path: '/dashboard' },
    { text: /检测|Detection/i, path: '/detection' },
    { text: /告警|Alert/i, path: '/alerts' },
    { text: /模型|Model/i, path: '/models' },
    { text: /流水线|Pipeline/i, path: '/pipeline' },
    { text: /报告|Report/i, path: '/reports' },
  ];

  for (const route of routes) {
    const menuItem = page.locator('.ant-menu-item').filter({ hasText: route.text }).first();
    if (await menuItem.isVisible().catch(() => false)) {
      await menuItem.click();
      await page.waitForTimeout(1000);
      const url = page.url();
      log(name, `导航到${route.path}`, url.includes(route.path) ? 'PASS' : 'WARN', `URL: ${url}`);
    }
  }

  // Check chat panel toggle
  const chatBtn = page.locator('[class*="chat"], button').filter({ hasText: /AI|Chat|助手/i }).first();
  if (await chatBtn.isVisible().catch(() => false)) {
    await chatBtn.click();
    await page.waitForTimeout(500);
    log(name, 'Chat面板', 'PASS', 'Chat按钮可点击');
  } else {
    log(name, 'Chat面板', 'WARN', '未找到Chat入口');
  }
}

// ─── 9. Responsive & Error Handling ───
async function testResponsive(page: Page) {
  const name = 'Responsive';

  // Test 404 page
  await page.goto(`${BASE}/nonexistent-page`);
  await waitForPageReady(page);
  const url404 = page.url();
  log(name, '404处理', url404.includes('/dashboard') || url404.includes('/nonexistent') ? 'PASS' : 'WARN', `URL: ${url404}`);

  // Test smaller viewport
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${BASE}/dashboard`);
  await waitForPageReady(page);
  await page.screenshot({ path: 'frontend/screenshots-v2/responsive-1024.png', fullPage: true });
  log(name, '1024px视口', 'PASS', '截图已保存');

  // Reset viewport
  await page.setViewportSize({ width: 1440, height: 900 });
}

// ─── Main ───
async function main() {
  console.log('🚀 开始 DGA 平台全功能 E2E 测试...\n');

  // Ensure screenshot dir
  const fs = await import('fs');
  if (!fs.existsSync('frontend/screenshots-v2')) fs.mkdirSync('frontend/screenshots-v2', { recursive: true });

  const browser: Browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors: string[] = [];
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(`[${msg.location().url}] ${msg.text()}`); });
  page.on('pageerror', (err) => { consoleErrors.push(`PageError: ${err.message}`); });

  try {
    await testDashboard(page);
    await testDetection(page);
    await testAlerts(page);
    await testModels(page);
    await testPipeline(page);
    await testReports(page);
    await testAgentMonitor(page);
    await testNavigation(page);
    await testResponsive(page);
  } catch (err) {
    console.error('测试执行异常:', err);
  }

  // --- Cleanup E2E test data ---
  try {
    console.log('\n🧹 清理 E2E 测试数据...');
    const listResp = await fetch('http://localhost:3000/api/dag/pipelines');
    if (listResp.ok) {
      const { pipelines } = await listResp.json();
      const testPipelines = (pipelines || []).filter((p: { name: string }) => /E2E|测试Pipeline/i.test(p.name));
      for (const p of testPipelines) {
        const delResp = await fetch(`http://localhost:3000/api/dag/pipelines/${encodeURIComponent(p.pipeline_id)}`, { method: 'DELETE' });
        console.log(`  ${delResp.ok ? '✅' : '❌'} 删除: ${p.name} (${p.pipeline_id})`);
      }
      if (testPipelines.length === 0) console.log('  无需清理');
    }
  } catch {
    console.log('  ⚠️ 清理失败（可忽略）');
  }

  await browser.close();

  // ─── Summary ───
  console.log('\n' + '='.repeat(70));
  console.log('📊 测试结果汇总');
  console.log('='.repeat(70));

  const pass = results.filter((r) => r.status === 'PASS').length;
  const fail = results.filter((r) => r.status === 'FAIL').length;
  const warn = results.filter((r) => r.status === 'WARN').length;
  console.log(`\n✅ PASS: ${pass}  ❌ FAIL: ${fail}  ⚠️ WARN: ${warn}  📋 Total: ${results.length}\n`);

  if (fail > 0) {
    console.log('--- FAILURES ---');
    results.filter((r) => r.status === 'FAIL').forEach((r) => console.log(`  ❌ [${r.page}] ${r.test}: ${r.detail}`));
  }
  if (warn > 0) {
    console.log('--- WARNINGS ---');
    results.filter((r) => r.status === 'WARN').forEach((r) => console.log(`  ⚠️ [${r.page}] ${r.test}: ${r.detail}`));
  }
  if (consoleErrors.length > 0) {
    console.log(`\n--- Console Errors (${consoleErrors.length}) ---`);
    [...new Set(consoleErrors)].slice(0, 20).forEach((e) => console.log(`  🔴 ${e}`));
  }

  console.log('\n' + '='.repeat(70));
  console.log('测试完成');
  console.log('='.repeat(70));
}

main().catch(console.error);
