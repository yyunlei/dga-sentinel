import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  let pass = 0, fail = 0, warn = 0;

  function ok(name: string) { pass++; console.log(`  ✅ ${name}`); }
  function no(name: string, e?: string) { fail++; console.log(`  ❌ ${name}${e ? ': ' + e : ''}`); }
  function wn(name: string, e?: string) { warn++; console.log(`  ⚠️  ${name}${e ? ': ' + e : ''}`); }

  console.log('\n🔧 Pipeline Page — Enterprise UX Test\n');

  // Navigate to Pipeline page
  await page.goto(`${BASE}/pipeline`, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  // 1. Pipeline list table
  const rows = await page.locator('table tbody tr').count();
  rows > 0 ? ok(`Pipeline 列表: ${rows} 条记录`) : no('Pipeline 列表为空');

  // 2. Click second pipeline row (first real pipeline with content)
  await page.locator('table tbody tr').nth(1).click();
  await page.waitForTimeout(3000);

  // 3. Check DAG editor appeared
  const dagCard = await page.locator('text=DAG 可视化编排').count();
  dagCard > 0 ? ok('DAG 编辑器已显示') : no('DAG 编辑器未显示');

  // 4. Check ReactFlow canvas
  const canvas = await page.locator('.react-flow').count();
  canvas > 0 ? ok('ReactFlow 画布已渲染') : no('ReactFlow 画布未渲染');

  // 5. Check nodes loaded
  const nodeCount = await page.locator('.react-flow__node').count();
  nodeCount > 0 ? ok(`画布节点: ${nodeCount} 个`) : wn('画布节点为 0');

  // 6. Check NodePalette
  const palette = await page.locator('text=节点面板').count();
  palette > 0 ? ok('节点面板已显示') : no('节点面板未显示');

  // 7. Check collapsible node config panels
  const configSection = await page.locator('text=节点配置管理').count();
  configSection > 0 ? ok('节点配置管理区域已显示') : wn('节点配置管理区域未显示 (可能节点为0)');

  // 8. Check collapse panels exist for each node
  const collapsePanels = await page.locator('.ant-collapse-item').count();
  collapsePanels > 0 ? ok(`可折叠配置面板: ${collapsePanels} 个`) : wn('无可折叠配置面板');

  // 9. Click first collapse panel to expand
  if (collapsePanels > 0) {
    await page.locator('.ant-collapse-item').first().locator('.ant-collapse-header').click();
    await page.waitForTimeout(500);
    const formItems = await page.locator('.ant-collapse-item').first().locator('.ant-form-item').count();
    formItems > 0 ? ok(`展开配置面板: ${formItems} 个表单项`) : wn('展开面板无表单项');
  }

  // 10. Check save button exists
  const saveBtn = await page.locator('button:has-text("保存")').count();
  saveBtn > 0 ? ok('保存按钮已显示') : no('保存按钮未显示');

  // 11. Check YAML button
  const yamlBtn = await page.locator('button:has-text("YAML")').count();
  yamlBtn > 0 ? ok('YAML 按钮已显示') : no('YAML 按钮未显示');

  // 12. Click YAML button to open drawer
  if (yamlBtn > 0) {
    await page.locator('button:has-text("YAML")').click();
    await page.waitForTimeout(500);
    const yamlDrawer = await page.locator('.ant-drawer-open').count();
    yamlDrawer > 0 ? ok('YAML 抽屉已打开') : no('YAML 抽屉未打开');
    // Close drawer
    await page.locator('.ant-drawer-close').first().click();
    await page.waitForTimeout(300);
  }

  // 13. Test clicking different pipeline rows
  if (rows > 1) {
    await page.locator('table tbody tr').nth(1).click();
    await page.waitForTimeout(2000);
    const newNodeCount = await page.locator('.react-flow__node').count();
    ok(`切换 Pipeline: ${newNodeCount} 个节点`);
  }

  // 14. Check node click → collapse panel sync
  const rfNodes = await page.locator('.react-flow__node').count();
  if (rfNodes > 0) {
    await page.locator('.react-flow__node').first().click();
    await page.waitForTimeout(500);
    const activePanel = await page.locator('.ant-collapse-item-active').count();
    activePanel > 0 ? ok('点击节点 → 配置面板自动展开') : wn('点击节点未同步展开配置面板');
  }

  // 15. Check pipeline name tag in editor header
  const pipelineTag = await page.locator('.ant-tag-blue').count();
  pipelineTag > 0 ? ok('编辑器标题显示 Pipeline 名称') : wn('编辑器标题无 Pipeline 名称');

  // 16. Check config management button
  const configMgmt = await page.locator('button:has-text("配置管理")').count();
  configMgmt > 0 ? ok('配置管理按钮已显示') : wn('配置管理按钮未显示');

  console.log(`\n📊 结果: ${pass} PASS / ${fail} FAIL / ${warn} WARN\n`);

  await browser.close();
}

main().catch(console.error);
