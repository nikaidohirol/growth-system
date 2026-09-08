"""佐证材料上传 — 统一入口，实体创建通过 files[] 引用"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.config import settings
from app.security import get_current_user

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload(files: list[UploadFile], _=Depends(get_current_user)):
    if not files:
        raise HTTPException(400, "未选择文件")
    saved, day = [], datetime.now().strftime("%Y%m%d")
    folder = settings.UPLOAD_DIR + "/" + day
    import os
    os.makedirs(folder, exist_ok=True)
    for f in files:
        ext = ("." + f.filename.rsplit(".", 1)[-1].lower()) if "." in (f.filename or "") else ""
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"不支持的文件类型：{f.filename}")
        content = await f.read()
        if len(content) > MAX_SIZE:
            raise HTTPException(400, f"文件超过 10MB：{f.filename}")
        name = f"{uuid.uuid4().hex[:12]}{ext}"
        with open(f"{folder}/{name}", "wb") as out:
            out.write(content)
        saved.append({"label": f.filename, "url": f"/files/{day}/{name}"})
    return {"code": 0, "data": saved}
