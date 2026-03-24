#!/usr/bin/env python3
"""
AI 做歌系统 - 网页操作界面
运行: python3 app.py
"""

import streamlit as st
import subprocess
import os
import sys
import json
import tempfile
import time
from pathlib import Path

# ── 项目路径 ──
PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / "suno-api" / ".env"
SUNO_CLIENT = PROJECT_DIR / "suno-api" / "suno_client.py"
VIDEO_SCRIPT = PROJECT_DIR / "daily-video" / "gen_video_v2.py"

# ── 加载 .env ──
def load_env():
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))

load_env()

# ── 页面配置 ──
st.set_page_config(page_title="AI 做歌系统", page_icon="🎵", layout="wide")

# ── 侧边栏导航 ──
page = st.sidebar.radio(
    "选择功能",
    ["🎵 写一首歌", "🔄 二创翻唱", "🎬 生成视频", "⚙️ 设置"],
    index=0
)

# ── 工具函数 ──
def run_suno_cmd(args, progress_placeholder=None):
    """调用 suno_client.py"""
    cmd = [sys.executable, str(SUNO_CLIENT)] + args
    env = os.environ.copy()
    if progress_placeholder:
        progress_placeholder.info("正在调用 Suno API，请耐心等待（通常需要 2-5 分钟）...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时：Suno 生成超过 10 分钟未完成", 1

def get_credits():
    """查询 Suno 积分"""
    out, err, code = run_suno_cmd(["credits"])
    if code == 0:
        return out.strip()
    return f"查询失败: {err}"

def save_env(key, value):
    """更新 .env 文件中的某个值"""
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    os.environ[key] = value


# ════════════════════════════════════════
#  页面：写一首歌
# ════════════════════════════════════════
if page == "🎵 写一首歌":
    st.title("🎵 写一首歌")
    st.markdown("告诉我你想做什么样的歌，剩下的交给 AI。")

    # 检查 Suno 是否配置
    if not os.environ.get("SUNO_COOKIE"):
        st.error("还没有配置 Suno 账号，请先去「⚙️ 设置」页面填写。")
        st.stop()

    st.markdown("---")

    # ── 创作方式 ──
    mode = st.radio(
        "你想怎么做？",
        ["💡 我有一个灵感/想法", "📝 我已经写好歌词了", "🎵 我有参考曲，想做类似的"],
        horizontal=True
    )

    if mode == "💡 我有一个灵感/想法":
        st.markdown("""
        **随便描述你的想法就行，比如：**
        - 「深夜加班后走在空旷马路上的孤独感」
        - 「异地恋，她在北京他在成都」
        - 「像《晴天》那种感觉的歌」
        """)
        inspiration = st.text_area(
            "你的灵感/想法",
            placeholder="随便写，比如：一首关于夏天毕业的歌，有点伤感但也有释怀的感觉...",
            height=120
        )
        lyrics_input = ""
        ref_audio = None

    elif mode == "📝 我已经写好歌词了":
        inspiration = ""
        lyrics_input = st.text_area(
            "粘贴你的歌词",
            placeholder="[Verse 1]\n第一段歌词...\n\n[Chorus]\n副歌歌词...",
            height=200
        )
        ref_audio = st.file_uploader("上传参考曲（可选，AI 会参考它的旋律）", type=["mp3", "wav", "m4a"])

    else:  # 有参考曲
        inspiration = st.text_area(
            "你想做什么样的歌？（可选）",
            placeholder="比如：保留旋律感觉，但换成古风歌词...",
            height=80
        )
        lyrics_input = st.text_area(
            "歌词（可选，不填的话 Suno 会自动生成）",
            placeholder="留空则由 AI 自动生成歌词",
            height=120
        )
        ref_audio = st.file_uploader("上传参考曲", type=["mp3", "wav", "m4a"])

    st.markdown("---")

    # ── 风格设置 ──
    col1, col2 = st.columns(2)

    with col1:
        genre = st.selectbox("曲风", [
            "indie pop（独立流行）",
            "R&B（节奏蓝调）",
            "acoustic pop（民谣流行）",
            "cinematic pop（电影感流行）",
            "lo-fi（低保真）",
            "folk（民谣）",
            "trap pop（陷阱流行）",
            "古风 Chinese traditional",
            "其他（自己写）",
        ])
        if genre == "其他（自己写）":
            genre = st.text_input("自定义曲风", placeholder="比如: jazz ballad")

        mood = st.selectbox("情绪", [
            "melancholic（伤感）",
            "heartfelt（深情）",
            "cheerful（欢快）",
            "dreamy（梦幻）",
            "energetic（充满活力）",
            "easygoing（轻松）",
            "nostalgic（怀旧）",
        ])

    with col2:
        vocal = st.selectbox("声线", [
            "breathy female（气声女声）",
            "sweet clear female（甜美清亮女声）",
            "warm male tenor（温暖男高音）",
            "natural male（自然男声）",
            "rap-singing male（说唱男声）",
        ])

        bpm = st.slider("速度 (BPM)", 60, 160, 100)

    # 组装 Style Prompt
    genre_clean = genre.split("（")[0].strip() if "（" in genre else genre.split("(")[0].strip() if "(" in genre else genre
    mood_clean = mood.split("（")[0].strip() if "（" in mood else mood.split("(")[0].strip() if "(" in mood else mood
    vocal_clean = vocal.split("（")[0].strip() if "（" in vocal else vocal.split("(")[0].strip() if "(" in vocal else vocal

    style_prompt = f"{genre_clean}, {bpm} BPM, {mood_clean}, {vocal_clean}"
    if len(style_prompt) > 200:
        style_prompt = style_prompt[:200]

    with st.expander("查看生成的 Style Prompt"):
        st.code(style_prompt)
        st.caption(f"长度: {len(style_prompt)}/200 字符")

    # ── 歌曲标题 ──
    title = st.text_input("歌名（可选，不填会自动起名）", placeholder="比如: 深夜便利店")

    # ── 输出目录 ──
    output_dir = st.text_input(
        "保存到哪里？",
        value=str(Path.home() / "Desktop" / "做歌输出"),
        help="生成的歌曲会保存到这个文件夹"
    )

    st.markdown("---")

    # ── 开始生成 ──
    if st.button("🚀 开始做歌", type="primary", use_container_width=True):
        if not inspiration and not lyrics_input and not ref_audio:
            st.error("请至少填写一个灵感、歌词或上传参考曲")
            st.stop()

        os.makedirs(output_dir, exist_ok=True)
        progress = st.empty()
        status = st.empty()

        # 保存上传的参考曲
        ref_path = None
        if ref_audio:
            ref_path = os.path.join(output_dir, f"ref_{ref_audio.name}")
            with open(ref_path, "wb") as f:
                f.write(ref_audio.read())
            status.success(f"参考曲已保存: {ref_path}")

        # 确定调用模式
        args = []
        if ref_path:
            if lyrics_input:
                # inspo 模式：参考曲 + 自定义歌词
                args = ["inspo",
                    "--audio", ref_path,
                    "--description", style_prompt,
                    "--title", title or "未命名",
                    "--lyrics", lyrics_input,
                    "--out", output_dir]
            else:
                # remix 模式：纯翻唱
                args = ["remix",
                    "--audio", ref_path,
                    "--style", style_prompt,
                    "--title", title or "未命名",
                    "--out", output_dir]
        elif lyrics_input:
            # 有歌词无参考曲
            args = ["inspo",
                "--description", style_prompt,
                "--title", title or "未命名",
                "--lyrics", lyrics_input,
                "--out", output_dir]
        else:
            # 纯灵感模式 — 需要 AI 先写词
            st.warning("纯灵感模式需要 AI 助手帮你写歌词。请在终端中用 AI 助手（如 Cursor）打开本项目，把你的想法告诉它。")
            st.info(f"你的灵感：{inspiration}\n\n你可以复制下面这段话发给 AI 助手：\n\n「帮我写一首歌，{inspiration}，风格{genre_clean}，{vocal_clean}，{mood_clean}，BPM {bpm}」")
            st.stop()

        # 调用 Suno
        stdout, stderr, code = run_suno_cmd(args, progress)

        if code == 0:
            progress.empty()
            st.success("做歌完成！")
            st.text(stdout)
            # 列出生成的文件
            output_files = [f for f in os.listdir(output_dir) if f.endswith(('.wav', '.mp3'))]
            if output_files:
                st.markdown("### 生成的歌曲")
                for f in output_files:
                    filepath = os.path.join(output_dir, f)
                    st.audio(filepath)
                    st.caption(f)
        else:
            progress.empty()
            st.error("生成失败")
            st.text(f"错误信息:\n{stderr}\n\n输出:\n{stdout}")


# ════════════════════════════════════════
#  页面：二创翻唱
# ════════════════════════════════════════
elif page == "🔄 二创翻唱":
    st.title("🔄 二创翻唱")
    st.markdown("上传一首歌，换一种风格或声线重新唱。旋律保留，只换感觉。")

    if not os.environ.get("SUNO_COOKIE"):
        st.error("还没有配置 Suno 账号，请先去「⚙️ 设置」页面填写。")
        st.stop()

    st.markdown("---")

    audio_file = st.file_uploader("上传原曲", type=["mp3", "wav", "m4a"])

    col1, col2 = st.columns(2)
    with col1:
        target_style = st.selectbox("想换成什么风格？", [
            "R&B 慢版",
            "微醺民谣版",
            "轻电子版",
            "古风版",
            "爵士版",
            "其他（自己写）",
        ])
        if target_style == "其他（自己写）":
            target_style = st.text_input("自定义风格")

    with col2:
        target_vocal = st.selectbox("声线", [
            "气声女声",
            "甜美女声",
            "温柔男声",
            "低沉男声",
            "说唱风格",
        ])

    vocal_map = {
        "气声女声": "breathy airy female vocals",
        "甜美女声": "sweet clear female vocals",
        "温柔男声": "warm gentle male tenor",
        "低沉男声": "deep warm male baritone",
        "说唱风格": "rap-singing character vocals",
    }

    title = st.text_input("新版本的名字", placeholder="比如: 告白气球-R&B版")

    output_dir = st.text_input("保存到哪里？", value=str(Path.home() / "Desktop" / "做歌输出"))

    if st.button("🚀 开始二创", type="primary", use_container_width=True):
        if not audio_file:
            st.error("请先上传原曲")
            st.stop()

        os.makedirs(output_dir, exist_ok=True)
        progress = st.empty()

        # 保存上传文件
        audio_path = os.path.join(output_dir, f"original_{audio_file.name}")
        with open(audio_path, "wb") as f:
            f.write(audio_file.read())

        style = f"{target_style}, {vocal_map.get(target_vocal, target_vocal)}, studio quality"
        if len(style) > 200:
            style = style[:200]

        args = ["remix",
            "--audio", audio_path,
            "--style", style,
            "--title", title or "二创版本",
            "--out", output_dir]

        stdout, stderr, code = run_suno_cmd(args, progress)
        progress.empty()

        if code == 0:
            st.success("二创完成！")
            st.text(stdout)
            output_files = [f for f in os.listdir(output_dir)
                          if f.endswith(('.wav', '.mp3')) and not f.startswith("original_")]
            for f in output_files:
                filepath = os.path.join(output_dir, f)
                st.audio(filepath)
                st.caption(f)
        else:
            st.error(f"生成失败\n{stderr}")


# ════════════════════════════════════════
#  页面：生成视频
# ════════════════════════════════════════
elif page == "🎬 生成视频":
    st.title("🎬 生成歌词短视频")
    st.markdown("给一首歌配上动态背景和卡点歌词，生成抖音竖屏视频。")

    st.markdown("---")

    audio_file = st.file_uploader("上传歌曲", type=["mp3", "wav", "m4a"])

    col1, col2 = st.columns(2)
    with col1:
        song_name = st.text_input("歌名", placeholder="晴天")
        artist_name = st.text_input("歌手", placeholder="周杰伦")

    with col2:
        mood_options = {
            "A - 伤感/失恋（深色焦散光）": "A",
            "B - 思念/暗恋（星空流动）": "B",
            "C - 治愈/释怀（暖色焦散）": "C",
            "D - 愤怒/执念（霓虹脉冲）": "D",
            "E - 甜蜜/浪漫（粉色泡泡）": "E",
            "F - 孤独/深夜（烟雾氛围）": "F",
            "G - 古风/情感（墨迹晕染）": "G",
        }
        mood_label = st.selectbox("视频情绪模版", list(mood_options.keys()))
        mood_tag = mood_options[mood_label]

        duration = st.slider("视频时长（秒）", 15, 60, 30)

    lyrics = st.text_area(
        "歌词（可选，不填会自动识别）",
        placeholder="[Verse 1]\n歌词...\n\n[Chorus]\n副歌...",
        height=150
    )

    hook = st.text_input("Hook 金句（可选，显示在视频开头）", placeholder="比如: 深夜听到这首，想起一个人")

    output_dir = st.text_input("保存到哪里？", value=str(Path.home() / "Desktop" / "视频输出"))

    if st.button("🚀 生成视频", type="primary", use_container_width=True):
        if not audio_file:
            st.error("请先上传歌曲")
            st.stop()

        os.makedirs(output_dir, exist_ok=True)
        progress = st.empty()
        progress.info("正在生成视频，请耐心等待（通常需要 1-3 分钟）...")

        # 保存上传文件
        audio_path = os.path.join(output_dir, audio_file.name)
        with open(audio_path, "wb") as f:
            f.write(audio_file.read())

        output_path = os.path.join(output_dir, f"{song_name or 'video'}.mp4")

        env = os.environ.copy()
        env.update({
            "SONG_NAME": song_name or "未命名",
            "ARTIST_NAME": artist_name or "未知",
            "AUDIO_PATH": audio_path,
            "LYRICS_RAW": lyrics,
            "OUTPUT_PATH": output_path,
            "MOOD_TAG": mood_tag,
            "VIDEO_DURATION": str(duration),
            "HOOK_OVERLAY_TEXT": hook or "",
        })

        try:
            result = subprocess.run(
                [sys.executable, str(VIDEO_SCRIPT)],
                capture_output=True, text=True, timeout=300, env=env
            )
            progress.empty()

            if result.returncode == 0 and os.path.exists(output_path):
                st.success("视频生成完成！")
                st.video(output_path)
                st.caption(f"保存在: {output_path}")
            else:
                st.error("视频生成失败")
                st.text(result.stderr[-1000:] if result.stderr else result.stdout[-1000:])
        except subprocess.TimeoutExpired:
            progress.empty()
            st.error("视频生成超时（超过 5 分钟）")


# ════════════════════════════════════════
#  页面：设置
# ════════════════════════════════════════
elif page == "⚙️ 设置":
    st.title("⚙️ 账号设置")
    st.markdown("配置你的 API 密钥。每个密钥下面都有获取教程。")

    st.markdown("---")

    # ── Suno ──
    st.subheader("🎵 Suno（做歌必须）")
    st.markdown("""
    **怎么获取？**
    1. 用 Chrome 打开 [suno.com](https://suno.com) 并登录
    2. 按 **F12** 打开开发者工具
    3. 点顶部「**Application**」标签
    4. 左侧找到 **Cookies** → `https://suno.com`
    5. 找到名为 `__client` 的那一行，双击 Value 列，**全选复制**
    """)

    suno_cookie = st.text_input(
        "Suno Cookie（__client 的值）",
        value=os.environ.get("SUNO_COOKIE", "").replace("__client=", ""),
        type="password"
    )
    if st.button("保存 Suno Cookie"):
        save_env("SUNO_COOKIE", f"__client={suno_cookie}" if not suno_cookie.startswith("__client=") else suno_cookie)
        st.success("已保存！")
        st.rerun()

    # 查积分
    if os.environ.get("SUNO_COOKIE"):
        if st.button("🔍 查询 Suno 积分"):
            with st.spinner("查询中..."):
                result = get_credits()
            st.info(f"积分: {result}")

    st.markdown("---")

    # ── Gemini ──
    st.subheader("🧠 Gemini API（写歌词用）")
    st.markdown("""
    **怎么获取？**
    1. 打开 [Google AI Studio](https://aistudio.google.com/apikey)
    2. 用 Google 账号登录
    3. 点「**Create API Key**」
    4. 复制生成的 Key（以 `AIza` 开头）
    """)

    gemini_key = st.text_input(
        "Gemini API Key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password"
    )
    if st.button("保存 Gemini Key"):
        save_env("GEMINI_API_KEY", gemini_key)
        st.success("已保存！")
        st.rerun()

    st.markdown("---")

    # ── 豆包 ──
    st.subheader("🎨 豆包 API（生成封面图，可选）")
    st.markdown("""
    **怎么获取？**
    1. 打开 [火山引擎控制台](https://console.volcengine.com/ark)
    2. 注册/登录
    3. 进入「模型推理」→「API Key 管理」→「创建 API Key」
    """)

    ark_key = st.text_input(
        "豆包 API Key",
        value=os.environ.get("ARK_API_KEY", ""),
        type="password"
    )
    if st.button("保存豆包 Key"):
        save_env("ARK_API_KEY", ark_key)
        st.success("已保存！")
        st.rerun()

    st.markdown("---")

    # ── 邮件 ──
    st.subheader("📧 邮件通知（可选）")
    st.markdown("配置后，做完歌会收到邮件通知。不配也不影响做歌。")

    col1, col2 = st.columns(2)
    with col1:
        smtp_user = st.text_input("发件邮箱", value=os.environ.get("SMTP_USER", ""))
        smtp_pass = st.text_input("SMTP 授权码", value=os.environ.get("SMTP_PASS", ""), type="password")
    with col2:
        notify_to = st.text_input("接收通知的邮箱", value=os.environ.get("NOTIFY_TO", ""))

    if st.button("保存邮件设置"):
        save_env("SMTP_USER", smtp_user)
        save_env("SMTP_PASS", smtp_pass)
        save_env("NOTIFY_TO", notify_to)
        st.success("已保存！")
        st.rerun()

    st.markdown("---")

    # ── 状态总览 ──
    st.subheader("📊 配置状态")

    checks = [
        ("Suno Cookie", bool(os.environ.get("SUNO_COOKIE", "")), "做歌必须"),
        ("Gemini API", bool(os.environ.get("GEMINI_API_KEY", "")), "写歌词用"),
        ("豆包 API", bool(os.environ.get("ARK_API_KEY", "")), "封面图，可选"),
        ("邮件通知", bool(os.environ.get("SMTP_USER", "")), "可选"),
    ]

    for name, ok, desc in checks:
        if ok:
            st.markdown(f"✅ **{name}** — {desc}")
        else:
            st.markdown(f"⬜ **{name}** — {desc}（未配置）")


# ── 底部信息 ──
st.sidebar.markdown("---")
st.sidebar.caption("AI 做歌系统 v1.0")

# ── 启动入口 ──
if __name__ == "__main__":
    # 直接用 python3 app.py 启动
    os.system(f"{sys.executable} -m streamlit run {__file__} --server.headless=false --browser.gatherUsageStats=false")
