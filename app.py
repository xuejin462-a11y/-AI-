#!/usr/bin/env python3
"""
AI 做歌系统 - 网页操作界面（Streamlit Cloud 版）
AI 模型调用通过浏览器端 JavaScript 直接走网易 AI 网关（绕过 Cloud 服务器 IP 限制）。
"""

import streamlit as st
from streamlit_javascript import st_javascript
import subprocess
import os
import sys
import tempfile
import time
import requests
import json
from pathlib import Path

# ── 项目路径 ──
PROJECT_DIR = Path(__file__).resolve().parent
SUNO_CLIENT = PROJECT_DIR / "suno-api" / "suno_client.py"

# ── 页面配置 ──
st.set_page_config(page_title="AI 做歌系统", page_icon="🎵", layout="wide")


# ═══════════════════════════════════════════
#  会话状态管理（替代 .env 文件）
# ═══════════════════════════════════════════

def init_session():
    """初始化 session_state 默认值"""
    defaults = {
        "suno_cookie": "",
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
#  参考曲搜索下载（网易云 API + yt-dlp 兜底）
# ═══════════════════════════════════════════

def _download_from_netease(query, output_dir):
    """通过网易云音乐 API 搜索并下载，返回 (filepath, title) 或 (None, None)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://music.163.com/",
    }
    try:
        r = requests.post(
            "https://music.163.com/api/search/get/web",
            data={"s": query, "type": 1, "limit": 10, "offset": 0},
            headers=headers, timeout=15,
        )
        data = r.json()
        if data.get("code") != 200 or not data.get("result", {}).get("songs"):
            return None, None
        songs = data["result"]["songs"]
        song_ids = [s["id"] for s in songs]
        r2 = requests.get(
            "https://music.163.com/api/song/enhance/player/url",
            params={"ids": json.dumps(song_ids), "br": 320000},
            headers=headers, timeout=15,
        )
        url_map = {d["id"]: d for d in r2.json().get("data", [])}
        os.makedirs(output_dir, exist_ok=True)
        for s in songs:
            audio_url = url_map.get(s["id"], {}).get("url")
            if not audio_url:
                continue
            artists = "/".join(a["name"] for a in s["artists"])
            title = f"{artists} - {s['name']}"
            safe_name = title.replace("/", "_").replace("\\", "_")[:50]
            filepath = os.path.join(output_dir, f"ref_{safe_name}.mp3")
            r3 = requests.get(audio_url, headers=headers, timeout=60, stream=True)
            r3.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r3.iter_content(8192):
                    f.write(chunk)
            if os.path.getsize(filepath) > 1000:
                return filepath, title
            os.remove(filepath)
    except Exception:
        pass
    return None, None


def _download_from_youtube(query, output_dir):
    """通过 yt-dlp 从 YouTube 搜索下载，返回 (filepath, title) 或 (None, error_msg)"""
    try:
        import yt_dlp
    except ImportError:
        return None, "yt-dlp 未安装"

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
        "default_search": "ytsearch1",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title", "unknown")
            mp3_files = sorted(
                [f for f in os.listdir(output_dir) if f.startswith("ref_") and f.endswith(".mp3")],
                key=lambda f: os.path.getmtime(os.path.join(output_dir, f)),
                reverse=True,
            )
            if mp3_files:
                return os.path.join(output_dir, mp3_files[0]), title
    except Exception as e:
        return None, str(e)
    return None, "下载完成但找不到文件"


def search_and_download_song(query, output_dir):
    """搜索并下载歌曲：网易云 API 优先 → yt-dlp YouTube 兜底"""
    # 优先：网易云音乐 API（纯 HTTP，Cloud 兼容）
    filepath, title = _download_from_netease(query, output_dir)
    if filepath:
        return filepath, title

    # 兜底：yt-dlp 从 YouTube 下载
    filepath, result = _download_from_youtube(query, output_dir)
    if filepath:
        return filepath, result

    return None, (
        f"「{query}」下载失败（网易云无免费版本，YouTube 下载也未成功）。\n\n"
        f"你可以去 Melody 工具下载：\n"
        f"https://melody.panshi-gy.netease.com/tools\n"
        f"账号: xuejin01 / 密码: melody888\n\n"
        f"下载后用「上传文件」方式上传即可。"
    )


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

LYRICS_PROMPT_TEMPLATE = """你是一位顶尖华语流行音乐词作者，擅长根据主题和情绪创作触动人心的歌词。

## 任务
根据以下信息创作一首原创歌词。

## 基本信息
- 主题/灵感: {inspiration}
- 情感基调: {mood}
- 曲风: {genre}
- 声线: {vocal}
- BPM: {bpm}
- 语言: 中英混搭

## 歌词红线（硬性要求，违反任何一条即不合格）

### 核心原则
1. **100%原创**，禁止照搬任何现有歌词
2. **不叙事讲故事，要抽象提炼核心情感，用意象书写感情**
3. **一首歌一个情绪切面**，不要把爱恨离愁全塞进去

### 意象与表达
4. **禁止直述情绪**，每句必须有意象转化（物代情技法）：
   - ❌ 我很孤独 → ✅ 窗外的麻雀在电线杆上多嘴
   - ❌ 你让我心碎 → ✅ 你说"随便"的那个下午，咖啡凉了两遍
   - ❌ 我想你 → ✅ 对话框停在"正在输入"
5. **禁止意象堆砌** — 全曲只用1-2个核心意象深入展开，不要风/雨/花/海/月/星全上
6. **禁止万能情感词** — "回忆/遗憾/永远/离开/一切/自由/只能/最后"全曲最多出现1次
7. **禁止励志口号/库存套话** — 「收伞也能走出来」「千年修行留不住」都是反面教材
8. **禁止古风腔** — "旧罗裳/西厢/轩窗"是反面教材，要现代意象+诗意表达

### 韵律与结构
9. **押韵是硬性要求** — 每段韵脚统一，提前规划韵脚方案
10. **副歌高音位用开口韵母**: -a, -ai, -ao, -ang, -iang, -uang
11. **高音位禁用第三声**，用一声或四声
12. 用 [Verse] [Chorus] [Bridge] 等标签分段
13. 每行7-11字，Verse 3-4行/段，Chorus 4-6行
14. **Chorus核心句要有传唱记忆点** — 至少有一处"看似A实则B"的反转/张力

### 内容安全
15. **禁止出现真实人名/角色名** — 用"你""我"代替
16. **禁止血腥/暴力意象**
17. **内容必须大众可理解** — 禁止小众梗/品牌名/圈层黑话
18. 禁止连续3句以上相同句式开头
19. 禁止无意义口癖词（baby/darling/oh yeah 除非是Hook核心）

### 其他
20. **中英混搭加分** — 适当位置用有实际含义的英文短句
21. 多音字标注拼音（如：觉jiao4）
22. 控制歌词量对应 150-180秒
23. **常识校验** — 写完逐句检查场景是否合理

## 输出格式（严格按此顺序）
1. **歌词**（带段落标签 [Verse 1] [Chorus] 等，完整输出，不得省略任何段落）
2. **押韵方案说明**（每段用什么韵）
3. **一句话创作思路**
"""


# ── 网易 AI 网关配置 ──
NETEASE_BASE_URL = "https://aigw.netease.com/v1"
NETEASE_API_KEY = "trltfs9kdk59cyfw.ov211ltwsnx1fm0kwtz4v8dfp8xmls8t"

# Google Gemini 直连（仅作为浏览器端也失败时的最终降级）
GEMINI_API_KEY = "AIzaSyBrPTIhe9LO3yjZST7Vnq0hh4QTHGTaxJI"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_GATEWAY_TO_GEMINI_FALLBACK = {
    "gemini-3-pro": "gemini-2.5-pro",
    "claude-opus-4-20250514": "gemini-2.5-pro",
    "claude-sonnet-4-20250514": "gemini-2.5-pro",
    "moonshot-v1-8k": "gemini-2.5-flash",
}


def _call_gemini_direct(model, prompt, max_tokens=4096):
    """直接调用 Google Gemini API（最终降级通道）"""
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _build_fetch_js(model, prompt, max_tokens=4096):
    """构建浏览器端 fetch 调用网易 AI 网关的 JavaScript 代码"""
    # 转义 prompt 中的特殊字符（反引号、反斜杠、${}）
    safe_prompt = (prompt
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    return f"""
(async () => {{
    try {{
        const resp = await fetch("{NETEASE_BASE_URL}/chat/completions", {{
            method: "POST",
            headers: {{
                "Authorization": "Bearer {NETEASE_API_KEY}",
                "Content-Type": "application/json"
            }},
            body: JSON.stringify({{
                model: "{model}",
                max_tokens: {max_tokens},
                messages: [{{role: "user", content: `{safe_prompt}`}}]
            }})
        }});
        if (!resp.ok) {{
            const t = await resp.text();
            return JSON.stringify({{error: "HTTP " + resp.status + ": " + t.substring(0, 200), status: "error"}});
        }}
        const data = await resp.json();
        const msg = data.choices[0].message;
        const content = msg.content || msg.reasoning_content || "";
        return JSON.stringify({{content: content, status: "ok"}});
    }} catch (e) {{
        return JSON.stringify({{error: e.message, status: "error"}});
    }}
}})()
"""


def render_browser_ai(model, prompt, max_tokens=4096, component_key="default"):
    """通过 st_javascript 从浏览器端调用网易 AI 网关。

    请求从用户浏览器（中国 IP）发出，绕过服务器 IP 限制。
    返回: dict | 0（等待中）
    """
    js_code = _build_fetch_js(model, prompt, max_tokens)
    return st_javascript(js_code, key=component_key)


def extract_ai_result(result, model=""):
    """从浏览器端调用结果中提取文本"""
    # st_javascript 返回 0 表示 JS 还未执行完
    if result is None or result == 0:
        return None
    # 解析 JSON 字符串结果
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if parsed.get("status") == "ok":
                return parsed.get("content", "")
            return f"__BROWSER_FAILED__:{parsed.get('error', 'unknown')}"
        except json.JSONDecodeError:
            return result  # 直接返回文本
    if isinstance(result, dict):
        if result.get("status") == "ok":
            return result.get("content", "")
        return f"__BROWSER_FAILED__:{result.get('error', 'unknown')}"
    return str(result)


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
    st.sidebar.success("Suno 已连接（自动生成模式）")
else:
    st.sidebar.info("Suno 未配置（手动模式）")

page = st.sidebar.radio(
    "选择功能",
    ["🎵 写一首歌", "🔄 二创翻唱", "⚙️ 设置"],
    index=0,  # 默认打开写歌页面，Suno Cookie 可选
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
    st.subheader("🎵 Suno Cookie（可选，填写后可自动生成歌曲）")

    with st.expander("📖 怎么获取 Suno Cookie？（不填也能用，只是需要手动去 Suno 网页生成）"):
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

    # ── 配置状态总览 ──
    st.subheader("📊 当前配置状态")

    checks = [
        ("Suno Cookie", is_suno_ready(), "可选，填写后自动生成歌曲；不填则跳转 Suno 网页手动操作"),
        ("AI 写歌词", True, "已就绪（Gemini + Claude 双模型比稿，无需配置）"),
    ]

    for name, ok, desc in checks:
        if ok:
            st.markdown(f"✅ **{name}** — {desc}")
        else:
            st.markdown(f"⬜ **{name}** — {desc}（未配置）")

    st.markdown("---")

    # ── 网关连通性诊断 ──
    st.subheader("🔧 网关诊断")
    st.caption("AI 功能通过你的浏览器直接调用网易 AI 网关（不经过 Streamlit 服务器），需要中国大陆网络。")

    if st.button("测试 AI 网关连通性"):
        st.session_state["diag_running"] = True
        st.session_state["diag_id"] = str(int(time.time() * 1000))
        st.rerun()

    if st.session_state.get("diag_running"):
        # 浏览器端调用测试
        st.info("正在通过浏览器测试网关...")
        diag_result = render_browser_ai(
            "gemini-3-pro", "回复OK两个字", max_tokens=20,
            component_key=f"diag_{st.session_state['diag_id']}",
        )
        text = extract_ai_result(diag_result)
        if text is not None:
            st.session_state["diag_running"] = False
            if text and not text.startswith("__BROWSER_FAILED__"):
                st.success(f"✅ 浏览器端网关调用成功！返回: {text[:50]}")
            else:
                st.error(f"❌ 浏览器端网关调用失败: {text}")
                st.warning("请确保你使用中国大陆网络访问。")

    st.markdown("---")
    st.caption("💡 你的密钥只保存在当前浏览器会话中，关闭页面后需要重新输入。我们不会存储你的密钥。")


# ═══════════════════════════════════════════
#  页面：写一首歌
# ═══════════════════════════════════════════
elif page == "🎵 写一首歌":
    st.title("🎵 写一首歌")
    st.markdown("告诉我你想做什么样的歌，剩下的交给 AI。")

    if not is_suno_ready():
        st.info("💡 未填写 Suno Cookie，做歌完成后将跳转 Suno 网页手动生成。填写 Cookie 可自动生成。")

    st.markdown("---")

    # ── 创作方式 ──
    mode = st.radio(
        "你想怎么做？",
        ["💡 我有一个灵感/想法", "📝 我已经写好歌词了", "🎵 我有参考曲，想做类似的"],
        horizontal=True,
    )

    if mode == "💡 我有一个灵感/想法":
        # ── 灵感来源选择 ──
        inspo_source = st.radio(
            "灵感来源",
            ["✏️ 自由输入", "🔥 抖音热点", "📚 Melody 灵感库"],
            horizontal=True,
            key="inspo_source",
        )

        if inspo_source == "✏️ 自由输入":
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
                key="inspo_free",
            )

        elif inspo_source == "🔥 抖音热点":
            # 获取抖音热搜
            if "douyin_trending" not in st.session_state:
                st.session_state["douyin_trending"] = None
                st.session_state["douyin_analysis"] = ""

            if st.button("🔄 获取今日抖音热搜", type="secondary"):
                with st.spinner("正在获取抖音热搜..."):
                    try:
                        _headers = {
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                            "Referer": "https://www.douyin.com/",
                        }
                        r = requests.get(
                            "https://www.douyin.com/aweme/v1/web/hot/search/list/",
                            headers=_headers, timeout=15,
                        )
                        data = r.json()
                        words = data.get("data", {}).get("word_list", [])
                        st.session_state["douyin_trending"] = words[:20]
                    except Exception as e:
                        st.error(f"获取热搜失败: {e}")

            trending = st.session_state.get("douyin_trending")
            if trending:
                st.markdown("### 今日抖音热搜")
                # 展示热搜列表供选择
                topic_options = [f"{i+1}. {t.get('word', '')}" for i, t in enumerate(trending)]
                selected_topics = st.multiselect(
                    "选择感兴趣的热点话题（可多选）",
                    topic_options,
                    key="trending_select",
                )

                if selected_topics and st.button("🤖 AI 分析创作角度", type="secondary"):
                    topics_text = "\n".join(selected_topics)
                    trend_prompt = (
                        f"你是一位华语流行音乐创作顾问。以下是今天的抖音热搜话题：\n\n{topics_text}\n\n"
                        f"请从这些热点中提炼 2-3 个适合写歌的创作角度，每个角度包括：\n"
                        f"1. 核心情感（一句话）\n"
                        f"2. 歌曲方向描述（2-3句，描述这首歌应该表达什么）\n"
                        f"3. 推荐情绪基调（伤感/治愈/热血/甜蜜等）\n\n"
                        f"注意：不要直接写新闻，要提炼其中的情感共鸣点，转化为歌曲创作灵感。"
                    )
                    st.session_state["trend_requesting"] = True
                    st.session_state["trend_prompt"] = trend_prompt
                    st.session_state["trend_req_id"] = str(int(time.time() * 1000))
                    st.rerun()

                # 热点分析进行中（浏览器端调用）
                if st.session_state.get("trend_requesting"):
                    trend_raw = render_browser_ai(
                        "claude-opus-4-20250514",
                        st.session_state["trend_prompt"],
                        max_tokens=1500,
                        component_key=f"trend_{st.session_state['trend_req_id']}",
                    )
                    trend_text = extract_ai_result(trend_raw)
                    if trend_text is not None:
                        if trend_text.startswith("__BROWSER_FAILED__"):
                            try:
                                trend_text = _call_gemini_direct(
                                    "gemini-2.5-pro", st.session_state["trend_prompt"], 1500
                                )
                            except Exception as e:
                                trend_text = f"AI 分析失败: {e}"
                        st.session_state["douyin_analysis"] = trend_text
                        st.session_state["trend_requesting"] = False
                        st.rerun()
                    else:
                        st.info("AI 正在分析创作角度...")

                if st.session_state.get("douyin_analysis"):
                    st.markdown("### AI 创作角度分析")
                    st.markdown(st.session_state["douyin_analysis"])
                    st.markdown("---")

            inspiration = st.text_area(
                "基于热点话题，写下你的创作灵感",
                placeholder="可以直接复制上面 AI 的分析，也可以用自己的想法...",
                height=120,
                key="inspo_trending",
            )

        else:  # Melody 灵感库
            st.markdown("""
            ### Melody 合伙人灵感库

            点击下方链接进入灵感库，浏览灵感后回来填写。
            """)
            st.link_button(
                "🔗 打开 Melody 灵感库",
                "https://melody.panshi-gy.netease.com/creative?tab=inspirationLibrary",
                type="primary",
            )
            st.info("**登录账号:** xuejin01 &nbsp;&nbsp; **密码:** melody888")
            st.markdown("---")
            inspiration = st.text_area(
                "从灵感库获取灵感后，描述你的创作想法",
                placeholder="比如：灵感库里有一条「雨天咖啡馆的邂逅」，我想做一首类似氛围的歌...",
                height=120,
                key="inspo_melody",
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
    #  使用浏览器端组件调用网易 AI 网关（绕过服务器 IP 限制）
    # ═══════════════════════════════════════════
    if mode == "💡 我有一个灵感/想法" and not lyrics_input:
        if can_generate_lyrics():
            st.subheader("第 1 步：AI 写歌词")
            st.caption("Gemini + Claude 各写一版，你来挑最好的")

            # 点击按钮 → 生成 request_id → 触发浏览器端 AI 调用
            if st.button("✍️ AI 写歌词", type="secondary", use_container_width=True):
                if not inspiration:
                    st.error("请先填写你的灵感/想法")
                    st.stop()
                lyrics_prompt = LYRICS_PROMPT_TEMPLATE.format(
                    inspiration=inspiration, mood=mood_clean, genre=genre_clean,
                    vocal=vocal_clean, bpm=bpm,
                )
                st.session_state["lyrics_prompt"] = lyrics_prompt
                st.session_state["lyrics_requesting"] = True
                st.session_state["lyrics_req_id"] = str(int(time.time() * 1000))
                st.session_state["lyrics_generated"] = False
                st.session_state["lyrics_gemini"] = ""
                st.session_state["lyrics_claude"] = ""
                st.rerun()

            # 浏览器端 AI 调用进行中
            if st.session_state.get("lyrics_requesting"):
                req_id = st.session_state["lyrics_req_id"]
                prompt = st.session_state["lyrics_prompt"]

                st.info("🎵 AI 正在写歌词（从浏览器端调用网易 AI 网关），请稍等约 30-60 秒...")

                # 两个隐藏组件并行调用：Gemini + Opus（从用户浏览器发出请求）
                gemini_raw = render_browser_ai(
                    "gemini-3-pro", prompt, max_tokens=4096,
                    component_key=f"lyrics_gemini_{req_id}",
                )
                opus_raw = render_browser_ai(
                    "claude-opus-4-20250514", prompt, max_tokens=4096,
                    component_key=f"lyrics_opus_{req_id}",
                )

                gemini_text = extract_ai_result(gemini_raw, "gemini-3-pro")
                opus_text = extract_ai_result(opus_raw, "claude-opus-4-20250514")

                # 检查是否有浏览器端失败（用户不在中国），尝试 Gemini 服务端降级
                if gemini_text and gemini_text.startswith("__BROWSER_FAILED__"):
                    try:
                        gemini_text = _call_gemini_direct("gemini-2.5-pro", prompt)
                    except Exception as e:
                        gemini_text = f"写词失败: {e}"
                if opus_text and opus_text.startswith("__BROWSER_FAILED__"):
                    try:
                        opus_text = _call_gemini_direct("gemini-2.5-pro", prompt)
                    except Exception as e:
                        opus_text = f"写词失败: {e}"

                # 两个都完成了
                if gemini_text is not None and opus_text is not None:
                    st.session_state["lyrics_gemini"] = gemini_text
                    st.session_state["lyrics_claude"] = opus_text
                    st.session_state["lyrics_requesting"] = False
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

                # 自动生成歌名（浏览器端调用）
                if lyrics_input and not title:
                    if "auto_title" not in st.session_state:
                        st.session_state["auto_title"] = ""

                    if st.button("🏷️ AI 起歌名", type="secondary"):
                        name_prompt = (
                            f"你是抖音爆款歌曲命名专家。根据以下歌词，起5个有抖音网感的歌名。\n\n"
                            f"要求：\n- 2-5个字\n- 有意境、有记忆点\n"
                            f"- 适合在抖音传播（年轻化、有情绪共鸣）\n"
                            f"- 可以用「·」分隔增加格调感\n"
                            f"- 只输出歌名，每行一个，不要编号不要解释\n\n"
                            f"歌词：\n{lyrics_input[:500]}"
                        )
                        st.session_state["name_requesting"] = True
                        st.session_state["name_prompt"] = name_prompt
                        st.session_state["name_req_id"] = str(int(time.time() * 1000))
                        st.rerun()

                    # 歌名生成中
                    if st.session_state.get("name_requesting"):
                        name_raw = render_browser_ai(
                            "moonshot-v1-8k",
                            st.session_state["name_prompt"],
                            max_tokens=150,
                            component_key=f"name_{st.session_state['name_req_id']}",
                        )
                        name_text = extract_ai_result(name_raw)
                        if name_text is not None:
                            if name_text.startswith("__BROWSER_FAILED__"):
                                try:
                                    name_text = _call_gemini_direct(
                                        "gemini-2.5-flash", st.session_state["name_prompt"], 150
                                    )
                                except Exception:
                                    name_text = ""
                            st.session_state["auto_title"] = name_text.strip()
                            st.session_state["name_requesting"] = False
                            st.rerun()
                        else:
                            st.info("AI 起名中...")

                    if st.session_state.get("auto_title"):
                        st.markdown(f"**AI 建议歌名：**\n{st.session_state['auto_title']}")
                        st.caption("请在上方「歌名」输入框填入你喜欢的名字")

                st.markdown("---")
    # ═══════════════════════════════════════════
    #  第二步：提交 Suno 做歌
    # ═══════════════════════════════════════════
    st.subheader("第 2 步：提交做歌" if mode == "💡 我有一个灵感/想法" and can_generate_lyrics() else "")

    if st.button("🚀 开始做歌", type="primary", use_container_width=True):
        has_searched_ref = bool(st.session_state.get("searched_ref_path"))
        if not inspiration and not lyrics_input and not ref_audio and not has_searched_ref:
            st.error("请至少填写一个灵感、歌词或上传/搜索参考曲")
            st.stop()

        # 没有 Cookie → 直接走手动模式
        if not is_suno_ready():
            show_suno_fallback(lyrics_input, style_prompt, title)
        else:
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
        st.info("💡 未填写 Suno Cookie，二创完成后将跳转 Suno 网页手动生成。填写 Cookie 可自动生成。")

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

        style = f"{target_style}, {vocal_map.get(target_vocal, target_vocal)}, studio quality"
        if len(style) > 200:
            style = style[:200]

        # 没有 Cookie → 直接走手动模式
        if not is_suno_ready():
            show_suno_fallback("", style, title or "二创版本")
        else:
            output_dir = get_output_dir()
            progress = st.empty()

            # 保存上传文件
            audio_path = os.path.join(output_dir, f"original_{audio_file.name}")
            with open(audio_path, "wb") as f:
                f.write(audio_file.read())

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


# ── 启动入口（本地运行时） ──
if __name__ == "__main__":
    os.system(f"{sys.executable} -m streamlit run {__file__} --server.headless=false --browser.gatherUsageStats=false")
