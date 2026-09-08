import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EntityPage, { inApplyWindow } from '@/pages/student/EntityPage'
import { useMetaStore } from '@/store/meta'
import type { EntityMeta, EntityRecord, FieldMeta, MetaAll } from '@/types'

/**
 * 泛型实体页（注册表驱动核心组件）：
 *   契约渲染表格列/状态标签、生效记录锁定编辑删除、新增表单提交走服务端核定 payload
 * API 全桩化，只验证组件与契约的交互行为。
 */

vi.mock('@/api/modules', () => ({
  entityAPI: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    detail: vi.fn(),
    importEntities: vi.fn(),
  },
  aiAPI: { formAssist: vi.fn() },
  filesAPI: { upload: vi.fn(async () => []) },
  oplogAPI: { recordLogs: vi.fn(async () => ({ code: 0, data: [] })) },
}))
vi.mock('@/components/common/ExcelImportModal', () => ({ default: () => null }))
vi.mock('@/components/entity/RecordLogs', () => ({ default: () => null }))

import { entityAPI } from '@/api/modules'

const fields: FieldMeta[] = [
  { name: 'team', label: '团队名称', type: 'text', required: true, inTable: true, half: true },
  { name: 'theme', label: '实践主题', type: 'text', required: true, inTable: true, half: true },
  { name: 'type', label: '实践类型', type: 'text', required: true, inTable: true, half: true },
]

const def: EntityMeta = {
  key: 'practice', label: '社会实践活动', group: 'practice', deanReview: false,
  searchPlaceholder: '团队名称/主题', searchFields: ['team'], fields,
}

const meta = {
  practice_type: ['自主实践团队'],
  audit_flow: { publicityDays: 7, windowStart: '2000-01-01', windowEnd: '2099-12-31' },
} as unknown as MetaAll

const rows: EntityRecord[] = [
  { id: 'r1', status: '待审核', team: '三下乡小队', theme: '乡村支教', type: '自主实践团队',
    files: [], createdAt: '2026-07-01' },
  { id: 'r2', status: '通过', team: '已生效团', theme: '社区服务', type: '自主实践团队',
    files: [], createdAt: '2026-07-02' },
]

beforeEach(() => {
  vi.clearAllMocks()
  useMetaStore.setState({ loaded: true, meta, entities: [def] })
  // modules.ts 内部已 unwrap：mock 直接返回解包后的业务数据
  vi.mocked(entityAPI.list).mockResolvedValue({ list: rows, total: 2, page: 1, pageSize: 10 })
})

function renderPage() {
  return render(
    <AntdApp>
      <MemoryRouter initialEntries={['/entity/practice']}>
        <EntityPage />
      </MemoryRouter>
    </AntdApp>,
  )
}

describe('EntityPage（注册表契约驱动）', () => {
  it('按契约渲染表格列与状态标签', async () => {
    renderPage()

    expect(await screen.findByText('三下乡小队')).toBeInTheDocument()
    expect(screen.getByText('已生效团')).toBeInTheDocument()
    expect(screen.getByText('待审核')).toBeInTheDocument()
    expect(screen.getByText('共 2 条')).toBeInTheDocument()
    expect(entityAPI.list).toHaveBeenCalledWith('practice',
      expect.objectContaining({ page: 1, pageSize: 10 }))
  })

  it('已生效（通过）记录锁定编辑/删除，未生效记录可操作', async () => {
    renderPage()

    await screen.findByText('三下乡小队')
    // r1 待审核 → 有编辑/删除；r2 已通过 → 锁定
    expect(screen.getAllByText('删除')).toHaveLength(1)
    expect(screen.getAllByText('编辑')).toHaveLength(1)
    expect(screen.getAllByText('详情')).toHaveLength(2)
  })

  it('新增申请：表单按契约渲染，提交调用 create 并携带表单值', async () => {
    vi.mocked(entityAPI.create).mockResolvedValue({
      id: 'r3', status: '待审核', files: [], createdAt: '',
    })
    renderPage()

    fireEvent.click(await screen.findByText('新增申请'))
    expect(await screen.findByText('新增社会实践活动')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('团队名称'), { target: { value: '测试实践团' } })
    fireEvent.change(screen.getByLabelText('实践主题'), { target: { value: '校园垃圾分类调研' } })
    fireEvent.change(screen.getByLabelText('实践类型'), { target: { value: '自主实践团队' } })
    fireEvent.click(screen.getByText('提交申请'))

    await waitFor(() => expect(entityAPI.create).toHaveBeenCalledTimes(1))
    const [key, payload] = vi.mocked(entityAPI.create).mock.calls[0]
    expect(key).toBe('practice')
    expect(payload).toMatchObject({ team: '测试实践团', theme: '校园垃圾分类调研' })
    expect(await screen.findByText('提交成功，等待审核')).toBeInTheDocument()
  })

  it('必填校验：空表单提交被前端拦截，不发起请求', async () => {
    renderPage()

    fireEvent.click(await screen.findByText('新增申请'))
    fireEvent.click(await screen.findByText('提交申请'))

    await waitFor(() => expect(screen.getAllByText(/不能为空/).length).toBeGreaterThan(0))
    expect(entityAPI.create).not.toHaveBeenCalled()
  })

  it('搜索回车：带 keyword 重新拉取列表', async () => {
    renderPage()

    await screen.findByText('三下乡小队')
    fireEvent.change(screen.getByPlaceholderText('搜索团队名称/主题'),
      { target: { value: '三下乡' } })
    fireEvent.keyDown(screen.getByPlaceholderText('搜索团队名称/主题'), { key: 'Enter' })

    await waitFor(() => expect(entityAPI.list).toHaveBeenLastCalledWith('practice',
      expect.objectContaining({ keyword: '三下乡', page: 1 })))
  })
})

describe('申报窗口判断 inApplyWindow', () => {
  it('窗口内/窗口外/未配置三种口径', () => {
    expect(inApplyWindow({ windowStart: '2000-01-01', windowEnd: '2099-12-31' })).toBe(true)
    expect(inApplyWindow({ windowStart: '2026-01-01', windowEnd: '2026-01-02' })).toBe(false)
    expect(inApplyWindow(undefined)).toBe(true)   // 未配置窗口不限制
  })
})
