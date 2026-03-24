#!/usr/bin/env python3
"""推歌账号每日通知邮件"""

import smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.163.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
TO_EMAIL = os.environ.get("NOTIFY_TO", "")

def send_notification(song_name: str, artist: str, hook_text: str, video_path: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎵 今日推歌视频已生成：{song_name} - {artist}"
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL

    body = f"""
<h2>今日推歌视频已生成</h2>
<table border="1" cellpadding="8">
<tr><td><b>歌曲</b></td><td>{song_name} - {artist}</td></tr>
<tr><td><b>开场旁白</b></td><td>{hook_text}</td></tr>
<tr><td><b>视频路径</b></td><td><code>{video_path}</code></td></tr>
</table>
<br>
<p>👆 打开路径，手动上传抖音</p>
<p>⭐ 上传后第一条评论：<b>听完的打个🎵，我继续挖</b></p>
"""
    msg.attach(MIMEText(body, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, TO_EMAIL, msg.as_string())
    print(f"✅ 通知邮件已发送至 {TO_EMAIL}")

if __name__ == "__main__":
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_pass:
        print("⚠️  SMTP_PASS 未配置，跳过发送测试。模块加载正常。")
    else:
        send_notification("晴天", "周杰伦", "凌晨听到这首，想起一个人", "/tmp/test.mp4")
