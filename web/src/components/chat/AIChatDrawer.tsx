import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App, Button, Drawer, Dropdown, Empty, Image, Input, Popconfirm, Space, Spin, Tag, Tooltip,
  Upload,
} from 'antd'
import {
  AudioOutlined, DeleteOutlined, LoadingOutlined, PictureOutlined, PlusOutlined,
  SendOutlined, SoundOutlined,
} from '@ant-design/icons'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { aiAPI, filesAPI } from '@/api/modules'
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

// Web Speech 语音识别（Chrome/Edge），不支持时优雅降级
function getSpeechRecognition(): any {
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const len = chunks.reduce((n, c) => n + c.length, 0)
  const out = new Float32Array(len)
  let off = 0
  chunks.forEach((c) => { out.set(c, off); off += c.length })
  return out
}

/** 线性插值重采样到目标采样率 */
function resample(data: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return data
  const len = Math.round(data.length / (from / to))
  const out = new Float32Array(len)
  for (let i = 0; i < len; i++) {
    const pos = i * (from / to)
    const idx = Math.floor(pos)
    const a = data[idx] ?? 0
    const b = data[idx + 1] ?? a
    out[i] = a + (b - a) * (pos - idx)
  }
  return out
}

/** Float32 采样合并 → 16kHz 单声道 PCM s16le（讯飞 RTASR 要求） */
function toPcm16k(chunks: Float32Array[], srcRate: number): Blob {
  const data = resample(mergeChunks(chunks), srcRate, 16000)
  const view = new DataView(new ArrayBuffer(data.length * 2))
  for (let i = 0; i < data.length; i++) {
    const s = Math.max(-1, Math.min(1, data[i]))
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([view.buffer], { type: 'audio/pcm' })
}

/** AI 助手：SSE 流式对话 + 多会话 + 知识库来源 + 语音朗读（讯飞/浏览器降级） */
export default function AIChatDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message: antdMsg, modal } = App.useApp()
  const [sessions, setSessions] = useState<ChatSessionItem[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [mode, setMode] = useState<'agent' | 'offline'>('agent')
  const [pendingImages, setPendingImages] = useState<{ label: string; url: string }[]>([])
  const [listening, setListening] = useState(false)
  const [serverAsr, setServerAsr] = useState(false)
  const [recognizing, setRecognizing] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const recRef = useRef<any>(null)
  const listenTimerRef = useRef<number | null>(null)
  // 讯飞服务端录音资源
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const chunksRef = useRef<Float32Array[]>([])
  const recordingRef = useRef(false)

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

  const clearAllSessions = () => {
    modal.confirm({
      title: '清空全部历史会话？',
      content: `共 ${sessions.length} 条会话及其消息，删除后不可恢复`,
      okText: '全部删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await aiAPI.clearSessions()
        newSession()
        loadSessions()
        antdMsg.success('历史会话已清空')
      },
    })
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

  const stopWebSpeech = useCallback(() => {
    if (listenTimerRef.current) {
      clearTimeout(listenTimerRef.current)
      listenTimerRef.current = null
    }
    try {
      recRef.current?.abort?.()
    } catch { /* 已停止则忽略 */ }
    recRef.current = null
    setListening(false)
  }, [])

  /** 停止服务端录音；discard=true 时直接丢弃（抽屉关闭），否则送讯飞转写 */
  const stopServerRecording = useCallback(async (discard = false) => {
    if (!recordingRef.current) return
    recordingRef.current = false
    if (listenTimerRef.current) {
      clearTimeout(listenTimerRef.current)
      listenTimerRef.current = null
    }
    try { processorRef.current?.disconnect() } catch { /* noop */ }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    const ctx = audioCtxRef.current
    const chunks = chunksRef.current
    const srcRate = ctx?.sampleRate ?? 16000
    try { await ctx?.close() } catch { /* noop */ }
    processorRef.current = null
    streamRef.current = null
    audioCtxRef.current = null
    chunksRef.current = []
    setListening(false)
    if (discard || !chunks.length) return

    setRecognizing(true)
    try {
      const { text } = await aiAPI.asr(toPcm16k(chunks, srcRate))
      if (text.trim()) setInput((prev) => (prev ? `${prev} ${text.trim()}` : text.trim()))
      else antdMsg.info('没有识别到内容，请靠近麦克风再说一次')
    } catch (e: any) {
      if (e?.response?.status === 501) {
        // 服务端未配置讯飞 → 静默切换浏览器识别（501 提示已由 http 拦截器弹出）
        setServerAsr(false)
      }
      // 其余错误（讯飞错误码 / 超时）detail 已由拦截器提示，不再重复弹
    } finally {
      setRecognizing(false)
    }
  }, [antdMsg])

  const startServerRecording = async () => {
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
    } catch {
      return antdMsg.error('无法访问麦克风，请在浏览器地址栏允许麦克风权限后重试')
    }
    streamRef.current = stream
    const ctx = new AudioContext({ sampleRate: 16000 })
    audioCtxRef.current = ctx
    const processor = ctx.createScriptProcessor(4096, 1, 1)
    processorRef.current = processor
    chunksRef.current = []
    processor.onaudioprocess = (e) => {
      if (recordingRef.current) chunksRef.current.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }
    ctx.createMediaStreamSource(stream).connect(processor)
    // 经零增益节点接到输出，保证回调持续触发且不外放麦克风
    const sink = ctx.createGain()
    sink.gain.value = 0
    processor.connect(sink)
    sink.connect(ctx.destination)
    recordingRef.current = true
    setListening(true)
    // 上限 60 秒自动停止送识别
    listenTimerRef.current = window.setTimeout(() => { void stopServerRecording() }, 60000)
  }

  // 打开抽屉时探测服务端讯飞识别是否可用
  useEffect(() => {
    if (open) aiAPI.asrStatus().then((r) => setServerAsr(r.available)).catch(() => setServerAsr(false))
  }, [open])

  // 关闭抽屉时释放麦克风与识别器（服务端录音直接丢弃）
  useEffect(() => {
    if (!open) {
      stopWebSpeech()
      if (recordingRef.current) void stopServerRecording(true)
    }
  }, [open, stopWebSpeech, stopServerRecording])

  const startWebSpeech = () => {
    const SR = getSpeechRecognition()
    if (!SR) return antdMsg.warning('当前浏览器不支持语音输入（推荐使用 Chrome / Edge）')
    if (recRef.current) stopWebSpeech()

    const rec = new SR()
    rec.lang = 'zh-CN'
    rec.interimResults = true
    rec.continuous = false
    rec.onresult = (e: any) => {
      const text = Array.from(e.results as ArrayLike<any>)
        .map((r) => r[0].transcript).join('')
      setInput(text)
    }
    rec.onend = () => {
      if (listenTimerRef.current) {
        clearTimeout(listenTimerRef.current)
        listenTimerRef.current = null
      }
      setListening(false)
    }
    rec.onerror = (e: any) => {
      stopWebSpeech()
      const code = e?.error
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        antdMsg.error('麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试')
      } else if (code === 'network') {
        antdMsg.error('语音服务连接失败，请检查网络后重试（Chrome 需访问谷歌语音服务），或直接键盘输入')
      } else if (code === 'audio-capture') {
        antdMsg.error('未检测到麦克风设备，请检查设备连接')
      } else if (code === 'no-speech') {
        antdMsg.info('没有听到说话，请点击麦克风后再说话')
      }
      // aborted：主动停止，静默处理
    }
    recRef.current = rec
    setListening(true)
    try {
      rec.start()
    } catch {
      stopWebSpeech()
      return antdMsg.warning('语音启动失败，请重试')
    }
    // 兜底：最长聆听 20s 自动停止，避免"正在聆听"卡死
    listenTimerRef.current = window.setTimeout(stopWebSpeech, 20000)
  }

  const toggleVoice = () => {
    if (recognizing) return
    if (listening) {
      if (recordingRef.current) void stopServerRecording()
      else stopWebSpeech()
      return
    }
    if (serverAsr) return void startServerRecording()
    return startWebSpeech()
  }

  const uploadImages = async (files: File[]) => {
    const imgs = files.filter((f) => f.type.startsWith('image/') && f.size <= 10 * 1024 * 1024)
    if (!imgs.length) return antdMsg.warning('仅支持 10MB 内的图片')
    const saved = await filesAPI.upload(imgs).catch(() => [])
    setPendingImages((prev) => [...prev, ...saved].slice(0, 4))
  }

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content && !pendingImages.length) return
    if (streaming) return
    const images = pendingImages.map((p) => p.url)
    const shown = content + images.map((u) => `\n\n![图片](${u})`).join('')
    setInput('')
    setPendingImages([])
    setBubbles((prev) => [...prev,
      { id: `u-${Date.now()}`, role: 'user', content: shown, sources: [] },
      { id: `a-${Date.now()}`, role: 'assistant', content: '', sources: [], streaming: true },
    ])
    setStreaming(true)
    abortRef.current = new AbortController()
    const patchLast = (patch: Partial<Bubble>) =>
      setBubbles((prev) => prev.map((b, i) => (i === prev.length - 1 ? { ...b, ...patch } : b)))

    try {
      await ssePost('/api/ai/chat', { message: content || '请看图片', images, sessionId: activeSession }, {
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
    items: [
      { key: '__clear__', danger: true, icon: <DeleteOutlined />,
        label: '清空全部', onClick: clearAllSessions },
      { type: 'divider' as const },
      ...sessions.map((s) => ({
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
    ],
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
                <Markdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    img: (props) => (
                      <Image src={props.src} alt={props.alt ?? ''} width={180}
                             style={{ borderRadius: 6, display: 'block' }} />
                    ),
                  }}
                >
                  {b.role === 'assistant' ? (b.content || (b.streaming ? '…' : '')) : b.content}
                </Markdown>
                {b.role === 'assistant' && (
                  <>
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
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div style={{ paddingTop: 10, borderTop: '1px solid #eee' }}>
          {pendingImages.length > 0 && (
            <Space wrap size={6} style={{ marginBottom: 8 }}>
              {pendingImages.map((p) => (
                <span key={p.url} style={{ position: 'relative', display: 'inline-block' }}>
                  <Image src={p.url} width={52} height={52}
                         style={{ objectFit: 'cover', borderRadius: 6 }} />
                  <DeleteOutlined
                    style={{
                      position: 'absolute', top: -6, right: -6, color: '#999',
                      background: '#fff', borderRadius: '50%', padding: 2, cursor: 'pointer',
                    }}
                    onClick={() => setPendingImages((prev) => prev.filter((x) => x.url !== p.url))} />
                </span>
              ))}
            </Space>
          )}
          <Space.Compact style={{ width: '100%' }}>
            <Upload
              accept="image/*" multiple showUploadList={false}
              customRequest={({ file }) => uploadImages([file as File])}
            >
              <Button icon={<PictureOutlined />} disabled={streaming}
                      title="发送图片（AI 视觉理解）" />
            </Upload>
            <Tooltip title={!serverAsr && !getSpeechRecognition()
              ? '当前浏览器不支持语音输入（推荐 Chrome / Edge）'
              : listening ? '停止录音'
              : serverAsr ? '语音输入（讯飞识别）' : '语音输入（浏览器识别）'}>
              <Button
                icon={recognizing ? <LoadingOutlined /> : <AudioOutlined />}
                disabled={streaming || recognizing}
                danger={listening}
                title={listening ? '停止录音' : '语音输入'}
                onClick={toggleVoice}
              />
            </Tooltip>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={() => send()}
              placeholder={listening ? '正在聆听…请说话'
                : recognizing ? '正在识别语音…' : '询问学分规则 / 查询个人进度…'}
              disabled={streaming}
            />
            {streaming ? (
              <Button danger onClick={() => abortRef.current?.abort()}>停止</Button>
            ) : (
              <Button type="primary" icon={<SendOutlined />}
                      onClick={() => send()} disabled={!input.trim() && !pendingImages.length} />
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
