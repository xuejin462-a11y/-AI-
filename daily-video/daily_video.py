#!/usr/bin/env python3
"""每日视频生成器 — 模式1(从歌出发)+模式2(从热点出发)，每天产出4个视频"""

import json, os, sys, subprocess, tempfile, urllib.request, time, random, glob, re
from datetime import date
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

# === 路径 ===
BASE_DIR = os.path.expanduser("~/Documents/claude/自动化")
POOL_FILE = os.path.join(BASE_DIR, "daily-music/rhythm_pool.json")
DONE_FILE = os.path.join(BASE_DIR, "daily-video/video_done_ids.txt")
TEMPLATE_SCRIPT = os.path.join(BASE_DIR, "daily-video/gen_video_v2.py")
OUTPUT_BASE = os.path.expanduser("~/Documents/claude/输出文件/视频")
CLAUDE_CLI = os.path.expanduser("~/.npm-global/bin/claude")

TODAY = date.today().isoformat()
USED_TOPICS_FILE = os.path.join(BASE_DIR, "daily-video/used_topics.json")

# ============================================================
# 7套模版参数映射：mood -> 视频环境变量
# ============================================================
BG_LIBRARY = os.path.join(BASE_DIR, "daily-video/bg_library")

def pick_bg_image(mood):
    """从bg_library中随机选一条驾车视频，fallback到公路静态图"""
    # 优先用驾车视频
    videos = glob.glob(os.path.join(BG_LIBRARY, "road_drive_*.mp4"))
    if videos:
        chosen = random.choice(videos)
        print(f"    背景视频: {os.path.basename(chosen)}")
        return chosen
    # fallback: 静态公路图
    images = glob.glob(os.path.join(BG_LIBRARY, "road_*.png"))
    if not images:
        images = glob.glob(os.path.join(BG_LIBRARY, "*.png"))
    if not images:
        return ""
    chosen = random.choice(images)
    print(f"    背景图: {os.path.basename(chosen)}")
    return chosen

MOOD_TEMPLATES = {
    "A": {  # 深海沉溺 -- 伤感/失恋
        "name": "深海沉溺", "bg_type": "bokeh_v5", "style_name": "classic",
        "lyric_bottom_alpha": "0",  # 单层模式
        "lyric_top_color": "255,255,255",
        "no_flash": "true", "no_shake": "true",
    },
    "B": {  # 星空低语 -- 思念/暗恋
        "name": "星空低语", "bg_type": "starfield", "style_name": "classic",
        "lyric_bottom_alpha": "0",
        "lyric_top_color": "255,240,180",
        "no_flash": "true", "no_shake": "true",
    },
    "C": {  # 晨光治愈 -- 治愈/释怀
        "name": "晨光治愈", "bg_type": "bokeh_warm", "style_name": "classic",
        "lyric_bottom_alpha": "0",
        "lyric_top_color": "255,255,255",
        "no_flash": "true", "no_shake": "true",
    },
    "D": {  # 霓虹燃烧 -- 愤怒/执念
        "name": "霓虹燃烧", "bg_type": "neon_pulse", "style_name": "dark",
        "lyric_bottom_alpha": "0",
        "lyric_top_color": "255,60,60",
        "no_flash": "false", "no_shake": "false",
    },
    "E": {  # 粉色泡泡 -- 甜蜜/浪漫
        "name": "粉色泡泡", "bg_type": "bokeh_sweet", "style_name": "sweet",
        "lyric_bottom_alpha": "0",
        "lyric_top_color": "255,235,240",
        "no_flash": "true", "no_shake": "true",
    },
    "F": {  # 烟雾独白 -- 孤独/深夜
        "name": "烟雾独白", "bg_type": "jazz_smoke", "style_name": "classic",
        "lyric_bottom_alpha": "0",
        "lyric_top_color": "200,200,210",
        "no_flash": "true", "no_shake": "true",
    },
    "G": {  # 墨韵叠章 -- 情感丰富/古风（双层字幕）
        "name": "墨韵叠章", "bg_type": "ink_wash", "style_name": "dark",
        "lyric_bottom_alpha": "0.65",  # 双层模式，底层红字更透
        "lyric_top_color": "220,215,210",  # 柔灰白，不刺眼
        "no_flash": "true", "no_shake": "true",
    },
}

def load_done_ids():
    if not os.path.exists(DONE_FILE):
        return set()
    with open(DONE_FILE) as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_done_id(song_id):
    with open(DONE_FILE, 'a') as f:
        f.write(f"{song_id}\n")

def load_pool():
    with open(POOL_FILE) as f:
        data = json.load(f)
    return data.get('pool', [])

MELODY_LIBRARY_SONGS = os.path.expanduser("~/Documents/claude/melody-library/songs.json")
MELODY_LIBRARY_WAV = os.path.expanduser("~/Documents/claude/melody-library/wav")
TARGET_ARTISTS = ['树离', '屿川', '晴日西多士', 'S1ent', '靓仔阿辉']

def pick_songs(pool, done_ids, count, trending_data=None):
    """选歌策略（三步）：
    1. 旋律适合抖音：rhythm_score排序 + 排除民谣/慢歌（BPM预估，此处用rhythm_score代理）
    2. 匹配今日热搜：如有trending_data则优先热搜关联歌曲
    3. 来源：优先从melody-library全量曲库选5位目标音乐人的歌
    """
    # 优先从melody-library读取5位目标音乐人的歌
    library_songs = []
    if os.path.exists(MELODY_LIBRARY_SONGS):
        try:
            with open(MELODY_LIBRARY_SONGS) as f:
                lib_data = json.load(f)
            all_songs = lib_data.get('songs', [])
            for s in all_songs:
                artist = s.get('artist_name', '')
                if any(t in artist for t in TARGET_ARTISTS):
                    wav_name = f"{artist}-{s.get('name', '')}.wav"
                    wav_path = os.path.join(MELODY_LIBRARY_WAV, wav_name)
                    if os.path.exists(wav_path):
                        s['wav_path'] = wav_path
                        library_songs.append(s)
        except Exception as e:
            print(f"  melody-library读取失败({e})，回退到rhythm_pool")

    # 合并两个来源，melody-library优先
    combined = {s['id']: s for s in library_songs}
    for s in pool:
        if s['id'] not in combined:
            combined[s['id']] = s

    candidates = [s for s in combined.values()
                  if s['id'] not in done_ids
                  and s.get('artist_name', '').startswith('artist_') is False
                  and s.get('artist_name', '') not in ('', 'artist_None')
                  and s.get('original_lyric', '').strip()]

    # 热搜关联优先（若trending_data存在）
    if trending_data:
        hot_words = [t["word"] for t in trending_data.get("trending", [])[:20]]
        def trending_score(s):
            lyric = s.get('original_lyric', '') + s.get('name', '')
            return sum(1 for w in hot_words if any(c in lyric for c in w if len(c) > 1))
        candidates.sort(key=lambda s: (trending_score(s), s.get('rhythm_score', 0)), reverse=True)
    else:
        candidates.sort(key=lambda x: x.get('rhythm_score', 0), reverse=True)

    return candidates[:count]

def download_audio(url, dest):
    """下载音频文件"""
    print(f"  下载音频...")
    try:
        urllib.request.urlretrieve(url, dest)
        size = os.path.getsize(dest) / 1024 / 1024
        print(f"  下载完成 ({size:.1f} MB)")
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False

def truncate_audio(input_path, output_path, duration=20):
    """用librosa截取高潮段"""
    try:
        import librosa
        import soundfile as sf
        import numpy as np

        y, sr = librosa.load(input_path, sr=22050)
        total_dur = len(y) / sr

        if total_dur <= duration + 5:
            y_clip = y[:int(duration * sr)]
        else:
            rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
            window = int(duration * sr / 512)
            best_start = 0
            best_energy = 0
            for i in range(len(rms) - window):
                energy = np.sum(rms[i:i+window])
                if energy > best_energy:
                    best_energy = energy
                    best_start = i

            start_sample = best_start * 512
            start_sample = max(0, start_sample - 5 * sr)
            end_sample = start_sample + int(duration * sr)
            y_clip = y[start_sample:end_sample]

        sf.write(output_path, y_clip, sr)
        print(f"  截取 {duration}s 高潮段")
        return True
    except Exception as e:
        print(f"  截取失败: {e}")
        return False


# ============================================================
# Gemini 歌曲背景研究 -- 分析歌词主题，生成有梗弹幕+Hooks
# ============================================================
def research_song_context(song_name, artist_name, lyrics, trending_data=None):
    """用Gemini分析歌曲背景/热梗/话题，生成弹幕和Hooks，并关联抖音热搜"""
    try:
        _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if _proxy:
            os.environ['http_proxy'] = _proxy
            os.environ['https_proxy'] = _proxy

        from google import genai
        from google.genai import types

        env_path = os.path.expanduser("~/Documents/claude/自动化/suno-api/.env")
        api_key = None
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip('"').strip("'")
        if not api_key:
            return None

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=60000),
        )

        # 构建热搜上下文
        trending_context = ""
        if trending_data:
            hot_words = [t["word"] for t in trending_data.get("trending", [])[:30]]
            rising_words = [r["word"] for r in trending_data.get("rising", [])]
            trending_context = f"""
5. 【重要】以下是抖音当前实时热搜，请从中找出与这首歌在情绪、场景、意象上有关联的话题（不要硬蹭无关新闻，要找情感/场景/氛围上的自然连接）：
   热搜榜：{', '.join(hot_words[:20])}
   上升热点：{', '.join(rising_words)}
   关联方式举例：歌曲写春天怀旧->蹭"有一种春天叫油菜花开"；歌曲写成长->蹭"停下来是为了更好地出发"
"""

        prompt = f"""你是抖音音乐视频的内容策划。分析这首歌的背景和主题，生成弹幕和开头Hook文案。

歌名：《{song_name}》
艺人：{artist_name}
歌词（节选）：
{lyrics[:800]}

请分析：
1. 这首歌的主题/情绪是什么？（爱情/失恋/励志/叛逆/搞笑...）
2. 可能关联的热梗/话题/圈层（比如：les圈、分手后听的歌、打工人anthem、某部热播剧...）
3. 歌词中有没有能引发共鸣的金句
4. 情绪分类（从以下7类中选1类）：
   A=伤感/失恋  B=思念/暗恋  C=治愈/释怀  D=愤怒/执念  E=甜蜜/浪漫  F=孤独/深夜  G=情感丰富/古风
   G的判断标准：歌词意象密集、有文学感或古风元素（江湖/红尘/故人/长安/风月等）、情感层次丰富
{trending_context}
基于分析，输出JSON：
{{
  "theme": "一句话主题描述",
  "mood": "A",  // 情绪分类，只填A-G中的一个字母
  "mood_reason": "一句话理由",
  "opening_quote": "歌词中最扎心且不需要上下文就能看懂的一句原文（10字以内，必须独立成句能理解，禁止选需要前后文才能理解的句子）",
  "lyric_color": "R,G,B",  // 歌词颜色，根据歌曲情绪推荐：治愈用暖白(255,245,230)、伤感用冷蓝(200,220,255)、甜蜜用粉(255,220,230)、古风用金(255,235,170)、愤怒用红(255,100,80)、孤独用灰蓝(180,200,220)
  "trending_hooks": [  // 从当前热搜中找到的可蹭话题（0-3条），每条包含热搜词和蹭法
    {{"topic": "热搜原文", "angle": "一句话说明怎么关联到这首歌"}},
  ],
  "danmu": ["弹幕1", "弹幕2", ...],  // 15-20条，混合以下类型：
    // - 主题相关梗（如"les圈必听"、"打工人DNA动了"）
    // - 歌词共鸣（如"这句写的就是我"）
    // - 情绪反应（如"副歌直接泪目"、"太上头了"）
    // - 互动引导（如"评论区打出你的故事"）
    // - 如有可蹭热搜，加入1-2条热搜相关弹幕
    // 注意：不要用emoji，纯文字
  "hooks": ["hook文案1", "hook文案2", "hook文案3"],  // 3条开头Hook，≤15字，让用户感到"说的就是我"
    // 写法：场景代入("一个人骑车春天听这首") / 行为说穿("把这首发给那个你没联系的人") / 身份标签("能在春天听进这首歌的都有件没做完的事")
    // 禁止：广告体("趁现在记录你的春天" ❌)、空泛口号("必听神曲" ❌)
  "voiceover": "配音旁白文案",  // 1-2句，10秒以内，结合抖音爆款句式+歌词内容
    // 句式参考："家人们谁懂啊，xxx"、"有没有一首歌 让你xxx"、"这歌词写进心里了 xxx"
    // 要求：卖点分明，吸引人看下去，必须贴合这首歌的具体歌词内容，不能纯套话
  "copy_tags": ["标签1", "标签2", ...]  // 5-8个抖音话题标签（不含#号），如有匹配热搜也加入
}}

只返回JSON，不要其他内容。"""

        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=[types.Content(parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.7,
                response_mime_type="application/json",
            ),
        )

        result = json.loads(response.text.strip())
        print(f"  Gemini研究完成: 主题={result.get('theme', '?')}")
        print(f"    弹幕{len(result.get('danmu', []))}条, Hooks{len(result.get('hooks', []))}条")
        # 打印热搜关联
        trending_hooks = result.get('trending_hooks', [])
        if trending_hooks:
            print(f"    热搜关联{len(trending_hooks)}条:")
            for th in trending_hooks:
                print(f"      - #{th.get('topic','')} -> {th.get('angle','')}")
        return result

    except Exception as e:
        print(f"  Gemini研究失败({e})，重试一次...")
        try:
            time.sleep(5)
            response = client.models.generate_content(
                model="gemini-3.1-pro-preview",
                contents=[types.Content(parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    response_mime_type="application/json",
                ),
            )
            result = json.loads(response.text.strip())
            print(f"  重试成功: 主题={result.get('theme', '?')}")
            return result
        except Exception as e2:
            print(f"  重试也失败({e2})，使用默认弹幕")
            return None


# ============================================================
# Claude CLI 情绪分类 -- 通过 subprocess 调用本地 Claude (Max订阅)
# ============================================================
def classify_mood_claude(song_name, artist_name, lyrics):
    """用Claude CLI判断歌曲情绪分类 A-G"""
    prompt = (
        f"你是音乐情绪分析专家。分析这首歌的情绪，从以下7类中选1类：\n"
        f"A=伤感/失恋  B=思念/暗恋  C=治愈/释怀  D=愤怒/执念  E=甜蜜/浪漫  F=孤独/深夜  G=情感丰富/古风\n\n"
        f"G的判断标准：歌词意象密集（每句有强画面感关键词）、有文学感或古风元素（江湖/红尘/故人/长安/风月等）、"
        f"情感层次丰富（不是单一情绪而是多层递进）\n\n"
        f"歌名：《{song_name}》\n"
        f"艺人：{artist_name}\n"
        f"歌词：\n{lyrics[:800]}\n\n"
        f'只返回JSON: {{"mood": "A", "reason": "一句话理由"}}'
    )
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--model", "claude-opus-4-6", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "NO_COLOR": "1"},
        )
        if result.returncode != 0:
            print(f"    Claude CLI 返回码 {result.returncode}")
            return None, None

        # Claude CLI --output-format json 输出结构: {"result": "...", ...}
        cli_output = json.loads(result.stdout.strip())
        text = cli_output.get("result", result.stdout.strip())

        # 从text中提取JSON
        json_match = re.search(r'\{[^}]*"mood"[^}]*\}', text)
        if json_match:
            parsed = json.loads(json_match.group())
            mood = parsed.get("mood", "").upper().strip()
            reason = parsed.get("reason", "")
            if mood in "ABCDEFG" and len(mood) == 1:
                return mood, reason

        print(f"    Claude 返回格式异常: {text[:100]}")
        return None, None

    except subprocess.TimeoutExpired:
        print(f"    Claude CLI 超时(60s)")
        return None, None
    except Exception as e:
        print(f"    Claude CLI 调用失败: {e}")
        return None, None


def resolve_mood(gemini_mood, gemini_reason, claude_mood, claude_reason,
                 song_name, artist_name, lyrics):
    """双模型情绪比对，不一致时由Claude裁决"""
    # 两者都失败 -> 默认C（治愈，最通用）
    if not gemini_mood and not claude_mood:
        print(f"    双模型都无结果，使用默认模版C")
        return "C"

    # 只有一方有结果 -> 用有结果的
    if not gemini_mood:
        print(f"    Gemini无结果，采用Claude判断: {claude_mood}")
        return claude_mood
    if not claude_mood:
        print(f"    Claude无结果，采用Gemini判断: {gemini_mood}")
        return gemini_mood

    # 一致 -> 直接用
    if gemini_mood == claude_mood:
        print(f"    双模型一致: {gemini_mood}")
        return gemini_mood

    # 不一致 -> Claude裁决
    print(f"    意见分歧: Gemini={gemini_mood}({gemini_reason}) vs Claude={claude_mood}({claude_reason})")
    print(f"    交由Claude裁决...")

    resolve_prompt = (
        f"你是音乐视频模版选择的最终裁决者。两个AI对同一首歌的情绪分类产生了分歧：\n\n"
        f"歌名：《{song_name}》 -- {artist_name}\n"
        f"歌词节选：\n{lyrics[:500]}\n\n"
        f"Gemini判断：{gemini_mood}，理由：{gemini_reason}\n"
        f"Claude判断：{claude_mood}，理由：{claude_reason}\n\n"
        f"7类情绪：A=伤感/失恋  B=思念/暗恋  C=治愈/释怀  D=愤怒/执念  E=甜蜜/浪漫  F=孤独/深夜  G=情感丰富/古风\n\n"
        f"综合两方理由和歌词内容，做出最终判断。\n"
        f'只返回JSON: {{"mood": "A", "reason": "裁决理由"}}'
    )
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--model", "claude-opus-4-6", "-p", resolve_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "NO_COLOR": "1"},
        )
        if result.returncode == 0:
            cli_output = json.loads(result.stdout.strip())
            text = cli_output.get("result", result.stdout.strip())
            json_match = re.search(r'\{[^}]*"mood"[^}]*\}', text)
            if json_match:
                parsed = json.loads(json_match.group())
                mood = parsed.get("mood", "").upper().strip()
                reason = parsed.get("reason", "")
                if mood in "ABCDEFG" and len(mood) == 1:
                    print(f"    裁决结果: {mood}（{reason}）")
                    return mood
    except Exception as e:
        print(f"    裁决失败({e})，采用Claude首轮判断: {claude_mood}")

    return claude_mood  # 裁决失败时倾向Claude


def generate_copy(song_name, artist_name, context=None, topic_name=None):
    """生成抖音文案（如有Gemini研究结果则使用）"""
    # 话题标签
    if context and context.get('copy_tags'):
        tags = ' '.join(f'#{t}' for t in context['copy_tags'])
        tags += f' #{song_name} #{artist_name} #歌词视频 #戴耳机听'
    else:
        tags = f'#{song_name} #{artist_name} #原创音乐 #华语新歌 #歌词视频 #戴耳机听 #副歌循环 #宝藏歌手 #音乐推荐'

    # 影视话题标签
    if topic_name:
        tags += f' #{topic_name}'

    # 主题描述
    theme = context.get('theme', '') if context else ''
    theme_line = f'\n主题：{theme}\n' if theme else ''

    # 影视话题关联描述
    topic_line = ''
    if topic_name:
        topic_line = f'\n话题关联：#{topic_name}\n'

    copy_text = f"""【{song_name} -- {artist_name} 抖音发布文案】

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标题/文案：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{theme_line}{topic_line}
"听到副歌那段直接起鸡皮疙瘩了"
这首《{song_name}》是 {artist_name} 的作品
建议戴耳机 音量拉满
完整版在主页 记得点关注

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标签Tags：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{tags}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
发布建议：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 发布时间：18:30-19:00
- 定位城市：成都 或 重庆
- 封面：选视频中副歌高潮画面截图
"""
    return copy_text


# ============================================================
# 话题去重管理
# ============================================================
def load_used_topics():
    """加载已用话题列表"""
    if not os.path.exists(USED_TOPICS_FILE):
        return []
    try:
        with open(USED_TOPICS_FILE) as f:
            data = json.load(f)
        return data.get("topics", [])
    except Exception:
        return []

def save_used_topic(word, song_id):
    """追加一条已用话题"""
    topics = load_used_topics()
    topics.append({"word": word, "date": TODAY, "song_id": song_id})
    with open(USED_TOPICS_FILE, 'w') as f:
        json.dump({"topics": topics}, f, ensure_ascii=False, indent=2)


# ============================================================
# 影视类热搜筛选
# ============================================================
YINGSHI_KEYWORDS = ["开播", "杀青", "名场面", "花絮", "官宣", "热播", "大结局", "预告", "定档"]

def filter_yingshi_topics(trending_data, used_topic_words):
    """从热搜中筛选影视/综艺类话题，排除已用过的"""
    if not trending_data:
        return []

    all_topics = trending_data.get("trending", []) + trending_data.get("rising", [])
    results = []
    for t in all_topics:
        word = t.get("word", "")
        if not word:
            continue
        # 检查是否包含影视关键词
        if any(kw in word for kw in YINGSHI_KEYWORDS):
            # 排除已用过的
            if word not in used_topic_words:
                results.append(word)

    return results


# ============================================================
# Claude匹配歌曲与话题
# ============================================================
def match_song_to_topic(topic, candidates):
    """用Claude CLI从候选歌曲中选出与话题最匹配的一首

    Args:
        topic: 影视话题字符串
        candidates: 候选歌曲列表 [{"id": ..., "name": ..., "artist_name": ..., "original_lyric": ...}, ...]

    Returns:
        匹配的歌曲dict，或None
    """
    if not candidates:
        return None

    # 构建候选列表文本
    candidate_text = ""
    for i, s in enumerate(candidates):
        lyric_preview = s.get('original_lyric', '')[:200].replace('\n', ' ')
        candidate_text += f"\n{i+1}. [{s['id']}] 《{s['name']}》-- {s['artist_name']}  歌词节选: {lyric_preview}"

    prompt = (
        f"你是音乐推荐专家。现在有一个影视/综艺热搜话题：\n"
        f"「{topic}」\n\n"
        f"请从以下候选歌曲中选出1首最适合配这个话题的歌（考虑情绪、氛围、意境的匹配度）：\n"
        f"{candidate_text}\n\n"
        f'只返回JSON: {{"song_id": 123, "reason": "一句话理由"}}'
    )

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--model", "claude-opus-4-6", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "NO_COLOR": "1"},
        )
        if result.returncode != 0:
            print(f"    Claude匹配返回码 {result.returncode}")
            return None

        cli_output = json.loads(result.stdout.strip())
        text = cli_output.get("result", result.stdout.strip())

        json_match = re.search(r'\{[^}]*"song_id"[^}]*\}', text)
        if json_match:
            parsed = json.loads(json_match.group())
            song_id = parsed.get("song_id")
            reason = parsed.get("reason", "")
            # 在候选中找到这首歌
            for s in candidates:
                if s['id'] == song_id:
                    print(f"    Claude匹配: 《{s['name']}》-- {reason}")
                    return s

        # fallback: 用第一首
        print(f"    Claude匹配格式异常，使用第一首候选")
        return candidates[0]

    except Exception as e:
        print(f"    Claude匹配失败({e})，使用第一首候选")
        return candidates[0]


# ============================================================
# 视频生成核心流程（单首歌 -> 竖版+横版）
# ============================================================
def generate_video_pair(song, tpl, bg_img_path, final_mood, output_dir, tmp_clip_path, label="", opening_quote="", context=None):
    """为一首歌生成竖版+横版视频

    Returns:
        True if at least one video generated successfully
    """
    safe_name = song['name'].replace('；', '_').replace('/', '_').replace(':', '_')
    bg_type = tpl['bg_type']
    success = False

    for landscape, suffix in [(False, ''), (True, '_横版')]:
        orientation = "横版" if landscape else "竖版"
        video_filename = f"{safe_name}_{song['artist_name']}_歌词视频_动态背景版{suffix}.mp4"
        video_path = os.path.join(output_dir, video_filename)

        print(f"  生成{orientation} (背景: {bg_type})...")

        env = os.environ.copy()
        env['SONG_NAME'] = song['name']
        env['ARTIST_NAME'] = song['artist_name']
        env['AUDIO_PATH'] = tmp_clip_path
        env['LYRICS_RAW'] = song.get('original_lyric', '')
        env['OUTPUT_PATH'] = video_path
        env['VIDEO_DURATION'] = '20'
        env['USE_GEMINI'] = 'true'

        # 动态背景模版参数
        env['STYLE_NAME'] = tpl['style_name']
        env['BG_TYPE'] = bg_type
        env['LANDSCAPE'] = 'true' if landscape else 'false'
        env['NO_FLASH'] = tpl['no_flash']
        env['NO_SHAKE'] = tpl['no_shake']
        env['SHOW_PINYIN'] = 'false'
        env['LYRIC_COLOR_CYCLE'] = 'false'
        env['LYRIC_BOTTOM_ALPHA'] = tpl['lyric_bottom_alpha']
        env['LYRIC_TOP_COLOR'] = tpl['lyric_top_color']
        env['DANMU_DURATION'] = '0'
        env['NO_HEADER'] = 'false'  # 显示歌名歌手
        env['VOICEOVER_TEXT'] = ''
        env['MOOD'] = final_mood
        env['MOOD_TAG'] = final_mood  # 传给gen_video_v2.py做字体自动匹配
        if opening_quote:
            env['OPENING_QUOTE'] = opening_quote
        # Gemini推荐的歌词颜色（覆盖模版默认颜色）
        lyric_color = context.get('lyric_color', '') if context else ''
        if lyric_color and ',' in lyric_color:
            env['LYRIC_TOP_COLOR'] = lyric_color
        if bg_img_path:
            # 视频文件用BG_VIDEO，图片文件用BG_IMG
            if bg_img_path.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                env['BG_VIDEO'] = bg_img_path
            else:
                env['BG_IMG'] = bg_img_path

        try:
            result = subprocess.run(
                [sys.executable, TEMPLATE_SCRIPT],
                env=env, capture_output=True, text=True, timeout=900
            )
        except subprocess.TimeoutExpired:
            print(f"  {orientation}超时(900s)，跳过")
            continue

        if result.returncode == 0:
            print(f"  {orientation}完成: {video_filename}")
            if result.stdout:
                print(result.stdout[-200:] if len(result.stdout) > 200 else result.stdout)
            success = True
        else:
            print(f"  {orientation}生成失败:")
            print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)

    return success


# ============================================================
# 模式1：从歌出发 -> 动态背景版
# ============================================================
def run_mode1(pool, done_ids, trending_data, output_dir):
    """从歌出发，选1首歌生成竖版+横版视频"""
    songs = pick_songs(pool, done_ids, 1)
    if not songs:
        print("  没有可用歌曲，跳过模式1")
        return

    song = songs[0]
    print(f"  选歌: [{song['id']}] 《{song['name']}》-- {song['artist_name']} (节奏分: {song.get('rhythm_score', 0)})")

    # Step 1: Gemini研究 + 双模型情绪判断
    print(f"  [1/4] 研究歌曲背景 + 情绪判断...")
    song_lyrics = song.get('original_lyric', '')
    context = research_song_context(song['name'], song['artist_name'], song_lyrics, trending_data)

    gemini_mood, gemini_reason = None, None
    if context:
        gemini_mood = context.get('mood', '').upper().strip()
        gemini_reason = context.get('mood_reason', '')
        if gemini_mood not in "ABCDEFG" or len(gemini_mood) != 1:
            gemini_mood = None
        if gemini_mood:
            print(f"    Gemini情绪: {gemini_mood}（{gemini_reason}）")

    print(f"    Claude判断中...")
    claude_mood, claude_reason = classify_mood_claude(song['name'], song['artist_name'], song_lyrics)
    if claude_mood:
        print(f"    Claude情绪: {claude_mood}（{claude_reason}）")

    final_mood = resolve_mood(
        gemini_mood, gemini_reason, claude_mood, claude_reason,
        song['name'], song['artist_name'], song_lyrics
    )

    # Step 2: 选模版 + 背景图
    tpl = MOOD_TEMPLATES.get(final_mood, MOOD_TEMPLATES["C"])
    bg_img_path = pick_bg_image(final_mood)
    print(f"    最终模版: {final_mood}「{tpl['name']}」")

    # Step 3: 下载音频 + 截取
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_full:
        tmp_full_path = tmp_full.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_clip:
        tmp_clip_path = tmp_clip.name

    try:
        print(f"  [2/4] 下载+截取音频...")
        if not download_audio(song['nos_url'], tmp_full_path):
            print(f"  下载失败，跳过模式1")
            return
        if not truncate_audio(tmp_full_path, tmp_clip_path, 20):
            print(f"  截取失败，跳过模式1")
            return

        # Step 4: 生成竖版+横版视频
        print(f"  [3/4] 生成视频（竖版+横版）...")
        oq = context.get('opening_quote', '') if context else ''
        success = generate_video_pair(song, tpl, bg_img_path, final_mood, output_dir, tmp_clip_path, label="模式1", opening_quote=oq, context=context)

        if success:
            # Step 5: 生成文案
            print(f"  [4/4] 生成文案...")
            safe_name = song['name'].replace('；', '_').replace('/', '_').replace(':', '_')
            copy_path = os.path.join(output_dir, f"{safe_name}_{song['artist_name']}_抖音文案.txt")
            with open(copy_path, 'w') as f:
                f.write(generate_copy(song['name'], song['artist_name'], context))

            save_done_id(song['id'])
            print(f"  模式1完成: 《{song['name']}》")
        else:
            print(f"  模式1视频生成失败")

    finally:
        for tmp in [tmp_full_path, tmp_clip_path]:
            if os.path.exists(tmp):
                os.remove(tmp)


# ============================================================
# 模式2：从热点出发 -> 影视版
# ============================================================
def run_mode2(pool, done_ids, trending_data, output_dir):
    """从影视热搜出发，匹配歌曲，生成竖版+横版视频"""
    if not trending_data:
        print("  无热搜数据，跳过模式2")
        return

    # Step 1: 筛选影视类话题
    used_topics = load_used_topics()
    used_topic_words = set(t["word"] for t in used_topics)
    yingshi_topics = filter_yingshi_topics(trending_data, used_topic_words)

    if not yingshi_topics:
        print("  未找到可用的影视类热搜话题，跳过模式2")
        return

    print(f"  找到 {len(yingshi_topics)} 个影视话题:")
    for t in yingshi_topics[:5]:
        print(f"    - {t}")

    topic = yingshi_topics[0]
    print(f"  选定话题: 「{topic}」")

    # Step 2: 反向匹配歌曲（排除模式1已用的done_ids需要重新加载）
    current_done_ids = load_done_ids()
    candidates = pick_songs(pool, current_done_ids, 10)
    if not candidates:
        print("  没有候选歌曲，跳过模式2")
        return

    print(f"  [1/5] Claude匹配歌曲...")
    song = match_song_to_topic(topic, candidates)
    if not song:
        print("  匹配失败，跳过模式2")
        return

    print(f"  匹配结果: [{song['id']}] 《{song['name']}》-- {song['artist_name']}")

    # Step 3: Gemini研究 + 双模型情绪判断
    print(f"  [2/5] 研究歌曲背景 + 情绪判断...")
    song_lyrics = song.get('original_lyric', '')
    context = research_song_context(song['name'], song['artist_name'], song_lyrics, trending_data)

    gemini_mood, gemini_reason = None, None
    if context:
        gemini_mood = context.get('mood', '').upper().strip()
        gemini_reason = context.get('mood_reason', '')
        if gemini_mood not in "ABCDEFG" or len(gemini_mood) != 1:
            gemini_mood = None
        if gemini_mood:
            print(f"    Gemini情绪: {gemini_mood}（{gemini_reason}）")

    print(f"    Claude判断中...")
    claude_mood, claude_reason = classify_mood_claude(song['name'], song['artist_name'], song_lyrics)
    if claude_mood:
        print(f"    Claude情绪: {claude_mood}（{claude_reason}）")

    final_mood = resolve_mood(
        gemini_mood, gemini_reason, claude_mood, claude_reason,
        song['name'], song['artist_name'], song_lyrics
    )

    # Step 4: 选模版 + 背景图
    tpl = MOOD_TEMPLATES.get(final_mood, MOOD_TEMPLATES["C"])
    bg_img_path = pick_bg_image(final_mood)
    print(f"    最终模版: {final_mood}「{tpl['name']}」")

    # Step 5: 下载音频 + 截取
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_full:
        tmp_full_path = tmp_full.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_clip:
        tmp_clip_path = tmp_clip.name

    try:
        print(f"  [3/5] 下载+截取音频...")
        if not download_audio(song['nos_url'], tmp_full_path):
            print(f"  下载失败，跳过模式2")
            return
        if not truncate_audio(tmp_full_path, tmp_clip_path, 20):
            print(f"  截取失败，跳过模式2")
            return

        # Step 6: 生成竖版+横版视频
        print(f"  [4/5] 生成视频（竖版+横版）...")
        oq = context.get('opening_quote', '') if context else ''
        success = generate_video_pair(song, tpl, bg_img_path, final_mood, output_dir, tmp_clip_path, label="模式2", opening_quote=oq, context=context)

        if success:
            # Step 7: 生成文案（包含影视话题名）
            print(f"  [5/5] 生成文案...")
            safe_name = song['name'].replace('；', '_').replace('/', '_').replace(':', '_')
            copy_path = os.path.join(output_dir, f"{safe_name}_{song['artist_name']}_抖音文案_影视版.txt")
            with open(copy_path, 'w') as f:
                f.write(generate_copy(song['name'], song['artist_name'], context, topic_name=topic))

            save_done_id(song['id'])
            save_used_topic(topic, song['id'])
            print(f"  模式2完成: 「{topic}」-> 《{song['name']}》")
        else:
            print(f"  模式2视频生成失败")

    finally:
        for tmp in [tmp_full_path, tmp_clip_path]:
            if os.path.exists(tmp):
                os.remove(tmp)


# ============================================================
# main
# ============================================================
def main():
    # 代理（Gemini API + edge-tts 需要）
    _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if _proxy:
        os.environ['http_proxy'] = _proxy
        os.environ['https_proxy'] = _proxy

    # 加载数据
    pool = load_pool()
    done_ids = load_done_ids()

    # 获取热搜
    from douyin_trending import fetch_trending
    print("获取抖音热搜...")
    trending_data = fetch_trending(use_cache_minutes=30)

    # 创建输出目录
    output_dir = os.path.join(OUTPUT_BASE, TODAY)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 50)
    print(f"每日视频生成 -- {TODAY}")
    print("=" * 50)
    print(f"歌曲池: {len(pool)}首, 已完成: {len(done_ids)}首")

    # ======== 模式1：从歌出发 ========
    print(f"\n{'─'*40}")
    print("【模式1】从歌出发 -- 动态背景版")
    print(f"{'─'*40}")
    run_mode1(pool, done_ids, trending_data, output_dir)

    # ======== 模式2：从热点出发 ========
    print(f"\n{'─'*40}")
    print("【模式2】从热点出发 -- 影视版")
    print(f"{'─'*40}")
    run_mode2(pool, done_ids, trending_data, output_dir)

    print(f"\n{'='*50}")
    print(f"完成，输出: {output_dir}")
    print(f"{'='*50}")

if __name__ == '__main__':
    main()
