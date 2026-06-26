import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ChartOption = Record<string, any>;

interface Props {
  option: ChartOption;
  style?: React.CSSProperties;
  className?: string;
}

export default function Chart({ option, style, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !ref.current) return;
    
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current, 'dark');
      const ro = new ResizeObserver(() => chartRef.current?.resize());
      ro.observe(ref.current);
    }
    
    return () => {
      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }
    };
  }, [mounted]);

  useEffect(() => {
    if (mounted && chartRef.current && option) {
      chartRef.current.setOption(option, { notMerge: true });
    }
  }, [option, mounted]);

  if (!mounted) {
    return <div style={{ height: 300, ...style }} className={className} />;
  }

  return <div ref={ref} style={{ height: 300, ...style }} className={className} />;
}
