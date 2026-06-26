import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  let pass = 0, fail = 0, warn = 0;

  function ok(name: string) { pass++; console.log(`  ✅ ${name}`); }
  function no(name: string, e?: string) { fail++; console.log(`  ❌ ${name}${e ? ': ' + e : ''}`); }
  function wn(name: string, e?: string) { warn++; console.log(`  ⚠️  ${name}${e ? ': ' + e : ''}`); }

  console.log('\n🔧 Pipeline CRUD — E2E 测试\n');

  await page.goto(`${BASE}/pipeline`, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  // 1. Check "新建 Pipeline" button exists
  const createBtn = await page.locator('button:has-text("新建 Pipeline")').count();
  createBtn > 0 ? ok('新建 Pipeline 按钮已显示') : no('新建 Pipeline 按钮未显示');

  // 2. Check empty state guidance
  const emptyGuide = await page.locator('text=请从列表中选择一个 Pipeline').count();
  emptyGuide > 0 ? ok('空状态引导已显示') : wn('空状态引导未显示');

  // 3. Click "新建 Pipeline" → modal opens
  await page.locator('button:has-text("新建 Pipeline")').first().click();
  await page.waitForTimeout(500);
  const modal = await page.locator('.ant-modal-content').count();
  modal > 0 ? ok('新建 Modal 已打开') : no('新建 Modal 未打开');

  // 4. Check modal has name input and mode select
  const nameInput = await page.locator('.ant-modal-content input').count();
  nameInput > 0 ? ok('名称输入框已显示') : no('名称输入框未显示');

  const modeSelect = await page.locator('.ant-modal-content .ant-select').count();
  modeSelect > 0 ? ok('模式选择器已显示') : no('模式选择器未显示');

  // 5. Input name and create
  await page.getByRole('textbox', { name: '例如：DGA 实时检测流水线' }).fill('E2E 测试流水线');
  await page.waitForTimeout(200);
  // Click the OK button in the modal footer
  await page.locator('.ant-modal-footer .ant-btn-primary').click();
  await page.waitForTimeout(3000);

  // 6. Check modal closed and pipeline created
  await page.waitForTimeout(1000);
  const modalAfter = await page.locator('.ant-modal-wrap:not([style*="display: none"]) .ant-modal-content').count();
  modalAfter === 0 ? ok('创建后 Modal 已关闭') : wn('Modal 未关闭');

  // Close modal if still open
  if (modalAfter > 0) {
    const cancelBtn = page.locator('.ant-modal-footer .ant-btn-default');
    if (await cancelBtn.count() > 0) await cancelBtn.click();
    await page.waitForTimeout(500);
  }

  // 7. Check new pipeline in list
  const newRow = await page.locator('text=E2E 测试流水线').count();
  newRow > 0 ? ok('新 Pipeline 出现在列表中') : no('新 Pipeline 未出现在列表');

  // 8. Check DAG editor appeared (auto-selected)
  const dagEditor = await page.locator('text=DAG 可视化编排').count();
  dagEditor > 0 ? ok('DAG 编辑器已自动打开') : no('DAG 编辑器未自动打开');

  // 9. Check empty canvas (new pipeline has no nodes)
  const nodeCount = await page.locator('.react-flow__node').count();
  nodeCount === 0 ? ok('新 Pipeline 画布为空') : wn(`新 Pipeline 有 ${nodeCount} 个节点`);

  // 10. Check delete button exists in table
  const deleteBtn = await page.locator('table .anticon-delete').count();
  deleteBtn > 0 ? ok(`删除按钮已显示: ${deleteBtn} 个`) : no('删除按钮未显示');

  // 11. Delete the test pipeline
  const testRow = page.locator('table tbody tr').filter({ hasText: 'E2E 测试流水线' });
  const testRowCount = await testRow.count();
  if (testRowCount > 0) {
    await testRow.locator('.anticon-delete').first().click({ force: true });
    await page.waitForTimeout(1000);

    // Confirm delete modal (Modal.confirm uses ant-modal-confirm)
    const confirmModal = page.locator('.ant-modal-confirm-btns .ant-btn-dangerous');
    const confirmCount = await confirmModal.count();
    confirmCount > 0 ? ok('删除确认弹窗已显示') : no('删除确认弹窗未显示');

    if (confirmCount > 0) {
      await confirmModal.click();
      await page.waitForTimeout(2000);

      // Check pipeline removed from list
      const removedRow = await page.locator('table tbody tr').filter({ hasText: 'E2E 测试流水线' }).count();
      removedRow === 0 ? ok('Pipeline 已从列表中删除') : no('Pipeline 未被删除');

      // Check editor cleared
      const editorAfterDelete = await page.locator('text=DAG 可视化编排').count();
      editorAfterDelete === 0 ? ok('编辑器已清空') : wn('编辑器未清空');
    }
  } else {
    no('未找到测试 Pipeline 行');
  }

  // 12. Check empty state returned
  const emptyAfter = await page.locator('text=请从列表中选择一个 Pipeline').count();
  emptyAfter > 0 ? ok('删除后空状态引导已恢复') : wn('空状态引导未恢复');

  console.log(`\n📊 结果: ${pass} PASS / ${fail} FAIL / ${warn} WARN\n`);

  await browser.close();
}

main().catch(console.error);
