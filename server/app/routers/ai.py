"""AI 能力路由：SSE 流式对话（含多模态图片理解）/ 表单智能填充 / 审核建议 / 讯飞 TTS / 会话管理"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import ChatMessage, ChatSession, User, get_db
from app.models.schemas import AuditAssistReq, ChatReq, FormAssistReq
from app.security import get_current_user
from app.services.agent import (build_agent, ensure_thread, stream_agent,
                                stream_offline)
from app.services.entity_registry import ENTITY_REGISTRY
from app.services.llm import llm_available
from app.services.rag import search_knowledge

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------- 对话 ----------------
async def _load_history(db: AsyncSession, session_id: str) -> list[dict]:
    rows = (await db.execute(select(ChatMessage).where(
        ChatMessage.sessionId == session_id).order_by(ChatMessage.createdAt))).scalars().all()
    return [{"role": r.role, "content": r.content} for r in rows]


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "gif": "image/gif", "webp": "image/webp"}


def _build_multimodal_message(message: str, images: list[str]):
    """把 /files 图片 URL 转成 base64 data URL，构造多模态 HumanMessage（仅图片后缀）"""
    from langchain_core.messages import HumanMessage
    root = Path(settings.UPLOAD_DIR).resolve()
    parts: list[dict] = []
    for url in images[:4]:
        rel = url.lstrip("/")
        if rel.startswith("files/"):  # 去掉静态挂载前缀，保留日期子目录
            rel = rel[len("files/"):]
        path = (root / rel).resolve()
        if not path.is_relative_to(root):  # 防路径穿越
            continue
        suffix = path.suffix.lstrip(".").lower()
        if not path.is_file() or suffix not in _IMG_MIME:
            continue
        b64 = base64.b64encode(path.read_bytes()).decode()
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{_IMG_MIME[suffix]};base64,{b64}"}})
    parts.append({"type": "text", "text": message})
    return HumanMessage(content=parts)


@router.post("/chat")
async def chat(req: ChatReq, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    """SSE 流式对话：meta → token* → sources → done；images 走多模态视觉理解"""
    # 会话管理
    if req.sessionId:
        session = await db.get(ChatSession, req.sessionId)
        if session is None or session.sid != user.id:
            raise HTTPException(404, "会话不存在")
    else:
        session = ChatSession(sid=user.id, title=req.message[:16])
        db.add(session)
        await db.flush()

    history = await _load_history(db, session.id)
    # 持久化：图片以 markdown 形式并入用户消息（历史记录 react-markdown 可直接渲染）
    stored = req.message + "".join(f"\n\n![图片]({u})" for u in req.images)
    user_msg = ChatMessage(sessionId=session.id, role="user", content=stored)
    db.add(user_msg)
    await db.commit()

    online = llm_available()

    async def gen():
        yield sse("meta", {"sessionId": session.id, "title": session.title,
                           "mode": "agent" if online else "offline"})
        full_text = []
        sources: list[dict] = []
        try:
            agent = build_agent()
            if agent is not None:
                await ensure_thread(agent, session.id, history)
                message = (_build_multimodal_message(req.message, req.images)
                           if req.images else req.message)
                async for delta in stream_agent(agent, session.id, message, db, user):
                    full_text.append(delta)
                    yield sse("token", {"delta": delta})
                sources = search_knowledge(req.message, k=3)
            else:
                if req.images:
                    notice = ("（当前为离线模式，图片理解需在 .env 配置 LLM_API_KEY，"
                              "以下仅就文字内容回答）\n\n")
                    full_text.append(notice)
                    yield sse("token", {"delta": notice})
                async for delta in stream_offline(req.message, history):
                    full_text.append(delta)
                    yield sse("token", {"delta": delta})
                sources = search_knowledge(req.message, k=3)
        except Exception as e:  # 单次对话失败不应拖垮连接
            yield sse("error", {"message": f"AI 服务异常：{e}"})
        text = "".join(full_text)
        db.add(ChatMessage(sessionId=session.id, role="assistant",
                           content=text, sources=sources))
        await db.commit()
        yield sse("sources", {"list": sources})
        yield sse("done", {"sessionId": session.id})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions")
async def sessions(user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ChatSession).where(ChatSession.sid == user.id)
                             .order_by(ChatSession.createdAt.desc()))).scalars().all()
    return {"code": 0, "data": [{"id": r.id, "title": r.title, "createdAt": r.createdAt}
                                for r in rows]}


@router.get("/sessions/{sid}/messages")
async def session_messages(sid: str, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, sid)
    if session is None or session.sid != user.id:
        raise HTTPException(404, "会话不存在")
    rows = (await db.execute(select(ChatMessage).where(
        ChatMessage.sessionId == sid).order_by(ChatMessage.createdAt))).scalars().all()
    return {"code": 0, "data": [{"id": r.id, "role": r.role, "content": r.content,
                                 "sources": r.sources or []} for r in rows]}


@router.delete("/sessions/{sid}")
async def del_session(sid: str, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, sid)
    if session is None or session.sid != user.id:
        raise HTTPException(404, "会话不存在")
    await db.execute(delete(ChatMessage).where(ChatMessage.sessionId == sid))
    await db.delete(session)
    await db.commit()
    return {"code": 0}


# ---------------- 表单智能填充 ----------------
FORM_PROMPT = """你是学生成长系统的填表助手。根据用户的自然语言描述，为「{label}」申请表生成字段值。
字段定义（JSON）：
{fields}
已知字典选项：
{options}
只输出 JSON 对象（键为字段名，值为字符串/数字），不要输出其他内容。描述中未提及的字段留空字符串。"""


@router.post("/form-assist")
async def form_assist(req: FormAssistReq, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    from app.meta import META_ALL
    e = ENTITY_REGISTRY.get(req.entityKey)
    if e is None:
        raise HTTPException(404, "未知实体")
    fields = {f.name: f.label for f in e.fields}
    options = {f.name: (META_ALL.get(f.options) if f.options else None)
               for f in e.fields if f.options}

    model = None
    from app.services.llm import get_chat_model
    model = get_chat_model()
    if model is None:
        raise HTTPException(503, "未配置 LLM_API_KEY，表单智能填充不可用")
    from langchain_core.messages import HumanMessage
    resp = await model.ainvoke([HumanMessage(content=FORM_PROMPT.format(
        label=e.label, fields=json.dumps(fields, ensure_ascii=False),
        options=json.dumps(options, ensure_ascii=False, default=str)) + 
        f"\n\n用户描述：{req.description}")])
    try:
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        data = json.loads(content[content.index("{"): content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        data = {}
    return {"code": 0, "data": {"fields": data}}


# ---------------- 审核建议（辅导员） ----------------
AUDIT_PROMPT = """你是学生成长系统的审核助手。请对下面这条「{label}」申请给出审核建议。
申请数据：{item}
审核要点：
1. 字段是否完整、日期是否合理（如结束时间不早于开始时间）；
2. 级别/奖项与学分匹配是否在合理范围；
3. 是否存在明显夸大或矛盾之处。
输出 JSON：{{"suggestion": "通过|驳回|需人工复核", "reason": "50字以内理由"}}"""


@router.post("/audit-assist")
async def audit_assist(req: AuditAssistReq, user: User = Depends(get_current_user)):
    from app.services.llm import get_chat_model
    model = get_chat_model()
    if model is None:
        # 离线规则兜底：字段完整性与日期合理性检查
        item = req.item
        issues = [k for k, v in item.items() if v in (None, "", []) and k not in ("id", "files")]
        suggestion = "需人工复核" if issues else "通过"
        reason = ("字段缺失：" + "、".join(issues)) if issues else "字段完整，未发现明显异常，建议人工确认材料后通过"
        return {"code": 0, "data": {"suggestion": suggestion, "reason": reason}}
    e = ENTITY_REGISTRY.get(req.entityKey)
    if e is None:
        raise HTTPException(404, "未知实体")
    from langchain_core.messages import HumanMessage
    resp = await model.ainvoke([HumanMessage(content=AUDIT_PROMPT.format(
        label=e.label, item=json.dumps(req.item, ensure_ascii=False, default=str)))])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        data = json.loads(content[content.index("{"): content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        data = {"suggestion": "需人工复核", "reason": content[:100]}
    return {"code": 0, "data": data}


# ---------------- 科大讯飞 TTS（可选） ----------------
def _iflytek_auth_url() -> str:
    from urllib.parse import urlencode
    url = "wss://tts-api.xfyun.cn/v2/tts"
    now_ms = str(int(time.time() * 1000))
    signature_origin = f"host: tts-api.xfyun.cn\ndate: {now_ms}\nGET /v2/tts HTTP/1.1"
    import hmac
    signature = base64.b64encode(hmac.new(
        settings.IFLYTEK_API_SECRET.encode(), signature_origin.encode(),
        hashlib.sha256).digest()).decode()
    authorization = base64.b64encode(
        f'api_key="{settings.IFLYTEK_API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'.encode()).decode()
    return f"{url}?{urlencode({'authorization': authorization, 'date': now_ms, 'host': 'tts-api.xfyun.cn'})}"


@router.post("/tts")
async def tts(payload: dict, user: User = Depends(get_current_user)):
    """讯飞在线合成；未配置 Key 返回 501，前端降级浏览器 Web Speech"""
    text = (payload.get("text") or "")[:800]
    if not text:
        raise HTTPException(400, "文本为空")
    if not (settings.IFLYTEK_APP_ID and settings.IFLYTEK_API_KEY and settings.IFLYTEK_API_SECRET):
        raise HTTPException(501, "未配置讯飞 TTS，请使用浏览器合成")
    try:
        import websockets
    except ImportError:
        raise HTTPException(501, "服务端未安装 websockets 库")

    audio = bytearray()

    async def run():
        async with websockets.connect(_iflytek_auth_url()) as ws:
            await ws.send(json.dumps({
                "common": {"app_id": settings.IFLYTEK_APP_ID},
                "business": {"aue": "lame", "sfl": 1, "vcn": "xiaoyan", "speed": 50},
                "data": {"status": 2, "text": base64.b64encode(text.encode()).decode()},
            }))
            async for msg in ws:
                d = json.loads(msg)
                if d.get("code") != 0:
                    raise HTTPException(500, f"讯飞 TTS 错误：{d.get('message')}")
                if d["data"].get("audio"):
                    audio.extend(base64.b64decode(d["data"]["audio"]))
                if d["data"].get("status") == 2:
                    break

    await asyncio.wait_for(run(), timeout=20)
    return StreamingResponse(iter([bytes(audio)]), media_type="audio/mpeg")


# ---------------- 科大讯飞 实时语音听写 ASR（可选，为空时前端降级浏览器识别） ----------------
def _rtasr_auth_url() -> str:
    """RTASR 鉴权：signa = base64( HmacSHA1(key=apiKey, msg=MD5(appid+ts)) )，由 urlencode 统一编码一次"""
    from urllib.parse import urlencode
    ts = str(int(time.time()))
    md5 = hashlib.md5(f"{settings.IFLYTEK_APP_ID}{ts}".encode()).hexdigest()
    signa = base64.b64encode(hmac.new(
        settings.IFLYTEK_API_KEY.encode(), md5.encode(), hashlib.sha1).digest()).decode()
    return f"wss://rtasr.xfyun.cn/v1/ws?{urlencode({'appid': settings.IFLYTEK_APP_ID, 'ts': ts, 'signa': signa})}"


@router.get("/asr/status")
async def asr_status(user: User = Depends(get_current_user)):
    return {"code": 0, "data": {"available": bool(settings.IFLYTEK_APP_ID and settings.IFLYTEK_API_KEY)}}


@router.post("/asr")
async def asr(audio: UploadFile = File(...), user: User = Depends(get_current_user)):
    """一句话转写：前端上传 16k16bit 单声道 PCM，走讯飞实时语音听写，返回识别文本"""
    if not (settings.IFLYTEK_APP_ID and settings.IFLYTEK_API_KEY):
        raise HTTPException(501, "未配置讯飞语音识别，请使用浏览器识别")
    try:
        import websockets
    except ImportError:
        raise HTTPException(501, "服务端未安装 websockets 库")

    pcm = await audio.read()
    if not pcm:
        raise HTTPException(400, "音频为空")
    if len(pcm) > 16000 * 2 * 60:  # 最长 60 秒
        raise HTTPException(400, "录音超过 60 秒，请缩短后重试")

    finals: list[str] = []
    # 常见错误码 → 用户可操作的提示
    asr_hints = {
        "10105": "APP_ID 无效或该应用未开通「实时语音转写」服务（讯飞控制台 → 我的应用 → 添加服务并领取免费包）",
        "10110": "无授权许可：请在讯飞控制台领取实时语音转写免费试用包，或确认服务未到期",
    }

    async def run():
        async with websockets.connect(_rtasr_auth_url()) as ws:

            async def sender():
                # 16k16bit 单声道：1280 字节 ≈ 40ms，官方建议按此节奏发送，过快可能导致引擎出错
                try:
                    frame = 1280
                    for i in range(0, len(pcm), frame):
                        await ws.send(pcm[i:i + frame])
                        await asyncio.sleep(0.04)
                    await ws.send('{"end": true}'.encode())
                except websockets.exceptions.ConnectionClosed:
                    pass  # 服务端提前关闭（授权错误等），错误帧交给 receiver 处理

            async def receiver():
                async for msg in ws:
                    d = json.loads(msg)
                    if d.get("action") == "error":
                        code = str(d.get("code"))
                        hint = asr_hints.get(code, d.get("desc"))
                        raise HTTPException(500, f"讯飞语音识别错误（{code}）：{hint}")
                    if d.get("action") != "result":
                        continue
                    r = json.loads(d["data"])
                    st = r.get("cn", {}).get("st")
                    if not st or not st.get("rt"):
                        continue
                    # 报文层级 rt[].ws[].cw[].w
                    text = "".join(
                        cw.get("w", "")
                        for rt_ in st["rt"]
                        for ws_ in rt_.get("ws", [])
                        for cw in ws_.get("cw", [])
                    )
                    # type=0 才是最终结果；中间结果(type=1)是累计草稿、seg_id 各不相同，只保留最终帧
                    if st.get("type") == "0" and text:
                        finals.append(text)

            await asyncio.gather(sender(), receiver())

    try:
        await asyncio.wait_for(run(), timeout=60)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        raise HTTPException(504, "语音识别超时，请重试")
    except websockets.exceptions.InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", "?")
        raise HTTPException(502, f"讯飞拒绝连接（HTTP {code}）：请确认已开通「实时语音转写」服务、"
                                 f"APP_ID/API_KEY 正确，且控制台未开启 IP 白名单")
    except (websockets.exceptions.WebSocketException, OSError) as e:
        raise HTTPException(502, f"无法连接讯飞语音服务：{e}")
    text = "".join(finals).strip()
    return {"code": 0, "data": {"text": text}}
