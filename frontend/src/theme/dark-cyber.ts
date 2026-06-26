/**
 * DGA 平台 — 深色科技主题配置
 * 基于 Ant Design 5.x Token 系统
 */

import type { ThemeConfig } from 'antd';

export const darkCyberTheme: ThemeConfig = {
  token: {
    // 主色
    colorPrimary: '#1668dc',
    colorInfo: '#1668dc',
    colorSuccess: '#52c41a',
    colorWarning: '#faad14',
    colorError: '#f5222d',

    // 背景
    colorBgBase: '#0a0e1a',
    colorBgContainer: '#141928',
    colorBgElevated: '#1a2035',
    colorBgLayout: '#0a0e1a',

    // 文字
    colorText: '#e8e8e8',
    colorTextSecondary: '#8c8c8c',
    colorTextTertiary: '#595959',

    // 边框
    colorBorder: '#1f2937',
    colorBorderSecondary: '#1a2035',

    // 圆角
    borderRadius: 8,
    borderRadiusSM: 4,

    // 字体
    fontFamily: "'Inter', 'JetBrains Mono', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: '#0d1220',
      siderBg: '#0d1220',
      bodyBg: '#0a0e1a',
    },
    Menu: {
      darkItemBg: '#0d1220',
      darkItemSelectedBg: 'rgba(22, 104, 220, 0.15)',
    },
    Card: {
      colorBgContainer: '#141928',
      boxShadowTertiary: '0 4px 24px rgba(0, 0, 0, 0.5)',
    },
    Table: {
      colorBgContainer: '#141928',
      headerBg: '#1a2035',
      rowHoverBg: 'rgba(22, 104, 220, 0.08)',
    },
    Button: {
      borderRadius: 4,
    },
    Input: {
      colorBgContainer: '#1a2035',
    },
    Select: {
      colorBgContainer: '#1a2035',
    },
  },
  algorithm: undefined, // 使用 antd 的 theme.darkAlgorithm
};

// ECharts 主题色板
export const echartsColors = [
  '#1668dc', '#13c2c2', '#52c41a', '#faad14',
  '#f5222d', '#722ed1', '#eb2f96', '#fa8c16',
];

// 严重度颜色映射
export const severityColors: Record<string, string> = {
  CRITICAL: '#f5222d',
  HIGH: '#fa8c16',
  MEDIUM: '#faad14',
  LOW: '#52c41a',
};
