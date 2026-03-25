#!/usr/bin/env python3
"""
AI 做歌系统 - 网页操作界面（Streamlit Cloud 版）
每个用户在浏览器中输入自己的 API 密钥，密钥只存在当前会话中。
"""

import streamlit as st
import subprocess
import os
import sys
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# ── 项目路径 ──
PROJECT_DIR = Path(__file__).resolve().parent
SUNO_CLIENT = PROJECT_DIR / "suno-api" / "suno_client.py"
VIDEO_SCRIPT = PROJECT_DIR / "daily-video" / "gen_video_v2.py"

# ── 页面配置 ──
st.set_page_config(page_title="AI 做歌系统", page_icon="🎵", layout="wide")


# ═══════════════════════════════════════════
#  会话状态管理（替代 .env 文件）
# ═══════════════════════════════════════════

def init_session():
    """初始化 session_state 默认值"""
    defaults = {
        "suno_cookie": "",
        "gemini_key": "",
        "anthropic_key": "",
        "ark_key": "",
        "keys_configured": False,
        "lyrics_claude": "",
        "lyrics_gemini": "",
        "lyrics_final": "",
        "lyrics_generated": False,
        "searched_ref_path": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_suno_ready():
    """检查 Suno Cookie 是否已配置"""
    return bool(st.session_state.get("suno_cookie", ""))


def get_suno_token():
    """获取干净的 Suno refresh token"""
    cookie = st.session_state.get("suno_cookie", "")
    # 去掉可能的 __client= 前缀
    return cookie.replace("__client=", "").strip()


init_session()


# ═══════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════

def run_suno_cmd(args, progress_placeholder=None):
    """调用 suno_client.py，通过 --refresh-token 传递用户的 Cookie"""
    token = get_suno_token()
    cmd = [sys.executable, str(SUNO_CLIENT), "--refresh-token", token] + args

    # 构建干净的环境变量（不污染其他用户的会话）
    env = os.environ.copy()
    env["SUNO_COOKIE"] = f"__client={token}"
    if st.session_state.get("gemini_key"):
        env["GEMINI_API_KEY"] = st.session_state["gemini_key"]
    if st.session_state.get("ark_key"):
        env["ARK_API_KEY"] = st.session_state["ark_key"]

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


def get_output_dir():
    """获取输出目录：本地用桌面，云端用临时目录"""
    desktop = Path.home() / "Desktop" / "做歌输出"
    if desktop.parent.exists():
        desktop.mkdir(parents=True, exist_ok=True)
        return str(desktop)
    # Streamlit Cloud 没有桌面，用临时目录
    tmp = Path(tempfile.mkdtemp(prefix="songmaker_"))
    return str(tmp)


# ═══════════════════════════════════════════
#  参考曲搜索下载（yt-dlp）
# ═══════════════════════════════════════════

def search_and_download_song(query, output_dir):
    """按歌名从 YouTube 搜索并下载音频，返回文件路径"""
    try:
        import yt_dlp
    except ImportError:
        return None, "yt-dlp 未安装，请直接上传音频文件"

    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "ref_%(title).50s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": output_template,
        "default_search": "ytsearch1",  # 只取第一个结果
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if "entries" in info:
                info = info["entries"][0]
            # 找到下载的文件
            title = info.get("title", "unknown")
            # yt-dlp 下载后文件名可能被截断，搜索目录中最新的 mp3
            mp3_files = sorted(
                [f for f in os.listdir(output_dir) if f.startswith("ref_") and f.endswith(".mp3")],
                key=lambda f: os.path.getmtime(os.path.join(output_dir, f)),
                reverse=True,
            )
            if mp3_files:
                return os.path.join(output_dir, mp3_files[0]), title
            return None, f"下载完成但找不到文件"
    except BrokenPipeError:
        return None, "云端环境下载受限（Broken pipe），请改用「上传文件」方式：在本地下载好歌曲后上传"
    except Exception as e:
        err_msg = str(e)
        if "Broken pipe" in err_msg or "Errno 32" in err_msg:
            return None, "云端环境下载受限，请改用「上传文件」方式：在本地下载好歌曲后上传"
        return None, f"搜索/下载失败: {e}"


def show_suno_fallback(lyrics, style_prompt, title):
    """Cookie 过期时的降级方案：展示可复制内容 + 操作指引"""
    st.error("Suno Cookie 已过期，无法自动生成。请手动操作：")

    st.markdown("### 手动做歌步骤")
    st.markdown("""
1. 点击下方按钮打开 Suno 创作页面
2. 在 Suno 页面选择「**Custom**」模式
3. 把下面的内容逐项复制粘贴进去
4. 点击 Suno 的「**Create**」按钮
5. 做完后记得更新你的 Cookie（去「⚙️ 设置」页面）
    """)

    st.link_button("🔗 打开 Suno 创作页面", "https://suno.com/create", type="primary")

    st.markdown("---")

    # Style Prompt — 一键复制
    st.markdown("**Style Prompt**（粘贴到 Suno 的「Style of Music」框）")
    st.code(style_prompt, language=None)

    # 歌词 — 一键复制
    if lyrics:
        st.markdown("**歌词**（粘贴到 Suno 的「Lyrics」框）")
        st.code(lyrics, language=None)

    # 歌名
    if title:
        st.markdown(f"**歌名**（填到 Suno 的「Title」框）：`{title}`")


# ═══════════════════════════════════════════
#  AI 写词引擎（Gemini + Claude 双模型比稿）
# ═══════════════════════════════════════════

LYRICS_PROMPT_TEMPLATE = """你是一位顶尖华语流行音乐词作者。

## 任务
创作一首原创歌词。

## 基本信息
- 主题/灵感: {inspiration}
- 情感基调: {mood}
- 曲风: {genre}
- 声线: {vocal}
- BPM: {bpm}
- 语言: 中英混搭

## 歌词标准（硬性要求）
1. 禁止照搬任何现有歌词，必须100%原创
2. 用意象写感情，禁止直述情绪（❌我很孤独 → ✅窗外的麻雀在电线杆上多嘴）
3. 每首歌一个情绪切面，不要贪多
4. 副歌高音位用开口韵母：-a, -ai, -ao, -ang
5. 押韵是硬性要求，每段韵脚统一
6. 用 [Verse] [Chorus] [Bridge] 等标签分段
7. 每行7-11字，Verse 3-4行/段，Chorus 4-6行
8. 禁止大白话/流水账，每句必须有意象转化
9. 禁止励志口号/库存套话/万能情感词堆砌
10. Chorus 核心句要有传唱记忆点
11. 有画面有行为，口语化年轻化，无书面腔/古风腔
12. 中英混搭加分（适当位置用有实际含义的英文短句）
13. 多音字标注拼音（如：觉jiao4）
14. 控制总时长 150-180秒

## Suno Style Prompt（同时输出）
按公式输出：[流派+情绪] + [主导乐器] + [人声特质] + [节奏与动态]
严格不超过200字符。

## 输出格式
1. 完整歌词（带段落标签 [Verse 1] [Chorus] 等）
2. Suno Style Prompt
3. 押韵方案说明（每段用什么韵）
4. 一句话创作思路
"""


# ── 网易 AI 网关配置 ──
NETEASE_BASE_URL = "https://aigw.netease.com/v1"
NETEASE_API_KEY = "trltfs9kdk59cyfw.ov211ltwsnx1fm0kwtz4v8dfp8xmls8t"


def _call_netease_gateway(model, prompt, max_tokens=4096):
    """通过网易 AI 网关调用模型（OpenAI-compatible）"""
    from openai import OpenAI
    client = OpenAI(base_url=NETEASE_BASE_URL, api_key=NETEASE_API_KEY)
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def generate_lyrics_gemini(inspiration, mood, genre, vocal, bpm):
    """调用 Gemini 写歌词（通过网易 AI 网关）"""
    try:
        prompt = LYRICS_PROMPT_TEMPLATE.format(
            inspiration=inspiration, mood=mood, genre=genre, vocal=vocal, bpm=bpm
        )
        return _call_netease_gateway("gemini-3-pro", prompt)
    except Exception as e:
        return f"Gemini 写词失败: {e}"


def generate_lyrics_claude(inspiration, mood, genre, vocal, bpm):
    """调用 Claude 写歌词（通过网易 AI 网关）"""
    try:
        prompt = LYRICS_PROMPT_TEMPLATE.format(
            inspiration=inspiration, mood=mood, genre=genre, vocal=vocal, bpm=bpm
        )
        return _call_netease_gateway("claude-opus-4-20250514", prompt)
    except Exception as e:
        return f"Claude 写词失败: {e}"


def can_generate_lyrics():
    """AI 写词始终可用（走网易 AI 网关，无需用户填 Key）"""
    return True


def can_dual_generate():
    """比稿模式始终可用（走网易 AI 网关）"""
    return True


# ═══════════════════════════════════════════
#  侧边栏
# ═══════════════════════════════════════════

# 配置状态指示
if is_suno_ready():
    st.sidebar.success("Suno 已连接")
else:
    st.sidebar.warning("Suno 未配置")

page = st.sidebar.radio(
    "选择功能",
    ["🎵 写一首歌", "🔄 二创翻唱", "🎬 生成视频", "⚙️ 设置"],
    index=3 if not is_suno_ready() else 0,  # 未配置时默认打开设置页
)

st.sidebar.markdown("---")
st.sidebar.caption("AI 做歌系统 v2.0（云端版）")


# ═══════════════════════════════════════════
#  页面：设置
# ═══════════════════════════════════════════
if page == "⚙️ 设置":
    st.title("⚙️ 账号设置")

    if not is_suno_ready():
        st.info("👋 欢迎！请先配置你的账号信息，然后就可以开始做歌了。")

    st.markdown("---")

    # ── Suno Cookie ──
    st.subheader("🎵 Suno Cookie（必须，用来生成歌曲）")

    with st.expander("📖 怎么获取 Suno Cookie？点这里看教程", expanded=not is_suno_ready()):
        st.markdown("""
**一步一步来，很简单：**

1. 打开 Chrome 浏览器，访问 **suno.com** 并登录你的账号
2. 登录后，按键盘上的 **F12**（打开开发者工具）
3. 在弹出的面板顶部，点击「**Application**」这个标签
   - 如果看不到，点右边的 `>>` 展开就能找到
4. 左侧栏找到 **Cookies**，点击展开，然后点 `https://suno.com`
5. 在右侧列表里找到名为 **`__client`** 的那一行
6. 双击它右边的 **Value**（值）那一栏
7. 按 **Ctrl+A**（全选），再按 **Ctrl+C**（复制）
8. 回到这里，粘贴到下面的输入框

> 💡 这个值很长（几百个字符），这是正常的。
> ⚠️ Cookie 会过期，如果做歌时报错，重新获取一个新的粘贴进来就行。
        """)

    suno_input = st.text_input(
        "粘贴你的 Suno Cookie",
        value=st.session_state.get("suno_cookie", ""),
        type="password",
        placeholder="粘贴 __client 的值...",
        key="suno_cookie_input",
    )

    if st.button("保存 Suno Cookie", type="primary"):
        if suno_input and len(suno_input) > 20:
            st.session_state["suno_cookie"] = suno_input.replace("__client=", "").strip()
            st.session_state["keys_configured"] = True
            st.success("Suno Cookie 已保存！")
            st.rerun()
        else:
            st.error("Cookie 看起来不对，应该是一段很长的字符串")

    # 查积分
    if is_suno_ready():
        if st.button("🔍 查询 Suno 积分"):
            with st.spinner("查询中..."):
                result = get_credits()
            st.info(result)

    st.markdown("---")

    # ── Gemini API Key ──
    st.subheader("🧠 Gemini API Key（写歌词用，推荐配置）")

    with st.expander("📖 怎么获取 Gemini API Key？"):
        st.markdown("""
1. 打开 **aistudio.google.com/apikey**（Google AI Studio）
2. 用你的 **Google 账号**登录（没有就注册一个，免费的）
3. 点击「**Create API Key**」按钮
4. 会生成一串以 **AIza** 开头的字符串
5. 点复制，粘贴到下面

> 💡 Gemini API 有免费额度，日常写歌词完全够用。
        """)

    gemini_input = st.text_input(
        "粘贴你的 Gemini API Key",
        value=st.session_state.get("gemini_key", ""),
        type="password",
        placeholder="以 AIza 开头...",
        key="gemini_key_input",
    )

    if st.button("保存 Gemini Key"):
        st.session_state["gemini_key"] = gemini_input.strip()
        st.success("Gemini Key 已保存！")

    st.markdown("---")

    # ── Anthropic API Key ──
    st.subheader("🤖 Claude API Key（写歌词用，推荐配置）")

    with st.expander("📖 怎么获取 Claude API Key？"):
        st.markdown("""
1. 打开 **console.anthropic.com**（Anthropic 控制台）
2. 注册或登录你的账号
3. 点左侧「**API Keys**」
4. 点「**Create Key**」，给它起个名字（比如"做歌"）
5. 复制生成的 Key（以 `sk-ant-` 开头）
6. 粘贴到下面

> 💡 Claude 用来写歌词（和 Gemini 各写一版，然后选最好的）。
> 如果只配了一个模型，也能用，只是不能比稿。两个都配效果最好。
        """)

    anthropic_input = st.text_input(
        "粘贴你的 Claude API Key",
        value=st.session_state.get("anthropic_key", ""),
        type="password",
        placeholder="以 sk-ant- 开头...",
        key="anthropic_key_input",
    )

    if st.button("保存 Claude Key"):
        st.session_state["anthropic_key"] = anthropic_input.strip()
        st.success("Claude Key 已保存！")

    st.markdown("---")

    # ── 豆包 API Key ──
    st.subheader("🎨 豆包 API Key（生成封面图，可选）")

    with st.expander("📖 怎么获取豆包 API Key？"):
        st.markdown("""
1. 打开 **console.volcengine.com/ark**（火山引擎控制台）
2. 注册或登录你的火山引擎账号
3. 进入「模型推理」→「API Key 管理」
4. 点「创建 API Key」，复制生成的 Key
5. 粘贴到下面

> 💡 这个是可选的，不配也完全不影响做歌。
        """)

    ark_input = st.text_input(
        "粘贴你的豆包 API Key",
        value=st.session_state.get("ark_key", ""),
        type="password",
        placeholder="可选，不填也不影响做歌",
        key="ark_key_input",
    )

    if st.button("保存豆包 Key"):
        st.session_state["ark_key"] = ark_input.strip()
        st.success("豆包 Key 已保存！")

    st.markdown("---")

    # ── 配置状态总览 ──
    st.subheader("📊 当前配置状态")

    checks = [
        ("Suno Cookie", is_suno_ready(), "做歌必须"),
        ("Gemini API", bool(st.session_state.get("gemini_key")), "写歌词用，推荐"),
        ("Claude API", bool(st.session_state.get("anthropic_key")), "写歌词用，推荐（两个都配可比稿）"),
        ("豆包 API", bool(st.session_state.get("ark_key")), "封面图，可选"),
    ]

    for name, ok, desc in checks:
        if ok:
            st.markdown(f"✅ **{name}** — {desc}")
        else:
            st.markdown(f"⬜ **{name}** — {desc}（未配置）")

    st.markdown("---")
    st.caption("💡 你的密钥只保存在当前浏览器会话中，关闭页面后需要重新输入。我们不会存储你的密钥。")


# ═══════════════════════════════════════════
#  页面：写一首歌
# ═══════════════════════════════════════════
elif page == "🎵 写一首歌":
    st.title("🎵 写一首歌")
    st.markdown("告诉我你想做什么样的歌，剩下的交给 AI。")

    if not is_suno_ready():
        st.error("还没有配置 Suno 账号，请先去左边「⚙️ 设置」页面填写 Suno Cookie。")
        st.stop()

    st.markdown("---")

    # ── 创作方式 ──
    mode = st.radio(
        "你想怎么做？",
        ["💡 我有一个灵感/想法", "📝 我已经写好歌词了", "🎵 我有参考曲，想做类似的"],
        horizontal=True,
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
            height=120,
        )
        lyrics_input = ""

        # 参考曲：上传或搜索
        ref_method = st.radio("参考曲", ["📁 上传文件", "🔍 输入歌名搜索"], horizontal=True, key="ref1")
        if ref_method == "📁 上传文件":
            ref_audio = st.file_uploader("上传参考曲（推荐）", type=["mp3", "wav", "m4a"], key="upload1")
        else:
            ref_audio = None
            song_query = st.text_input("输入歌名（如：周杰伦 晴天）", key="search1",
                                       placeholder="歌手名 + 歌名，或粘贴 YouTube 链接")
            if song_query and st.button("🔍 搜索并下载", key="btn_search1"):
                with st.spinner(f"正在搜索「{song_query}」..."):
                    path, info = search_and_download_song(song_query, get_output_dir())
                if path:
                    st.success(f"找到：{info}")
                    st.audio(path)
                    st.session_state["searched_ref_path"] = path
                else:
                    st.error(info)

    elif mode == "📝 我已经写好歌词了":
        inspiration = ""
        lyrics_input = st.text_area(
            "粘贴你的歌词",
            placeholder="[Verse 1]\n第一段歌词...\n\n[Chorus]\n副歌歌词...",
            height=200,
        )
        ref_method = st.radio("参考曲（可选）", ["📁 上传文件", "🔍 输入歌名搜索"], horizontal=True, key="ref2")
        if ref_method == "📁 上传文件":
            ref_audio = st.file_uploader("上传参考曲", type=["mp3", "wav", "m4a"], key="upload2")
        else:
            ref_audio = None
            song_query = st.text_input("输入歌名", key="search2",
                                       placeholder="歌手名 + 歌名，或粘贴 YouTube 链接")
            if song_query and st.button("🔍 搜索并下载", key="btn_search2"):
                with st.spinner(f"正在搜索「{song_query}」..."):
                    path, info = search_and_download_song(song_query, get_output_dir())
                if path:
                    st.success(f"找到：{info}")
                    st.audio(path)
                    st.session_state["searched_ref_path"] = path
                else:
                    st.error(info)

    else:  # 有参考曲
        inspiration = st.text_area(
            "你想做什么样的歌？（可选）",
            placeholder="比如：保留旋律感觉，但换成古风歌词...",
            height=80,
        )
        lyrics_input = st.text_area(
            "歌词（可选，不填的话 Suno 会自动生成）",
            placeholder="留空则由 AI 自动生成歌词",
            height=120,
        )
        ref_method = st.radio("参考曲", ["📁 上传文件", "🔍 输入歌名搜索"], horizontal=True, key="ref3")
        if ref_method == "📁 上传文件":
            ref_audio = st.file_uploader("上传参考曲", type=["mp3", "wav", "m4a"], key="upload3")
        else:
            ref_audio = None
            song_query = st.text_input("输入歌名", key="search3",
                                       placeholder="歌手名 + 歌名，或粘贴 YouTube 链接")
            if song_query and st.button("🔍 搜索并下载", key="btn_search3"):
                with st.spinner(f"正在搜索「{song_query}」..."):
                    path, info = search_and_download_song(song_query, get_output_dir())
                if path:
                    st.success(f"找到：{info}")
                    st.audio(path)
                    st.session_state["searched_ref_path"] = path
                else:
                    st.error(info)

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

    st.markdown("---")

    # ═══════════════════════════════════════════
    #  第一步：AI 写歌词（灵感模式专属）
    # ═══════════════════════════════════════════
    if mode == "💡 我有一个灵感/想法" and not lyrics_input:
        if can_generate_lyrics():
            st.subheader("第 1 步：AI 写歌词")

            if can_dual_generate():
                st.caption("Gemini + Claude 各写一版，你来挑最好的")
            elif st.session_state.get("gemini_key"):
                st.caption("使用 Gemini 写歌词（配上 Claude API Key 可以比稿）")
            else:
                st.caption("使用 Claude 写歌词（配上 Gemini API Key 可以比稿）")

            if st.button("✍️ AI 写歌词", type="secondary", use_container_width=True):
                if not inspiration:
                    st.error("请先填写你的灵感/想法")
                    st.stop()

                with st.spinner("AI 正在写歌词，请稍等..."):
                    has_gemini = bool(st.session_state.get("gemini_key"))
                    has_claude = bool(st.session_state.get("anthropic_key"))

                    if has_gemini and has_claude:
                        # 双模型并行写词
                        with ThreadPoolExecutor(max_workers=2) as executor:
                            future_g = executor.submit(
                                generate_lyrics_gemini, inspiration, mood_clean, genre_clean, vocal_clean, bpm
                            )
                            future_c = executor.submit(
                                generate_lyrics_claude, inspiration, mood_clean, genre_clean, vocal_clean, bpm
                            )
                            st.session_state["lyrics_gemini"] = future_g.result()
                            st.session_state["lyrics_claude"] = future_c.result()
                    elif has_gemini:
                        st.session_state["lyrics_gemini"] = generate_lyrics_gemini(
                            inspiration, mood_clean, genre_clean, vocal_clean, bpm
                        )
                        st.session_state["lyrics_claude"] = ""
                    else:
                        st.session_state["lyrics_claude"] = generate_lyrics_claude(
                            inspiration, mood_clean, genre_clean, vocal_clean, bpm
                        )
                        st.session_state["lyrics_gemini"] = ""

                    st.session_state["lyrics_generated"] = True
                st.rerun()

            # 显示写词结果
            if st.session_state.get("lyrics_generated"):
                has_both = st.session_state.get("lyrics_gemini") and st.session_state.get("lyrics_claude")

                if has_both:
                    st.markdown("### 两版歌词对比")
                    col_g, col_c = st.columns(2)
                    with col_g:
                        st.markdown("**Gemini 版**")
                        st.text_area("Gemini 歌词", value=st.session_state["lyrics_gemini"],
                                    height=400, key="display_gemini", disabled=True)
                    with col_c:
                        st.markdown("**Claude 版**")
                        st.text_area("Claude 歌词", value=st.session_state["lyrics_claude"],
                                    height=400, key="display_claude", disabled=True)

                    pick = st.radio("选哪个版本？", ["用 Gemini 版", "用 Claude 版", "自己改（复制到下面编辑）"],
                                   horizontal=True)
                    if pick == "用 Gemini 版":
                        st.session_state["lyrics_final"] = st.session_state["lyrics_gemini"]
                    elif pick == "用 Claude 版":
                        st.session_state["lyrics_final"] = st.session_state["lyrics_claude"]
                else:
                    single = st.session_state.get("lyrics_gemini") or st.session_state.get("lyrics_claude") or ""
                    st.markdown("### AI 写的歌词")
                    st.text_area("AI 歌词", value=single, height=400, key="display_single", disabled=True)
                    st.session_state["lyrics_final"] = single

                # 可编辑的最终歌词
                st.markdown("### 最终歌词（可编辑）")
                lyrics_input = st.text_area(
                    "编辑歌词后，点下面的按钮提交做歌",
                    value=st.session_state.get("lyrics_final", ""),
                    height=300,
                    key="final_lyrics_edit",
                )

                st.markdown("---")
        else:
            st.info("💡 要让 AI 帮你写歌词，请在「⚙️ 设置」页面配置 Gemini 和/或 Claude API Key。")
            st.info("你也可以直接切到「📝 我已经写好歌词了」模式，粘贴自己的歌词。")

    # ═══════════════════════════════════════════
    #  第二步：提交 Suno 做歌
    # ═══════════════════════════════════════════
    st.subheader("第 2 步：提交做歌" if mode == "💡 我有一个灵感/想法" and can_generate_lyrics() else "")

    if st.button("🚀 开始做歌", type="primary", use_container_width=True):
        has_searched_ref = bool(st.session_state.get("searched_ref_path"))
        if not inspiration and not lyrics_input and not ref_audio and not has_searched_ref:
            st.error("请至少填写一个灵感、歌词或上传/搜索参考曲")
            st.stop()

        output_dir = get_output_dir()
        progress = st.empty()
        status = st.empty()

        # 参考曲路径：上传的 > 搜索下载的
        ref_path = None
        if ref_audio:
            ref_path = os.path.join(output_dir, f"ref_{ref_audio.name}")
            with open(ref_path, "wb") as f:
                f.write(ref_audio.read())
            status.success("参考曲已保存")
        elif has_searched_ref:
            ref_path = st.session_state["searched_ref_path"]
            status.success(f"使用搜索到的参考曲")

        # 确定调用模式
        args = []
        if ref_path:
            if lyrics_input:
                args = ["inspo",
                    "--audio", ref_path,
                    "--description", style_prompt,
                    "--title", title or "未命名",
                    "--lyrics", lyrics_input,
                    "--out", output_dir]
            else:
                args = ["remix",
                    "--audio", ref_path,
                    "--style", style_prompt,
                    "--title", title or "未命名",
                    "--out", output_dir]
        elif lyrics_input:
            st.info("没有参考曲，Suno 会从零生成旋律。上传参考曲效果更好，但不上传也能用。")
            args = ["inspo",
                "--description", style_prompt,
                "--title", title or "未命名",
                "--lyrics", lyrics_input,
                "--out", output_dir]
        else:
            st.error("请先让 AI 写歌词，或者自己填写歌词，或者上传/搜索参考曲。")
            st.stop()

        # 调用 Suno
        stdout, stderr, code = run_suno_cmd(args, progress)

        if code == 0:
            progress.empty()
            st.success("做歌完成！🎉")
            st.text(stdout)
            output_files = [f for f in os.listdir(output_dir)
                          if f.endswith((".wav", ".mp3")) and not f.startswith("ref_")]
            if output_files:
                st.markdown("### 生成的歌曲")
                for f in sorted(output_files):
                    filepath = os.path.join(output_dir, f)
                    st.audio(filepath)
                    with open(filepath, "rb") as fh:
                        st.download_button(
                            f"⬇️ 下载 {f}",
                            data=fh.read(),
                            file_name=f,
                            mime="audio/wav",
                        )
        else:
            progress.empty()
            # Cookie 过期 → 降级为手动模式
            if "422" in stderr or "Token validation" in stderr:
                show_suno_fallback(lyrics_input, style_prompt, title)
            else:
                st.error("生成失败")
                st.text(f"错误信息:\n{stderr}\n\n输出:\n{stdout}")


# ═══════════════════════════════════════════
#  页面：二创翻唱
# ═══════════════════════════════════════════
elif page == "🔄 二创翻唱":
    st.title("🔄 二创翻唱")
    st.markdown("上传一首歌，换一种风格或声线重新唱。旋律保留，只换感觉。")

    if not is_suno_ready():
        st.error("还没有配置 Suno 账号，请先去左边「⚙️ 设置」页面填写 Suno Cookie。")
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

    if st.button("🚀 开始二创", type="primary", use_container_width=True):
        if not audio_file:
            st.error("请先上传原曲")
            st.stop()

        output_dir = get_output_dir()
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
            st.success("二创完成！🎉")
            st.text(stdout)
            output_files = [f for f in os.listdir(output_dir)
                          if f.endswith((".wav", ".mp3")) and not f.startswith("original_")]
            for f in sorted(output_files):
                filepath = os.path.join(output_dir, f)
                st.audio(filepath)
                with open(filepath, "rb") as fh:
                    st.download_button(
                        f"⬇️ 下载 {f}",
                        data=fh.read(),
                        file_name=f,
                        mime="audio/wav",
                    )
        else:
            if "422" in stderr or "Token validation" in stderr:
                show_suno_fallback("", style, title)
            else:
                st.error("生成失败")
                st.text(f"错误信息:\n{stderr}")


# ═══════════════════════════════════════════
#  页面：生成视频
# ═══════════════════════════════════════════
elif page == "🎬 生成视频":
    st.title("🎬 生成歌词短视频")
    st.markdown("给一首歌配上动态背景和卡点歌词，生成抖音竖屏视频。")

    st.warning("⚠️ 视频生成功能需要在本地运行（需要 ffmpeg 等工具）。如果你在云端访问，这个功能可能无法使用。")

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
        height=150,
    )

    hook = st.text_input("Hook 金句（可选，显示在视频开头）", placeholder="比如: 深夜听到这首，想起一个人")

    if st.button("🚀 生成视频", type="primary", use_container_width=True):
        if not audio_file:
            st.error("请先上传歌曲")
            st.stop()

        output_dir = get_output_dir()
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
        if st.session_state.get("gemini_key"):
            env["GEMINI_API_KEY"] = st.session_state["gemini_key"]

        try:
            result = subprocess.run(
                [sys.executable, str(VIDEO_SCRIPT)],
                capture_output=True, text=True, timeout=300, env=env,
            )
            progress.empty()

            if result.returncode == 0 and os.path.exists(output_path):
                st.success("视频生成完成！")
                st.video(output_path)
                with open(output_path, "rb") as fh:
                    st.download_button(
                        "⬇️ 下载视频",
                        data=fh.read(),
                        file_name=f"{song_name or 'video'}.mp4",
                        mime="video/mp4",
                    )
            else:
                st.error("视频生成失败")
                st.text(result.stderr[-1000:] if result.stderr else result.stdout[-1000:])
        except subprocess.TimeoutExpired:
            progress.empty()
            st.error("视频生成超时（超过 5 分钟）")


# ── 启动入口（本地运行时） ──
if __name__ == "__main__":
    os.system(f"{sys.executable} -m streamlit run {__file__} --server.headless=false --browser.gatherUsageStats=false")
