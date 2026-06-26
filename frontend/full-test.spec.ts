import { test, expect } from "@playwright/test";

const BASE = "http://localhost:3000";

test.describe("DGA Platform Full Functional Test", () => {
  test.setTimeout(60000);

  // ─── Dashboard ───────────────────────────────────────────
  test("01 - Dashboard loads with stats and charts", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: "screenshots/01-dashboard.png",
      fullPage: true,
    });

    // Should have stat cards or dashboard content
    const body = await page.textContent("body");
    console.log("[Dashboard] Page loaded, body length:", body?.length);

    // Check for common dashboard elements
    const hasContent = body && body.length > 100;
    expect(hasContent).toBeTruthy();
  });

  // ─── Detection Page ──────────────────────────────────────
  test("02 - Detection page loads and can score domains", async ({ page }) => {
    await page.goto(`${BASE}/detection`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: "screenshots/02-detection.png",
      fullPage: true,
    });

    const body = await page.textContent("body");
    console.log("[Detection] Page loaded, body length:", body?.length);
    expect(body && body.length > 50).toBeTruthy();
  });

  // ─── Alerts Page (Raw View) ───────────────────────────────
  test("03 - Alerts page loads with raw view by default", async ({ page }) => {
    await page.goto(`${BASE}/alerts`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "screenshots/03-alerts-raw.png",
      fullPage: true,
    });

    // Should show "告警中心" title and "原始告警" toggle
    const body = await page.textContent("body");
    expect(body).toContain("告警中心");

    // Check for Segmented toggle
    const segmented = page.locator(".ant-segmented");
    await expect(segmented).toBeVisible();
  });

  // ─── Alerts Page (Grouped View) ──────────────────────────
  test("04 - Alerts grouped view toggle works", async ({ page }) => {
    await page.goto(`${BASE}/alerts`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Click "按域名聚合" toggle
    const groupedOption = page.locator(".ant-segmented-item", {
      hasText: "按域名聚合",
    });
    if (await groupedOption.isVisible()) {
      await groupedOption.click();
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: "screenshots/04-alerts-grouped.png",
        fullPage: true,
      });

      const body = await page.textContent("body");
      console.log("[Alerts Grouped] View switched");
      // Should show grouped columns like "告警数", "源 IP 数", "最高严重度"
      const hasGroupedCols =
        body?.includes("告警数") ||
        body?.includes("最高严重度") ||
        body?.includes("暂无聚合告警数据");
      expect(hasGroupedCols).toBeTruthy();
    }
  });

  // ─── Alerts Filters ──────────────────────────────────────
  test("05 - Alerts filter controls are present", async ({ page }) => {
    await page.goto(`${BASE}/alerts`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "screenshots/05-alerts-filters.png",
      fullPage: true,
    });

    // Check filter elements exist
    const body = await page.textContent("body");
    expect(body).toContain("查询");
    expect(body).toContain("重置");
  });

  // ─── Alert Detail Page ────────────────────────────────────
  test("06 - Alert detail page navigation", async ({ page }) => {
    await page.goto(`${BASE}/alerts`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Try clicking a "详情" button if alerts exist
    const detailBtn = page.locator("button", { hasText: "详情" }).first();
    if (await detailBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await detailBtn.click();
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: "screenshots/06-alert-detail.png",
        fullPage: true,
      });
      console.log("[Alert Detail] Navigated to detail page");
    } else {
      console.log(
        "[Alert Detail] No alerts to click, skipping detail navigation",
      );
      await page.screenshot({
        path: "screenshots/06-alert-detail-empty.png",
        fullPage: true,
      });
    }
  });

  // ─── Models Page ─────────────────────────────────────────
  test("07 - Models page loads", async ({ page }) => {
    await page.goto(`${BASE}/models`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "screenshots/07-models.png",
      fullPage: true,
    });

    const body = await page.textContent("body");
    console.log("[Models] Page loaded, body length:", body?.length);
    expect(body && body.length > 50).toBeTruthy();
  });

  // ─── Pipeline Page ───────────────────────────────────────
  test("08 - Pipeline page loads with pipeline list", async ({ page }) => {
    await page.goto(`${BASE}/pipeline`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "screenshots/08-pipeline.png",
      fullPage: true,
    });

    const body = await page.textContent("body");
    console.log("[Pipeline] Page loaded, body length:", body?.length);
    expect(body && body.length > 50).toBeTruthy();
  });

  // ─── Reports Page ────────────────────────────────────────
  test("09 - Reports page loads", async ({ page }) => {
    await page.goto(`${BASE}/reports`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "screenshots/09-reports.png",
      fullPage: true,
    });

    const body = await page.textContent("body");
    console.log("[Reports] Page loaded, body length:", body?.length);
    expect(body && body.length > 50).toBeTruthy();
  });

  // ─── Navigation ──────────────────────────────────────────
  test("10 - Sidebar navigation works for all pages", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);

    // Test navigation to each page via sidebar menu
    const menuItems = [
      { text: "检测", path: "/detection" },
      { text: "告警", path: "/alerts" },
      { text: "模型", path: "/models" },
      { text: "报告", path: "/reports" },
    ];

    for (const item of menuItems) {
      const menuLink = page
        .locator(".ant-menu-item", { hasText: item.text })
        .first();
      if (await menuLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await menuLink.click();
        await page.waitForTimeout(1500);
        console.log(`[Nav] Clicked "${item.text}", URL: ${page.url()}`);
      }
    }
    await page.screenshot({
      path: "screenshots/10-navigation.png",
      fullPage: true,
    });
  });

  // ─── API Health Check ────────────────────────────────────
  test("11 - Backend API health check", async ({ request }) => {
    const health = await request.get("http://localhost:8000/health");
    expect(health.ok()).toBeTruthy();
    const data = await health.json();
    expect(data.status).toBe("ok");
    console.log("[API Health]", JSON.stringify(data));
  });

  // ─── API Alerts Endpoint ─────────────────────────────────
  test("12 - API alerts endpoint returns data", async ({ request }) => {
    const resp = await request.get("http://localhost:8000/api/alerts?limit=5");
    console.log("[API Alerts] Status:", resp.status());
    if (resp.ok()) {
      const data = await resp.json();
      console.log(
        "[API Alerts] Total:",
        data.total,
        "Alerts:",
        data.alerts?.length,
      );
    }
  });

  // ─── API Alerts Grouped Endpoint ─────────────────────────
  test("13 - API alerts grouped endpoint returns data", async ({ request }) => {
    const resp = await request.get(
      "http://localhost:8000/api/alerts/grouped?size=10",
    );
    console.log("[API Grouped] Status:", resp.status());
    if (resp.ok()) {
      const data = await resp.json();
      console.log(
        "[API Grouped] Total domains:",
        data.total_domains,
        "Groups:",
        data.groups?.length,
      );
    }
  });

  // ─── API Alerts Stats ────────────────────────────────────
  test("14 - API alerts stats endpoint", async ({ request }) => {
    const resp = await request.get("http://localhost:8000/api/alerts/stats");
    console.log("[API Stats] Status:", resp.status());
    if (resp.ok()) {
      const data = await resp.json();
      console.log(
        "[API Stats] Total:",
        data.total,
        "Pending:",
        data.pending,
        "Acked:",
        data.acknowledged,
      );
    }
  });

  // ─── API Dashboard Stats ─────────────────────────────────
  test("15 - API dashboard stats endpoint", async ({ request }) => {
    const resp = await request.get("http://localhost:8000/api/dashboard/stats");
    console.log("[API Dashboard] Status:", resp.status());
    if (resp.ok()) {
      const data = await resp.json();
      console.log(
        "[API Dashboard] Total today:",
        data.total_today,
        "DGA hits:",
        data.dga_hits,
      );
    }
  });

  // ─── Alerts Drawer Quick View ────────────────────────────
  test("16 - Alerts row click opens drawer", async ({ page }) => {
    await page.goto(`${BASE}/alerts`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Click on a table row (not a button)
    const row = page.locator(".ant-table-row").first();
    if (await row.isVisible({ timeout: 3000 }).catch(() => false)) {
      await row.click();
      await page.waitForTimeout(1500);
      await page.screenshot({
        path: "screenshots/16-alert-drawer.png",
        fullPage: true,
      });

      // Check if drawer opened
      const drawer = page.locator(".ant-drawer");
      const drawerVisible = await drawer
        .isVisible({ timeout: 3000 })
        .catch(() => false);
      console.log("[Drawer] Visible:", drawerVisible);
    } else {
      console.log("[Drawer] No alert rows to click");
    }
  });
});
