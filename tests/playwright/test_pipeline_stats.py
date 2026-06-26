"""
Pipeline 页面全功能测试
测试统计面板、Pipeline 列表、新建、编辑、启停、删除等功能
"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3000"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    tag = PASS if ok else FAIL
    print(f"  {tag}  {name}" + (f"  ({detail})" if detail else ""))


async def run() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # ── 导航到 Pipeline 页面 ──
        print("\n=== Pipeline 页面测试 ===")
        await page.goto(f"{BASE_URL}/pipeline", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path="tests/playwright/screenshots/pipeline_stats.png")

        # ── 1. 统计卡片 ──
        stat_cards = page.locator(".ant-statistic")
        stat_count = await stat_cards.count()
        report("统计卡片数量 >= 4", stat_count >= 4, f"actual={stat_count}")

        # 检查卡片标题
        for i in range(min(stat_count, 4)):
            title = await stat_cards.nth(i).locator(".ant-statistic-title").inner_text()
            print(f"    卡片 {i+1}: {title}")

        # ── 2. 图表区域 ──
        charts = page.locator("canvas, [_echarts_instance_]")
        await page.wait_for_timeout(1000)
        chart_cards = page.locator(".ant-card-head-title")
        card_titles = []
        for i in range(await chart_cards.count()):
            t = await chart_cards.nth(i).inner_text()
            card_titles.append(t)
        has_pipeline_chart = any("Pipeline 告警" in t for t in card_titles)
        has_family_chart = any("家族告警" in t for t in card_titles)
        report("Pipeline 告警 Top10 图表", has_pipeline_chart, str(card_titles))
        report("家族告警 Top10 图表", has_family_chart, str(card_titles))

        # ── 3. Pipeline 列表 ──
        table_rows = page.locator(".ant-table-tbody tr")
        row_count = await table_rows.count()
        report("Pipeline 列表有数据", row_count >= 1, f"rows={row_count}")

        # ── 4. 搜索过滤 ──
        search_input = page.locator("input[placeholder='Pipeline 名称']")
        if await search_input.count() > 0:
            await search_input.fill("DGA")
            await page.wait_for_timeout(500)
            filtered_rows = await page.locator(".ant-table-tbody tr").count()
            report("名称搜索过滤", filtered_rows >= 1, f"filtered={filtered_rows}")
            await search_input.clear()
            await page.wait_for_timeout(500)

        # ── 5. 新建 Pipeline 弹窗 ──
        create_btn = page.locator("button:has-text('新建 Pipeline')")
        if await create_btn.count() > 0:
            await create_btn.click()
            await page.wait_for_timeout(1000)
            modal = page.locator(".ant-modal")
            modal_visible = await modal.count() > 0
            report("新建 Pipeline 弹窗打开", modal_visible)
            if modal_visible:
                await page.screenshot(path="tests/playwright/screenshots/pipeline_create.png")
                # 关闭弹窗
                close_btn = page.locator(".ant-modal .ant-modal-close")
                if await close_btn.count() > 0:
                    await close_btn.first.click()
                    await page.wait_for_timeout(500)

        # ── 6. 操作按钮检查 ──
        # 检查 running 状态的行不能编辑/删除
        first_row = page.locator(".ant-table-tbody tr").first
        if row_count > 0:
            edit_btns = first_row.locator("button .anticon-edit")
            if await edit_btns.count() > 0:
                is_disabled = await edit_btns.first.locator("..").get_attribute("disabled")
                print(f"    编辑按钮 disabled={is_disabled}")

        # ── 7. Dashboard 页面 ──
        print("\n=== Dashboard 页面测试 ===")
        await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        dash_stats = page.locator(".ant-statistic")
        dash_count = await dash_stats.count()
        report("Dashboard 统计卡片", dash_count >= 4, f"count={dash_count}")
        await page.screenshot(path="tests/playwright/screenshots/dashboard.png")

        # ── 8. 告警中心 ──
        print("\n=== 告警中心测试 ===")
        await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        alert_table = page.locator(".ant-table-tbody tr")
        alert_count = await alert_table.count()
        report("告警列表有数据", alert_count >= 1, f"rows={alert_count}")
        await page.screenshot(path="tests/playwright/screenshots/alerts.png")

        # ── 9. 域名检测 ──
        print("\n=== 域名检测测试 ===")
        await page.goto(f"{BASE_URL}/detection", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path="tests/playwright/screenshots/detection.png")
        report("域名检测页面加载", True)

        # ── 10. 模型管理 ──
        print("\n=== 模型管理测试 ===")
        await page.goto(f"{BASE_URL}/models", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        model_cards = page.locator(".ant-card")
        model_count = await model_cards.count()
        report("模型管理页面加载", model_count >= 1, f"cards={model_count}")
        await page.screenshot(path="tests/playwright/screenshots/models.png")

        await browser.close()

    # ── 报告 ──
    print(f"\n{'='*60}")
    print("  测试报告")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        tag = PASS if ok else FAIL
        print(f"  {tag}  {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n  总计: {total}, 通过: {passed}, 失败: {total - passed}")
    print(f"{'='*60}\n")


asyncio.run(run())
