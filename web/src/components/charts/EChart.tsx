import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

// echarts 按需注册：仅打包项目用到的图表类型与组件，显著减小体积
echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

/** echarts 轻量封装：声明式 option，自适应容器宽度 */
export default function EChart({ option, height = 300 }: { option: EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.EChartsType>()

  useEffect(() => {
    if (!ref.current) return
    chartRef.current ??= echarts.init(ref.current)
    const chart = chartRef.current
    chart.setOption(option, true)
    // rAF 节流：窗口缩放/侧边栏动画期间每帧最多 resize 一次，图表平滑跟随不跳变
    let raf = 0
    const onResize = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => chart.resize())
    }
    window.addEventListener('resize', onResize)
    const ro = new ResizeObserver(onResize)
    ro.observe(ref.current)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      ro.disconnect()
    }
  }, [option])

  return <div ref={ref} style={{ height, width: '100%' }} />
}
