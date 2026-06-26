/**
 * M5 前端集成测试 — 验证关键组件和路由
 *
 * 注意: 这些测试需要在 vitest + jsdom 环境下运行
 * 当前为结构验证测试，不依赖 DOM 渲染
 */

// T079: 验证模块可导入
describe('Module imports', () => {
  test('dagStore exports required functions', async () => {
    const mod = await import('../stores/dagStore');
    expect(mod.useDagStore).toBeDefined();
  });

  test('api service exports all APIs', async () => {
    const mod = await import('../services/api');
    expect(mod.scoreAPI).toBeDefined();
    expect(mod.alertsAPI).toBeDefined();
    expect(mod.modelsAPI).toBeDefined();
    expect(mod.dagAPI).toBeDefined();
  });

  test('stores export all hooks', async () => {
    const mod = await import('../stores/index');
    expect(mod.useDashboardStore).toBeDefined();
    expect(mod.useDetectionStore).toBeDefined();
    expect(mod.useModelsStore).toBeDefined();
    expect(mod.usePipelineStore).toBeDefined();
  });
});

// T079: 验证 dagStore YAML 转换
describe('DAG Store YAML', () => {
  test('toYAML returns string', async () => {
    const { useDagStore } = await import('../stores/dagStore');
    const yaml = useDagStore.getState().toYAML();
    expect(typeof yaml).toBe('string');
    expect(yaml.length).toBeGreaterThan(0);
  });
});
