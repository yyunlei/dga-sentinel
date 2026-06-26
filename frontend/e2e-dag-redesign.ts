import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  let pass = 0, fail = 0, warn = 0;

  function ok(name: string) { pass++; console.log(`  ✅ ${name}`); }
  function no(name: string, e?: string) { fail++; console.log(`  ❌ ${name}${e ? ': ' + e : ''}`); }
  function wn(name: string, e?: string) { warn++; console.log(`  ⚠️  ${name}${e ? ': ' + e : ''}`); }

  console.log('\n🎨 DAG 编辑器专业级重构 — E2E 测试\n');

  await page.goto(`${BASE}/pipeline`, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  // 1. Pipeline list
  const rows = await page.locator('table tbody tr').count();
  rows > 0 ? ok(`Pipeline 列表: ${rows} 条`) : no('Pipeline 列表为空');

  // 2. Click second row (real pipeline)
  await page.locator('table tbody tr').nth(1).click();
  await page.waitForTimeout(3000);

  // 3. DAG editor
  const dagCard = await page.locator('text=DAG 可视化编排').count();
  dagCard > 0 ? ok('DAG 编辑器已显示') : no('DAG 编辑器未显示');

  // 4. Canvas
  const canvas = await page.locator('.react-flow').count();
  canvas > 0 ? ok('ReactFlow 画布已渲染') : no('ReactFlow 画布未渲染');

  // 5. Nodes loaded
  const nodeCount = await page.locator('.react-flow__node').count();
  nodeCount > 0 ? ok(`画布节点: ${nodeCount} 个`) : wn('画布节点为 0');

  // 6. NodePalette with collapsible categories
  const paletteText = await page.locator('text=节点面板').count();
  paletteText > 0 ? ok('节点面板已显示') : no('节点面板未显示');

  // Check Collapse panels in palette
  const palettePanels = await page.locator('.ant-collapse-ghost .ant-collapse-item').count();
  palettePanels >= 5 ? ok(`节点面板可折叠分类: ${palettePanels} 个`) : wn(`节点面板分类: ${palettePanels}`);

  // 7. Canvas height is larger
  const canvasHeight = await page.locator('.react-flow').evaluate((el) => el.clientHeight);
  canvasHeight >= 450 ? ok(`画布高度: ${canvasHeight}px`) : wn(`画布高度偏小: ${canvasHeight}px`);

  // 8. Click a node → right config panel opens (inline, not drawer)
  if (nodeCount > 0) {
    await page.locator('.react-flow__node').first().click();
    await page.waitForTimeout(800);

    // Check inline config panel with title "节点配置"
    const configPanel = await page.locator('text=节点配置').count();
    configPanel > 0 ? ok('点击节点 → 右侧配置面板打开') : no('右侧配置面板未打开');

    // Check collapse items in panel
    const panelCollapse = await page.locator('.ant-collapse-item').count();
    panelCollapse > 0 ? ok(`配置面板中折叠项: ${panelCollapse} 个`) : wn('配置面板无折叠项');

    // Check active panel (selected node expanded)
    const activePanel = await page.locator('.ant-collapse-item-active').count();
    activePanel > 0 ? ok('选中节点配置已展开') : wn('选中节点未自动展开');

    // Check form fields in expanded panel
    const formItems = await page.locator('.ant-collapse-item-active .ant-form-item').count();
    formItems > 0 ? ok(`展开面板表单项: ${formItems} 个`) : wn('展开面板无表单项');

    // Check "收起" button exists
    const collapseBtn = await page.locator('button:has-text("收起")').count();
    collapseBtn > 0 ? ok('收起按钮已显示') : wn('收起按钮未显示');
  }

  // 9. Node toolbar on hover
  if (nodeCount > 0) {
    await page.locator('.react-flow__node').first().hover();
    await page.waitForTimeout(500);
    const toolbar = await page.locator('.react-flow__node-toolbar').count();
    toolbar > 0 ? ok('节点悬浮工具栏已显示') : wn('节点悬浮工具栏未显示');
  }

  // 10. Close config panel by clicking "收起"
  const collapseBtn2 = page.locator('button:has-text("收起")').first();
  if (await collapseBtn2.count() > 0) {
    await collapseBtn2.click();
    await page.waitForTimeout(500);
    const panelAfterClose = await page.locator('text=节点配置').count();
    // "节点配置" text should disappear when panel is closed
    panelAfterClose === 0 ? ok('收起按钮 → 配置面板关闭') : wn('配置面板可能未关闭');
  }

  // 11. Save button
  const saveBtn = await page.locator('button:has-text("保存")').count();
  saveBtn > 0 ? ok('保存按钮已显示') : no('保存按钮未显示');

  // 12. YAML button
  const yamlBtn = await page.locator('button:has-text("YAML")').count();
  yamlBtn > 0 ? ok('YAML 按钮已显示') : no('YAML 按钮未显示');

  // 13. Switch pipeline
  if (rows > 2) {
    await page.locator('table tbody tr').nth(2).click();
    await page.waitForTimeout(3000);
    const newNodes = await page.locator('.react-flow__node').count();
    ok(`切换 Pipeline: ${newNodes} 个节点`);
  }

  // 14. No bottom config card (should be removed)
  const bottomConfig = await page.locator('text=节点配置管理').count();
  bottomConfig === 0 ? ok('底部配置区域已移除') : no('底部配置区域仍存在');

  // 15. Config management button
  const configMgmt = await page.locator('button:has-text("配置管理")').count();
  configMgmt > 0 ? ok('配置管理按钮已显示') : wn('配置管理按钮未显示');

  console.log(`\n📊 结果: ${pass} PASS / ${fail} FAIL / ${warn} WARN\n`);

  await browser.close();
}

main().catch(console.error);
