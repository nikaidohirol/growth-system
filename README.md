# AI 学生成长发展系统（growth-system）v3.0

前后端分离的「学生第二课堂/成长档案」管理系统，面向 **学生 / 辅导员 / 院长** 三种角色，内置 **LangChain + RAG + SSE 流式** 的 AI 助手。

## 技术栈

| 端 | 技术 |
|---|---|
| 前端 | React 18 · TypeScript · Vite 5 · Ant Design 5 · Zustand · React Router 6 · ECharts · jspdf/html2canvas/xlsx |
| 后端 | FastAPI · SQLAlchemy 2 (async) · SQLite(aiosqlite) · JWT · LangChain/LangGraph · FAISS |
| AI | OpenAI 兼容协议多模型切换（DeepSeek/通义/自建）；RAG 知识库向量检索；SSE 流式对话；多轮记忆；TTS |

## 端口规范（重要）

- 后端：**8000**（`/api` 业务接口，`/files` 静态文件）
- 前端：**3000**（Vite dev server，`/api`、`/files` 代理到 8000）

## 快速启动

### 1. 后端

```bash
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # 按需填 LLM_API_KEY / EMBED_API_KEY，可留空离线运行
.venv\Scripts\python seed.py  # 初始化演示数据（12 名学生 + 辅导员 + 院长 + 样例记录）
.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. 前端

```bash
cd web
npm install
npm run dev     # http://localhost:3000
```

### 3. 演示账号（密码均为 123456）

| 角色 | 账号 |
|---|---|
| 学生 | 202300001 ~ 202300012 |
| 辅导员 | C0001 |
| 院长 | D0001 |

## 核心设计

### 实体注册表驱动（前后端一份契约）

13 类成长记录（社会实践/志愿服务/8 类创新创业/荣誉/证书/组织经历/入党）由 `entity_registry` 一处定义：

- 后端：通用 CRUD `/api/entities/{key}` + 统一审核流 `/api/audit/*`，新增实体类型零路由代码
- 前端：`EntityPage` 泛型组件按契约渲染表格/搜索/表单/详情，新增实体零页面代码
- 学分计算、审核 AI 建议、看板统计同样由注册表循环驱动

### AI 能力

- `POST /api/ai/chat`：SSE 流式对话（meta → delta → sources → done），多轮会话持久化
- `POST /api/ai/form-assist`：一句话描述 → AI 自动填充表单字段
- `POST /api/ai/audit-assist`：AI 审核建议（建议通过/驳回 + 理由）
- RAG：`knowledge_base/*.md` 按标题切块 → FAISS 向量索引；配置 `EMBED_API_KEY` 用 BGE-M3，未配置自动降级本地 TF-IDF 哈希向量（离线可用）
- LLM 未配置 API Key 时自动进入离线规则模式，全系统功能不受阻

### 权限与数据范围

JWT + RBAC 三角色；辅导员只能查看/审核名下学生，院长全局可见。

## 测试

```bash
cd server
.venv\Scripts\python -m pytest tests/ -v
```

## 目录结构

```
growth-system/
├── web/                    # React 前端
│   └── src/
│       ├── api/            # axios 封装 + API 模块
│       ├── components/     # 布局 / 泛型实体字段渲染 / AI 聊天抽屉 / EChart 封装
│       ├── pages/          # dashboard(三角色) / entity(13类通吃) / audit / students / export / info
│       ├── store/          # zustand（auth / meta）
│       └── types/          # 与后端契约一一对应的 TS 类型
└── server/                 # FastAPI 后端
    ├── app/
    │   ├── routers/        # auth / entities / audit / dashboard / users / experience / files / ai
    │   ├── services/       # entity_registry / credits / agent / llm / rag
    │   └── models/         # SQLAlchemy 2 async 模型
    ├── knowledge_base/     # RAG 知识库（markdown）
    ├── seed.py             # 演示数据
    └── tests/              # pytest 接口测试
```
