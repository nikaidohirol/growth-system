import { useEffect, useRef, useState } from 'react'
import { Button, Card, Space, Spin } from 'antd'
import { FileExcelOutlined, FilePdfOutlined } from '@ant-design/icons'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import * as XLSX from 'xlsx'
import { exportAPI } from '@/api/modules'

type Row = Record<string, unknown>
type Dossier = {
  student: Record<string, string | null>
  experiences: Row[]
  gpaList: Row[]
  parties: Row[]
  organizations: Row[]
  honors: Row[]
  certificates: Row[]
  voluntarys: Row[]
  practices: Row[]
  innovations: Record<string, Row[]>
}

/** head 为中文表头，keys 与之一一对应取行数据 */
function Table({ head, keys, rows }: { head: string[]; keys: string[]; rows: Row[] }) {
  if (!rows.length) {
    return <p style={{ fontSize: 11, color: '#999', textAlign: 'center', margin: '4px 0' }}>暂无记录</p>
  }
  return (
    <table>
      <thead>
        <tr>{head.map((h) => <th key={h}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{keys.map((k) => <td key={k}>{String(r[k] ?? '-')}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

/** 把英文键行数据转成中文键（Excel 导出用），keys: 英文键 -> 中文表头 */
function zh(rows: Row[], keys: Record<string, string>): Row[] {
  return rows.map((r) => Object.fromEntries(Object.entries(keys).map(([k, z]) => [z, r[k]])))
}

const INN_CAT_ZH: Record<string, string> = {
  chair: '前沿学术报告', project: '年度创新创业项目', competition: '科技创新竞赛',
  enterprise: '创业实践', paper: '学术论文', patent: '申请专利', other: '其他实践活动',
}

/** A4 成长档案：5 页卡片，水印 + PDF/Excel 一键导出（仅含审核通过记录） */
export default function ExportPage() {
  const [data, setData] = useState<Dossier | null>(null)
  const [exporting, setExporting] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    exportAPI.dossier().then((d) => setData(d as Dossier)).catch(() => undefined)
  }, [])

  if (!data) return <Spin style={{ display: 'block', margin: '120px auto' }} />
  const s = data.student
  const innAll = Object.entries(data.innovations).flatMap(([cat, rows]) =>
    rows.map((r) => ({ ...r, category: INN_CAT_ZH[cat] ?? cat })))

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
      const sheet = (name: string, head: string[], rows: Row[]) => {
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
      sheet('教育经历', ['开始日期', '结束日期', '学院', '专业', '班级'],
        zh(data.experiences, { startDate: '开始日期', endDate: '结束日期', college: '学院', major: '专业', classId: '班级' }))
      sheet('综合成绩', ['学期', 'GPA', '综测成绩', 'GPA排名', '综测排名', '专业人数'],
        zh(data.gpaList, { semester: '学期', gpa: 'GPA', comp: '综测成绩', gpaRank: 'GPA排名', compRank: '综测排名', maxRank: '专业人数' }))
      sheet('入党情况', ['日期', '发展阶段', '党支部', '介绍人', '培养联系人'],
        zh(data.parties, { date: '日期', type: '发展阶段', department: '党支部', boss: '介绍人', leader: '培养联系人' }))
      sheet('组织经历', ['组织名称', '类型', '职务', '开始日期', '结束日期'],
        zh(data.organizations, { team: '组织名称', type: '类型', post: '职务', startDate: '开始日期', endDate: '结束日期' }))
      sheet('个人荣誉', ['荣誉名称', '级别', '授予单位', '获得日期'],
        zh(data.honors, { project: '荣誉名称', level: '级别', team: '授予单位', date: '获得日期' }))
      sheet('技能证书', ['证书名称', '证书编号', '获得日期'],
        zh(data.certificates, { project: '证书名称', code: '证书编号', date: '获得日期' }))
      sheet('志愿服务', ['项目', '时长(小时)', '组织单位'],
        zh(data.voluntarys, { project: '项目', duration: '时长(小时)', sponsor: '组织单位' }))
      sheet('社会实践', ['团队名称', '类型', '主题', '主办单位', '开始日期', '结束日期'],
        zh(data.practices, { team: '团队名称', type: '类型', theme: '主题', sponsor: '主办单位', startDate: '开始日期', endDate: '结束日期' }))
      sheet('创新创业', ['类别', '名称', '说明/级别', '获奖情况', '人员次序', '日期', '学分'], zh(innAll, {
        category: '类别', project: '名称', implementation: '说明/级别',
        honor: '获奖情况', post: '人员次序', date: '日期', credit: '学分',
      }))
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
          <Table head={['开始日期', '结束日期', '学院', '专业', '班级']}
                 keys={['startDate', 'endDate', 'college', 'major', 'classId']}
                 rows={data.experiences} />
          <h3>综合学分绩</h3>
          <Table head={['学期', 'GPA', '综测成绩', 'GPA排名', '综测排名', '专业人数']}
                 keys={['semester', 'gpa', 'comp', 'gpaRank', 'compRank', 'maxRank']}
                 rows={data.gpaList} />
        </div>

        {/* P2 入党 + 组织经历 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>思想与组织发展</h2>
          <h3>入党情况</h3>
          <Table head={['日期', '发展阶段', '党支部', '介绍人', '培养联系人']}
                 keys={['date', 'type', 'department', 'boss', 'leader']}
                 rows={data.parties} />
          <h3>组织经历</h3>
          <Table head={['组织名称', '类型', '职务', '开始日期', '结束日期']}
                 keys={['team', 'type', 'post', 'startDate', 'endDate']}
                 rows={data.organizations} />
        </div>

        {/* P3 荣誉 + 证书 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>荣誉与技能</h2>
          <h3>个人荣誉</h3>
          <Table head={['荣誉名称', '级别', '授予单位', '获得日期']}
                 keys={['project', 'level', 'team', 'date']} rows={data.honors} />
          <h3>技能证书</h3>
          <Table head={['证书名称', '证书编号', '获得日期']}
                 keys={['project', 'code', 'date']} rows={data.certificates} />
        </div>

        {/* P4 实践 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>社会实践</h2>
          <h3>社会实践活动</h3>
          <Table head={['团队名称', '类型', '主题', '主办单位', '开始日期', '结束日期']}
                 keys={['team', 'type', 'theme', 'sponsor', 'startDate', 'endDate']}
                 rows={data.practices} />
          <h3>志愿服务活动</h3>
          <Table head={['项目', '时长(小时)', '组织单位']}
                 keys={['project', 'duration', 'sponsor']} rows={data.voluntarys} />
        </div>

        {/* P5 创新创业 */}
        <div className="a4">
          <div className="a4-watermark" />
          <h2>创新创业实践</h2>
          <h3>前沿学术报告</h3>
          <Table head={['讲座系列', '报告主题/场次', '学分']}
                 keys={['project', 'implementation', 'credit']}
                 rows={data.innovations.chair ?? []} />
          <h3>年度创新创业项目</h3>
          <Table head={['项目名称', '立项级别', '承担角色', '结题时间', '学分']}
                 keys={['implementation', 'project', 'post', 'deadline', 'credit']}
                 rows={data.innovations.project ?? []} />
          <h3>科技创新竞赛</h3>
          <Table head={['竞赛名称', '获奖情况', '人员次序', '获奖日期', '学分']}
                 keys={['project', 'honor', 'post', 'date', 'credit']}
                 rows={data.innovations.competition ?? []} />
          <h3>创业实践</h3>
          <Table head={['创业项目名称', '创业类型', '承担角色', '日期', '学分']}
                 keys={['project', 'implementation', 'post', 'date', 'credit']}
                 rows={data.innovations.enterprise ?? []} />
          <h3>学术论文 / 申请专利 / 其他</h3>
          <Table head={['名称', '认定情况', '日期', '学分']}
                 keys={['project', 'implementation', 'date', 'credit']}
                 rows={[
                   ...(data.innovations.paper ?? []),
                   ...(data.innovations.patent ?? []),
                   ...(data.innovations.other ?? []),
                 ]} />
        </div>
      </div>
    </Card>
  )
}
