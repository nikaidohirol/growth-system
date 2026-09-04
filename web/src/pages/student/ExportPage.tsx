import { useEffect, useRef, useState } from 'react'
import { Button, Card, Space, Spin } from 'antd'
import { FileExcelOutlined, FilePdfOutlined } from '@ant-design/icons'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import * as XLSX from 'xlsx'
import { exportAPI } from '@/api/modules'

type Dossier = {
  student: Record<string, string | null>
  experiences: Record<string, string>[]
  gpaList: Record<string, string | number>[]
  parties: Record<string, string>[]
  organizations: Record<string, string>[]
  honors: Record<string, string>[]
  certificates: Record<string, string>[]
  voluntarys: Record<string, string | number>[]
  practices: Record<string, string>[]
  innovations: Record<string, Record<string, string>[]>
}

const empty: Record<string, never>[] = []

function Table({ head, rows }: { head: string[]; rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p style={{ fontSize: 11, color: '#999', textAlign: 'center', margin: '4px 0' }}>暂无记录</p>
  return (
    <table>
      <thead>
        <tr>{head.map((h) => <th key={h}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{head.map((h) => <td key={h}>{String(r[h] ?? '-')}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

/** A4 成长档案：5 页卡片，水印 + PDF/Excel 一键导出 */
export default function ExportPage() {
  const [data, setData] = useState<Dossier | null>(null)
  const [exporting, setExporting] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    exportAPI.dossier().then((d) => setData(d as Dossier)).catch(() => undefined)
  }, [])

  if (!data) return <Spin style={{ display: 'block', margin: '120px auto' }} />
  const s = data.student

  const exportPDF = async () => {
    setExporting('pdf')
    try {
      const pages = wrapRef.current?.querySelectorAll<HTMLElement>('.a4')
      if (!pages?.length) return
      const pdf = new jsPDF({ unit: 'mm', format: 'a4' })
      for (let i = 0; i < pages.length; i++) {
        const canvas = await html2canvas(pages[i], { scale: 2, useCORS: true })
        if (i > 0) pdf.addPage()
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, 297)
      }
      pdf.save(`${s.name}的成长记录.pdf`)
    } finally {
      setExporting('')
    }
  }

  const exportXLSX = () => {
    setExporting('xlsx')
    try {
      const wb = XLSX.utils.book_new()
      const sheet = (name: string, head: string[], rows: Record<string, unknown>[]) => {
        const ws = XLSX.utils.json_to_sheet(rows.length ? rows : [{}], { header: head })
        XLSX.utils.book_append_sheet(wb, ws, name)
      }
      const stu = [
        { 项目: '姓名', 内容: s.name }, { 项目: '学号', 内容: s.uid },
        { 项目: '性别', 内容: s.sex }, { 项目: '民族', 内容: s.nation },
        { 项目: '政治面貌', 内容: s.politicsStatus }, { 项目: '年级', 内容: s.periods },
        { 项目: '班级', 内容: s.classId }, { 项目: '学院', 内容: s.college },
        { 项目: '专业', 内容: s.major }, { 项目: '生源地', 内容: s.origin },
      ]
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(stu), '基本信息')
      sheet('教育经历', ['startDate', 'endDate', 'college', 'major', 'classId'], data.experiences)
      sheet('综合成绩', ['semester', 'gpa', 'comp', 'gpaRank', 'compRank', 'maxRank'], data.gpaList)
      sheet('入党情况', ['date', 'type', 'department', 'boss', 'leader'], data.parties)
      sheet('组织经历', ['team', 'type', 'post', 'startDate', 'endDate'], data.organizations)
      sheet('个人荣誉', ['project', 'level', 'team', 'date'], data.honors)
      sheet('技能证书', ['project', 'code', 'date'], data.certificates)
      sheet('志愿服务', ['project', 'duration', 'sponsor'], data.voluntarys)
      sheet('社会实践', ['team', 'type', 'theme', 'sponsor', 'startDate', 'endDate'], data.practices)
      const inn = Object.entries(data.innovations).flatMap(([cat, rows]) => rows)
      sheet('创新创业', ['project', 'implementation', 'honor', 'post', 'date', 'deadline', 'credit'],
        inn as Record<string, unknown>[])
      XLSX.writeFile(wb, `${s.name}的成长记录.xlsx`)
    } finally {
      setExporting('')
    }
  }

  return (
    <Card
      title="成长档案"
      extra={
        <Space>
          <Button type="primary" icon={<FilePdfOutlined />} loading={exporting === 'pdf'} onClick={exportPDF}>
            导出 PDF
          </Button>
          <Button icon={<FileExcelOutlined />} loading={exporting === 'xlsx'} onClick={exportXLSX}>
            导出 Excel
          </Button>
        </Space>
      }
    >
      <div ref={wrapRef}>
        {/* P1 基本信息 + 教育经历 + 综合成绩 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>学生成长档案 · 基本情况</h2>
          <div className="info-grid">
            <div>姓名：{s.name}</div><div>学号：{s.uid}</div>
            <div>性别：{s.sex}</div><div>民族：{s.nation}</div>
            <div>政治面貌：{s.politicsStatus}</div><div>年级：{s.periods}</div>
            <div>班级：{s.classId}</div><div>生源地：{s.origin}</div>
            <div style={{ gridColumn: 'span 2' }}>学院：{s.college}</div>
            <div style={{ gridColumn: 'span 2' }}>专业：{s.major}</div>
          </div>
          <h3>教育经历</h3>
          <Table head={['起止时间', '学院', '专业', '班级']}
                 rows={data.experiences.map((e) => ({
                   ...e, 起止时间: `${e.startDate} ~ ${e.endDate}`,
                 })) as never} />
          <h3>综合学分绩</h3>
          <Table head={['学期', 'GPA', '综测成绩', 'GPA排名', '综测排名', '专业人数']}
                 rows={data.gpaList as never} />
        </div>

        {/* P2 入党 + 组织经历 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>思想与组织发展</h2>
          <h3>入党情况</h3>
          <Table head={['日期', '发展阶段', '党支部', '介绍人', '培养联系人']}
                 rows={data.parties.map((p) => ({ ...p })) as never} />
          <h3>组织经历</h3>
          <Table head={['组织名称', '类型', '职务', '起止时间']}
                 rows={data.organizations.map((o) => ({
                   ...o, 起止时间: `${o.startDate} ~ ${o.endDate}`,
                 })) as never} />
        </div>

        {/* P3 荣誉 + 证书 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>荣誉与技能</h2>
          <h3>个人荣誉</h3>
          <Table head={['荣誉名称', '级别', '授予单位', '获得日期']} rows={data.honors as never} />
          <h3>技能证书</h3>
          <Table head={['证书名称', '证书编号', '获得日期']} rows={data.certificates as never} />
        </div>

        {/* P4 实践 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>社会实践</h2>
          <h3>社会实践活动</h3>
          <Table head={['团队名称', '类型', '主题', '主办单位', '时间']}
                 rows={data.practices.map((p) => ({
                   ...p, 时间: `${p.startDate} ~ ${p.endDate}`,
                 })) as never} />
          <h3>志愿服务活动</h3>
          <Table head={['项目', '时长(小时)', '组织单位']} rows={data.voluntarys as never} />
        </div>

        {/* P5 创新创业 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>创新创业实践</h2>
          <h3>前沿学术报告</h3>
          <Table head={['讲座系列', '主题/场次', '学分']}
                 rows={data.innovations.chair ?? empty} />
          <h3>年度创新创业项目</h3>
          <Table head={['项目名称', '立项级别', '角色', '学分']}
                 rows={(data.innovations.project ?? []).map((r) => ({
                   project: r.implementation, implementation: r.project, post: r.post, credit: r.credit,
                 }))} />
          <h3>科技创新竞赛</h3>
          <Table head={['竞赛名称', '获奖情况', '人员次序', '日期', '学分']}
                 rows={data.innovations.competition ?? empty} />
          <h3>创业实践</h3>
          <Table head={['项目名称', '类型', '角色', '日期', '学分']}
                 rows={(data.innovations.enterprise ?? []).map((r) => ({
                   project: r.project, implementation: r.implementation, post: r.post, date: r.date, credit: r.credit,
                 }))} />
          <h3>学术论文 / 申请专利 / 其他</h3>
          <Table head={['名称', '认定情况', '日期', '学分']}
                 rows={[
                   ...(data.innovations.paper ?? []).map((r) => ({
                     名称: r.project, 认定情况: r.implementation, 日期: r.date, 学分: r.credit,
                   })),
                   ...(data.innovations.patent ?? []).map((r) => ({
                     名称: r.project, 认定情况: r.implementation, 日期: r.date, 学分: r.credit,
                   })),
                   ...(data.innovations.other ?? []).map((r) => ({
                     名称: r.project, 认定情况: r.implementation, 日期: r.date, 学分: r.credit,
                   })),
                 ]} />
        </div>
      </div>
    </Card>
  )
}
