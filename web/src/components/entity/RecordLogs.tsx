import { useEffect, useState } from 'react'
import { Empty, Skeleton, Tag, Timeline, Typography } from 'antd'
import { oplogAPI } from '@/api/modules'
import type { RecordLog } from '@/types'

const { Text } = Typography

/** 动作 → 时间线颜色/文案 */
const ACTION_META: Record<RecordLog['action'], { color: string; label: string }> = {
  create: { color: 'blue', label: '申报' },
  update: { color: 'orange', label: '修改' },
  delete: { color: 'red', label: '删除' },
  audit: { color: 'green', label: '审核' },
  login: { color: 'gray', label: '登录' },
}

/**
 * 单条记录的操作日志时间线（合规留痕展示）
 * 嵌入 EntityPage / AuditCenter 的详情弹窗，弹窗打开时加载
 */
export default function RecordLogs({ entityKey, recordId }: {
  entityKey: string
  recordId?: string
}) {
  const [logs, setLogs] = useState<RecordLog[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!recordId) return
    setLoading(true)
    oplogAPI.recordLogs(entityKey, recordId)
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false))
  }, [entityKey, recordId])

  if (!recordId) return null
  if (loading) return <Skeleton active paragraph={{ rows: 2 }} style={{ marginTop: 16 }} />
  if (!logs.length) return <Empty description="暂无操作记录" style={{ margin: '16px 0' }} />

  return (
    <Timeline
      style={{ marginTop: 16 }}
      items={logs.map((log) => {
        const meta = ACTION_META[log.action] ?? ACTION_META.update
        return {
          color: meta.color,
          children: (
            <>
              <Tag color={meta.color} style={{ marginRight: 8 }}>{meta.label}</Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {log.createdAt} · {log.operatorName}
              </Text>
              <div style={{ fontSize: 13 }}>{log.summary}</div>
            </>
          ),
        }
      })}
    />
  )
}
