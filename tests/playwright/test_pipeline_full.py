"""
Pipeline 页面全功能测试 — Playwright
测试范围：列表加载、Pipeline CRUD、DAG 编辑器、节点配置、YAML、历史记录
"""
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:3000"
TIMEOUT = 10_000
SCREENSHOT_DIR = Path(__file__).parent


def test_pipeline_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(TIMEOUT)
        results = []

        def record(name: str, ok: bool, detail: str = ""):
            status = "PASS" if ok else "FAIL"
            results.append(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
            print(results[-1])

        # ── 1. 页面加载 ──────────────────────────────────────
        page.goto(f"{BASE}/pipeline", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 检查 Pipeline 列表卡片
        list_card = page.locator("text=Pipeline 列表")
        try:
            expect(list_card).to_be_visible(timeout=5000)
            record("页面加载 — Pipeline 列表卡片", True)
        except Exception as e:
            record("页面加载 — Pipeline 列表卡片", False, str(e))

        # ── 2. 列表数据 ──────────────────────────────────────
        page.wait_for_timeout(1500)
        rows = page.locator(".ant-table-tbody tr")
        row_count = rows.count()
        record("列表数据加载", row_count >= 4, f"共 {row_count} 行")

        # 检查种子 pipeline 是否存在
        for name in ["DGA 实时检测流水线", "DGA 批量回溯分析", "C2 域名实时检测", "DNS 隧道检测"]:
            visible = page.locator(f"text={name}").count() > 0
            record(f"种子 Pipeline「{name}」", visible)

        # 检查状态标签
        running_tags = page.locator(".ant-tag-green")
        stopped_tags = page.locator(".ant-tag-red")
        record("状态标签 — running", running_tags.count() >= 1, f"{running_tags.count()} 个 running")
        record("状态标签 — stopped", stopped_tags.count() >= 1, f"{stopped_tags.count()} 个 stopped")

        # ── 3. 搜索过滤 ──────────────────────────────────────
        search_input = page.locator("input[placeholder='Pipeline 名称']")
        search_input.fill("DGA")
        page.wait_for_timeout(500)
        filtered_rows = page.locator(".ant-table-tbody tr")
        record("搜索过滤 — 输入 DGA", filtered_rows.count() >= 2, f"过滤后 {filtered_rows.count()} 行")
        search_input.clear()
        page.wait_for_timeout(500)

        # ── 4. 加载 Pipeline 到编辑器 ────────────────────────
        page.locator("text=DGA 实时检测流水线").first.click()
        page.wait_for_timeout(2000)

        # 检查编辑器区域出现
        editor_card = page.locator("text=DAG 可视化编排")
        try:
            expect(editor_card).to_be_visible(timeout=5000)
            record("加载 Pipeline — 编辑器区域", True)
        except Exception as e:
            record("加载 Pipeline — 编辑器区域", False, str(e))

        # 检查节点面板
        palette = page.locator("text=节点面板")
        try:
            expect(palette).to_be_visible(timeout=3000)
            record("节点面板可见", True)
        except Exception as e:
            record("节点面板可见", False, str(e))

        # 检查 ReactFlow 画布中有节点
        page.wait_for_timeout(2000)
        rf_nodes = page.locator(".react-flow__node")
        record("DAG 画布节点", rf_nodes.count() >= 1, f"画布中 {rf_nodes.count()} 个节点")

        # ── 5. 节点面板 — 检查所有分类 ───────────────────────
        for cat in ["数据接入", "数据转换", "模型推理", "过滤规则", "数据输出"]:
            visible = page.locator(f"text={cat}").count() > 0
            record(f"节点面板分类「{cat}」", visible)

        # 检查新增的节点类型
        for node_label in ["ES 数据源", "严重度标记", "威胁情报富化", "GeoIP 定位", "风险聚合", "家族分类"]:
            visible = page.locator(f"text={node_label}").count() > 0
            record(f"新增节点「{node_label}」", visible)

        # ── 6. 点击节点 → 配置面板 ───────────────────────────
        first_node = rf_nodes.first
        first_node.click()
        page.wait_for_timeout(1000)

        config_panel = page.locator("text=节点配置")
        try:
            expect(config_panel).to_be_visible(timeout=3000)
            record("点击节点 — 配置面板打开", True)
        except Exception as e:
            record("点击节点 — 配置面板打开", False, str(e))

        # ── 7. YAML 导出 ─────────────────────────────────────
        yaml_btn = page.locator("button:has-text('YAML')")
        if yaml_btn.count() > 0:
            yaml_btn.first.click()
            page.wait_for_timeout(1000)
            yaml_drawer = page.locator("text=YAML 编辑")
            try:
                expect(yaml_drawer).to_be_visible(timeout=3000)
                record("YAML 抽屉打开", True)
            except Exception as e:
                record("YAML 抽屉打开", False, str(e))

            # 检查 YAML 内容
            textarea = page.locator("textarea").first
            yaml_content = textarea.input_value()
            has_nodes = "nodes:" in yaml_content or "stages:" in yaml_content
            record("YAML 内容包含节点", has_nodes, f"长度 {len(yaml_content)}")

            # 关闭 YAML 抽屉
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        else:
            record("YAML 按钮", False, "未找到")

        # ── 8. 操作历史 ──────────────────────────────────────
        # 先关闭配置面板（如果打开）
        close_btn = page.locator("button:has-text('收起')")
        if close_btn.count() > 0:
            try:
                close_btn.first.click(timeout=2000)
                page.wait_for_timeout(500)
            except Exception:
                pass

        # 滚动到表格区域，找历史按钮
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        history_btns = page.locator(".anticon-history")
        if history_btns.count() > 0:
            history_btns.first.click()
            page.wait_for_timeout(1500)
            history_drawer = page.locator("text=操作历史")
            try:
                expect(history_drawer).to_be_visible(timeout=3000)
                record("操作历史抽屉", True)
            except Exception as e:
                record("操作历史抽屉", False, str(e))
            # 关闭：用 visible drawer 的 close 按钮
            visible_close = page.locator(".ant-drawer-open .ant-drawer-close")
            if visible_close.count() > 0:
                visible_close.first.click(timeout=3000)
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        else:
            record("操作历史按钮", False, "未找到")

        # ── 9. 新建 Pipeline ─────────────────────────────────
        create_btn = page.locator("button:has-text('新建 Pipeline')").first
        create_btn.click()
        page.wait_for_timeout(1000)

        create_modal = page.locator("text=新建 Pipeline").last
        try:
            expect(create_modal).to_be_visible(timeout=3000)
            record("新建 Pipeline 弹窗", True)
        except Exception as e:
            record("新建 Pipeline 弹窗", False, str(e))

        # 填写表单
        name_input = page.locator("input[placeholder*='DGA 实时检测流水线']")
        if name_input.count() > 0:
            name_input.fill("Playwright 测试流水线")
            page.wait_for_timeout(300)

            # 点击创建
            ok_btn = page.locator(".ant-modal-footer button.ant-btn-primary")
            if ok_btn.count() > 0:
                ok_btn.click()
                page.wait_for_timeout(2000)

                # 检查是否创建成功
                new_pipeline = page.locator("text=Playwright 测试流水线")
                record("创建 Pipeline", new_pipeline.count() > 0)
            else:
                record("创建 Pipeline — 确认按钮", False, "未找到")
        else:
            # 尝试其他选择器
            modal_inputs = page.locator(".ant-modal input[type='text']")
            if modal_inputs.count() > 0:
                modal_inputs.first.fill("Playwright 测试流水线")
                page.wait_for_timeout(300)
                ok_btn = page.locator(".ant-modal-footer button.ant-btn-primary")
                if ok_btn.count() > 0:
                    ok_btn.click()
                    page.wait_for_timeout(2000)
                    new_pipeline = page.locator("text=Playwright 测试流水线")
                    record("创建 Pipeline", new_pipeline.count() > 0)
                else:
                    record("创建 Pipeline", False, "确认按钮未找到")
            else:
                record("创建 Pipeline — 输入框", False, "未找到")

        # ── 10. 配置管理 ─────────────────────────────────────
        config_mgmt_btn = page.locator("button:has-text('配置管理')")
        if config_mgmt_btn.count() > 0:
            config_mgmt_btn.first.click()
            page.wait_for_timeout(1500)

            config_drawer = page.locator("text=已保存的节点配置")
            try:
                expect(config_drawer).to_be_visible(timeout=3000)
                record("配置管理抽屉", True)
            except Exception as e:
                record("配置管理抽屉", False, str(e))

            # 检查预置配置
            for cfg_name in ["DNS 日志默认消费者", "DGA 二分类评分", "DGA 事件 ES 输出"]:
                visible = page.locator(f"text={cfg_name}").count() > 0
                record(f"预置配置「{cfg_name}」", visible)

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        else:
            record("配置管理按钮", False, "未找到")

        # ── 11. 停止/启动操作 ────────────────────────────────
        # 找到一个 running 状态的 pipeline 的停止按钮
        stop_btns = page.locator(".anticon-pause-circle")
        if stop_btns.count() > 0:
            record("停止按钮可见", True, f"{stop_btns.count()} 个")
        else:
            record("停止按钮可见", False)

        start_btns = page.locator(".anticon-play-circle")
        if start_btns.count() > 0:
            record("启动按钮可见", True, f"{start_btns.count()} 个")
        else:
            record("启动按钮可见", False)

        # ── 12. 删除测试 Pipeline ────────────────────────────
        # 找到 Playwright 测试流水线的删除按钮
        test_row = page.locator("tr:has-text('Playwright 测试流水线')")
        if test_row.count() > 0:
            delete_btn = test_row.locator(".anticon-delete")
            if delete_btn.count() > 0:
                delete_btn.first.click()
                page.wait_for_timeout(1500)
                # 确认删除 — 使用 modal confirm 内的按钮
                confirm_btn = page.locator(".ant-modal-confirm-btns button:has-text('确认删除')")
                if confirm_btn.count() > 0:
                    confirm_btn.first.click()
                    page.wait_for_timeout(2000)
                    remaining = page.locator("text=Playwright 测试流水线").count()
                    record("删除 Pipeline", remaining == 0)
                else:
                    # fallback: 点击 modal 中的 OK 按钮
                    ok_btn = page.locator(".ant-modal-confirm-btns .ant-btn-primary")
                    if ok_btn.count() > 0:
                        ok_btn.first.click()
                        page.wait_for_timeout(2000)
                        remaining = page.locator("text=Playwright 测试流水线").count()
                        record("删除 Pipeline", remaining == 0)
                    else:
                        record("删除 Pipeline — 确认按钮", False, "未找到")
            else:
                record("删除 Pipeline — 删除按钮", False, "未找到")
        else:
            record("删除 Pipeline — 测试行", False, "未找到")

        # ── 截图 ─────────────────────────────────────────────
        page.goto(f"{BASE}/pipeline", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.locator("text=DGA 实时检测流水线").first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SCREENSHOT_DIR / "pipeline_final.png"), full_page=True)

        # ── 汇总 ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("Pipeline 页面功能测试汇总")
        print("=" * 60)
        pass_count = sum(1 for r in results if r.startswith("[PASS]"))
        fail_count = sum(1 for r in results if r.startswith("[FAIL]"))
        for r in results:
            print(r)
        print(f"\n总计: {pass_count} PASS / {fail_count} FAIL / {len(results)} TOTAL")
        print("=" * 60)

        browser.close()

        assert fail_count == 0, f"{fail_count} tests failed"


if __name__ == "__main__":
    test_pipeline_page()
