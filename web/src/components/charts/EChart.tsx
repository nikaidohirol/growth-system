import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/** echarts 轻量封装：声明式 option，自适应容器宽度 */
export default function EChart({ option, height = 300 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts>()

  useEffect(() => {
    if (!ref.current) return
    chartRef.current ??= echarts.init(ref.current)
    const chart = chartRef.current
    chart.setOption(option, true)
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    const ro = new ResizeObserver(onResize)
    ro.observe(ref.current)
    return () => {
      window.removeEventListener('resize', onResize)
      ro.disconnect()
    }
  }, [option])

  return <div ref={ref} style={{ height, width: '100%' }} />
}
