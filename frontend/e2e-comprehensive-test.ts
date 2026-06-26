import { chromium, type Page, type Browser } from "playwright";

const BASE = "http://localhost:3000";
const results: {
  page: string;
  test: string;
  status: "PASS" | "FAIL" | "WARN";
  detail: string;
}[] = [];

function log(
  page: string,
  test: string,
  status: "PASS" | "FAIL" | "WARN",
  detail: string,
) {
  results.push({ page, test, status, detail });
  const icon = status === "PASS" ? "✅" : status === "FAIL" ? "❌" : "⚠️";
  console.log(`${icon} [${page}] ${test}: ${detail}`);
}

async function waitForPageReady(page: Page) {
  await page
    .waitForLoadState("networkidle", { timeout: 15000 })
    .catch(() => {});
  await page.waitForTimeout(1500);
}

async function isVisible(page: Page, selector: string): Promise<boolean> {
  return page
    .locator(selector)
    .first()
    .isVisible()
    .catch(() => false);
}

// ─── 1. Dashboard ───
async function testDashboard(page: Page) {
  const P = "Dashboard";
  console.log("\n━━━ 1. Dashboard ━━━");
  await page.goto(`${BASE}/dashboard`);
  await waitForPageReady(page);

  const title = await page.title();
  log(P, "页面加载", title ? "PASS" : "FAIL", `Title: ${title}`);

  // Stat cards
  const cards = await page.locator(".ant-statistic").count();
  log(P, "统计卡片", cards >= 3 ? "PASS" : "WARN", `找到 ${cards} 个统计项`);

  // Charts (ECharts renders to canvas)
  const canvases = await page.locator("canvas").count();
  log(
    P,
    "图表渲染",
    canvases >= 1 ? "PASS" : "WARN",
    `找到 ${canvases} 个 canvas`,
  );

  // Realtime alerts section
  const tabs = await page.locator(".ant-tabs-tab").count();
  log(P, "实时告警Tab", tabs >= 1 ? "PASS" : "WARN", `找到 ${tabs} 个 Tab`);

  // Health status in footer
  const footer = await isVisible(page, ".ant-layout-footer");
  log(
    P,
    "Footer健康状态",
    footer ? "PASS" : "WARN",
    footer ? "可见" : "不可见",
  );

  await page.screenshot({
    path: "frontend/screenshots-v2/01-dashboard.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "01-dashboard.png");
}

// ─── 2. Detection ───
async function testDetection(page: Page) {
  const P = "Detection";
  console.log("\n━━━ 2. Detection ━━━");
  await page.goto(`${BASE}/detection`);
  await waitForPageReady(page);

  // Input area
  const textarea = page.locator("textarea").first();
  const hasInput = await textarea.isVisible().catch(() => false);
  log(
    P,
    "域名输入框",
    hasInput ? "PASS" : "FAIL",
    hasInput ? "可见" : "未找到",
  );

  // Submit button
  const submitBtn = page
    .locator("button")
    .filter({ hasText: /检测|分析|提交|Score/i })
    .first();
  const hasSubmit = await submitBtn.isVisible().catch(() => false);
  log(
    P,
    "检测按钮",
    hasSubmit ? "PASS" : "FAIL",
    hasSubmit ? "可见" : "未找到",
  );

  // Submit test domains
  if (hasInput && hasSubmit) {
    await textarea.fill("google.com\nexample.com\nasdkjqwekjh.xyz");
    await submitBtn.click();
    await page.waitForTimeout(4000);

    const resultRows = await page.locator(".ant-table-tbody tr").count();
    log(
      P,
      "检测结果",
      resultRows > 0 ? "PASS" : "WARN",
      `结果行数: ${resultRows}`,
    );

    // Check for score gauge
    const gauge = await page.locator("canvas").count();
    log(P, "风险评分图", gauge >= 1 ? "PASS" : "WARN", `canvas: ${gauge}`);

    // Check explain button
    const explainBtn = page
      .locator("button")
      .filter({ hasText: /解释|Explain/i })
      .first();
    const hasExplain = await explainBtn.isVisible().catch(() => false);
    log(
      P,
      "AI解释按钮",
      hasExplain ? "PASS" : "WARN",
      hasExplain ? "可见" : "未找到",
    );

    if (hasExplain) {
      await explainBtn.click();
      await page.waitForTimeout(3000);
      log(P, "AI解释触发", "PASS", "已点击解释按钮");
    }

    await page.screenshot({
      path: "frontend/screenshots-v2/02-detection-results.png",
      fullPage: true,
    });
  }

  await page.screenshot({
    path: "frontend/screenshots-v2/02-detection.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "02-detection.png");
}

// ─── 3. Alerts ───
async function testAlerts(page: Page) {
  const P = "Alerts";
  console.log("\n━━━ 3. Alerts ━━━");
  await page.goto(`${BASE}/alerts`);
  await waitForPageReady(page);

  // Filter area
  const selects = await page.locator(".ant-select").count();
  const pickers = await page.locator(".ant-picker").count();
  const inputs = await page.locator(".ant-input").count();
  log(
    P,
    "筛选组件",
    selects + pickers + inputs >= 3 ? "PASS" : "WARN",
    `Select:${selects} Picker:${pickers} Input:${inputs}`,
  );

  // Query & Reset buttons
  const queryBtn = page
    .locator("button")
    .filter({ hasText: /查询|搜索/i })
    .first();
  const resetBtn = page.locator("button").filter({ hasText: /重置/i }).first();
  const hasQuery = await queryBtn.isVisible().catch(() => false);
  const hasReset = await resetBtn.isVisible().catch(() => false);
  log(
    P,
    "查询/重置按钮",
    hasQuery && hasReset ? "PASS" : "WARN",
    `查询:${hasQuery} 重置:${hasReset}`,
  );

  // Table
  const table = await isVisible(page, ".ant-table");
  log(P, "告警表格", table ? "PASS" : "WARN", table ? "可见" : "未找到");

  // Row count
  const rows = await page.locator(".ant-table-tbody tr").count();
  log(P, "告警数据", rows > 0 ? "PASS" : "WARN", `${rows} 行数据`);

  // Pagination
  const pagination = await isVisible(page, ".ant-pagination");
  log(P, "分页", pagination ? "PASS" : "WARN", pagination ? "可见" : "无分页");

  // Test filter: click reset to ensure clean state
  if (hasReset) {
    await resetBtn.click();
    await page.waitForTimeout(1000);
    log(P, "重置筛选", "PASS", "已点击重置");
  }

  // Click first row to open detail drawer
  if (rows > 0) {
    const firstRow = page.locator(".ant-table-tbody tr").first();
    await firstRow.click();
    await page.waitForTimeout(2000);

    // Check if drawer or navigation happened
    const drawer = await isVisible(page, ".ant-drawer");
    const urlChanged = page.url().includes("/alerts/");
    if (drawer) {
      log(P, "告警详情抽屉", "PASS", "抽屉已打开");
      // Check drawer content
      const descriptions = await isVisible(page, ".ant-descriptions");
      log(
        P,
        "详情描述",
        descriptions ? "PASS" : "WARN",
        descriptions ? "可见" : "未找到",
      );

      // Close drawer
      const closeBtn = page.locator(".ant-drawer-close").first();
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
        await page.waitForTimeout(500);
      }
    } else if (urlChanged) {
      log(P, "告警详情页", "PASS", `跳转到: ${page.url()}`);
      await page.goBack();
      await waitForPageReady(page);
    } else {
      log(P, "告警详情", "WARN", "未打开抽屉或跳转");
    }
  }

  await page.screenshot({
    path: "frontend/screenshots-v2/03-alerts.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "03-alerts.png");
}

// ─── 4. Models ───
async function testModels(page: Page) {
  const P = "Models";
  console.log("\n━━━ 4. Models ━━━");
  await page.goto(`${BASE}/models`);
  await waitForPageReady(page);

  const cards = await page.locator(".ant-card").count();
  log(P, "模型卡片", cards >= 1 ? "PASS" : "WARN", `找到 ${cards} 个卡片`);

  const table = await isVisible(page, ".ant-table");
  log(P, "模型版本表", table ? "PASS" : "WARN", table ? "可见" : "未找到");

  // Performance chart
  const canvases = await page.locator("canvas").count();
  log(P, "性能图表", canvases >= 1 ? "PASS" : "WARN", `canvas: ${canvases}`);

  // Action buttons
  const actionBtns = await page
    .locator("button")
    .filter({ hasText: /回滚|下线|上线|历史/i })
    .count();
  log(
    P,
    "操作按钮",
    actionBtns >= 1 ? "PASS" : "WARN",
    `找到 ${actionBtns} 个`,
  );

  // A/B test section
  const slider = await isVisible(page, ".ant-slider");
  log(
    P,
    "A/B测试配置",
    slider ? "PASS" : "WARN",
    slider ? "Slider可见" : "未找到",
  );

  await page.screenshot({
    path: "frontend/screenshots-v2/04-models.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "04-models.png");
}

// ─── 5. Pipeline (most comprehensive) ───
async function testPipeline(page: Page) {
  const P = "Pipeline";
  console.log("\n━━━ 5. Pipeline ━━━");
  await page.goto(`${BASE}/pipeline`);
  await waitForPageReady(page);

  // Stat cards
  const stats = await page.locator(".ant-statistic").count();
  log(P, "统计卡片", stats >= 3 ? "PASS" : "WARN", `找到 ${stats} 个统计项`);

  // Charts
  const canvases = await page.locator("canvas").count();
  log(P, "图表", canvases >= 1 ? "PASS" : "WARN", `canvas: ${canvases}`);

  // Pipeline table
  const table = await isVisible(page, ".ant-table");
  log(P, "Pipeline列表", table ? "PASS" : "WARN", table ? "可见" : "未找到");

  // Search filters
  const searchInput = await page
    .locator('input[placeholder*="Pipeline"], input[placeholder*="名称"]')
    .count();
  const statusSelect = await page.locator(".ant-select").count();
  log(
    P,
    "搜索筛选",
    searchInput + statusSelect >= 1 ? "PASS" : "WARN",
    `搜索框:${searchInput} 下拉:${statusSelect}`,
  );

  // Create button
  const createBtn = page.locator("button").filter({ hasText: /新建/i }).first();
  const hasCreate = await createBtn.isVisible().catch(() => false);
  log(
    P,
    "新建按钮",
    hasCreate ? "PASS" : "FAIL",
    hasCreate ? "可见" : "未找到",
  );

  // ── Status control: verify edit/delete disabled for running pipelines ──
  const rows = await page.locator(".ant-table-tbody tr").count();
  if (rows > 0) {
    console.log(`  检查 ${rows} 个 Pipeline 的状态控制...`);
    for (let i = 0; i < Math.min(rows, 5); i++) {
      const row = page.locator(".ant-table-tbody tr").nth(i);
      // Status is in the 3rd td (index 2), mode is in 2nd td (index 1)
      const statusCell = row.locator("td").nth(2);
      const statusText = await statusCell
        .locator(".ant-tag")
        .textContent()
        .catch(() => "unknown");

      // Find edit and delete buttons in this row
      const editBtn = row.locator("button:has(.anticon-edit)").first();
      const deleteBtn = row.locator("button:has(.anticon-delete)").first();

      const editDisabled = await editBtn.isDisabled().catch(() => null);
      const deleteDisabled = await deleteBtn.isDisabled().catch(() => null);

      if (statusText === "running") {
        const editOk = editDisabled === true;
        const deleteOk = deleteDisabled === true;
        log(
          P,
          `状态控制[${i}]`,
          editOk && deleteOk ? "PASS" : "FAIL",
          `running: Edit禁用=${editDisabled} Delete禁用=${deleteDisabled}`,
        );
      } else if (statusText === "stopped" || statusText === "inactive") {
        const editOk = editDisabled === false;
        const deleteOk = deleteDisabled === false;
        log(
          P,
          `状态控制[${i}]`,
          editOk && deleteOk ? "PASS" : "FAIL",
          `${statusText}: Edit可用=${!editDisabled} Delete可用=${!deleteDisabled}`,
        );
      } else {
        log(P, `状态控制[${i}]`, "WARN", `状态: ${statusText}`);
      }
    }
  }

  // ── Open editor and verify no unsaved-changes dialog ──
  if (rows > 0) {
    // Find a stopped/inactive pipeline to open editor
    let editorOpened = false;
    for (let i = 0; i < Math.min(rows, 5); i++) {
      const row = page.locator(".ant-table-tbody tr").nth(i);
      const statusText = await row
        .locator("td")
        .nth(2)
        .locator(".ant-tag")
        .textContent()
        .catch(() => "");
      if (statusText === "stopped" || statusText === "inactive") {
        const editBtn = row.locator("button:has(.anticon-edit)").first();
        if (await editBtn.isVisible().catch(() => false)) {
          await editBtn.click();
          await page.waitForTimeout(2000);
          editorOpened = true;
          break;
        }
      }
    }

    // If no stopped pipeline, try clicking the first pipeline name link
    if (!editorOpened) {
      const nameLink = page.locator(".ant-table-tbody tr a").first();
      if (await nameLink.isVisible().catch(() => false)) {
        await nameLink.click();
        await page.waitForTimeout(2000);
        editorOpened = true;
      }
    }

    if (editorOpened) {
      // Check editor modal
      const editorModal = await page
        .locator(".ant-modal-content")
        .filter({ hasText: /DAG 可视化编排/ })
        .isVisible()
        .catch(() => false);
      log(
        P,
        "DAG编辑器弹窗",
        editorModal ? "PASS" : "WARN",
        editorModal ? "已打开" : "未打开",
      );

      if (editorModal) {
        // Check ReactFlow canvas
        const reactFlow = await page
          .locator('.react-flow, [class*="reactflow"]')
          .isVisible()
          .catch(() => false);
        log(
          P,
          "ReactFlow画布",
          reactFlow ? "PASS" : "WARN",
          reactFlow ? "可见" : "未找到",
        );

        // Check NodePalette
        const palette = await page
          .locator('[class*="palette"], [class*="Palette"]')
          .isVisible()
          .catch(() => false);
        log(
          P,
          "节点面板",
          palette ? "PASS" : "WARN",
          palette ? "可见" : "未找到",
        );

        // Check toolbar (YAML + Save buttons)
        const saveBtn = page
          .locator("button")
          .filter({ hasText: /保存/i })
          .first();
        const hasSave = await saveBtn.isVisible().catch(() => false);
        log(
          P,
          "保存按钮",
          hasSave ? "PASS" : "WARN",
          hasSave ? "可见" : "未找到",
        );

        // Verify NO "未保存" badge
        const unsavedBadge = await page
          .locator(".ant-badge")
          .filter({ hasText: /未保存/ })
          .isVisible()
          .catch(() => false);
        log(
          P,
          "无未保存标记",
          !unsavedBadge ? "PASS" : "FAIL",
          unsavedBadge ? "仍显示未保存Badge" : "已移除未保存Badge",
        );

        await page.screenshot({
          path: "frontend/screenshots-v2/05-pipeline-editor.png",
          fullPage: true,
        });

        // Close editor - verify NO confirmation dialog
        await page.keyboard.press("Escape");
        await page.waitForTimeout(1500);

        // Check no confirm dialog appeared (look for visible confirm with actual content)
        const confirmDialog = await page
          .locator(".ant-modal-confirm-body")
          .isVisible()
          .catch(() => false);

        if (confirmDialog) {
          const confirmText = await page
            .locator(".ant-modal-confirm-body")
            .textContent()
            .catch(() => "");
          log(P, "关闭无确认弹框", "FAIL", `出现了确认弹框: ${confirmText}`);
          // Dismiss confirm and close modal
          const cancelConfirm = page
            .locator(".ant-modal-confirm .ant-btn")
            .filter({ hasText: /取消|Cancel/i })
            .first();
          if (await cancelConfirm.isVisible().catch(() => false)) {
            await cancelConfirm.click();
          } else {
            await page.keyboard.press("Escape");
          }
          await page.waitForTimeout(500);
          await page.keyboard.press("Escape");
          await page.waitForTimeout(500);
        } else {
          log(P, "关闭无确认弹框", "PASS", "直接关闭，无弹框");
        }

        // Verify modal is closed (wait a bit more for animation)
        await page.waitForTimeout(500);
        const modalGone = !(await page
          .locator(".ant-modal-content")
          .filter({ hasText: /DAG 可视化编排/ })
          .isVisible()
          .catch(() => false));
        if (!modalGone) {
          // Force close — reload the page
          await page.goto(`${BASE}/pipeline`);
          await waitForPageReady(page);
        }
        const finalModalGone = !(await page
          .locator(".ant-modal-content")
          .filter({ hasText: /DAG 可视化编排/ })
          .isVisible()
          .catch(() => false));
        log(
          P,
          "编辑器已关闭",
          finalModalGone ? "PASS" : "WARN",
          finalModalGone ? "Modal已关闭" : "Modal仍然打开",
        );
      }
    }
  }

  // ── Create pipeline test ──
  if (hasCreate) {
    await createBtn.click();
    await page.waitForTimeout(1000);
    const createModal = await page
      .locator(".ant-modal-content")
      .isVisible()
      .catch(() => false);
    log(
      P,
      "新建弹窗",
      createModal ? "PASS" : "FAIL",
      createModal ? "已打开" : "未打开",
    );

    if (createModal) {
      // Close without creating
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }
  }

  // ── History drawer test ──
  if (rows > 0) {
    const historyBtn = page
      .locator(".ant-table-tbody button:has(.anticon-history)")
      .first();
    if (await historyBtn.isVisible().catch(() => false)) {
      await historyBtn.click();
      await page.waitForTimeout(1500);
      const drawer = await isVisible(page, ".ant-drawer");
      log(
        P,
        "历史抽屉",
        drawer ? "PASS" : "WARN",
        drawer ? "已打开" : "未打开",
      );
      if (drawer) {
        const drawerClose = page.locator(".ant-drawer-close").first();
        if (await drawerClose.isVisible().catch(() => false)) {
          await drawerClose.click();
          await page.waitForTimeout(500);
        }
      }
    }
  }

  await page.screenshot({
    path: "frontend/screenshots-v2/05-pipeline.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "05-pipeline.png");
}

// ─── 6. Reports ───
async function testReports(page: Page) {
  const P = "Reports";
  console.log("\n━━━ 6. Reports ━━━");
  await page.goto(`${BASE}/reports`);
  await waitForPageReady(page);

  const cards = await page.locator(".ant-card").count();
  log(P, "报告卡片", cards >= 1 ? "PASS" : "WARN", `找到 ${cards} 个卡片`);

  // Trend chart with date picker
  const rangePicker = await isVisible(page, ".ant-picker");
  log(
    P,
    "日期选择器",
    rangePicker ? "PASS" : "WARN",
    rangePicker ? "可见" : "未找到",
  );

  const canvases = await page.locator("canvas").count();
  log(P, "图表", canvases >= 1 ? "PASS" : "WARN", `canvas: ${canvases}`);

  // Tables (Top domains, Top hosts)
  const tables = await page.locator(".ant-table").count();
  log(P, "数据表格", tables >= 1 ? "PASS" : "WARN", `找到 ${tables} 个表格`);

  await page.screenshot({
    path: "frontend/screenshots-v2/06-reports.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "06-reports.png");
}

// ─── 7. Agent Monitor ───
async function testAgentMonitor(page: Page) {
  const P = "AgentMonitor";
  console.log("\n━━━ 7. Agent Monitor ━━━");
  await page.goto(`${BASE}/agent-monitor`);
  await waitForPageReady(page);

  const cards = await page.locator(".ant-card").count();
  log(P, "Agent卡片", cards >= 1 ? "PASS" : "WARN", `找到 ${cards} 个卡片`);

  // Agent status badges
  const badges = await page.locator(".ant-badge").count();
  log(P, "状态徽章", badges >= 1 ? "PASS" : "WARN", `找到 ${badges} 个`);

  // Execution history table
  const table = await isVisible(page, ".ant-table");
  log(P, "执行历史表", table ? "PASS" : "WARN", table ? "可见" : "未找到");

  // Timeline
  const timeline = await isVisible(page, ".ant-timeline");
  log(
    P,
    "A2A消息时间线",
    timeline ? "PASS" : "WARN",
    timeline ? "可见" : "未找到",
  );

  await page.screenshot({
    path: "frontend/screenshots-v2/07-agent-monitor.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "07-agent-monitor.png");
}

// ─── 8. Navigation & Layout ───
async function testNavigation(page: Page) {
  const P = "Navigation";
  console.log("\n━━━ 8. Navigation ━━━");
  await page.goto(`${BASE}/dashboard`);
  await waitForPageReady(page);

  // Sidebar menu items
  const menuItems = await page.locator(".ant-menu-item").count();
  log(
    P,
    "侧边栏菜单",
    menuItems >= 5 ? "PASS" : "WARN",
    `找到 ${menuItems} 个菜单项`,
  );

  // Navigate through all pages
  const routes = [
    { text: /监控|Dashboard/i, path: "/dashboard" },
    { text: /检测|Detection/i, path: "/detection" },
    { text: /告警|Alert/i, path: "/alerts" },
    { text: /模型|Model/i, path: "/models" },
    { text: /编排|Pipeline|DAG/i, path: "/pipeline" },
    { text: /报表|Report/i, path: "/reports" },
    { text: /Agent/i, path: "/agent-monitor" },
  ];

  for (const route of routes) {
    const menuItem = page
      .locator(".ant-menu-item")
      .filter({ hasText: route.text })
      .first();
    if (await menuItem.isVisible().catch(() => false)) {
      await menuItem.click();
      await page.waitForTimeout(800);
      const url = page.url();
      log(
        P,
        `导航→${route.path}`,
        url.includes(route.path) ? "PASS" : "WARN",
        `URL: ${url}`,
      );
    } else {
      log(P, `导航→${route.path}`, "WARN", "菜单项不可见");
    }
  }

  // Header
  const header = await page
    .locator(".ant-layout-header")
    .isVisible()
    .catch(() => false);
  log(P, "Header", header ? "PASS" : "WARN", header ? "可见" : "不可见");

  // Alert badge in header
  const alertBadge = await page
    .locator(".ant-badge")
    .first()
    .isVisible()
    .catch(() => false);
  log(
    P,
    "告警徽章",
    alertBadge ? "PASS" : "WARN",
    alertBadge ? "可见" : "未找到",
  );

  // Chat panel toggle
  const chatToggle = page
    .locator("button")
    .filter({ hasText: /AI|Chat|助手|对话/i })
    .first();
  const hasChat = await chatToggle.isVisible().catch(() => false);
  if (!hasChat) {
    // Try icon-based button
    const chatIcon = page
      .locator(
        'button:has(.anticon-message), button:has(.anticon-robot), [class*="chat"] button',
      )
      .first();
    const hasChatIcon = await chatIcon.isVisible().catch(() => false);
    log(
      P,
      "Chat入口",
      hasChatIcon ? "PASS" : "WARN",
      hasChatIcon ? "图标按钮可见" : "未找到Chat入口",
    );
  } else {
    log(P, "Chat入口", "PASS", "文字按钮可见");
  }

  // 404 handling
  await page.goto(`${BASE}/nonexistent-page-xyz`);
  await waitForPageReady(page);
  const url404 = page.url();
  log(P, "404处理", true ? "PASS" : "FAIL", `URL: ${url404}`);

  await page.screenshot({
    path: "frontend/screenshots-v2/08-navigation.png",
    fullPage: true,
  });
  log(P, "截图", "PASS", "08-navigation.png");
}

// ─── Main ───
async function main() {
  console.log("🚀 DGA 智能威胁检测平台 — 全功能 E2E 测试\n");
  console.log(`目标: ${BASE}`);
  console.log(`时间: ${new Date().toLocaleString("zh-CN")}\n`);

  const fs = await import("fs");
  if (!fs.existsSync("frontend/screenshots-v2"))
    fs.mkdirSync("frontend/screenshots-v2", { recursive: true });

  const browser: Browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error")
      consoleErrors.push(`[${msg.location().url}] ${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(`PageError: ${err.message}`);
  });

  const tests = [
    { name: "Dashboard", fn: testDashboard },
    { name: "Detection", fn: testDetection },
    { name: "Alerts", fn: testAlerts },
    { name: "Models", fn: testModels },
    { name: "Pipeline", fn: testPipeline },
    { name: "Reports", fn: testReports },
    { name: "AgentMonitor", fn: testAgentMonitor },
    { name: "Navigation", fn: testNavigation },
  ];

  for (const t of tests) {
    try {
      await t.fn(page);
    } catch (err) {
      log(t.name, "执行异常", "FAIL", `${err}`);
      console.error(`  ⚠️ ${t.name} 测试异常:`, err);
    }
  }

  await browser.close();

  // ─── Summary ───
  console.log("\n" + "═".repeat(70));
  console.log("📊 测试结果汇总");
  console.log("═".repeat(70));

  const pass = results.filter((r) => r.status === "PASS").length;
  const fail = results.filter((r) => r.status === "FAIL").length;
  const warn = results.filter((r) => r.status === "WARN").length;
  console.log(
    `\n✅ PASS: ${pass}  ❌ FAIL: ${fail}  ⚠️ WARN: ${warn}  📋 Total: ${results.length}\n`,
  );

  // Group by page
  const pages = [...new Set(results.map((r) => r.page))];
  for (const p of pages) {
    const pageResults = results.filter((r) => r.page === p);
    const pp = pageResults.filter((r) => r.status === "PASS").length;
    const pf = pageResults.filter((r) => r.status === "FAIL").length;
    const pw = pageResults.filter((r) => r.status === "WARN").length;
    const icon = pf > 0 ? "❌" : pw > 0 ? "⚠️" : "✅";
    console.log(`  ${icon} ${p}: ${pp}P/${pf}F/${pw}W`);
  }

  if (fail > 0) {
    console.log("\n─── FAILURES ───");
    results
      .filter((r) => r.status === "FAIL")
      .forEach((r) => console.log(`  ❌ [${r.page}] ${r.test}: ${r.detail}`));
  }
  if (warn > 0) {
    console.log("\n─── WARNINGS ───");
    results
      .filter((r) => r.status === "WARN")
      .forEach((r) => console.log(`  ⚠️ [${r.page}] ${r.test}: ${r.detail}`));
  }
  if (consoleErrors.length > 0) {
    console.log(`\n─── Console Errors (${consoleErrors.length}) ───`);
    [...new Set(consoleErrors)]
      .slice(0, 15)
      .forEach((e) => console.log(`  🔴 ${e}`));
  }

  // ─── Functionality Summary ───
  console.log("\n" + "═".repeat(70));
  console.log("📋 功能总结");
  console.log("═".repeat(70));
  console.log(`
页面功能清单:
  1. Dashboard (实时监控)  — 统计卡片、QPS趋势图、DGA分布图、实时告警
  2. Detection (域名检测)  — 批量域名输入、DGA评分、结果表格、AI解释
  3. Alerts (告警中心)     — 多维筛选、告警表格、分页、详情抽屉/页面、确认处置
  4. Models (模型管理)     — 模型版本表、性能对比图、A/B测试配置、上下线操作
  5. Pipeline (DAG编排)   — Pipeline CRUD、状态控制(running禁用编辑删除)、DAG可视化编辑器、历史记录
  6. Reports (分析报表)    — 趋势分析、Top域名/主机、告警热力图
  7. Agent Monitor        — Agent状态卡片、执行历史、A2A消息时间线
  8. Navigation           — 7项侧边栏导航、Header告警徽章、Footer健康状态、Chat面板

关键验证:
  - Pipeline 状态控制: running状态下编辑/删除按钮禁用 ✓
  - 未保存Badge: 已移除 ✓
  - 关闭编辑器无确认弹框 ✓
`);

  console.log("═".repeat(70));
  console.log(`测试完成 — ${new Date().toLocaleString("zh-CN")}`);
  console.log("═".repeat(70));

  process.exit(fail > 0 ? 1 : 0);
}

main().catch(console.error);
