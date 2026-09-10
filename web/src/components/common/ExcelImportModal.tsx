import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Modal, Space, Table, Tag, Typography, Upload,
} from 'antd'
import { DownloadOutlined, FileExcelOutlined, InboxOutlined } from '@ant-design/icons'
import type { ImportResult } from '@/types'

const { Text } = Typography

export interface ImportColumn {
  key: string        // 提交给后端的字段名
  title: string      // Excel 表头（导入按表头精确匹配）
  required?: boolean
  example?: string   // 填表说明：示例
  options?: string[] // 填表说明：可选值
}

/** 解析后的行：Excel 表头 → column.key 的键值对（空行已剔除） */
export type ImportRow = Record<string, string>

/**
 * 通用 Excel 批量导入弹窗：上传解析 → 模板下载 → 预览 → 导入回执（逐行错误）。
 * 纯前端 xlsx 解析，表头必须与 columns[].title 一致；导入逻辑由调用方 doImport 注入。
 */
export default function ExcelImportModal({ open, title, columns, doImport, onDone, onClose, extra }: {
  open: boolean
  title: string
  columns: ImportColumn[]
  doImport: (rows: ImportRow[]) => Promise<ImportResult>
  onDone: () => void
  onClose: () => void
  extra?: React.ReactNode   // 弹窗顶部的附加控件（如辅导员导入的状态选择）
}) {
  const { message } = App.useApp()
  const [fileName, setFileName] = useState('')
  const [rows, setRows] = useState<ImportRow[]>([])
  const [fatal, setFatal] = useState('')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)

  useEffect(() => {
    if (open) {
      setFileName(''); setRows([]); setFatal(''); setResult(null); setImporting(false)
    }
  }, [open])

  const parseFile = async (file: File) => {
    const XLSX = await import('xlsx')
    try {
      const buf = await file.arrayBuffer()
      const wb = XLSX.read(buf)
      const ws = wb.Sheets[wb.SheetNames[0]]
      const matrix = XLSX.utils.sheet_to_json<string[]>(ws, { header: 1, defval: '', raw: false })
      if (!matrix.length) { setFatal('表格为空'); setRows([]); return }
      const headers = (matrix[0] as unknown[]).map((h) => String(h).trim())
      const missing = columns.filter((c) => c.required && !headers.includes(c.title))
      if (missing.length) {
        setFatal(`缺少必需列：${missing.map((c) => c.title).join('、')}（可先下载模板填写）`)
        setRows([])
        return
      }
      const out: ImportRow[] = []
      for (const arr of matrix.slice(1)) {
        const obj: ImportRow = {}
        let has = false
        headers.forEach((h, i) => {
          const col = columns.find((c) => c.title === h)
          const v = String((arr as unknown[])[i] ?? '').trim()
          if (col && v) { obj[col.key] = v; has = true }
        })
        if (has) out.push(obj)
      }
      setFatal('')
      setResult(null)
      setRows(out)
      setFileName(file.name)
    } catch {
      message.error('文件解析失败，请确认为有效的 Excel/CSV 文件')
    }
  }

  const downloadTemplate = async () => {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([columns.map((c) => c.title)]), '导入数据')
    const notes = [
      ['列名', '是否必填', '填写说明'],
      ...columns.map((c) => [
        c.title,
        c.required ? '必填' : '选填',
        [c.options?.length ? `可选值：${c.options.join(' / ')}` : '', c.example]
          .filter(Boolean).join('；') || '-',
      ]),
    ]
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(notes), '填表说明')
    XLSX.writeFile(wb, `${title}模板.xlsx`)
  }

  const runImport = async () => {
    if (!rows.length) return
    setImporting(true)
    try {
      const res = await doImport(rows)
      setResult(res)
      onDone()
    } finally {
      setImporting(false)
    }
  }

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      width={640}
      footer={
        <Space>
          <Button onClick={downloadTemplate} icon={<DownloadOutlined />}>下载模板</Button>
          <Button onClick={onClose}>{result ? '关闭' : '取消'}</Button>
          <Button type="primary" icon={<FileExcelOutlined />} disabled={!rows.length || !!fatal || !!result}
                  loading={importing} onClick={runImport}>
            导入 {rows.length ? `${rows.length} 行` : ''}
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {extra}
        <Text type="secondary" style={{ fontSize: 12 }}>
          第一步：下载模板并按「填表说明」整理数据；第二步：上传 xlsx/xls/csv 文件；第三步：核对预览并导入。
          表头须与模板一致。
        </Text>
        <Upload.Dragger
          accept=".xlsx,.xls,.csv"
          maxCount={1}
          showUploadList={false}
          beforeUpload={(file) => { setFileName(''); parseFile(file); return false }}
        >
          <p style={{ margin: '8px 0 4px' }}>
            <InboxOutlined style={{ fontSize: 32, color: '#3b6fe0' }} />
          </p>
          <p style={{ fontSize: 13 }}>{fileName || '点击或拖拽 Excel 文件到此处解析'}</p>
          <p style={{ fontSize: 12, color: '#999' }}>支持 .xlsx / .xls / .csv，第一个工作表将被导入</p>
        </Upload.Dragger>

        {fatal && <Alert type="error" showIcon message={fatal} />}

        {rows.length > 0 && !result && (
          <>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已解析 <b style={{ color: '#3b6fe0' }}>{rows.length}</b> 行数据，预览前 5 行：
            </Text>
            <Table
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              dataSource={rows.slice(0, 5).map((r, i) => ({ ...r, __i: i }))}
              rowKey="__i"
              columns={columns.map((c, i) => ({
                title: c.title, dataIndex: c.key, key: c.key, ellipsis: true, width: 120,
                // 首列（学号等身份列）固定：弹窗内横向滚动时保持可见
                fixed: i === 0 ? ('left' as const) : undefined,
                render: (v: string) => v || <Text type="secondary">-</Text>,
              }))}
            />
          </>
        )}

        {result && (
          <>
            <Alert
              type={result.errors?.length ? 'warning' : 'success'}
              showIcon
              message={result.errors?.length
                ? `导入完成：成功 ${result.created} 行，失败 ${result.errors.length} 行（失败行已跳过，其余数据已入库）`
                : `导入成功：共 ${result.created} 行数据已入库`}
            />
            {!!result.skipped?.length && (
              <Alert type="info" showIcon
                     message={`学号已存在被跳过：${result.skipped.join('、')}`} />
            )}
            {!!result.errors?.length && (
              <Table
                size="small"
                pagination={{ pageSize: 5 }}
                rowKey={(r) => `${r.row}-${r.message}`}
                dataSource={result.errors}
                columns={[{
                  title: '行号', dataIndex: 'row', key: 'row', width: 70,
                  render: (v: number) => <Tag>第 {v} 行</Tag>,
                }, {
                  title: '失败原因', dataIndex: 'message', key: 'message',
                }]}
              />
            )}
          </>
        )}
      </Space>
    </Modal>
  )
}
