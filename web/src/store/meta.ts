import { create } from 'zustand'
import { metaAPI } from '@/api/modules'
import type { EntityMeta, MetaAll } from '@/types'

interface MetaState {
  meta: MetaAll | null
  entities: EntityMeta[]
  loaded: boolean
  load: () => Promise<void>
  entityByKey: (key: string) => EntityMeta | undefined
}

// 业务字典 + 实体契约全局缓存（一次拉取，处处使用）
export const useMetaStore = create<MetaState>()((set, get) => ({
  meta: null,
  entities: [],
  loaded: false,
  load: async () => {
    if (get().loaded) return
    const [meta, entities] = await Promise.all([metaAPI.all(), metaAPI.entities()])
    set({ meta, entities, loaded: true })
  },
  entityByKey: (key) => get().entities.find((e) => e.key === key),
}))
