"""
DGA 平台全功能自动化测试
测试所有页面功能：Dashboard、域名检测、告警中心、模型管理、Pipeline 管理
"""
import asyncio
import time
from playwright.async_api import async_playwright, expect

BASE_URL = "http://localhost:3000"
TIMEOUT = 15000


async def test_dashboard(page):
    """测试 Dashboard 页面"""
    print("\n=== 测试 Dashboard ===")
    await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    # 检查四个统计卡片
    cards = page.locator(".ant-statistic")
    count = await cards.count()
    print(f"  统计卡片数量: {count}")
    assert count >= 4, f"期望至少 4 个统计卡片，实际 {count}"

    # 检查实时告警流 Tabs
    tabs = page.locator(".ant-tabs-tab")
    tab_count = await tabs.count()
    print(f"  告警 Tab 数量: {tab_count}")
    assert tab_count >= 2, f"期望至少 2 个 Tab，实际 {tab_count}"

    # 检查 Tab 文本
    tab_texts = []
    for i in range(tab_count):
        text = await tabs.nth(i).inner_text()
        tab_texts.append(text)
    print(f"  Tab 标签: {tab_texts}")
    assert any("实时告警" in t for t in tab_texts), "缺少'实时告警' Tab"
    assert any("域名监测" in t for t in tab_texts), "缺少'域名监测告警' Tab"

    # 点击第二个 Tab
    await tabs.nth(1).click()
    await page.wait_for_timeout(500)
    print("  切换到域名监测告警 Tab: OK")

    # 截图
    await page.screenshot(path="tests/playwright/screenshots/dashboard.png")
    print("  Dashboard 测试通过 ✓")


async def test_detection(page):
    """测试域名检测页面"""
    print("\n=== 测试域名检测 ===")
    await page.goto(f"{BASE_URL}/detection", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    # 输入域名
    textarea = page.locator("textarea")
    await textarea.fill("google.com\nbaidu.com\nxyz123abc.top\nqwerty789.xyz")
    print("  输入域名: OK")

    # 点击检测
    detect_btn = page.get_by_role("button", name="检测")
    await detect_btn.click()
    await page.wait_for_timeout(5000)

    # 检查结果表格
    rows = page.locator(".ant-table-tbody tr")
    row_count = await rows.count()
    print(f"  检测结果行数: {row_count}")

    await page.screenshot(path="tests/playwright/screenshots/detection.png")
    print("  域名检测测试通过 ✓")


async def test_alerts(page):
    """测试告警中心页面"""
    print("\n=== 测试告警中心 ===")
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    # 检查筛选区域存在
    domain_input = page.locator("input[placeholder='域名']")
    assert await domain_input.count() > 0, "缺少域名筛选输入框"
    print("  域名筛选框: OK")

    src_ip_input = page.locator("input[placeholder='源 IP']")
    assert await src_ip_input.count() > 0, "缺少源 IP 筛选输入框"
    print("  源 IP 筛选框: OK")

    # 检查严重度、家族、状态下拉框
    selects = page.locator(".ant-select")
    select_count = await selects.count()
    print(f"  下拉筛选框数量: {select_count}")
    assert select_count >= 3, f"期望至少 3 个下拉框，实际 {select_count}"

    # 检查查询和重置按钮
    search_btn = page.get_by_role("button", name="查询")
    assert await search_btn.count() > 0, "缺少查询按钮"
    reset_btn = page.get_by_role("button", name="重置")
    assert await reset_btn.count() > 0, "缺少重置按钮"
    print("  查询/重置按钮: OK")

    # 点击查询
    await search_btn.click()
    await page.wait_for_timeout(2000)

    # 检查表格
    table = page.locator(".ant-table")
    assert await table.count() > 0, "缺少告警表格"
    print("  告警表格: OK")

    # 检查表格列头
    headers = page.locator(".ant-table-thead th")
    header_texts = []
    for i in range(await headers.count()):
        text = await headers.nth(i).inner_text()
        if text.strip():
            header_texts.append(text.strip())
    print(f"  表格列: {header_texts}")

    await page.screenshot(path="tests/playwright/screenshots/alerts.png")
    print("  告警中心测试通过 ✓")


async def test_alert_badge(page):
    """测试右上角告警 badge"""
    print("\n=== 测试告警 Badge ===")
    await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    badge = page.locator(".ant-badge")
    badge_count = await badge.count()
    print(f"  Badge 数量: {badge_count}")
    assert badge_count > 0, "缺少告警 Badge"

    # 检查 badge 不显示 99+
    badge_text = await badge.first.inner_text()
    print(f"  Badge 文本: '{badge_text}'")
    if badge_text.strip():
        assert "99+" not in badge_text, "Badge 仍显示 99+"
    print("  告警 Badge 测试通过 ✓")


async def test_models(page):
    """测试模型管理页面"""
    print("\n=== 测试模型管理 ===")
    await page.goto(f"{BASE_URL}/models", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    # 检查模型表格
    table = page.locator(".ant-table")
    assert await table.count() > 0, "缺少模型表格"

    rows = page.locator(".ant-table-tbody tr")
    row_count = await rows.count()
    print(f"  模型行数: {row_count}")
    assert row_count > 0, "模型列表为空"

    # 测试下线按钮（找 production 状态的行）
    offline_btn = page.locator("button").filter(has_text="下线").first
    if await offline_btn.count() > 0:
        await offline_btn.click()
        await page.wait_for_timeout(500)
        # 确认弹窗
        confirm_btn = page.locator(".ant-modal-confirm-btns .ant-btn-primary")
        if await confirm_btn.count() > 0:
            await confirm_btn.click()
            await page.wait_for_timeout(2000)
            print("  下线操作: OK")
        else:
            print("  下线确认弹窗未出现")
    else:
        print("  无可下线模型，跳过")

    # 测试上线按钮
    await page.wait_for_timeout(1000)
    deploy_btn = page.locator("button").filter(has_text="上线").first
    if await deploy_btn.count() > 0:
        await deploy_btn.click()
        await page.wait_for_timeout(500)
        confirm_btn = page.locator(".ant-modal-confirm-btns .ant-btn-primary")
        if await confirm_btn.count() > 0:
            await confirm_btn.click()
            await page.wait_for_timeout(2000)
            print("  上线操作: OK")
    else:
        print("  无可上线模型，跳过")

    # 测试回滚按钮
    await page.wait_for_timeout(1000)
    rollback_btn = page.locator("button").filter(has_text="回滚").first
    if await rollback_btn.count() > 0:
        await rollback_btn.click()
        await page.wait_for_timeout(1000)
        # 检查回滚弹窗
        modal = page.locator(".ant-modal")
        if await modal.count() > 0:
            print("  回滚弹窗: OK")
            # 关闭弹窗
            cancel_btn = page.locator(".ant-modal .ant-btn").filter(has_text="取消").first
            if await cancel_btn.count() > 0:
                await cancel_btn.click()
    else:
        print("  无可回滚模型，跳过")

    await page.screenshot(path="tests/playwright/screenshots/models.png")
    print("  模型管理测试通过 ✓")


async def test_pipeline(page):
    """测试 Pipeline 管理页面"""
    print("\n=== 测试 Pipeline 管理 ===")
    await page.goto(f"{BASE_URL}/pipeline", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    # 检查 Pipeline 列表
    table = page.locator(".ant-table")
    assert await table.count() > 0, "缺少 Pipeline 表格"

    rows = page.locator(".ant-table-tbody tr")
    row_count = await rows.count()
    print(f"  Pipeline 行数: {row_count}")

    # 测试新建 Pipeline
    create_btn = page.get_by_role("button", name="新建 Pipeline")
    if await create_btn.count() > 0:
        await create_btn.first.click()
        await page.wait_for_timeout(1000)
        modal = page.locator(".ant-modal")
        if await modal.count() > 0:
            name_input = modal.locator("input").first
            await name_input.fill("测试 Pipeline")
            await page.wait_for_timeout(500)
            # 点击创建（antd Modal 的 OK 按钮）
            ok_btn = modal.locator(".ant-modal-footer .ant-btn-primary")
            if await ok_btn.count() > 0:
                await ok_btn.click()
                await page.wait_for_timeout(3000)
                print("  新建 Pipeline: OK")
            else:
                cancel_btn = modal.locator(".ant-modal-footer .ant-btn").first
                if await cancel_btn.count() > 0:
                    await cancel_btn.click()
                print("  新建弹窗 OK 按钮未找到")
    else:
        print("  新建按钮未找到")

    # 测试删除 Pipeline（删除刚创建的）
    await page.wait_for_timeout(1000)
    delete_btns = page.locator("[data-icon='delete']")
    delete_count = await delete_btns.count()
    print(f"  删除按钮数量: {delete_count}")
    if delete_count > 0:
        await delete_btns.last.click(force=True)
        await page.wait_for_timeout(1000)
        confirm = page.locator(".ant-modal-confirm-btns .ant-btn-dangerous")
        if await confirm.count() > 0:
            await confirm.click()
            await page.wait_for_timeout(2000)
            print("  删除 Pipeline: OK")
        else:
            print("  删除确认弹窗未出现")

    # 测试加载 Pipeline 到编辑器
    await page.wait_for_timeout(1000)
    rows = page.locator(".ant-table-tbody tr:not(.ant-table-placeholder)")
    row_count = await rows.count()
    if row_count > 0:
        # 点击 Pipeline 名称链接
        first_link = rows.first.locator("a").first
        if await first_link.count() > 0:
            await first_link.click()
        else:
            await rows.first.click(force=True)
        await page.wait_for_timeout(3000)
        # 检查 DAG 编辑器出现
        dag_card = page.locator("text=DAG 可视化编排")
        if await dag_card.count() > 0:
            print("  加载 DAG 编辑器: OK")

            # 测试保存按钮
            save_btn = page.get_by_role("button", name="保存")
            if await save_btn.count() > 0:
                is_disabled = await save_btn.is_disabled()
                print(f"  保存按钮状态: {'禁用(无修改)' if is_disabled else '可用'}")
        else:
            print("  DAG 编辑器未出现")
    else:
        print("  Pipeline 列表为空，跳过编辑器测试")

    await page.screenshot(path="tests/playwright/screenshots/pipeline.png")
    print("  Pipeline 管理测试通过 ✓")


async def test_reports(page):
    """测试分析报表页面"""
    print("\n=== 测试分析报表 ===")
    await page.goto(f"{BASE_URL}/reports", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    cards = page.locator(".ant-card")
    card_count = await cards.count()
    print(f"  卡片数量: {card_count}")

    await page.screenshot(path="tests/playwright/screenshots/reports.png")
    print("  分析报表测试通过 ✓")


async def main():
    print("=" * 60)
    print("DGA 平台全功能自动化测试")
    print("=" * 60)

    # 确保截图目录存在
    import os
    os.makedirs("tests/playwright/screenshots", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT)

        results = {}
        tests = [
            ("Dashboard", test_dashboard),
            ("告警 Badge", test_alert_badge),
            ("域名检测", test_detection),
            ("告警中心", test_alerts),
            ("模型管理", test_models),
            ("Pipeline", test_pipeline),
            ("分析报表", test_reports),
        ]

        for name, test_fn in tests:
            try:
                await test_fn(page)
                results[name] = "PASS ✓"
            except Exception as e:
                results[name] = f"FAIL ✗ — {e}"
                await page.screenshot(path=f"tests/playwright/screenshots/error_{name}.png")
                print(f"  {name} 测试失败: {e}")

        await browser.close()

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    passed = sum(1 for v in results.values() if "PASS" in v)
    total = len(results)
    for name, result in results.items():
        print(f"  {name}: {result}")
    print(f"\n  总计: {passed}/{total} 通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
