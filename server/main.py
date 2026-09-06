"""AI 学生成长发展系统 — FastAPI 后端入口

端口规范：后端 8000（/api 业务接口，/files 静态文件），前端 3000
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.database import init_db
from app.routers import (ai, audit, auth, dashboard, entities, experience, files,
                         logs, meta_router, notifications, objections, users)

logger = logging.getLogger("growth-system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 预热 RAG 向量索引
    from app.services.rag import build_vectorstore
    vs = build_vectorstore()
    logger.info("知识库向量索引：%s", "已构建" if vs else "空（knowledge_base 无文档）")
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files", StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False), name="files")

for r in (auth, meta_router, entities, audit, objections, dashboard, users, experience,
          files, logs, ai, notifications):
    app.include_router(r.router)
app.include_router(users.gpa_router)


@app.get("/api/health")
async def health():
    from app.services.llm import llm_available
    return {"code": 0, "data": {"status": "ok", "llm": "online" if llm_available() else "offline"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
