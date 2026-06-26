"""
DGA 平台全功能 Playwright 测试
测试所有页面：Dashboard、Detection、Alerts、Models、Pipeline、Reports、AgentMonitor、Chat
"""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, Page, expect

BASE = "http://localhost:3000"
SCREENSHOT_DIR = str(Path(__file__).parent / "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results: list[dict] = []

def record(page_name: str, test_name: str, status: str, detail: str = ""):
    results.append({"page": page_name, "test": test_name, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"  {icon} [{page_name}] {test_name}: {status} {detail}")


async def screenshot(page: Page, name: str):
    await page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)


async def collect_console_errors(page: Page) -> list[str]:
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    return errors

async def test_dashboard(page: Page):
    """测试 Dashboard 页面"""
    print("\n📊 测试 Dashboard...")
    await page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "01_dashboard")

    # 检查页面是否加载
    try:
        title = await page.title()
        record("Dashboard", "页面加载", "PASS", f"title={title}")
    except Exception as e:
        record("Dashboard", "页面加载", "FAIL", str(e))

    # 检查左侧菜单
    try:
        menu = page.locator(".ant-menu")
        await expect(menu).to_be_visible(timeout=5000)
        record("Dashboard", "侧边栏菜单", "PASS")
    except Exception as e:
        record("Dashboard", "侧边栏菜单", "FAIL", str(e))

    # 检查统计卡片
    try:
        cards = page.locator(".ant-card")
        count = await cards.count()
        record("Dashboard", "统计卡片", "PASS" if count > 0 else "FAIL", f"找到 {count} 个卡片")
    except Exception as e:
        record("Dashboard", "统计卡片", "FAIL", str(e))

    # 检查图表是否渲染
    try:
        await page.wait_for_timeout(1500)
        charts = page.locator("canvas, .echarts-for-react, [_echarts_instance_]")
        chart_count = await charts.count()
        record("Dashboard", "图表渲染", "PASS" if chart_count > 0 else "WARN", f"找到 {chart_count} 个图表元素")
    except Exception as e:
        record("Dashboard", "图表渲染", "WARN", str(e))

    # 检查底部健康状态
    try:
        footer = page.locator(".ant-layout-footer")
        footer_text = await footer.inner_text()
        record("Dashboard", "健康状态栏", "PASS", footer_text.strip()[:80])
    except Exception as e:
        record("Dashboard", "健康状态栏", "FAIL", str(e))

async def test_detection(page: Page):
    """测试域名检测页面"""
    print("\n🔍 测试 Detection...")
    await page.goto(f"{BASE}/detection", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(1500)
    await screenshot(page, "02_detection_initial")

    # 检查页面加载
    try:
        content = await page.content()
        has_input = "input" in content.lower() or "textarea" in content.lower()
        record("Detection", "页面加载", "PASS" if has_input else "WARN", "检测输入区域")
    except Exception as e:
        record("Detection", "页面加载", "FAIL", str(e))

    # 尝试输入域名并检测
    try:
        input_el = page.locator("input, textarea").first
        await input_el.fill("google.com")
        await page.wait_for_timeout(500)
        # 查找提交按钮
        btn = page.locator("button").filter(has_text="检测").or_(
            page.locator("button").filter(has_text="查询")).or_(
            page.locator("button").filter(has_text="提交")).or_(
            page.locator("button[type='submit']")).first
        await btn.click()
        await page.wait_for_timeout(3000)
        await screenshot(page, "02_detection_result_normal")
        record("Detection", "正常域名检测", "PASS", "google.com")
    except Exception as e:
        record("Detection", "正常域名检测", "FAIL", str(e))
        await screenshot(page, "02_detection_result_normal_fail")

    # 测试 DGA 域名
    try:
        input_el = page.locator("input, textarea").first
        await input_el.clear()
        await input_el.fill("asdkjhqwekjh.com")
        btn = page.locator("button").filter(has_text="检测").or_(
            page.locator("button").filter(has_text="查询")).or_(
            page.locator("button").filter(has_text="提交")).or_(
            page.locator("button[type='submit']")).first
        await btn.click()
        await page.wait_for_timeout(3000)
        await screenshot(page, "02_detection_result_dga")
        record("Detection", "DGA域名检测", "PASS", "asdkjhqwekjh.com")
    except Exception as e:
        record("Detection", "DGA域名检测", "FAIL", str(e))

async def test_alerts(page: Page):
    """测试告警中心页面"""
    print("\n🚨 测试 Alerts...")
    await page.goto(f"{BASE}/alerts", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "03_alerts")

    # 检查表格
    try:
        table = page.locator(".ant-table")
        await expect(table).to_be_visible(timeout=5000)
        rows = page.locator(".ant-table-row")
        row_count = await rows.count()
        record("Alerts", "告警列表", "PASS", f"找到 {row_count} 条告警")
    except Exception as e:
        record("Alerts", "告警列表", "WARN", f"表格可能为空: {e}")

    # 检查筛选器
    try:
        filters = page.locator(".ant-select, .ant-input, .ant-picker")
        filter_count = await filters.count()
        record("Alerts", "筛选器", "PASS" if filter_count > 0 else "WARN", f"找到 {filter_count} 个筛选组件")
    except Exception as e:
        record("Alerts", "筛选器", "WARN", str(e))

    # 检查分页
    try:
        pagination = page.locator(".ant-pagination")
        pg_count = await pagination.count()
        record("Alerts", "分页组件", "PASS" if pg_count > 0 else "WARN", f"{'有' if pg_count > 0 else '无'}分页")
    except Exception as e:
        record("Alerts", "分页组件", "WARN", str(e))


async def test_models(page: Page):
    """测试模型管理页面"""
    print("\n🧪 测试 Models...")
    await page.goto(f"{BASE}/models", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "04_models")

    # 检查模型卡片或表格
    try:
        cards = page.locator(".ant-card")
        tables = page.locator(".ant-table")
        card_count = await cards.count()
        table_count = await tables.count()
        has_content = card_count > 0 or table_count > 0
        record("Models", "模型列表", "PASS" if has_content else "WARN",
               f"卡片:{card_count} 表格:{table_count}")
    except Exception as e:
        record("Models", "模型列表", "FAIL", str(e))

    # 检查模型操作按钮
    try:
        buttons = page.locator("button")
        btn_count = await buttons.count()
        record("Models", "操作按钮", "PASS" if btn_count > 0 else "WARN", f"找到 {btn_count} 个按钮")
    except Exception as e:
        record("Models", "操作按钮", "WARN", str(e))

async def test_pipeline(page: Page):
    """测试 DAG 编排页面"""
    print("\n🔗 测试 Pipeline...")
    await page.goto(f"{BASE}/pipeline", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "05_pipeline")

    # 检查 Pipeline 列表或编辑器
    try:
        content = await page.content()
        has_pipeline = "pipeline" in content.lower() or "dag" in content.lower() or "react-flow" in content.lower()
        cards = page.locator(".ant-card, .ant-table, .react-flow")
        count = await cards.count()
        record("Pipeline", "页面加载", "PASS" if count > 0 or has_pipeline else "WARN",
               f"组件数:{count}")
    except Exception as e:
        record("Pipeline", "页面加载", "FAIL", str(e))

    # 检查新建按钮
    try:
        create_btn = page.locator("button").filter(has_text="新建").or_(
            page.locator("button").filter(has_text="创建")).or_(
            page.locator("button").filter(has_text="添加")).first
        await expect(create_btn).to_be_visible(timeout=3000)
        record("Pipeline", "新建按钮", "PASS")
    except Exception as e:
        record("Pipeline", "新建按钮", "WARN", str(e))

    # 检查 Pipeline 操作（启动/停止）
    try:
        action_btns = page.locator("button").filter(has_text="启动").or_(
            page.locator("button").filter(has_text="停止")).or_(
            page.locator("button").filter(has_text="编辑"))
        action_count = await action_btns.count()
        record("Pipeline", "操作按钮", "PASS" if action_count > 0 else "WARN",
               f"找到 {action_count} 个操作按钮")
    except Exception as e:
        record("Pipeline", "操作按钮", "WARN", str(e))


async def test_reports(page: Page):
    """测试分析报表页面"""
    print("\n📈 测试 Reports...")
    await page.goto(f"{BASE}/reports", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "06_reports")

    # 检查图表
    try:
        charts = page.locator("canvas, .echarts-for-react, [_echarts_instance_]")
        chart_count = await charts.count()
        record("Reports", "图表渲染", "PASS" if chart_count > 0 else "WARN",
               f"找到 {chart_count} 个图表")
    except Exception as e:
        record("Reports", "图表渲染", "WARN", str(e))

    # 检查表格（Top 域名/主机）
    try:
        tables = page.locator(".ant-table")
        table_count = await tables.count()
        record("Reports", "数据表格", "PASS" if table_count > 0 else "WARN",
               f"找到 {table_count} 个表格")
    except Exception as e:
        record("Reports", "数据表格", "WARN", str(e))

    # 检查日期选择器
    try:
        picker = page.locator(".ant-picker, .ant-radio-group")
        picker_count = await picker.count()
        record("Reports", "时间筛选", "PASS" if picker_count > 0 else "WARN",
               f"找到 {picker_count} 个筛选组件")
    except Exception as e:
        record("Reports", "时间筛选", "WARN", str(e))

async def test_agent_monitor(page: Page):
    """测试 Agent 监控页面"""
    print("\n🤖 测试 Agent Monitor...")
    await page.goto(f"{BASE}/agent-monitor", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(2000)
    await screenshot(page, "07_agent_monitor")

    # 检查 Agent 状态卡片
    try:
        cards = page.locator(".ant-card")
        count = await cards.count()
        record("AgentMonitor", "Agent卡片", "PASS" if count > 0 else "WARN",
               f"找到 {count} 个卡片")
    except Exception as e:
        record("AgentMonitor", "Agent卡片", "FAIL", str(e))

    # 检查执行历史表格
    try:
        tables = page.locator(".ant-table")
        table_count = await tables.count()
        record("AgentMonitor", "执行历史", "PASS" if table_count > 0 else "WARN",
               f"找到 {table_count} 个表格")
    except Exception as e:
        record("AgentMonitor", "执行历史", "WARN", str(e))


async def test_chat(page: Page):
    """测试 Chat 面板"""
    print("\n💬 测试 Chat Panel...")
    await page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=15000)
    await page.wait_for_timeout(1500)

    # 查找聊天入口按钮
    try:
        chat_trigger = page.locator("[class*='chat'], [class*='Chat'], button").filter(
            has_text="对话").or_(page.locator("button").filter(has_text="问答")).or_(
            page.locator("button").filter(has_text="AI")).or_(
            page.locator("[class*='float']")).first
        await chat_trigger.click(timeout=3000)
        await page.wait_for_timeout(1000)
        await screenshot(page, "08_chat_open")
        record("Chat", "打开面板", "PASS")
    except Exception as e:
        record("Chat", "打开面板", "WARN", f"未找到聊天入口: {e}")
        await screenshot(page, "08_chat_not_found")


async def test_navigation(page: Page):
    """测试导航功能"""
    print("\n🧭 测试导航...")
    pages_to_test = [
        ("/dashboard", "实时监控"),
        ("/detection", "域名检测"),
        ("/alerts", "告警中心"),
        ("/models", "模型管理"),
        ("/pipeline", "DAG 编排"),
        ("/reports", "分析报表"),
        ("/agent-monitor", "Agent 监控"),
    ]
    for path, label in pages_to_test:
        try:
            await page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(800)
            # 检查没有白屏或错误页
            body_text = await page.locator("body").inner_text()
            is_blank = len(body_text.strip()) < 20
            has_error = "cannot read" in body_text.lower() or "undefined" in body_text.lower()
            if is_blank:
                record("Navigation", f"导航到 {label}", "FAIL", "页面空白")
            elif has_error:
                record("Navigation", f"导航到 {label}", "FAIL", "页面有JS错误")
            else:
                record("Navigation", f"导航到 {label}", "PASS")
        except Exception as e:
            record("Navigation", f"导航到 {label}", "FAIL", str(e))

async def test_api_health(page: Page):
    """测试后端 API 连通性"""
    print("\n🏥 测试 API 连通性...")
    api_endpoints = [
        ("GET", "/api/healthz", "健康检查"),
        ("GET", "/api/readyz", "就绪检查"),
        ("GET", "/api/dashboard/stats", "Dashboard统计"),
        ("GET", "/api/alerts?limit=5", "告警列表"),
        ("GET", "/api/models", "模型列表"),
        ("GET", "/api/dag/pipelines", "Pipeline列表"),
        ("GET", "/api/agents/metrics", "Agent指标"),
        ("GET", "/api/reports/stats?days=7", "报表统计"),
    ]
    for method, endpoint, name in api_endpoints:
        try:
            resp = await page.request.get(f"http://localhost:8000{endpoint}")
            status = resp.status
            if status == 200:
                record("API", name, "PASS", f"HTTP {status}")
            elif status < 500:
                body = await resp.text()
                record("API", name, "WARN", f"HTTP {status}: {body[:100]}")
            else:
                record("API", name, "FAIL", f"HTTP {status}")
        except Exception as e:
            record("API", name, "FAIL", str(e))

    # 测试 POST /api/score
    try:
        resp = await page.request.post("http://localhost:8000/api/score", data={
            "domains": ["google.com", "xyzabc123random.com"]
        })
        status = resp.status
        if status == 200:
            body = await resp.json()
            record("API", "域名评分POST", "PASS", f"返回 {len(body.get('results', []))} 个结果")
        else:
            record("API", "域名评分POST", "FAIL", f"HTTP {status}")
    except Exception as e:
        record("API", "域名评分POST", "FAIL", str(e))


async def test_console_errors(page: Page):
    """收集所有页面的控制台错误"""
    print("\n🐛 检查控制台错误...")
    all_errors: list[str] = []
    page.on("console", lambda msg: all_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

    pages = ["/dashboard", "/detection", "/alerts", "/models", "/pipeline", "/reports", "/agent-monitor"]
    for p in pages:
        try:
            await page.goto(f"{BASE}{p}", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass

    if all_errors:
        unique_errors = list(set(all_errors))[:10]
        for err in unique_errors:
            record("Console", "JS错误", "WARN", err[:120])
    else:
        record("Console", "JS错误", "PASS", "无控制台错误")


async def main():
    print("=" * 60)
    print("🚀 DGA 平台全功能测试开始")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        await test_api_health(page)
        await test_navigation(page)
        await test_dashboard(page)
        await test_detection(page)
        await test_alerts(page)
        await test_models(page)
        await test_pipeline(page)
        await test_reports(page)
        await test_agent_monitor(page)
        await test_chat(page)
        await test_console_errors(page)

        await browser.close()

    # 输出汇总
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    print(f"✅ PASS: {pass_count}  ❌ FAIL: {fail_count}  ⚠️ WARN: {warn_count}")
    print(f"总计: {len(results)} 项测试\n")

    if fail_count > 0:
        print("❌ 失败项:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  - [{r['page']}] {r['test']}: {r['detail']}")

    if warn_count > 0:
        print("\n⚠️ 警告项:")
        for r in results:
            if r["status"] == "WARN":
                print(f"  - [{r['page']}] {r['test']}: {r['detail']}")

    # 保存 JSON 报告
    with open(f"{SCREENSHOT_DIR}/report.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📸 截图保存在: {SCREENSHOT_DIR}/")
    print(f"📄 报告保存在: {SCREENSHOT_DIR}/report.json")


if __name__ == "__main__":
    asyncio.run(main())
