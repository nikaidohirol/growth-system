import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App, Button, Drawer, Dropdown, Empty, Input, Popconfirm, Space, Spin, Tag, Tooltip,
} from 'antd'
import {
  AudioOutlined, DeleteOutlined, PlusOutlined, SendOutlined, SoundOutlined,
} from '@ant-design/icons'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { aiAPI } from '@/api/modules'
import { ssePost } from '@/api/http'
import type { ChatMessageItem, ChatSessionItem } from '@/types'

const SUGGESTIONS = [
  '社会实践和志愿服务怎么算学分？',
  '我的创新创业学分够毕业要求吗？',
  '论文学分的认定标准是什么？',
  '申请被驳回后该怎么办？',
]

interface Bubble extends ChatMessageItem {
  streaming?: boolean
}

/** AI 助手：SSE 流式对话 + 多会话 + 知识库来源 + 语音朗读（讯飞/浏览器降级） */
export default function AIChatDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message: antdMsg } = App.useApp()
  const [sessions, setSessions] = useState<ChatSessionItem[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [mode, setMode] = useState<'agent' | 'offline'>('agent')
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadSessions = useCallback(async () => {
    setSessions(await aiAPI.sessions().catch(() => []))
  }, [])

  useEffect(() => {
    if (open) loadSessions()
  }, [open, loadSessions])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [bubbles])

  const openSession = async (sid: string) => {
    setActiveSession(sid)
    setBubbles(await aiAPI.sessionMessages(sid).catch(() => []))
  }

  const newSession = () => {
    setActiveSession(null)
    setBubbles([])
    setInput('')
  }

  const removeSession = async (sid: string) => {
    await aiAPI.removeSession(sid)
    if (sid === activeSession) newSession()
    loadSessions()
  }

  const speak = async (text: string) => {
    const audioBuf = await aiAPI.tts(text.slice(0, 600))
    if (audioBuf) {
      const url = URL.createObjectURL(new Blob([audioBuf], { type: 'audio/mpeg' }))
      new Audio(url).play()
      return
    }
    // 降级：浏览器 Web Speech
    const synth = window.speechSynthesis
    if (!synth) return antdMsg.warning('当前环境不支持语音朗读')
    synth.cancel()
    const utter = new SpeechSynthesisUtterance(text.slice(0, 600))
    utter.lang = 'zh-CN'
    synth.speak(utter)
  }

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || streaming) return
    setInput('')
    setBubbles((prev) => [...prev,
      { id: `u-${Date.now()}`, role: 'user', content, sources: [] },
      { id: `a-${Date.now()}`, role: 'assistant', content: '', sources: [], streaming: true },
    ])
    setStreaming(true)
    abortRef.current = new AbortController()
    const patchLast = (patch: Partial<Bubble>) =>
      setBubbles((prev) => prev.map((b, i) => (i === prev.length - 1 ? { ...b, ...patch } : b)))

    try {
      await ssePost('/api/ai/chat', { message: content, sessionId: activeSession }, {
        signal: abortRef.current.signal,
        onEvent: (event, data) => {
          if (event === 'meta') {
            setActiveSession(data.sessionId)
            setMode(data.mode)
            if (!activeSession) loadSessions()
          } else if (event === 'token') {
            setBubbles((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              next[next.length - 1] = { ...last, content: last.content + data.delta }
              return next
            })
          } else if (event === 'sources') {
            patchLast({ sources: data.list ?? [] })
          } else if (event === 'error') {
            antdMsg.error(data.message)
          }
        },
      })
    } catch (e) {
      if ((e as Error).name !== 'AbortError') antdMsg.error('连接中断，请重试')
    } finally {
      patchLast({ streaming: false })
      setStreaming(false)
      abortRef.current = null
      loadSessions()
    }
  }

  const sessionMenu = {
    items: sessions.map((s) => ({
      key: s.id,
      label: (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          gap: 8, maxWidth: 220,
        }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                onClick={() => openSession(s.id)}>
            {s.title}
          </span>
          <Popconfirm
            title="删除该会话？"
            onConfirm={(e) => { e?.stopPropagation(); removeSession(s.id) }}
            onCancel={(e) => e?.stopPropagation()}
          >
            <DeleteOutlined
              style={{ color: '#999' }}
              onClick={(e) => e.stopPropagation()}
            />
          </Popconfirm>
        </div>
      ),
    })),
  }

  return (
    <Drawer
      title={
        <Space>
          AI 助手
          <Tag color={mode === 'agent' ? 'purple' : 'orange'}>
            {mode === 'agent' ? 'Agent 模式' : '离线知识库'}
          </Tag>
        </Space>
      }
      placement="right"
      width={460}
      open={open}
      onClose={onClose}
      destroyOnClose
      extra={
        <Space>
          <Dropdown menu={sessionMenu} placement="bottomRight" disabled={!sessions.length}>
            <Button size="small">历史会话</Button>
          </Dropdown>
          <Button size="small" icon={<PlusOutlined />} onClick={newSession}>新对话</Button>
        </Space>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ flex: 1, overflow: 'auto', paddingRight: 4 }}>
          {bubbles.length === 0 && (
            <div style={{ paddingTop: 40 }}>
              <Empty description="有什么可以帮你？" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              <Space direction="vertical" style={{ width: '100%', padding: '0 12px' }}>
                {SUGGESTIONS.map((q) => (
                  <Button key={q} block size="small" style={{ textAlign: 'left' }}
                          onClick={() => send(q)}>
                    {q}
                  </Button>
                ))}
              </Space>
            </div>
          )}
          {bubbles.map((b) => (
            <div key={b.id} className={`chat-msg ${b.role === 'user' ? 'user' : 'ai'}`}>
              <div className="chat-bubble">
                {b.role === 'assistant' ? (
                  <>
                    <Markdown remarkPlugins={[remarkGfm]}>
                      {b.content || (b.streaming ? '…' : '')}
                    </Markdown>
                    {b.streaming && <Spin size="small" />}
                    {b.sources?.length > 0 && (
                      <div style={{ marginTop: 6, borderTop: '1px dashed #ddd', paddingTop: 4 }}>
                        {b.sources.map((s, i) => (
                          <Tooltip key={i} title={s.content} placement="left">
                            <Tag style={{ marginBottom: 4 }}>{s.source} · {s.title}</Tag>
                          </Tooltip>
                        ))}
                      </div>
                    )}
                    {!b.streaming && b.content && (
                      <Tooltip title="朗读">
                        <Button type="text" size="small" icon={<SoundOutlined />}
                                onClick={() => speak(b.content)} />
                      </Tooltip>
                    )}
                  </>
                ) : b.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div style={{ paddingTop: 10, borderTop: '1px solid #eee' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={() => send()}
              placeholder="询问学分规则 / 查询个人进度…"
              disabled={streaming}
            />
            {streaming ? (
              <Button danger onClick={() => abortRef.current?.abort()}>停止</Button>
            ) : (
              <Button type="primary" icon={<SendOutlined />} onClick={() => send()} />
            )}
          </Space.Compact>
          <div style={{ fontSize: 11, color: '#bbb', marginTop: 6 }}>
            <AudioOutlined /> 回答基于校内知识库与你的真实数据，涉及认定标准请以教务文件为准
          </div>
        </div>
      </div>
    </Drawer>
  )
}
