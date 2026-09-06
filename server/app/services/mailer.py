"""邮件触达 — aiosmtplib 异步发送（不阻塞事件循环），未配置 SMTP 自动降级为仅站内信"""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

log = logging.getLogger("growth-system.mailer")


def enabled() -> bool:
    """SMTP 未配置时降级：系统功能不受影响，通知只走站内信"""
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS)


def _render(title: str, content: str) -> str:
    return f"""<div style="max-width:560px;margin:0 auto;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="background:#3b6fe0;color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:18px;">AI 学生成长发展系统</h2>
  </div>
  <div style="border:1px solid #eee;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
    <h3 style="margin:0 0 12px;font-size:16px;color:#333;">{title}</h3>
    <p style="margin:0;color:#555;line-height:1.7;white-space:pre-wrap;">{content}</p>
    <p style="margin:16px 0 0;color:#999;font-size:12px;">请登录系统查看详情并处理。本邮件由系统自动发送，请勿回复。</p>
  </div>
</div>"""


async def send_async(to: str, subject: str, content: str) -> None:
    """后台发送：失败仅记日志，不影响主业务事务"""
    if not enabled() or not to:
        return
    try:
        import aiosmtplib
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(_render(subject, content), "html", "utf-8"))
        await aiosmtplib.send(
            msg, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
            use_tls=settings.SMTP_PORT == 465,
            username=settings.SMTP_USER, password=settings.SMTP_PASS,
        )
        log.info("邮件已发送 to=%s subject=%s", to, subject)
    except Exception as exc:
        log.warning("邮件发送失败 to=%s subject=%s: %s", to, subject, exc)
