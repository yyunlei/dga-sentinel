"""
真实场景 Pipeline 可视化验证 + 数据流测试
1. 打开 DGA 全链路检测 Pipeline，验证 DAG 渲染
2. 通过 scoring API 模拟数据流
"""
import json
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE_UI = "http://localhost:3000"
BASE_API = "http://localhost:8000/api"
TIMEOUT = 10_000
SCREENSHOT_DIR = str(Path(__file__).parent)


def test_real_scenario():
    results = []

    def record(name: str, ok: bool, detail: str = ""):
        status = "PASS" if ok else "FAIL"
        results.append(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        print(results[-1])

    # ── Part 1: UI 验证 ──────────────────────────────────
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(TIMEOUT)

        # 打开 Pipeline 页面
        page.goto(f"{BASE_UI}/pipeline", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 找到并点击 "DGA 全链路检测" pipeline
        full_pipeline = page.locator("text=DGA 全链路检测 (真实场景)")
        try:
            expect(full_pipeline).to_be_visible(timeout=5000)
            record("全链路 Pipeline 在列表中", True)
        except Exception:
            # 可能在第二页，翻页
            next_btn = page.locator(".ant-pagination-next")
            if next_btn.count() > 0:
                next_btn.click()
                page.wait_for_timeout(1000)
            record("全链路 Pipeline 在列表中", page.locator("text=DGA 全链路检测").count() > 0)

        full_pipeline.first.click()
        page.wait_for_timeout(3000)

        # 验证编辑器加载
        editor = page.locator("text=DAG 可视化编排")
        try:
            expect(editor).to_be_visible(timeout=5000)
            record("DAG 编辑器加载", True)
        except Exception as e:
            record("DAG 编辑器加载", False, str(e))

        # 验证节点数量
        rf_nodes = page.locator(".react-flow__node")
        page.wait_for_timeout(1000)
        node_count = rf_nodes.count()
        record("DAG 节点渲染", node_count >= 8, f"{node_count} 个节点")

        # 验证连线
        rf_edges = page.locator(".react-flow__edge")
        edge_count = rf_edges.count()
        record("DAG 连线渲染", edge_count >= 8, f"{edge_count} 条连线")

        # 截图 — DAG 全景
        page.screenshot(
            path=f"{SCREENSHOT_DIR}/pipeline_full_dag.png",
            full_page=True
        )
        record("DAG 全景截图", True)

        # 点击第一个节点验证配置面板
        if rf_nodes.count() > 0:
            rf_nodes.first.click()
            page.wait_for_timeout(1000)
            config_panel = page.locator("text=节点配置")
            try:
                expect(config_panel).to_be_visible(timeout=3000)
                record("节点配置面板", True)
            except Exception as e:
                record("节点配置面板", False, str(e))

        # 验证 YAML 导出包含 connections
        yaml_btn = page.locator("button:has-text('YAML')")
        if yaml_btn.count() > 0:
            yaml_btn.first.click()
            page.wait_for_timeout(1000)
            textarea = page.locator("textarea").first
            yaml_text = textarea.input_value()
            has_connections = "connections:" in yaml_text or "source:" in yaml_text
            record("YAML 导出含连线", has_connections, f"长度 {len(yaml_text)}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # 截图 — 带配置面板
        page.screenshot(
            path=f"{SCREENSHOT_DIR}/pipeline_with_config.png",
            full_page=True
        )

        browser.close()

    # ── Part 2: 数据流测试 ───────────────────────────────
    print("\n--- 数据流测试 ---")

    # 测试 1: Scoring API — 正常域名
    normal_domains = ["google.com", "github.com", "microsoft.com"]
    try:
        data = json.dumps({"domains": normal_domains}).encode()
        req = urllib.request.Request(
            f"{BASE_API}/score",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        all_low = all(r["score"] < 0.5 for r in result["results"])
        record("正常域名评分 (低分)", all_low,
               f"scores: {[r['score'] for r in result['results']]}")
    except Exception as e:
        record("正常域名评分", False, str(e))

    # 测试 2: Scoring API — DGA 域名
    dga_domains = [
        "xjkwnqpfrt.com",
        "asdkjhqwezxc.net",
        "qwertyuiopasdf.org",
        "zxcvbnmlkjhgf.info",
    ]
    try:
        data = json.dumps({"domains": dga_domains}).encode()
        req = urllib.request.Request(
            f"{BASE_API}/score",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        scores = [r["score"] for r in result["results"]]
        is_dga_flags = [r["is_dga"] for r in result["results"]]
        families = [r.get("family") for r in result["results"]]
        any_high = any(s > 0.5 for s in scores)
        record("DGA 域名评分 (高分)", any_high, f"scores: {scores}")
        record("DGA 标记", any(is_dga_flags), f"is_dga: {is_dga_flags}")
        record("家族分类", any(f is not None for f in families), f"families: {families}")
        record("延迟", True, f"{result.get('latency_ms', 'N/A')} ms")
    except Exception as e:
        record("DGA 域名评分", False, str(e))

    # 测试 3: Pipeline 启动/停止
    try:
        # 获取全链路 pipeline ID
        req = urllib.request.Request(f"{BASE_API}/dag/pipelines")
        resp = urllib.request.urlopen(req, timeout=10)
        pipelines = json.loads(resp.read())["pipelines"]
        full_pl = next((p for p in pipelines if "全链路" in p["name"]), None)
        if full_pl:
            pid = full_pl["pipeline_id"]
            # 启动
            req = urllib.request.Request(
                f"{BASE_API}/dag/pipelines/{pid}/start",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=10)
            start_result = json.loads(resp.read())
            record("Pipeline 启动", start_result.get("ok", False))

            # 停止
            req = urllib.request.Request(
                f"{BASE_API}/dag/pipelines/{pid}/stop",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=10)
            stop_result = json.loads(resp.read())
            record("Pipeline 停止", stop_result.get("ok", False))

            # 验证历史记录
            req = urllib.request.Request(f"{BASE_API}/dag/pipelines/{pid}/history")
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())["history"]
            record("操作历史记录", len(history) >= 2, f"{len(history)} 条记录")
        else:
            record("全链路 Pipeline 查找", False, "未找到")
    except Exception as e:
        record("Pipeline 启停测试", False, str(e))

    # ── 汇总 ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("真实场景 Pipeline 测试汇总")
    print("=" * 60)
    pass_count = sum(1 for r in results if r.startswith("[PASS]"))
    fail_count = sum(1 for r in results if r.startswith("[FAIL]"))
    for r in results:
        print(r)
    print(f"\n总计: {pass_count} PASS / {fail_count} FAIL / {len(results)} TOTAL")
    print("=" * 60)


if __name__ == "__main__":
    test_real_scenario()
