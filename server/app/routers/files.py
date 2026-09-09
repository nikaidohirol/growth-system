"""佐证材料上传 — 统一入口，实体创建通过 files[] 引用

防呆要点：
- 扩展名全量前置校验：任一文件违规则整批拒绝，杜绝「部分写盘成功」的孤儿文件
- 流式分块读取并按 10MB 上限截断：恶意超大文件不会先撑爆内存
- 写盘走线程池：不阻塞事件循环
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.security import get_current_user

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB / 文件
CHUNK = 1024 * 256


@router.post("/upload")
async def upload(files: list[UploadFile], _=Depends(get_current_user)):
    if not files:
        raise HTTPException(400, "未选择文件")

    # 第一遍：扩展名前置校验（全过才进入读取）
    for f in files:
        ext = ("." + f.filename.rsplit(".", 1)[-1].lower()) if "." in (f.filename or "") else ""
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"不支持的文件类型：{f.filename}")

    # 第二遍：流式读入内存，单文件超限即中断（此时尚未写任何盘）
    contents: list[tuple[str, str, bytes]] = []   # (原文件名, 扩展名, 字节)
    for f in files:
        ext = "." + f.filename.rsplit(".", 1)[-1].lower()
        buf = bytearray()
        while chunk := await f.read(CHUNK):
            buf.extend(chunk)
            if len(buf) > MAX_SIZE:
                raise HTTPException(400, f"文件超过 10MB：{f.filename}")
        contents.append((f.filename, ext, bytes(buf)))

    # 全部就绪才写盘
    day = datetime.now().strftime("%Y%m%d")
    folder = settings.UPLOAD_DIR + "/" + day
    await run_in_threadpool(os.makedirs, folder, exist_ok=True)
    saved = []
    for origin, ext, data in contents:
        name = f"{uuid.uuid4().hex[:12]}{ext}"
        await run_in_threadpool(lambda d=data, p=f"{folder}/{name}": _write(p, d))
        saved.append({"label": origin, "url": f"/files/{day}/{name}"})
    return {"code": 0, "data": saved}


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as out:
        out.write(data)
