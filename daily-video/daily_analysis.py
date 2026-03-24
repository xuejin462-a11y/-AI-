#!/usr/bin/env python3
"""每日视频分析+Cover准备 — 15:00自动执行
1. 分析热门视频案例+输出优化建议 → 邮件
2. 从抖音热搜筛选音乐类话题 → kie.ai Cover → 存成品供16:00视频任务用
"""

import json, os, sys, subprocess, time, smtplib, re, tempfile, urllib.request
from datetime import date, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

def load_env():
    env_file = Path(__file__).resolve().parent.parent / "suno-api" / ".env"
    if not env_file.exists():
        env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env()

BASE_DIR = os.path.expanduser("~/Documents/claude/自动化")
CLAUDE_CLI = os.path.expanduser("~/.npm-global/bin/claude")
TODAY = date.today().isoformat()
COVER_OUTPUT_DIR = os.path.expanduser(f"~/Documents/claude/歌曲/cover/{TODAY}")
USED_COVERS_FILE = os.path.join(BASE_DIR, "daily-video/used_covers.json")

# 邮件配置
SMTP_HOST = "smtp.163.com"
SMTP_PORT = 465
SMTP_USER = os.environ.get("SMTP_USER", "15876517929@163.com")
SMTP_PASS = os.environ["SMTP_PASS"]
TO_EMAIL = "xuejin01@corp.netease.com"

# kie.ai配置
KIE_API_KEY = ""
def load_kie_key():
    global KIE_API_KEY
    env_path = os.path.join(BASE_DIR, "suno-api/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("KIE_API_KEY="):
                    KIE_API_KEY = line.strip().split("=", 1)[1].strip('"').strip("'")
    return KIE_API_KEY

# 5位音乐人声线（kie.ai vocalGender参数）
ARTISTS = {
    "树离suliii_": "female",
    "屿川": "male",
    "晴日西多士": "female",
    "S1ent": "male",
    "靓仔阿辉Rex": "male",
}


# ============================================================
# Part 1: 分析报告（原有功能）
# ============================================================

def get_trending_topics():
    """获取当前抖音热搜"""
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, "daily-video"))
        from douyin_trending import fetch_trending
        data = fetch_trending(use_cache_minutes=60)
        if data:
            trending = data.get("trending", [])
            rising = data.get("rising", [])
            return trending, rising
    except Exception as e:
        print(f"热搜获取失败: {e}")
    return [], []


def get_account_stats():
    """查询抖音账号数据"""
    try:
        import requests
        r = requests.get(
            "https://www.iesdouyin.com/web/api/v2/user/info?unique_id=25402212346",
            headers={"User-Agent": "com.ss.android.ugc.aweme/110101"},
            timeout=15
        )
        if r.status_code == 200:
            text = r.text
            nickname = re.findall(r'"nickname":"([^"]+)"', text)
            followers = re.findall(r'"follower_count":(\d+)', text)
            total_favorited = re.findall(r'"total_favorited":"?(\d+)"?', text)
            aweme_count = re.findall(r'"aweme_count":(\d+)', text)
            return {
                "nickname": nickname[0] if nickname else "淘歌的小进",
                "followers": int(followers[0]) if followers else 0,
                "total_likes": int(total_favorited[0]) if total_favorited else 0,
                "video_count": int(aweme_count[0]) if aweme_count else 0,
            }
    except Exception as e:
        print(f"账号数据获取失败: {e}")
    return {"nickname": "淘歌的小进", "followers": 0, "total_likes": 0, "video_count": 0}


def get_our_recent_videos():
    """获取我们最近生成的视频信息"""
    output_base = os.path.expanduser("~/Documents/claude/输出文件/视频")
    recent = []
    if not os.path.exists(output_base):
        return recent
    for d in sorted(os.listdir(output_base), reverse=True)[:3]:
        dir_path = os.path.join(output_base, d)
        if os.path.isdir(dir_path):
            files = [f for f in os.listdir(dir_path) if f.endswith('.mp4')]
            txts = [f for f in os.listdir(dir_path) if f.endswith('.txt')]
            recent.append({"date": d, "videos": files, "copies": txts})
    return recent


def analyze_with_claude(trending, rising, account):
    """用Claude分析视频优化方向"""
    our_videos = get_our_recent_videos()

    kb_path = os.path.expanduser("~/Documents/claude/知识库/视频制作/动态背景模版组合.md")
    kb_content = ""
    if os.path.exists(kb_path):
        with open(kb_path) as f:
            kb_content = f.read()[:2000]

    trending_words = [t["word"] for t in trending[:20]]
    rising_words = [r["word"] for r in rising]

    prompt = f"""你是抖音歌词视频运营专家。请基于以下信息，输出今日视频优化分析报告。

## 我们的抖音账号「{account['nickname']}」
- 粉丝：{account['followers']}
- 总获赞：{account['total_likes']}
- 作品数：{account['video_count']}
- 阶段：起号期（粉丝<1000）
- 目标：先到1000粉开橱窗

## 当前抖音热搜TOP20
{chr(10).join(f'{i+1}. {t}' for i, t in enumerate(trending_words[:20]))}

## 上升热点
{chr(10).join(f'- {r}' for r in rising_words)}

## 我们最近生成的视频
{json.dumps(our_videos, ensure_ascii=False, indent=2)}

请输出以下内容（用中文）：

### 一、今日热搜中适合做歌词视频的话题（3-5个）
### 二、当前我们视频的优势
### 三、可以优化的方向（3-5个具体建议）
### 四、竞品案例参考（给出抖音搜索关键词）
### 五、账号诊断
### 六、对标账号跟踪（每日必看）
我们长期跟踪以下5个对标账号，分析他们最近的新动作：
1. **阿霖**（百万粉，情绪爆发型歌词视频）— 搜索：「阿霖 歌词」
2. **猫不懂**（百万粉，古风文学向）— 搜索：「猫不懂 歌词视频」
3. **音乐的入门到改行**（10万+，R&B改编+精致画面）— 搜索：「音乐的入门到改行」
4. **大头针**（50万粉，AI翻唱经典歌曲）— 搜索：「大头针 翻唱」
5. **奶茶小肥仔**（383万粉，影视剧+歌曲改编）— 搜索：「奶茶小肥仔」

针对每个账号分析：
- 最近有没有新爆款（点赞破万的视频），如果有，拆解它的做法
- 他们最近在用什么新手法/新模版/新特效
- 有没有我们可以立刻学的具体做法

### 七、热门歌词视频案例拆解
从当天抖音热搜/热门中，再找2-3个我们没跟踪但做得好的歌词视频案例：
每个案例包括：
- 搜索关键词（让人能在抖音搜到）
- 视频结构：前3秒怎么留人、歌词怎么展示、背景用了什么
- 我们能直接抄的具体做法（字号/字色/动画/背景类型）
- 和我们当前模版的差距

### 八、16:00视频模版迭代建议
基于以上对标跟踪+案例分析，给出今天16:00视频任务应该调整的具体参数：
- 字幕样式：字号/字色/描边/动画要怎么改
- 背景：用什么风格更好
- 前3秒金句：怎么设计
- 歌词展示节奏：逐句/逐字/淡入/弹入
- 其他可以立刻改的细节
每条建议要精确到参数级别（如"字号从110改为130"、"描边从3px改为5px"）

### 九、明日建议

报告要简洁实用，案例分析要具体到可执行。对标账号分析是最重要的部分，要认真跟踪。"""

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "NO_COLOR": "1"},
        )
        if result.returncode == 0:
            cli_output = json.loads(result.stdout.strip())
            return cli_output.get("result", result.stdout.strip())
        else:
            return f"Claude分析失败 (返回码{result.returncode})"
    except Exception as e:
        return f"Claude调用失败: {e}"


def send_email(subject, body):
    """发送邮件"""
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    html_content = f"""
    <html><body style="font-family: -apple-system, sans-serif; line-height: 1.6; color: #333; max-width: 700px; margin: 0 auto; padding: 20px;">
    <h1 style="color: #1a1a1a; border-bottom: 2px solid #d4a853; padding-bottom: 10px;">
        {subject}
    </h1>
    <pre style="white-space: pre-wrap; font-family: -apple-system, sans-serif; font-size: 14px;">{body}</pre>
    <hr style="border: 1px solid #eee; margin-top: 30px;">
    <p style="color: #999; font-size: 12px;">由 AI音乐工坊 自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </body></html>
    """
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        import ssl
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"  邮件已发送至 {TO_EMAIL}")
        return True
    except Exception as e:
        print(f"  邮件发送失败: {e}")
        return False


# ============================================================
# Part 2: Cover准备
# ============================================================

def filter_music_from_trending(trending, rising):
    """从热搜中筛选音乐类话题"""
    music_keywords = ["歌", "唱", "翻唱", "神曲", "音乐", "演唱会", "新歌",
                       "MV", "旋律", "歌词", "单曲", "专辑", "OST", "BGM", "cover"]
    results = []
    for t in trending + rising:
        word = t.get("word", "")
        matched = [k for k in music_keywords if k in word]
        if matched:
            results.append({"word": word, "matched_keywords": matched})
    return results


def load_used_covers():
    """加载已cover过的歌曲"""
    if os.path.exists(USED_COVERS_FILE):
        with open(USED_COVERS_FILE) as f:
            return json.load(f)
    return []


def save_used_cover(song_name, artist):
    """记录已cover的歌曲"""
    covers = load_used_covers()
    covers.append({"song": song_name, "artist": artist, "date": TODAY})
    with open(USED_COVERS_FILE, 'w') as f:
        json.dump(covers, f, ensure_ascii=False, indent=2)


def select_cover_song(music_topics):
    """用Claude从音乐类热搜中提取具体歌名+歌手，并选择最适合的音乐人声线"""
    if not music_topics:
        return None

    used = load_used_covers()
    used_songs = [c["song"] for c in used]
    topics_str = "\n".join(f"- {t['word']}" for t in music_topics)

    prompt = (
        f"以下是今天抖音热搜中的音乐相关话题：\n{topics_str}\n\n"
        f"已经cover过的歌（排除）：{', '.join(used_songs) if used_songs else '无'}\n\n"
        f"请从中提取出一首最适合做R&B风格Cover的歌曲。\n"
        f"然后从以下5位音乐人中选择声线最匹配的：\n"
        f"- 树离suliii_（女声，温柔清新）\n"
        f"- 屿川（男声，低沉磁性）\n"
        f"- 晴日西多士（女声，甜美）\n"
        f"- S1ent（男声，古风质感）\n"
        f"- 靓仔阿辉Rex（男声，说唱/潮流）\n\n"
        f'只返回JSON: {{"song": "歌名", "artist": "原唱歌手", "cover_by": "选择的音乐人", '
        f'"vocal_gender": "male或female", "reason": "选择理由"}}'
    )

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "NO_COLOR": "1"},
        )
        if result.returncode == 0:
            cli_output = json.loads(result.stdout.strip())
            text = cli_output.get("result", result.stdout.strip())
            json_match = re.search(r'\{[^}]*"song"[^}]*\}', text)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"  Claude选歌失败: {e}")
    return None


def download_original_song(song_name, artist):
    """用yt-dlp下载原曲音频，多种方式尝试"""
    output_path = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
    search_queries = [
        f"{song_name} {artist}",
        f"{song_name} official audio",
        f"{song_name} MV",
    ]

    # 多种下载方式：YouTube(带cookies) → B站(带cookies)
    _yt_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    _yt_proxy_args = ["--proxy", _yt_proxy] if _yt_proxy else []
    attempts = [
        # YouTube + Chrome cookies
        {"source": "ytsearch1", "extra": _yt_proxy_args + ["--cookies-from-browser", "chrome"]},
        # B站 + Chrome cookies
        {"source": "bilisearch1", "extra": ["--cookies-from-browser", "chrome"]},
        # YouTube 无cookies
        {"source": "ytsearch1", "extra": _yt_proxy_args},
    ]

    for query in search_queries:
        for attempt in attempts:
            try:
                cmd = ["yt-dlp", f"{attempt['source']}:{query}", "-x", "--audio-format", "mp3",
                       "--audio-quality", "0", "-o", output_path, "--no-playlist"] + attempt["extra"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                    src = "B站" if "bili" in attempt["source"] else "YouTube"
                    print(f"  原曲下载成功: {os.path.getsize(output_path)/1024/1024:.1f}MB ({src})")
                    return output_path
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass

    print(f"  所有下载方式都失败")
    return None


def truncate_for_cover(input_path, output_path, max_duration=100):
    """截取前100秒（kie.ai限制2分钟）"""
    try:
        import librosa
        import soundfile as sf
        y, sr = librosa.load(input_path, sr=22050)
        total = len(y) / sr
        if total > max_duration:
            y = y[:int(max_duration * sr)]
        sf.write(output_path, y, sr)
        print(f"  截取{min(total, max_duration):.0f}秒")
        return True
    except Exception as e:
        print(f"  截取失败: {e}")
        return False


def upload_to_tmpfiles(filepath):
    """上传到tmpfiles.org"""
    import requests
    try:
        with open(filepath, "rb") as f:
            resp = requests.post("https://tmpfiles.org/api/v1/upload",
                                files={"file": ("audio.mp3", f, "audio/mpeg")}, timeout=30)
        raw_url = resp.json().get("data", {}).get("url", "")
        url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        # 验证
        check = requests.head(url, timeout=10)
        if check.status_code == 200:
            print(f"  上传成功: {url}")
            return url
        else:
            print(f"  URL验证失败: HTTP {check.status_code}")
    except Exception as e:
        print(f"  上传失败: {e}")
    return None


def submit_kie_cover(audio_url, vocal_gender="female"):
    """提交kie.ai Cover任务（纯R&B风格，原词原曲不变）"""
    import requests
    load_kie_key()
    if not KIE_API_KEY:
        print("  KIE_API_KEY未配置")
        return None

    payload = {
        "audioUrl": audio_url,
        "model": "V5",
        "instrumental": False,
        "vocalGender": vocal_gender,
        "style": "R&B",
        "callBackUrl": "https://webhook.site/ignore",
    }

    try:
        resp = requests.post(
            "https://api.kie.ai/api/v1/generate/upload-cover",
            headers={"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        result = resp.json()
        if result.get("code") == 200:
            task_id = result.get("data", {}).get("taskId", "")
            print(f"  Cover任务提交成功: {task_id}")
            return task_id
        else:
            print(f"  提交失败: {result}")
    except Exception as e:
        print(f"  kie.ai调用失败: {e}")
    return None


def poll_kie_result(task_id, timeout_minutes=10):
    """轮询kie.ai Cover结果"""
    import requests
    load_kie_key()

    for i in range(timeout_minutes * 6):  # 每10秒查一次
        time.sleep(10)
        try:
            r = requests.get(
                f"https://api.kie.ai/api/v1/generate/record-info?taskId={task_id}",
                headers={"Authorization": f"Bearer {KIE_API_KEY}"},
                timeout=30,
            )
            data = r.json().get("data")
            if data is None:
                continue

            # kie.ai cover结果在 response.sunoData 里
            response = data.get("response", {})
            suno_data = response.get("sunoData", [])

            if suno_data and len(suno_data) > 0:
                audio_url = suno_data[0].get("audioUrl", "")
                if audio_url:
                    print(f"  Cover完成! ({i*10}秒)")
                    return audio_url

            status = data.get("status", "")
            if status in ("FAILED", "failed"):
                print(f"  Cover失败: {data.get('failMsg', '')}")
                return None

            if i % 6 == 0:
                print(f"  等待中... ({i*10}秒)")
        except Exception as e:
            if i % 12 == 0:
                print(f"  轮询错误: {e}")

    print("  Cover超时")
    return None


def download_cover_result(audio_url, song_name, cover_by):
    """下载cover成品"""
    os.makedirs(COVER_OUTPUT_DIR, exist_ok=True)
    safe_name = song_name.replace("/", "_").replace(" ", "_")
    output_path = os.path.join(COVER_OUTPUT_DIR, f"{safe_name}_R&B版_{cover_by}.wav")

    try:
        urllib.request.urlretrieve(audio_url, output_path)
        size = os.path.getsize(output_path) / 1024 / 1024
        print(f"  下载完成: {output_path} ({size:.1f}MB)")
        return output_path
    except Exception as e:
        print(f"  下载失败: {e}")
        return None


def run_cover_pipeline(music_topics):
    """Cover完整流水线"""
    if not music_topics:
        print("  今天热搜没有音乐类话题，跳过Cover")
        return None

    # Step 1: Claude选歌+选声线
    print("  [1/5] Claude选歌...")
    song_info = select_cover_song(music_topics)
    if not song_info:
        print("  选歌失败，跳过Cover")
        return None

    song_name = song_info.get("song", "")
    artist = song_info.get("artist", "")
    cover_by = song_info.get("cover_by", "树离suliii_")
    vocal_gender = song_info.get("vocal_gender", "female")
    print(f"  选定: 《{song_name}》({artist}) → {cover_by}({vocal_gender}) R&B版")

    # Step 2: 下载原曲
    print("  [2/5] 下载原曲...")
    original_path = download_original_song(song_name, artist)
    if not original_path:
        print("  原曲下载失败，跳过Cover")
        return None

    # Step 3: 截取+上传
    print("  [3/5] 截取+上传...")
    truncated_path = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
    if not truncate_for_cover(original_path, truncated_path):
        return None

    audio_url = upload_to_tmpfiles(truncated_path)
    if not audio_url:
        return None

    # Step 4: kie.ai Cover
    print("  [4/5] kie.ai Cover (R&B)...")
    task_id = submit_kie_cover(audio_url, vocal_gender)
    if not task_id:
        return None

    cover_url = poll_kie_result(task_id)
    if not cover_url:
        return None

    # Step 5: 下载成品
    print("  [5/5] 下载Cover成品...")
    result_path = download_cover_result(cover_url, song_name, cover_by)
    if result_path:
        save_used_cover(song_name, artist)
        return {
            "path": result_path,
            "song": song_name,
            "artist": artist,
            "cover_by": cover_by,
            "style": "R&B",
        }

    # 清理临时文件
    for tmp in [original_path, truncated_path]:
        if os.path.exists(tmp):
            os.remove(tmp)

    return None


# ============================================================
# Main
# ============================================================

def main():
    _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if _proxy:
        os.environ['http_proxy'] = _proxy
        os.environ['https_proxy'] = _proxy

    print(f"{'='*50}")
    print(f"每日视频分析 + Cover准备 — {TODAY} 15:00")
    print(f"{'='*50}")

    # === Part 1: 分析报告 ===
    print("\n【Part 1】分析报告")
    trending, rising = get_trending_topics()
    account = get_account_stats()
    print(f"  账号: {account['nickname']} | 粉丝{account['followers']} | 获赞{account['total_likes']} | 作品{account['video_count']}")

    print("  Claude分析中...")
    report = analyze_with_claude(trending, rising, account)
    print(f"  分析完成: {len(report)}字")

    # 保存+发送
    report_dir = os.path.join(BASE_DIR, "daily-video/analysis")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, f"{TODAY}.md"), 'w') as f:
        f.write(f"# 每日视频分析报告 — {TODAY}\n\n{report}")

    send_email(f"📊 每日视频分析报告 — {TODAY}", report)

    # === Part 2: Cover准备 ===
    print(f"\n【Part 2】Cover准备")

    # 从热搜筛选音乐类话题
    music_topics = filter_music_from_trending(trending, rising)
    print(f"  热搜中音乐类话题: {len(music_topics)}条")
    for t in music_topics:
        print(f"    - {t['word']} (命中: {','.join(t['matched_keywords'])})")

    # TODO: 抖音开放平台审核通过后，这里加官方热歌榜API
    # douyin_hot_songs = fetch_douyin_hot_songs(client_key, client_secret)
    # music_topics += douyin_hot_songs

    # 执行Cover流水线
    cover_result = run_cover_pipeline(music_topics)

    if cover_result:
        print(f"\n  ✅ Cover完成: 《{cover_result['song']}》{cover_result['style']}版 by {cover_result['cover_by']}")
        print(f"  文件: {cover_result['path']}")

        # 通知邮件
        cover_msg = (
            f"今日Cover完成：\n\n"
            f"歌曲：《{cover_result['song']}》\n"
            f"原唱：{cover_result['artist']}\n"
            f"Cover：{cover_result['cover_by']} ({cover_result['style']}版)\n"
            f"文件：{cover_result['path']}\n\n"
            f"16:00视频任务将使用此音频生成歌词视频。"
        )
        send_email(f"🎵 今日Cover完成 — 《{cover_result['song']}》", cover_msg)
    else:
        print(f"\n  ⚠️ 今天没有产出Cover（可能热搜没有音乐话题）")

    print(f"\n{'='*50}")
    print("完成")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
