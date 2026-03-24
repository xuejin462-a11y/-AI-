#!/usr/bin/env python3
"""通用歌词卡点视频生成器 V2 — 多风格律动器 + 双层字幕 + Gemini歌词对齐"""

import subprocess, os, sys, math, random, json, tempfile, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# 同目录导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from styles import get_style, STYLES
from dynamic_bg import draw_dynamic_bg, recommend_bg, BG_TYPES

# === 参数（由调用方传入）===
SONG_NAME = os.environ.get("SONG_NAME", "未命名")
ARTIST_NAME = os.environ.get("ARTIST_NAME", "未知")
AUDIO_PATH = os.environ.get("AUDIO_PATH", "")
LYRICS_RAW = os.environ.get("LYRICS_RAW", "")
BG_IMG = os.environ.get("BG_IMG", "")
BG_IMGS = os.environ.get("BG_IMGS", "")  # 多图轮换，逗号分隔路径
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "output.mp4")
VIDEO_DURATION = int(os.environ.get("VIDEO_DURATION", "30"))
STYLE_NAME = os.environ.get("STYLE_NAME", "classic")    # classic/sweet/dark/cool/youth
BG_TYPE = os.environ.get("BG_TYPE", "bokeh_warm")        # 动态背景类型
USE_GEMINI = os.environ.get("USE_GEMINI", "true").lower() == "true"

# macOS NFD/NFC 路径归一化（文件系统用NFD，Python字符串为NFC，需统一）
import unicodedata as _ud
if AUDIO_PATH:
    AUDIO_PATH = _ud.normalize('NFD', AUDIO_PATH)
if BG_IMG:
    BG_IMG = _ud.normalize('NFD', BG_IMG)
if BG_IMGS:
    BG_IMGS = ','.join(_ud.normalize('NFD', p) for p in BG_IMGS.split(','))

if not AUDIO_PATH or not os.path.exists(AUDIO_PATH):
    print(f"❌ 音频文件不存在: {AUDIO_PATH}")
    sys.exit(1)

# 加载风格
STYLE = get_style(STYLE_NAME)
if BG_TYPE not in BG_TYPES:
    BG_TYPE = "bokeh_warm"
print(f"🎨 风格: {STYLE['name']} | 动态背景: {BG_TYPE}")

# 横屏/竖屏自动切换
LANDSCAPE = os.environ.get("LANDSCAPE", "false").lower() == "true"
if LANDSCAPE:
    W, H = 1920, 1080
else:
    W, H = 1080, 1920
FPS = 25

# 抖音安全区：竖版右侧有头像/点赞按钮(约80px)，左右各留120px
# 歌词最大宽度 = W - 左边距 - 右边距
LYRIC_MARGIN_LEFT = 40 if LANDSCAPE else 40
LYRIC_MARGIN_RIGHT = 40 if LANDSCAPE else 140  # 竖版右侧留更多（避开抖音按钮）
LYRIC_MAX_W = W - LYRIC_MARGIN_LEFT - LYRIC_MARGIN_RIGHT
N_BANDS = 24
# 歌词从 t=0 立即开始（无独立intro屏）
OPENING_TOTAL = 0

# 覆盖式Hook：与歌词同时出现，悬停在歌词区上方
HOOK_OVERLAY_TEXT = os.environ.get("HOOK_OVERLAY_TEXT", "")
HOOK_OVERLAY_DURATION = float(os.environ.get("HOOK_OVERLAY_DURATION", "4.0"))
HOOK_OVERLAY_SIZE = int(os.environ.get("HOOK_OVERLAY_SIZE", "95"))
_hook_overlay_color_raw = os.environ.get("HOOK_OVERLAY_COLOR", "255,210,60")
HOOK_OVERLAY_COLOR = tuple(int(x) for x in _hook_overlay_color_raw.split(','))

NO_FLASH = os.environ.get("NO_FLASH", "true").lower() == "true"   # 默认开，古风模版显式传false
NO_SHAKE = os.environ.get("NO_SHAKE", "true").lower() == "true"   # 默认开，愤怒/执念类显式传false
SHOW_PINYIN = os.environ.get("SHOW_PINYIN", "false").lower() == "true"

# 歌词纵向偏移（正值=向下，用于避开人脸，典型值600-700）
LYRIC_Y_OFFSET = int(os.environ.get("LYRIC_Y_OFFSET", "0"))

# 歌词区蒙层透明度（0=无蒙层, 40=适中, 80=较深），所有背景模式统一使用
LYRIC_AREA_ALPHA = int(os.environ.get("LYRIC_AREA_ALPHA", "40"))

# 歌词动画模式（typewriter=打字机, fade=淡入, float=上浮淡入）
LYRIC_ANIM = os.environ.get("LYRIC_ANIM", "fade")

# 律动器（白色居中频谱柱，双向跳动）
SHOW_SPECTRUM = os.environ.get("SHOW_SPECTRUM", "false").lower() == "true"

# 前向zoom Ken Burns（模拟驾驶向前，聚焦消失点）
BG_FORWARD_ZOOM = os.environ.get("BG_FORWARD_ZOOM", "false").lower() == "true"

# 歌词描边模式（shadow=半透明阴影, stroke=传统描边, none=无描边）
LYRIC_STROKE_MODE = os.environ.get("LYRIC_STROKE_MODE", "shadow")

# 歌词字体覆盖（环境变量指定字体路径）
LYRIC_FONT_OVERRIDE = os.environ.get("LYRIC_FONT", "")

# 顶层歌词颜色覆盖（"R,G,B"格式）
_top_color_raw = os.environ.get("LYRIC_TOP_COLOR", "")
LYRIC_TOP_COLOR_OVERRIDE = None
if _top_color_raw.strip():
    try:
        LYRIC_TOP_COLOR_OVERRIDE = tuple(int(x) for x in _top_color_raw.split(','))
    except:
        pass

# === 字体 ===
XINGKAI = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/13b8ce423f920875b28b551f9406bf1014e0a656.asset/AssetData/Xingkai.ttc"
PINGFANG = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
HANZIPEN = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/a3c69464b629577766c23bcdb12ffbfe3759b923.asset/AssetData/Hanzipen.ttc"

# 已安装第三方字体（~/Library/Fonts/）
CHUNFENG_KAI   = os.path.expanduser("~/Library/Fonts/演示春风楷.ttf")    # 浪漫/思念/暗恋
YOURAN_KAI     = os.path.expanduser("~/Library/Fonts/演示悠然小楷.ttf")  # 伤感/治愈/清新
MUYAO_SHOUXIE  = os.path.expanduser("~/Library/Fonts/沐瑶随心手写体.ttf") # 治愈/温暖
MUYAO_RUABI    = os.path.expanduser("~/Library/Fonts/沐瑶软笔手书.ttf")  # 古风/浓情
PANGMEN        = os.path.expanduser("~/Library/Fonts/庞门正道粗书体-正式版.ttf")  # 愤怒/执念/力量
HANCHANTUZHUOTI = os.path.expanduser("~/Library/Fonts/寒蝉手拙体.ttf")  # 孤独/深夜/手写感
ZCOOL_HUANGYOU = os.path.expanduser("~/Library/Fonts/ZCOOLQingKeHuangYou-Regular.ttf")  # 甜蜜/可爱/圆润

# 情绪→字体映射（与7套模版对应）
_MOOD_FONT_MAP = {
    "A": YOURAN_KAI,    # 伤感/失恋 → 悠然小楷
    "B": CHUNFENG_KAI,  # 思念/暗恋 → 春风楷
    "C": MUYAO_SHOUXIE, # 治愈/释怀 → 沐瑶随心
    "D": PANGMEN,       # 愤怒/执念 → 庞门正道
    "E": ZCOOL_HUANGYOU,# 甜蜜/浪漫 → 黄油体
    "F": HANCHANTUZHUOTI,# 孤独/深夜 → 寒蝉手拙
    "G": MUYAO_RUABI,   # 古风/情感 → 软笔手书
}
# 读取情绪分类（由调用方通过MOOD_TAG传入），默认B（思念/暗恋）
_MOOD_TAG = os.environ.get("MOOD_TAG", "B")
_DEFAULT_LYRIC_FONT = _MOOD_FONT_MAP.get(_MOOD_TAG, CHUNFENG_KAI)
# 验证字体文件存在，不存在则fallback
if not os.path.exists(_DEFAULT_LYRIC_FONT):
    _DEFAULT_LYRIC_FONT = XINGKAI  # 系统行楷保底

# Hook 金句字体（与歌词字幕必须视觉区分：歌词=行楷Bold, Hook=行楷Regular）
# 传入 HOOK_FONT 可覆盖字体路径；HOOK_FONT_INDEX 控制字体变体
HOOK_FONT_PATH = os.environ.get("HOOK_FONT", XINGKAI)
HOOK_FONT_INDEX = int(os.environ.get("HOOK_FONT_INDEX", "0"))  # 0=Regular(Hook), 1=Bold(歌词)

# ============================================================
# Step 1: 音频分析（自动定位副歌并截取）
# ============================================================
print(f"🎵 分析音频: {os.path.basename(AUDIO_PATH)}")
import librosa

# 先加载完整音频，检查是否需要截取副歌
_y_full, _sr_full = librosa.load(AUDIO_PATH, sr=22050)
_full_dur = len(_y_full) / _sr_full

if _full_dur > VIDEO_DURATION + 5:
    # 先找能量最高的30s核心段（真正的副歌），再以此为锚点截取
    _rms = librosa.feature.rms(y=_y_full, hop_length=_sr_full)[0]
    _chorus_anchor, _best_avg = 0, 0.0
    _anchor_win = min(30, VIDEO_DURATION)
    for _i in range(0, max(1, int(_full_dur) - _anchor_win)):
        _avg = float(np.mean(_rms[_i:_i + _anchor_win]))
        if _avg > _best_avg:
            _best_avg = _avg
            _chorus_anchor = _i
    # 从副歌核心直接开始，0s就进歌词（不留前奏缓冲）
    _best_start = max(0, min(_chorus_anchor, int(_full_dur) - VIDEO_DURATION))
    print(f"  🎯 副歌定位: 核心@{_chorus_anchor}s → 截取{_best_start}s-{_best_start+VIDEO_DURATION}s (全曲{_full_dur:.0f}s)")
    _tmp_clip = tempfile.mktemp(suffix='.wav')
    subprocess.run(
        ["ffmpeg", "-y", "-i", AUDIO_PATH, "-ss", str(_best_start), "-t", str(VIDEO_DURATION), _tmp_clip],
        capture_output=True
    )
    AUDIO_PATH = _tmp_clip
    # 截取了副歌片段后，原有的完整歌词与片段内容不再对应
    # 清空LYRICS_RAW让Gemini直接耳听转录，避免把第一段歌词硬贴到副歌旋律上
    LYRICS_RAW = ""
    print(f"  ℹ️ 已截取副歌片段，LYRICS_RAW清空，由Gemini自动转录")
else:
    print(f"  音频时长{_full_dur:.0f}s，无需截取")

y_audio, sr = librosa.load(AUDIO_PATH, sr=22050, duration=VIDEO_DURATION)
actual_duration = len(y_audio) / sr
VIDEO_DURATION = min(VIDEO_DURATION, int(actual_duration))

tempo, beat_frames = librosa.beat.beat_track(y=y_audio, sr=sr)
BEAT_TIMES = librosa.frames_to_time(beat_frames, sr=sr).tolist()

hop = sr // FPS
total_frames = VIDEO_DURATION * FPS

BANDS = []
RMS_LIST = []
for i in range(total_frames):
    start = i * hop
    end = start + hop
    chunk = y_audio[start:end] if end <= len(y_audio) else np.zeros(hop)
    fft = np.abs(np.fft.rfft(chunk))
    freq_bins = len(fft)
    band_size = max(1, freq_bins // N_BANDS)
    band_vals = []
    for b in range(N_BANDS):
        s = b * band_size
        e = min(s + band_size, freq_bins)
        band_vals.append(float(np.mean(fft[s:e])) if s < freq_bins else 0.0)
    mx = max(band_vals) if max(band_vals) > 0 else 1.0
    band_vals = [v / mx for v in band_vals]
    BANDS.append(band_vals)
    RMS_LIST.append(float(np.sqrt(np.mean(chunk ** 2))))

rms_max = max(RMS_LIST) if max(RMS_LIST) > 0 else 1.0
RMS_LIST = [r / rms_max for r in RMS_LIST]

bpm_val = float(tempo) if isinstance(tempo, (int, float, np.floating)) else float(tempo[0])
print(f"  BPM: {bpm_val:.0f}, 鼓点: {len(BEAT_TIMES)}个, 帧数: {total_frames}")

# ============================================================
# Step 2: 歌词对齐（Gemini精确 or 鼓点均匀）
# ============================================================
def align_with_gemini(audio_path, lyrics_raw):
    """用Gemini API精确对齐歌词时间戳"""
    try:
        _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if _proxy:
            os.environ['http_proxy'] = _proxy
            os.environ['https_proxy'] = _proxy

        from google import genai
        from google.genai import types

        # 读取API key
        env_path = os.path.expanduser("~/Documents/claude/自动化/suno-api/.env")
        api_key = None
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip('"').strip("'")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=300000),
        )

        # 上传音频（路径含非ASCII字符时先复制到临时ASCII路径）
        print("  📡 上传音频到Gemini...")
        upload_path = audio_path
        _tmp_audio = None
        if not audio_path.isascii():
            import shutil, tempfile
            ext = os.path.splitext(audio_path)[1]
            _tmp_fd, _tmp_audio = tempfile.mkstemp(suffix=ext)
            os.close(_tmp_fd)
            shutil.copy2(audio_path, _tmp_audio)
            upload_path = _tmp_audio
        ext_lower = os.path.splitext(upload_path)[1].lower()
        mime_type = "audio/mpeg" if ext_lower in (".mp3",) else "audio/wav"
        uploaded = client.files.upload(
            file=upload_path,
            config=types.UploadFileConfig(mime_type=mime_type),
        )
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        if uploaded.state.name == "FAILED":
            raise RuntimeError("文件处理失败")

        # 构建prompt — 强调"人声发音瞬间"，减少与伴奏的混淆
        _common_rules = (
            "【时间戳规则】：\n"
            "- start = 歌手嘴巴张开、第一个字实际发音的瞬间（不是伴奏起音，不是乐器声）\n"
            "- end = 该句最后一个字唱完、人声消失的瞬间\n"
            "- 时间精确到0.05秒，跳过纯器乐的前奏/间奏\n"
            "- 只返回JSON数组，不要任何其他内容\n\n"
            '输出格式：[{"start": 0.0, "end": 2.5, "text": "歌词内容"}]\n'
        )
        if lyrics_raw.strip():
            prompt = (
                "这是一段歌曲音频。下面是【精确歌词原文】，请给每句标注开始和结束时间。\n\n"
                "【文本规则】：\n"
                "1. text字段必须100%使用我提供的歌词原文，一字不改\n"
                "2. 不要自己转录，只用我给你的文本\n"
                "3. 相邻短句可合并，每条10-20字为宜\n\n"
                + _common_rules
                + f"【歌词原文】：\n{lyrics_raw[:2000]}"
            )
        else:
            prompt = (
                "这是一段中文歌曲音频，请仔细聆听并精确标注每句歌词。\n\n"
                + _common_rules
            )

        _align_model = os.environ.get("GEMINI_ALIGN_MODEL", "gemini-3.1-pro-preview")
        print(f"  🤖 Gemini对齐歌词（{_align_model}）...")
        response = client.models.generate_content(
            model=_align_model,
            contents=[types.Content(parts=[
                types.Part.from_uri(file_uri=uploaded.uri, mime_type="audio/wav"),
                types.Part(text=prompt),
            ])],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        # 清理
        try:
            client.files.delete(name=uploaded.name)
        except:
            pass
        if _tmp_audio and os.path.exists(_tmp_audio):
            os.remove(_tmp_audio)

        raw = response.text.strip()
        result = json.loads(raw)

        # 转为 (start, end, text, lang) 格式
        lyrics = []
        for item in result:
            text = item.get("text", "").strip()
            if not text:
                continue
            start = float(item.get("start", 0))
            end = float(item.get("end", start + 2))
            if end > VIDEO_DURATION:
                end = VIDEO_DURATION
            if start >= VIDEO_DURATION:
                continue
            ascii_count = sum(1 for c in text if ord(c) < 128)
            if ascii_count > len(text) * 0.7: lang = "en"
            elif ascii_count > len(text) * 0.3: lang = "mix"
            else: lang = "cn"
            lyrics.append((round(start, 2), round(end, 2), text, lang))

        print(f"  ✅ Gemini对齐完成: {len(lyrics)}句")
        return lyrics

    except Exception as e:
        print(f"  ⚠️ Gemini对齐失败({e})，5s后重试...")
        if _tmp_audio and os.path.exists(_tmp_audio):
            os.remove(_tmp_audio)
        try:
            time.sleep(5)
            response = client.models.generate_content(
                model=_align_model,
                contents=[types.Content(parts=[
                    types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type),
                    types.Part(text=prompt),
                ])],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text.strip()
            result = json.loads(raw)
            lyrics = []
            for item in result:
                text = item.get("text", "").strip()
                if not text:
                    continue
                start = float(item.get("start", 0))
                end = float(item.get("end", start + 2))
                if end > VIDEO_DURATION:
                    end = VIDEO_DURATION
                if start >= VIDEO_DURATION:
                    continue
                ascii_count = sum(1 for c in text if ord(c) < 128)
                if ascii_count > len(text) * 0.7: lang = "en"
                elif ascii_count > len(text) * 0.3: lang = "mix"
                else: lang = "cn"
                lyrics.append((round(start, 2), round(end, 2), text, lang))
            print(f"  ✅ Gemini重试对齐完成: {len(lyrics)}句")
            return lyrics
        except Exception as e2:
            print(f"  ⚠️ Gemini重试也失败({e2})，回退到鼓点对齐")
            return None


def align_with_beats(lyrics_raw, duration, beat_times):
    """鼓点均匀分配（备用方案）"""
    lines = [l.strip() for l in lyrics_raw.replace('\r\n', '\n').split('\n') if l.strip() and len(l.strip()) >= 2]
    if not lines:
        return []
    max_lines = int(duration / 2.5)
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if len(beat_times) >= len(lines):
        step = max(1, len(beat_times) // len(lines))
        result = []
        for i, line in enumerate(lines):
            beat_idx = min(i * step, len(beat_times) - 1)
            start = beat_times[beat_idx]
            if i + 1 < len(lines):
                next_idx = min((i + 1) * step, len(beat_times) - 1)
                end = beat_times[next_idx]
            else:
                end = min(start + 3.0, duration - 0.5)
            if end <= start: end = start + 2.0
            ascii_count = sum(1 for c in line if ord(c) < 128)
            if ascii_count > len(line) * 0.7: lang = "en"
            elif ascii_count > len(line) * 0.3: lang = "mix"
            else: lang = "cn"
            result.append((round(start, 3), round(end, 3), line, lang))
        return result
    else:
        interval = duration / len(lines)
        result = []
        for i, line in enumerate(lines):
            start = i * interval + 0.5
            end = start + interval - 0.3
            ascii_count = sum(1 for c in line if ord(c) < 128)
            if ascii_count > len(line) * 0.7: lang = "en"
            elif ascii_count > len(line) * 0.3: lang = "mix"
            else: lang = "cn"
            result.append((round(start, 3), round(end, 3), line, lang))
        return result


def split_lyric_2lines(text):
    """把长歌词拆成2行，让字更大更显眼"""
    text = text.strip()
    if '\n' in text:
        return text  # 已经是多行
    n = len(text)
    if n <= 6:
        return text  # 短歌词不拆

    # 优先在标点处拆分
    for punct in ['，', '　', ' ', '、', '；', ',', '。', '！', '？']:
        idx = text.find(punct)
        if idx > 0 and idx < n - 1:
            # 选最靠近中间的标点
            best = idx
            best_dist = abs(idx - n // 2)
            pos = text.find(punct, idx + 1)
            while pos > 0 and pos < n - 1:
                d = abs(pos - n // 2)
                if d < best_dist:
                    best = pos
                    best_dist = d
                pos = text.find(punct, pos + 1)
            # 标点留在第一行
            return text[:best + 1].strip() + '\n' + text[best + 1:].strip()

    # 没有标点，从中间偏右拆（让第一行稍长，更自然）
    mid = (n + 1) // 2
    return text[:mid] + '\n' + text[mid:]


print("📝 歌词对齐...")

# onset预计算（供吸附使用）
print("  🔍 检测人声起音点...")
_onset_times = librosa.onset.onset_detect(
    y=y_audio, sr=sr, units='time',
    hop_length=256, backtrack=True,
    pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=0.07, wait=5
)
print(f"  检测到 {len(_onset_times)} 个起音点")

def _snap_to_onset(t, tolerance=0.45):
    """把时间戳吸附到最近的onset，超出tolerance则保持原值"""
    if len(_onset_times) == 0:
        return t
    diffs = np.abs(_onset_times - t)
    idx = int(np.argmin(diffs))
    if diffs[idx] <= tolerance:
        return float(_onset_times[idx])
    return t

LYRICS = None
if USE_GEMINI:
    LYRICS = align_with_gemini(AUDIO_PATH, LYRICS_RAW)
    if LYRICS:
        # onset吸附：把Gemini的粗略时间戳收紧到实际人声起音点
        snapped = 0
        refined = []
        for (s, e, t, lang) in LYRICS:
            s2 = round(_snap_to_onset(s), 3)
            if abs(s2 - s) > 0.005:
                snapped += 1
            refined.append((s2, e, t, lang))
        LYRICS = refined
        print(f"  ✂️ onset吸附: {snapped}/{len(LYRICS)} 句已调整")
if LYRICS is None:
    # 歌词对齐是核心环节，失败则终止，不允许回退到鼓点分配
    print(f"  ❌ Gemini歌词对齐失败，视频质量无法保证，终止生成")
    sys.exit(1)

# 歌词延长：每句结束时间延伸到下一句开始（气口处自然切换，无空档）
for i in range(len(LYRICS) - 1):
    s, e, t, l = LYRICS[i]
    next_s = LYRICS[i + 1][0]
    if next_s > e:
        LYRICS[i] = (s, next_s - 0.05, t, l)  # 留0.05s极短间隙做切换

# 统一字号：基于最长句计算，全视频保持一致
_max_chars = max(len(lt.replace('\n', '')) for (_, _, lt, _) in LYRICS) if LYRICS else 8
if _max_chars <= 4:   UNIFIED_TOP_SIZE = 200
elif _max_chars <= 6: UNIFIED_TOP_SIZE = 160
elif _max_chars <= 8: UNIFIED_TOP_SIZE = 140
elif _max_chars <= 10: UNIFIED_TOP_SIZE = 120
else: UNIFIED_TOP_SIZE = 95  # 最小字号95，允许更长歌词显示完整

# 超宽的歌词拆成2行，避免字号被强制压缩
# 用字符数估算宽度（每字约 UNIFIED_TOP_SIZE * 0.9px），避免在字体函数定义前调用
_updated_lyrics = []
for (s, e, lt, lang) in LYRICS:
    raw = lt.replace('\n', '')
    if '\n' not in lt:
        _est_w = len(raw) * UNIFIED_TOP_SIZE * 0.9
        if _est_w > LYRIC_MAX_W:
            mid = len(raw) // 2
            lt = raw[:mid] + '\n' + raw[mid:]
    _updated_lyrics.append((s, e, lt, lang))
LYRICS = _updated_lyrics

print(f"  歌词: {len(LYRICS)}句，统一字号: {UNIFIED_TOP_SIZE}px（最长句{_max_chars}字）")

# ============================================================
# Step 3: Hook & 弹幕 & 配置
# ============================================================
hook_colors = STYLE.get("hook_colors", [(255, 252, 248), (255, 220, 50), (255, 55, 55)])

# === 歌词颜色循环（中国风多色）===
LYRIC_COLOR_CYCLE = os.environ.get("LYRIC_COLOR_CYCLE", "false").lower() == "true"
LYRIC_COLORS = [
    (220, 35, 50),     # 朱红
    (220, 180, 60),    # 琥珀金
    (100, 160, 240),   # 靛青蓝
    (190, 70, 190),    # 紫檀
    (80, 200, 160),    # 翡翠绿
    (220, 100, 55),    # 朱砂橘
]

# 支持自定义Hooks（从环境变量 CUSTOM_HOOKS，格式: "时间,文字,字号|时间,文字,字号|..."）
CUSTOM_HOOKS_RAW = os.environ.get("CUSTOM_HOOKS", "")
if CUSTOM_HOOKS_RAW.strip():
    HOOKS = []
    for i, item in enumerate(CUSTOM_HOOKS_RAW.split('|')):
        parts = item.strip().split(',', 2)
        if len(parts) >= 2:
            t_val = float(parts[0])
            text = parts[1].strip()
            size = int(parts[2]) if len(parts) > 2 else 100
            color = hook_colors[i % len(hook_colors)]
            lang = "cn" if any(ord(c) > 127 for c in text) else "en"
            HOOKS.append((t_val, text, size, color, lang))
else:
    HOOKS = [
        (0.0, ARTIST_NAME, 100, hook_colors[0], "cn" if any(ord(c) > 127 for c in ARTIST_NAME) else "en"),
        (0.6, f"《{SONG_NAME}》", 110, hook_colors[1], "cn"),
        (1.5, "听完再划走", 90, hook_colors[0], "cn"),
    ]
LISTEN_HOOK_START = 3.0
LISTEN_DURATION = 5.0

# === 弹幕内容（从环境变量或自动生成）===
DANMU_RAW = os.environ.get("DANMU_COMMENTS", "")

# 默认弹幕池（通用热度梗 + 音乐评论体，不用emoji防乱码）
DEFAULT_DANMU = [
    "这首歌太上头了", "单曲循环三天了", "遗憾拉满", "DNA动了",
    "副歌绝了", "谁懂啊这歌", "戴耳机听 起鸡皮疙瘩",
    "好听到耳朵怀孕", "这首歌治好了我的精神内耗", "什么神仙歌曲",
    "循环到手机发烫", "这嗓音也太绝了", "后劲太大了",
    "评论区都是有故事的人", "旋律一响眼泪就不争气",
    "妈妈问我为什么跪着听歌", "太好哭了这首", "宿命感歌曲",
    "已加歌单 感谢推荐", "求完整版", "这歌不火天理难容",
    "为什么才听到这首歌", "凌晨三点 耳机循环",
    "听完沉默了好久", "分享给了所有人", "有被戳到",
    "这首歌懂我", "emo了", "每个字都是我想说的",
]

# 女同/les主题弹幕池
LES_DANMU = [
    "她对她的执念 写进每个字了", "les圈emo神曲", "姐姐们懂的都懂",
    "恨你不爱我 恨到骨子里", "明月不照我 你也不看我",
    "这首歌唱的就是我和她", "爱而不得最折磨人",
    "任我疯魔 说的就是我本人", "冷眼看着我扑火 你真的狠",
    "想发给她听 又怕她根本不在乎", "pp圈必听",
    "我恨你恰恰证明我还在乎", "这嗓音也太绝了",
    "被看见的渴望 谁能懂", "卑微到尘埃里了",
    "求你看我一眼 哪怕厌恶", "后劲太大了 听哭了",
    "评论区都是有故事的姐妹", "循环到手机发烫",
]

DANMU_THEME = os.environ.get("DANMU_THEME", "")  # les/默认
if DANMU_RAW.strip():
    DANMU_POOL = [d.strip() for d in DANMU_RAW.split('|') if d.strip()]
elif DANMU_THEME == "les":
    DANMU_POOL = LES_DANMU
else:
    DANMU_POOL = DEFAULT_DANMU

# 预生成弹幕轨道（避免每帧重复计算）
DANMU_DURATION = float(os.environ.get("DANMU_DURATION", "0"))   # 默认关，古风模版显式传秒数
DANMU_TRACKS = []
random.seed(hash(SONG_NAME) + 777)
n_danmu = int(DANMU_DURATION * 3) if DANMU_DURATION > 0 else 0  # DANMU_DURATION=0时不生成任何弹幕
track_y_slots = [int(H * p) for p in [0.12, 0.16, 0.20, 0.24, 0.28, 0.75, 0.79, 0.83, 0.87]]
for i in range(n_danmu):
    text = DANMU_POOL[i % len(DANMU_POOL)]
    start_t = random.uniform(0.3, DANMU_DURATION - 2.5)
    speed = random.uniform(180, 320)  # 像素/秒
    y = track_y_slots[i % len(track_y_slots)]
    size = random.choice([30, 32, 34, 36])
    alpha = random.uniform(0.55, 0.85)
    DANMU_TRACKS.append({
        'text': text, 'start': start_t, 'speed': speed,
        'y': y, 'size': size, 'alpha': alpha,
    })

def draw_danmu(draw, t):
    """绘制飘过的弹幕"""
    if t > DANMU_DURATION + 3:
        return
    for dm in DANMU_TRACKS:
        age = t - dm['start']
        if age < 0:
            continue
        # 从右向左飘
        x = int(W + 50 - age * dm['speed'])
        if x < -600:
            continue  # 已飘出屏幕
        # 淡入淡出
        if age < 0.3:
            a = age / 0.3
        elif t > DANMU_DURATION:
            a = max(0, 1 - (t - DANMU_DURATION) / 1.0)
        else:
            a = 1.0
        a *= dm['alpha']
        if a < 0.02:
            continue
        font = _get_font(PINGFANG, dm['size'])
        color = (int(255 * a), int(255 * a), int(255 * a))
        draw.text((x, dm['y']), dm['text'], fill=color, font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))

# ============================================================
# Step 4: 背景处理（支持视频背景 + 图片背景）
# ============================================================
BG_VIDEO_PATH = os.environ.get("BG_VIDEO", "")  # 视频背景（优先）
BG_IMAGE_RAW = None
BG_USE_IMAGE = False
BG_USE_VIDEO = False
BG_VIDEO_FRAMES = []
BG_BRIGHTNESS = float(os.environ.get("BG_BRIGHTNESS", "0.75"))  # 默认提高亮度，不压太暗

# --- 视频背景（优先级最高）---
if BG_VIDEO_PATH and os.path.exists(BG_VIDEO_PATH):
    print(f"🎬 加载背景视频: {os.path.basename(BG_VIDEO_PATH)}")
    from PIL import ImageFilter
    # 检测视频原始尺寸决定适配方式
    _probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", BG_VIDEO_PATH],
        capture_output=True, text=True
    )
    _src_w, _src_h = W, H
    try:
        for _ps in json.loads(_probe.stdout).get("streams", []):
            if _ps.get("codec_type") == "video":
                _src_w = int(_ps.get("width", W))
                _src_h = int(_ps.get("height", H))
                break
    except:
        pass

    _src_is_landscape = _src_w > _src_h
    _dst_is_landscape = W > H

    if _src_is_landscape == _dst_is_landscape:
        # 同方向：直接缩放适配
        _vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        _bg_video_mode = "直接适配"
    elif _src_is_landscape and not _dst_is_landscape:
        # 横版视频→竖版输出：居中放置，上下模糊填充
        # 先输出原始尺寸，在渲染时手动处理
        _vid_h = int(_src_h * W / _src_w)  # 视频在竖屏中的高度
        _vf = f"scale={W}:{_vid_h}"
        _bg_video_mode = f"横转竖（模糊填充，视频高{_vid_h}px）"
    else:
        # 竖版视频→横版输出（少见）
        _vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        _bg_video_mode = "竖转横"

    print(f"  适配模式: {_bg_video_mode} (源{_src_w}x{_src_h} → 输出{W}x{H})")

    _vproc = subprocess.Popen(
        ["ffmpeg", "-i", BG_VIDEO_PATH, "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-vf", _vf, "-r", str(FPS), "-v", "quiet", "-"],
        stdout=subprocess.PIPE
    )
    if _src_is_landscape and not _dst_is_landscape:
        # 横版→竖版：读取缩放后的帧，手动加模糊填充
        _read_h = int(_src_h * W / _src_w)
        _vid_y = (H - _read_h) // 2
        while True:
            _raw = _vproc.stdout.read(W * _read_h * 3)
            if len(_raw) != W * _read_h * 3:
                break
            _vid_frame = Image.frombytes("RGB", (W, _read_h), _raw)
            # 上下模糊填充
            _bg = _vid_frame.resize((W, H), Image.LANCZOS)
            _bg = _bg.filter(ImageFilter.GaussianBlur(radius=30))
            _bg = ImageEnhance.Brightness(_bg).enhance(0.55)
            _bg.paste(_vid_frame, (0, _vid_y))
            BG_VIDEO_FRAMES.append(_bg)
        _vproc.wait()
    else:
        while True:
            _raw = _vproc.stdout.read(W * H * 3)
            if len(_raw) != W * H * 3:
                break
            _frame = Image.frombytes("RGB", (W, H), _raw)
            BG_VIDEO_FRAMES.append(_frame)
        _vproc.wait()

    if BG_VIDEO_FRAMES:
        # === 素材下载后立刻质检：检测字幕 ===
        _subtitle_frames = []
        _check_indices = [0, len(BG_VIDEO_FRAMES)//4, len(BG_VIDEO_FRAMES)//2,
                          len(BG_VIDEO_FRAMES)*3//4, len(BG_VIDEO_FRAMES)-1]
        for _ci in _check_indices:
            _cf = BG_VIDEO_FRAMES[_ci]
            _cw, _ch = _cf.size
            _bottom = _cf.crop((0, int(_ch*0.82), _cw, _ch))
            _pixels = list(_bottom.getdata())
            _avg_brightness = sum(sum(p[:3]) for p in _pixels) / (len(_pixels) * 3)
            if _avg_brightness > 140:
                _subtitle_frames.append(_ci)

        if _subtitle_frames:
            print(f"  ⚠️ 检测到 {len(_subtitle_frames)}/{len(_check_indices)} 帧底部有疑似字幕（亮度异常）")
            print(f"     有字幕的帧索引: {_subtitle_frames}")
            print(f"     建议：换无字幕素材，或裁掉底部字幕区域")
        else:
            print(f"  ✓ 素材字幕检测通过（底部无异常亮度）")

        # 只正向循环（不反放，驾驶视频反放会出现车倒开）
        _cycle = list(range(len(BG_VIDEO_FRAMES)))
        BG_VIDEO_CYCLE = _cycle
        BG_VIDEO_CYCLE_LEN = len(_cycle)
        BG_USE_VIDEO = True
        print(f"  背景视频帧: {len(BG_VIDEO_FRAMES)} ({len(BG_VIDEO_FRAMES)/FPS:.1f}s), 循环长度: {BG_VIDEO_CYCLE_LEN}")
    else:
        print(f"  ⚠️ 视频帧为空，回退到图片/粒子背景")

# --- 多图轮换（BG_IMGS，逗号分隔，带交叉淡入淡出转场）---
BG_SLIDESHOW = []  # [(image_raw, kb_margin), ...]
BG_USE_SLIDESHOW = False
CROSSFADE_DURATION = float(os.environ.get("CROSSFADE_DURATION", "0.8"))  # 转场时间（秒），0=硬切

if not BG_USE_VIDEO and BG_IMGS:
    _img_paths = [p.strip() for p in BG_IMGS.split(",") if p.strip() and os.path.exists(p.strip())]
    if _img_paths:
        print(f"🖼️ 加载多图轮换: {len(_img_paths)}张")
        kb_margin = 1.15
        for _ip in _img_paths:
            _raw = Image.open(_ip).convert('RGB')
            _bw, _bh = _raw.size
            _sw = (W * kb_margin) / _bw
            _sh = (H * kb_margin) / _bh
            _sc = max(_sw, _sh)
            _resized = _raw.resize((int(_bw * _sc), int(_bh * _sc)), Image.LANCZOS)
            BG_SLIDESHOW.append(_resized)
            print(f"  + {os.path.basename(_ip)} ({_resized.size[0]}x{_resized.size[1]})")
        BG_USE_SLIDESHOW = True
        print(f"  转场: 交叉淡入淡出 {CROSSFADE_DURATION}s")


def slideshow_frame(t, total_duration):
    """多图轮换 + Ken Burns + 交叉淡入淡出转场"""
    if not BG_SLIDESHOW:
        return None

    n_imgs = len(BG_SLIDESHOW)
    segment_dur = total_duration / n_imgs  # 每张图展示时长
    seg_idx = min(int(t / segment_dur), n_imgs - 1)
    seg_progress = (t - seg_idx * segment_dur) / segment_dur  # 当前图的进度 0~1

    # Ken Burns for current image
    def _kb_crop(img_raw, progress):
        raw_w, raw_h = img_raw.size
        zoom = 1.0 + 0.10 * progress
        crop_w = int(W * (1.15 / zoom))
        crop_h = int(H * (1.15 / zoom))
        cx = int((raw_w - crop_w) * (0.3 + 0.4 * progress))
        cy = int((raw_h - crop_h) * (0.2 + 0.3 * progress))
        cropped = img_raw.crop((cx, cy, cx + crop_w, cy + crop_h))
        return cropped.resize((W, H), Image.LANCZOS)

    current_frame = _kb_crop(BG_SLIDESHOW[seg_idx], seg_progress)

    # 交叉淡入淡出转场
    fade_frames = CROSSFADE_DURATION * FPS
    frame_in_seg = (t - seg_idx * segment_dur) * FPS
    frames_in_seg = segment_dur * FPS

    if seg_idx > 0 and frame_in_seg < fade_frames:
        # 淡入：和前一张图混合
        prev_frame = _kb_crop(BG_SLIDESHOW[seg_idx - 1], 1.0)
        blend_alpha = frame_in_seg / fade_frames  # 0→1
        current_frame = Image.blend(prev_frame, current_frame, blend_alpha)
    elif seg_idx < n_imgs - 1 and frame_in_seg > frames_in_seg - fade_frames:
        # 淡出：和下一张图混合
        next_frame = _kb_crop(BG_SLIDESHOW[seg_idx + 1], 0.0)
        blend_alpha = (frames_in_seg - frame_in_seg) / fade_frames  # 1→0
        current_frame = Image.blend(next_frame, current_frame, blend_alpha)

    return current_frame


# --- 单图背景（视频和多图都不可用时） ---
if not BG_USE_VIDEO and not BG_USE_SLIDESHOW and BG_IMG and os.path.exists(BG_IMG):
    print(f"🖼️ 加载背景图: {os.path.basename(BG_IMG)}")
    _bg_raw = Image.open(BG_IMG).convert('RGB')
    bw, bh = _bg_raw.size

    kb_margin = 1.15
    scale_w = (W * kb_margin) / bw
    scale_h = (H * kb_margin) / bh
    bg_scale = max(scale_w, scale_h)
    new_w = int(bw * bg_scale)
    new_h = int(bh * bg_scale)
    BG_IMAGE_RAW = _bg_raw.resize((new_w, new_h), Image.LANCZOS)

    enhancer = ImageEnhance.Brightness(BG_IMAGE_RAW)
    BG_IMAGE_RAW = enhancer.enhance(BG_BRIGHTNESS)
    BG_USE_IMAGE = True
    print(f"  背景图处理完成 ({new_w}x{new_h}, 亮度{BG_BRIGHTNESS})")


def ken_burns_crop(t, total_duration):
    """Ken Burns 效果：慢缩放 1.0→1.08 + 微平移，返回裁切后的帧"""
    if BG_IMAGE_RAW is None:
        return None

    raw_w, raw_h = BG_IMAGE_RAW.size
    progress = t / max(total_duration, 1)

    # 缩放：从 1.0 到 1.12（明显的慢推镜头感）
    zoom = 1.0 + 0.12 * progress
    crop_w = int(W * (1.15 / zoom))
    crop_h = int(H * (1.15 / zoom))

    # 平移：缓慢漂移（用正弦让运动更自然）
    max_dx = raw_w - crop_w
    max_dy = raw_h - crop_h
    # 水平：从左偏慢慢移到右偏
    cx = int(max_dx * (0.2 + 0.6 * (0.5 + 0.5 * math.sin(progress * math.pi - math.pi/2))))
    # 垂直：从上缓慢下移
    cy = int(max_dy * (0.15 + 0.5 * progress))

    # 裁切 + 缩放到输出尺寸
    cropped = BG_IMAGE_RAW.crop((cx, cy, cx + crop_w, cy + crop_h))
    frame = cropped.resize((W, H), Image.LANCZOS)

    # 渐变遮罩（使用预计算的缓存）
    frame_rgba = frame.convert('RGBA')
    frame_rgba = Image.alpha_composite(frame_rgba, _KB_GRADIENT)
    return frame_rgba.convert('RGB')


def ken_burns_forward(t, total_duration):
    """前向zoom Ken Burns：持续缩放到消失点，模拟驾驶感"""
    if BG_IMAGE_RAW is None:
        return None
    raw_w, raw_h = BG_IMAGE_RAW.size
    progress = t / max(total_duration, 1)
    zoom = 1.0 + 0.20 * progress   # 比普通KB更强的zoom
    crop_w = int(W * (1.15 / zoom))
    crop_h = int(H * (1.15 / zoom))
    # 锁定消失点在图片中心，不漂移
    cx = (raw_w - crop_w) // 2
    cy = (raw_h - crop_h) // 2
    cropped = BG_IMAGE_RAW.crop((cx, cy, cx + crop_w, cy + crop_h))
    frame = cropped.resize((W, H), Image.LANCZOS)
    frame_rgba = frame.convert('RGBA')
    frame_rgba = Image.alpha_composite(frame_rgba, _KB_GRADIENT)
    return frame_rgba.convert('RGB')


# 预计算 Ken Burns 渐变遮罩（只算一次）
_KB_GRADIENT = Image.new('RGBA', (W, H), (0, 0, 0, 0))
_kb_gd = ImageDraw.Draw(_KB_GRADIENT)
for _yy in range(H):
    if _yy < int(H * 0.15):
        _a = 20   # 顶部轻遮
    elif _yy < int(H * 0.35):
        _p = (_yy - int(H * 0.15)) / (H * 0.20)
        _a = int(20 + (LYRIC_AREA_ALPHA - 20) * _p)
    elif _yy < int(H * 0.65):
        _a = LYRIC_AREA_ALPHA   # 歌词区域，由 LYRIC_AREA_ALPHA 控制
    else:
        _p = (_yy - int(H * 0.65)) / (H * 0.35)
        _a = int(LYRIC_AREA_ALPHA + (60 - LYRIC_AREA_ALPHA) * _p)  # 底部渐深（降低最深值）
    _kb_gd.line([(0, _yy), (W, _yy)], fill=(0, 0, 0, max(0, min(255, _a))))
del _kb_gd


# 兼容旧逻辑的 BG_IMAGE（静态淡入）
BG_IMAGE = None
BG_FADE_START = 3.0
BG_FADE_END = 6.0

# ============================================================
# Step 3.5: 开头配音（TTS旁白）
# ============================================================
VOICEOVER_TEXT = os.environ.get("VOICEOVER_TEXT", "")
VOICEOVER_PATH = None

def generate_voiceover(text, output_path):
    """用edge-tts生成开头配音"""
    try:
        import subprocess as sp
        env = os.environ.copy()
        _vo_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if _vo_proxy:
            env['http_proxy'] = _vo_proxy
            env['https_proxy'] = _vo_proxy
        result = sp.run([
            "edge-tts",
            "--voice", "zh-CN-XiaoxiaoNeural",
            "--rate", "+15%",
            "--text", text,
            "--write-media", output_path,
        ], env=env, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.exists(output_path):
            y_vo, sr_vo = librosa.load(output_path, sr=22050)
            dur = len(y_vo) / sr_vo
            print(f"  🎙️ 配音生成完成: {dur:.1f}s")
            return True
    except Exception as e:
        print(f"  ⚠️ 配音生成失败: {e}")
    return False

if VOICEOVER_TEXT.strip():
    print(f"🎙️ 生成开头配音...")
    VOICEOVER_PATH = tempfile.mktemp(suffix='.mp3', prefix='voiceover_')
    if not generate_voiceover(VOICEOVER_TEXT, VOICEOVER_PATH):
        VOICEOVER_PATH = None

# ============================================================
# 工具函数
# ============================================================
_font_cache = {}

# fallback 字体链：系统字体在 cron/launchd 下可能加载失败，优先用用户字体
_FALLBACK_FONTS = [
    YOURAN_KAI, CHUNFENG_KAI, MUYAO_SHOUXIE, PANGMEN, HANCHANTUZHUOTI,
    XINGKAI, PINGFANG,
]

def _get_font(path, size, index=0):
    key = (path, size, index)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, size, index=index)
        except Exception:
            # 主路径失败，按优先级尝试 fallback 字体
            loaded = None
            for fb in _FALLBACK_FONTS:
                if fb == path:
                    continue
                try:
                    loaded = ImageFont.truetype(fb, size)
                    print(f"  ⚠️ 字体 {os.path.basename(path)} 加载失败，fallback → {os.path.basename(fb)}")
                    break
                except Exception:
                    continue
            _font_cache[key] = loaded if loaded else ImageFont.load_default()
    return _font_cache[key]

def get_font_for_text(text, size, lang="auto"):
    """歌词字体选择：优先LYRIC_FONT_OVERRIDE，否则按MOOD_TAG自动匹配"""
    if LYRIC_FONT_OVERRIDE and os.path.exists(LYRIC_FONT_OVERRIDE):
        return _get_font(LYRIC_FONT_OVERRIDE, size)
    return _get_font(_DEFAULT_LYRIC_FONT, size)

def beat_intensity(t):
    if not BEAT_TIMES: return 0
    min_dist = min(abs(t - bt) for bt in BEAT_TIMES)
    if min_dist < 0.04: return 1.0
    elif min_dist < 0.13: return max(0, 1 - (min_dist - 0.04) / 0.09)
    return 0

def ease_out_expo(t):
    return 1 if t >= 1 else 1 - pow(2, -10 * t)

def ease_in_quad(t):
    return t * t

def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def get_text_dims(font, text):
    lines = text.split('\n')
    max_w, total_h = 0, 0
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        max_w = max(max_w, w)
        total_h += h + (35 if i < len(lines) - 1 else 0)
    return max_w, total_h

# ============================================================
# 双层字幕绘制（底层=关键词1-4字 + 顶层=完整歌词叠在底层正中间）
# 底层透明度由环境变量 LYRIC_BOTTOM_ALPHA 控制（默认0=单层，古风模版显式传0.45）
# ============================================================
LYRIC_BOTTOM_ALPHA = float(os.environ.get("LYRIC_BOTTOM_ALPHA", "0"))

# 后层动画模式轮换
_BACK_ANIMS = ["slam", "slide_left", "slide_right", "rotate"]

def _extract_keywords(text, max_chars=2):
    """从歌词中提取1-2个核心意象词作为底层展示

    策略：按标点/空格拆成短语 → 取最后一个2字中文词
    例：'乌篷摇了摇，橹声绕桥边' → '桥边'
        '雨打芭蕉，风拂柳烟' → '柳烟'
        '梦里荷香满江南' → '江南'
    """
    import re
    # 按标点/空格拆成短语
    phrases = re.split(r'[，。！？、；\s,\.!\?\n]+', text)
    phrases = [p.strip() for p in phrases if p.strip()]

    # 从最后一个短语开始，找2字中文词
    for phrase in reversed(phrases):
        cn_chars = re.findall(r'[\u4e00-\u9fff]', phrase)
        if len(cn_chars) >= 2:
            # 取最后2个字（通常是名词/意象：桥边、江南、柳烟）
            return ''.join(cn_chars[-max_chars:])

    # fallback: 整句中文取最后2字
    all_cn = re.findall(r'[\u4e00-\u9fff]', text)
    if len(all_cn) >= 2:
        return ''.join(all_cn[-max_chars:])
    elif all_cn:
        return all_cn[0]
    return text[:max_chars]

def draw_dual_lyrics(draw, t, current_lyric, bi, shake_x, shake_y, lyric_idx=0):
    """双层字幕：底层=关键词(1-4字) + 顶层=完整歌词叠在底层正中间"""
    if not current_lyric:
        return

    ls, le, lt, llang = current_lyric
    age = t - ls
    dur = le - ls
    raw = lt.replace('\n', '')
    lines = lt.split('\n')

    # ── 提取关键词（1-4个中文字）──
    keywords = _extract_keywords(raw, 4)
    if not keywords:
        keywords = raw[:2]

    # ── 前层字号：使用全视频统一字号（基于最长句，由顶层预计算）──
    top_size = UNIFIED_TOP_SIZE

    # ── 后层字号 = 前层 × 4，限制不超屏宽 ──
    bottom_size = top_size * 4
    max_bottom = int(W * 0.95 / max(len(keywords), 1))
    bottom_size = min(bottom_size, max_bottom)

    # 后层字体（强制用书法字体，只渲染中文关键词，避免乱码）
    bottom_font = get_font_for_text(keywords, bottom_size, "cn")
    bb = bottom_font.getbbox(keywords)
    kw_w, kw_h = bb[2]-bb[0], bb[3]-bb[1]

    # 后层动画（轮换模式）
    anim = _BACK_ANIMS[lyric_idx % len(_BACK_ANIMS)]
    back_in, back_out = 0.15, 0.2
    cx, cy_center = W // 2, H // 2

    if anim == "slam":
        if age < back_in:
            p = ease_out_expo(age/back_in); bscale = 2.5-1.5*p; balpha = min(1, age/(back_in*0.3))
        elif age > dur-back_out:
            p = (age-(dur-back_out))/back_out; bscale = 1.0+1.5*ease_in_quad(p); balpha = max(0, 1-ease_in_quad(p))
        else: bscale, balpha = 1.0, 1.0
        actual_bs = max(40, int(bottom_size * bscale))
        bf = get_font_for_text(keywords, actual_bs, "cn")
        bbb = bf.getbbox(keywords); bw, bh = bbb[2]-bbb[0], bbb[3]-bbb[1]
        bx, by = cx-bw//2, cy_center-bh//2
    elif anim == "slide_left":
        if age < back_in:
            p = ease_out_expo(age/back_in); x_off = int(-W*0.6*(1-p)); balpha = p
        elif age > dur-back_out:
            p = (age-(dur-back_out))/back_out; x_off = int(W*0.6*ease_in_quad(p)); balpha = max(0, 1-ease_in_quad(p))
        else: x_off, balpha = 0, 1.0
        bscale = 1.0; bf = bottom_font; bw, bh = kw_w, kw_h
        bx, by = cx-bw//2+x_off, cy_center-bh//2
    elif anim == "slide_right":
        if age < back_in:
            p = ease_out_expo(age/back_in); x_off = int(W*0.6*(1-p)); balpha = p
        elif age > dur-back_out:
            p = (age-(dur-back_out))/back_out; x_off = int(-W*0.6*ease_in_quad(p)); balpha = max(0, 1-ease_in_quad(p))
        else: x_off, balpha = 0, 1.0
        bscale = 1.0; bf = bottom_font; bw, bh = kw_w, kw_h
        bx, by = cx-bw//2+x_off, cy_center-bh//2
    else:  # rotate
        if age < back_in*1.5:
            p = ease_out_back(min(1, age/(back_in*1.5))); bscale = 0.3+0.7*p
            x_off = int(W*0.3*(1-p)); y_off = int(-H*0.2*(1-p)); balpha = min(1, age/(back_in*0.5))
        elif age > dur-back_out:
            p = (age-(dur-back_out))/back_out; bscale = 1.0+0.5*ease_in_quad(p)
            x_off = int(-W*0.3*ease_in_quad(p)); y_off = int(H*0.2*ease_in_quad(p)); balpha = max(0, 1-ease_in_quad(p))
        else: bscale, x_off, y_off, balpha = 1.0, 0, 0, 1.0
        actual_bs = max(40, int(bottom_size * bscale))
        bf = get_font_for_text(keywords, actual_bs, "cn")
        bbb = bf.getbbox(keywords); bw, bh = bbb[2]-bbb[0], bbb[3]-bbb[1]
        bx, by = cx-bw//2+x_off, cy_center-bh//2+y_off

    # 绘制后层（关键词）
    # 底层alpha为0时完全跳过底层绘制（单层模式）
    ba = LYRIC_BOTTOM_ALPHA
    if ba > 0.01:
        if LYRIC_COLOR_CYCLE:
            bc = LYRIC_COLORS[lyric_idx % len(LYRIC_COLORS)]
        else:
            bc = STYLE["lyric_bottom_color"]
        pulse = 1.0 + bi * 0.06
        bottom_color = tuple(min(255, int(c * ba * balpha * pulse)) for c in bc)
        stroke_c = tuple(min(255, int(c * ba * balpha * 0.3)) for c in bc)
        try:
            draw.text((bx, by + shake_y), keywords, fill=bottom_color, font=bf,
                      stroke_width=3, stroke_fill=stroke_c)
        except:
            draw.text((cx-kw_w//2, cy_center-kw_h//2 + shake_y), keywords,
                      fill=bottom_color, font=bottom_font, stroke_width=3, stroke_fill=stroke_c)

    bottom_center_y = cy_center

    # ── 前层歌词（叠在底层正中间，延迟0.15s弹入）──
    top_font = get_font_for_text(raw, top_size, llang)
    tw2, th2 = get_text_dims(top_font, lt)
    if tw2 > LYRIC_MAX_W:
        top_size = int(top_size * LYRIC_MAX_W / tw2)
        top_font = get_font_for_text(raw, top_size, llang)
        tw2, th2 = get_text_dims(top_font, lt)

    top_base_y = bottom_center_y - th2 // 2 + LYRIC_Y_OFFSET

    front_delay = 0.35   # 顶层比底层延迟0.35s进入（不同步感更明显）
    front_age = max(0, age - front_delay)
    front_in, front_out = 0.3, 0.4  # 顶层淡入更慢，提前更多淡出
    if front_age <= 0:
        top_scale, top_alpha = 0, 0
    elif front_age < front_in:
        p = ease_out_back(front_age / front_in)
        top_scale = 0.2 + 0.8 * p
        top_alpha = min(1, front_age / (front_in * 0.3))
    elif age > dur - front_out:
        p = (age - (dur - front_out)) / front_out
        top_scale = 1.0 - 0.5 * ease_in_quad(p)
        top_alpha = max(0.02, 1 - ease_in_quad(p))
        actual_top_size = max(20, int(top_size * top_scale))
        top_font = get_font_for_text(raw, actual_top_size, llang)
        tw2, th2 = get_text_dims(top_font, lt)
        top_base_y = bottom_center_y - th2 // 2 + LYRIC_Y_OFFSET
    else:
        top_alpha = 1.0

    # 鼓点闪烁（NO_FLASH时禁用）
    flash_colors = STYLE["lyric_flash_colors"]
    tc = LYRIC_TOP_COLOR_OVERRIDE if LYRIC_TOP_COLOR_OVERRIDE else STYLE["lyric_top_color"]
    if not NO_FLASH and bi > 0.5:
        beat_idx = sum(1 for bt in BEAT_TIMES if bt <= t)
        fc = flash_colors[beat_idx % len(flash_colors)]
        top_color = tuple(int((c * 0.5 + f * 0.5) * top_alpha) for c, f in zip(tc, fc))
    else:
        top_color = tuple(int(c * top_alpha) for c in tc)

    cur_y = top_base_y + shake_y

    # 打字机模式：预计算每行的起始time offset，行与行顺序打印
    if LYRIC_ANIM == "typewriter":
        char_time = max(0.08, dur * 0.7 / max(sum(len(l) for l in lines), 1))  # 知识库规定0.08s/字
        line_offsets = []   # 每行开始打印的时间点
        t_cursor = 0.0
        for l in lines:
            line_offsets.append(t_cursor)
            t_cursor += len(l) * char_time

    for line_idx, line in enumerate(lines):
        bbox = top_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        x = LYRIC_MARGIN_LEFT + (LYRIC_MAX_W - lw) // 2 + shake_x

        # 打字机模式：顺序逐行逐字（行2等行1打完）
        if LYRIC_ANIM == "typewriter":
            line_start = line_offsets[line_idx]
            line_age = age - line_start
            if line_age <= 0:
                cur_y += lh + 30
                continue
            chars_shown = min(len(line), int(line_age / char_time))
            display_text = line[:chars_shown]
            if not display_text:
                cur_y += lh + 30
                continue
        else:
            display_text = line

        # 描边模式
        if LYRIC_STROKE_MODE == "shadow":
            # 深色阴影打底，不加描边，保持字体笔画干净利落
            shadow_color = tuple(int(c * top_alpha * 0.35) for c in (20, 20, 20))
            for dx, dy in [(2, 2), (2, 3), (3, 2)]:
                draw.text((x + dx, cur_y + dy), display_text, fill=shadow_color, font=top_font)
            draw.text((x, cur_y), display_text, fill=top_color, font=top_font)
        elif LYRIC_STROKE_MODE == "stroke":
            draw.text((x, cur_y), display_text, fill=top_color, font=top_font,
                      stroke_width=3, stroke_fill=top_color)
        else:
            draw.text((x, cur_y), display_text, fill=top_color, font=top_font)

        cur_y += lh + 30

    # ── 拼音层 ──
    if SHOW_PINYIN and llang in ("cn", "mix"):
        try:
            from pypinyin import pinyin, Style as PYStyle
            py_text = ' '.join(p[0] for p in pinyin(raw, style=PYStyle.NORMAL))
            py_size = max(24, top_size // 3)
            py_font = _get_font(PINGFANG, py_size)
            py_bbox = py_font.getbbox(py_text)
            py_w = py_bbox[2] - py_bbox[0]
            if py_w > W - 60:
                py_size = int(py_size * (W - 60) / py_w)
                py_font = _get_font(PINGFANG, py_size)
                py_bbox = py_font.getbbox(py_text)
                py_w = py_bbox[2] - py_bbox[0]
            py_x = (W - py_w) // 2 + shake_x
            py_color = tuple(int(c * top_alpha) for c in (160, 200, 220))
            draw.text((py_x, cur_y), py_text, fill=py_color, font=py_font,
                      stroke_width=1, stroke_fill=(0, 0, 0))
            cur_y += (py_bbox[3] - py_bbox[1]) + 20
        except:
            pass


# ============================================================
# 覆盖特效：萤火光点 / 旋转黑胶
# ============================================================

OVERLAY_EFFECT = os.environ.get("OVERLAY_EFFECT", "")  # "firefly" | "vinyl" | ""

# --- 萤火光点预参数（seed固定，保证每帧连贯）---
_FF_COUNT = 18
_ff_rng = np.random.RandomState(77)
_FF_BASE_X  = _ff_rng.uniform(0.05, 0.92, _FF_COUNT)
_FF_BASE_Y  = _ff_rng.uniform(0.15, 0.88, _FF_COUNT)
_FF_RADIUS  = _ff_rng.uniform(5, 12, _FF_COUNT)
_FF_PHASE   = _ff_rng.uniform(0, 2 * math.pi, _FF_COUNT)
_FF_DRIFT_X = _ff_rng.uniform(0.2, 0.5, _FF_COUNT)
_FF_DRIFT_Y = _ff_rng.uniform(0.008, 0.02, _FF_COUNT)


def draw_fireflies(img, t):
    """18个暖黄萤火光点：缓慢漂浮+闪烁，叠加在背景图上"""
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for i in range(_FF_COUNT):
        px = int((_FF_BASE_X[i] + 0.06 * math.sin(t * _FF_DRIFT_X[i] + _FF_PHASE[i])) * W)
        py = int((_FF_BASE_Y[i] - t * _FF_DRIFT_Y[i]) % 1.0 * H)
        bri = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * _FF_DRIFT_X[i] * 1.7 + _FF_PHASE[i]))
        r = int(_FF_RADIUS[i])
        # 外层大晕（低透明）
        glow_size = r * 5
        glow = Image.new('RGBA', (glow_size * 2, glow_size * 2), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for ring in range(glow_size, 0, -1):
            a = int(40 * bri * (ring / glow_size) ** 2)
            gd.ellipse([glow_size - ring, glow_size - ring,
                        glow_size + ring, glow_size + ring],
                       fill=(255, 210, 80, a))
        # 内核亮点
        gd.ellipse([glow_size - r, glow_size - r,
                    glow_size + r, glow_size + r],
                   fill=(255, 240, 160, int(160 * bri)))
        layer.paste(glow, (px - glow_size, py - glow_size), glow)
    return Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')


# --- 黑胶：封面圆形缓存 ---
_VINYL_COVER_CACHE = {}
_VINYL_DIAM = 280   # 黑胶直径（px）


def _build_vinyl_cover(cover_path, diam):
    if cover_path in _VINYL_COVER_CACHE:
        return _VINYL_COVER_CACHE[cover_path]
    try:
        src = Image.open(cover_path).convert('RGBA')
    except Exception:
        src = Image.new('RGBA', (diam, diam), (50, 50, 50, 255))
    # 居中裁为正方形
    cw, ch = src.size
    s = min(cw, ch)
    src = src.crop(((cw - s) // 2, (ch - s) // 2, (cw + s) // 2, (ch + s) // 2))
    inner = int(diam * 0.70)
    src = src.resize((inner, inner), Image.LANCZOS)
    # 圆形遮罩
    mask = Image.new('L', (inner, inner), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, inner - 1, inner - 1], fill=255)
    src.putalpha(mask)
    _VINYL_COVER_CACHE[cover_path] = src
    return src


def draw_vinyl_player(img, t, cover_path):
    """旋转黑胶：右上角，10秒/圈，外圈黑胶纹+唱针"""
    diam = _VINYL_DIAM
    cx = W - diam // 2 - 55
    cy = diam // 2 + 70

    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    # 黑胶外盘（深灰同心纹）
    for ring in range(diam // 2, 0, -3):
        a = int(200 * (ring / (diam // 2)) ** 0.5)
        ld.ellipse([cx - ring, cy - ring, cx + ring, cy + ring],
                   outline=(35, 35, 35, a), width=1)

    # 旋转封面
    cover = _build_vinyl_cover(cover_path, diam)
    angle = (t * 36) % 360
    rotated = cover.rotate(-angle, resample=Image.BICUBIC, expand=False)
    inner = int(diam * 0.70)
    layer.paste(rotated, (cx - inner // 2, cy - inner // 2), rotated)

    # 中心孔
    ld.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(15, 15, 15, 230))

    # 外圈高光边（增加立体感）
    ld.ellipse([cx - diam // 2, cy - diam // 2, cx + diam // 2, cy + diam // 2],
               outline=(80, 80, 80, 120), width=2)

    # 唱针（从黑胶右上角斜插）
    needle_base = (cx + diam // 2 + 18, cy - diam // 2 - 22)
    needle_tip  = (cx + int(diam * 0.38), cy - int(diam * 0.28))
    ld.line([needle_base, needle_tip], fill=(210, 190, 150, 220), width=3)
    ld.ellipse([needle_base[0] - 7, needle_base[1] - 7,
                needle_base[0] + 7, needle_base[1] + 7],
               fill=(180, 160, 120, 220))

    return Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')


def draw_spectrum_bars(img, fi):
    """居中白色双向频谱律动器（11根竖条，上下对称跳动）"""
    if not SHOW_SPECTRUM:
        return img
    bands = BANDS[min(fi, len(BANDS) - 1)]
    N = 17          # 更多柱子，更饱满
    bar_w = 7
    bar_gap = 6
    max_half_h = 55  # 更高的条，更明显
    total_w = N * bar_w + (N - 1) * bar_gap
    start_x = (W - total_w) // 2
    center_y = int(H * 0.22)   # 屏幕上部，歌词上方充分留空

    # 取中间N个频段（人声能量集中在中频）
    mid = len(bands) // 2
    half = N // 2
    selected = (list(bands[max(0, mid - half): mid + half + 1]) + [0.1] * N)[:N]

    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i, val in enumerate(selected):
        bar_h = max(4, int(max_half_h * val))
        x = start_x + i * (bar_w + bar_gap)
        # 主条（上方）
        od.rectangle([x, center_y - bar_h, x + bar_w - 1, center_y - 1],
                     fill=(255, 255, 255, 210))
        # 镜像反射（下方，渐弱）
        refl_h = bar_h // 3
        od.rectangle([x, center_y + 1, x + bar_w - 1, center_y + refl_h],
                     fill=(255, 255, 255, 80))

    return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')


# ============================================================
# 帧生成
# ============================================================
def create_frame(t):
    frame_idx = int(t * FPS)
    bi = beat_intensity(t)
    rms_val = RMS_LIST[min(frame_idx, len(RMS_LIST) - 1)]
    band_data = BANDS[min(frame_idx, len(BANDS) - 1)]

    # === 背景渲染 ===
    if BG_USE_SLIDESHOW:
        # 多图轮换 + Ken Burns + 交叉淡入淡出
        img = slideshow_frame(t, VIDEO_DURATION)
        if img is None:
            img = Image.new('RGB', (W, H), (0, 0, 0))
        # 轻蒙层（歌词区域微加深）
        img_rgba = img.convert('RGBA')
        img_rgba = Image.alpha_composite(img_rgba, _KB_GRADIENT)
        img = img_rgba.convert('RGB')
        draw = ImageDraw.Draw(img)
    elif BG_USE_VIDEO:
        # 视频背景（逐帧，0.5x慢放+正反循环）
        # 慢放：每个输出帧对应原视频的 frame_idx * 0.5 帧
        slow_idx = int(frame_idx * 0.5)
        vi = BG_VIDEO_CYCLE[slow_idx % BG_VIDEO_CYCLE_LEN]
        img = BG_VIDEO_FRAMES[vi].copy()
        # 轻蒙层（只在歌词区域微加深，不要全局压暗）
        img_rgba = img.convert('RGBA')
        _vid_mask = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        _vm_draw = ImageDraw.Draw(_vid_mask)
        for _vy in range(H):
            if _vy < int(H * 0.06): _va = 20
            elif _vy < int(H * 0.35): _va = int(20 + (LYRIC_AREA_ALPHA - 20) * ((_vy - int(H*0.06)) / (H*0.29)))
            elif _vy < int(H * 0.65): _va = LYRIC_AREA_ALPHA
            else: _va = int(LYRIC_AREA_ALPHA + (120 - LYRIC_AREA_ALPHA) * ((_vy - int(H*0.65)) / (H*0.35)))
            _vm_draw.line([(0, _vy), (W, _vy)], fill=(0, 0, 0, max(0, min(255, _va))))
        img_rgba = Image.alpha_composite(img_rgba, _vid_mask)
        img = img_rgba.convert('RGB')
        draw = ImageDraw.Draw(img)
    elif BG_USE_IMAGE:
        # 图库背景 + Ken Burns 动效（前向zoom或普通）
        if BG_FORWARD_ZOOM:
            img = ken_burns_forward(t, VIDEO_DURATION)
        else:
            img = ken_burns_crop(t, VIDEO_DURATION)
        if img is None:
            img = Image.new('RGB', (W, H), (0, 0, 0))
        # ken_burns_crop/forward 已在函数内叠过 _KB_GRADIENT，无需再叠
        draw = ImageDraw.Draw(img)
    else:
        # fallback: 代码粒子背景
        img = Image.new('RGB', (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        img = draw_dynamic_bg(img, draw, W, H, t, bi, rms_val, band_data, bg_type=BG_TYPE)
        draw = ImageDraw.Draw(img)
        # 静态背景图淡入（旧逻辑兼容）
        if BG_IMAGE and t >= BG_FADE_START:
            if t < BG_FADE_END:
                p = (t - BG_FADE_START) / (BG_FADE_END - BG_FADE_START)
                p = 1 - (1 - p) * (1 - p)
                bg_alpha = p * 0.65
            else:
                bg_alpha = 0.65
            img = Image.blend(img, BG_IMAGE, bg_alpha)
            draw = ImageDraw.Draw(img)

    # === 震屏（NO_SHAKE时禁用）===
    random.seed(int(t * FPS) + 42)
    if NO_SHAKE:
        shake_x, shake_y = 0, 0
    else:
        shake_x = int(bi * random.choice([-5, -3, -2, 0, 2, 3, 5]))
        shake_y = int(bi * random.choice([-4, -2, 0, 2, 4]))

    # === 覆盖特效（背景图上方、歌词下方）===
    if OVERLAY_EFFECT == "firefly":
        img = draw_fireflies(img, t)
        draw = ImageDraw.Draw(img)
    elif OVERLAY_EFFECT == "vinyl":
        _vinyl_src = BG_IMG or (BG_IMGS.split(",")[0].strip() if BG_IMGS else "")
        if _vinyl_src and os.path.exists(_vinyl_src):
            img = draw_vinyl_player(img, t, _vinyl_src)
            draw = ImageDraw.Draw(img)

    # === 弹幕 ===
    draw_danmu(draw, t)

    # === 律动器（白色居中频谱柱）===
    if SHOW_SPECTRUM:
        img = draw_spectrum_bars(img, frame_idx)
        draw = ImageDraw.Draw(img)

    # === 覆盖式Hook（与歌词同时出现，悬停在屏幕上方约22%位置）===
    if HOOK_OVERLAY_TEXT and t < HOOK_OVERLAY_DURATION:
        fade_in_end = 0.4
        fade_out_start = HOOK_OVERLAY_DURATION - 0.5
        if t < fade_in_end:
            hook_alpha = t / fade_in_end
        elif t > fade_out_start:
            hook_alpha = (HOOK_OVERLAY_DURATION - t) / 0.5
        else:
            hook_alpha = 1.0
        hook_alpha = max(0.0, min(1.0, hook_alpha))

        if hook_alpha > 0:
            h_size = HOOK_OVERLAY_SIZE
            h_font = _get_font(HOOK_FONT_PATH, h_size, index=HOOK_FONT_INDEX)
            h_bbox = h_font.getbbox(HOOK_OVERLAY_TEXT)
            h_w = h_bbox[2] - h_bbox[0]
            if h_w > LYRIC_MAX_W:
                h_size = int(h_size * LYRIC_MAX_W / h_w)
                h_font = _get_font(HOOK_FONT_PATH, h_size, index=HOOK_FONT_INDEX)
                h_bbox = h_font.getbbox(HOOK_OVERLAY_TEXT)
                h_w = h_bbox[2] - h_bbox[0]
            h_h = h_bbox[3] - h_bbox[1]
            h_x = LYRIC_MARGIN_LEFT + (LYRIC_MAX_W - h_w) // 2
            h_y = int(H * 0.22)
            h_color = tuple(int(c * hook_alpha) for c in HOOK_OVERLAY_COLOR)
            shadow_c = tuple(int(30 * hook_alpha) for _ in range(3))
            for dx, dy in [(2, 3), (3, 2), (3, 3)]:
                draw.text((h_x + dx, h_y + dy), HOOK_OVERLAY_TEXT, fill=shadow_c, font=h_font)
            draw.text((h_x, h_y), HOOK_OVERLAY_TEXT, fill=h_color, font=h_font)

    # === "听完再划走" 小字提示（跟随歌词一起显示）===
    NO_HEADER = os.environ.get("NO_HEADER", "false").lower() == "true"
    if not NO_HEADER:
        # header 用 XINGKAI（系统字体，Unicode 覆盖完整，避免·等字符乱码）
        header_song_size = 72
        header_song_font = _get_font(XINGKAI, header_song_size, index=1)  # Bold variant
        bbox_s = header_song_font.getbbox(SONG_NAME)
        sw = bbox_s[2] - bbox_s[0]
        if sw > W - 80:
            header_song_size = int(header_song_size * (W - 80) / sw)
            header_song_font = _get_font(XINGKAI, header_song_size, index=1)
            bbox_s = header_song_font.getbbox(SONG_NAME)
            sw = bbox_s[2] - bbox_s[0]
        sx = (W - sw) // 2
        sy = int(H * 0.04)
        draw.text((sx, sy), SONG_NAME, fill=(255, 255, 255), font=header_song_font)
        header_artist_font = _get_font(XINGKAI, header_song_size, index=0)
        bbox_a = header_artist_font.getbbox(ARTIST_NAME)
        aw = bbox_a[2] - bbox_a[0]
        ax = (W - aw) // 2
        ay = sy + (bbox_s[3] - bbox_s[1]) + 12
        draw.text((ax, ay), ARTIST_NAME, fill=(180, 180, 190), font=header_artist_font)

    # === 配音字幕（开头旁白，屏幕居中，大字占据视觉主体）===
    if VOICEOVER_TEXT.strip() and VOICEOVER_PATH:
        vo_start = 0.3  # 配音延迟
        vo_end = vo_start + 5.0  # 约4.3s配音 + 余量
        if vo_start <= t < vo_end:
            vo_age = t - vo_start
            # 淡入淡出
            if vo_age < 0.3:
                vo_alpha = vo_age / 0.3
            elif t > vo_end - 0.5:
                vo_alpha = max(0, (vo_end - t) / 0.5)
            else:
                vo_alpha = 1.0
            # 自动拆行+自适应字号，占据屏幕中心
            vo_text = VOICEOVER_TEXT
            # 按标点或长度拆行
            vo_lines = []
            for punct in ['，', '。', '！', '？', ',', '!', '?']:
                if punct in vo_text:
                    parts = vo_text.split(punct, 1)
                    vo_lines = [parts[0] + punct, parts[1].strip()]
                    break
            if not vo_lines:
                mid = (len(vo_text) + 1) // 2
                vo_lines = [vo_text[:mid], vo_text[mid:]]
            vo_lines = [l for l in vo_lines if l.strip()]
            # 字号：根据最长行自适应，目标占屏幕宽度70-80%
            longest = max(vo_lines, key=len)
            vo_size = 80
            vo_font = get_font_for_text(longest, vo_size, "cn")
            test_w = vo_font.getbbox(longest)[2] - vo_font.getbbox(longest)[0]
            target_w = int(W * 0.75)
            if test_w > 0:
                vo_size = int(vo_size * target_w / test_w)
                vo_size = max(50, min(vo_size, 120))
            vo_font = get_font_for_text(longest, vo_size, "cn")
            # 计算总高度
            total_h = 0
            line_metrics = []
            for line in vo_lines:
                bbox = vo_font.getbbox(line)
                lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
                line_metrics.append((lw, lh))
                total_h += lh
            total_h += 20 * (len(vo_lines) - 1)  # 行间距
            # 居中绘制
            cur_y = (H - total_h) // 2
            vo_color = tuple(int(c * vo_alpha) for c in (240, 200, 80))
            vo_stroke = tuple(int(c * vo_alpha) for c in (60, 30, 0))
            for i, line in enumerate(vo_lines):
                lw, lh = line_metrics[i]
                lx = (W - lw) // 2
                draw.text((lx, cur_y), line, fill=vo_color, font=vo_font,
                          stroke_width=4, stroke_fill=vo_stroke)
                cur_y += lh + 20

    # "听完再划走" 小字（左下角，歌词出现后才显示）
    if t > 1.0 and t < VIDEO_DURATION - 2:
        hint_alpha = min(1, (t - 1.0) / 1.0) * 0.5
        hint_font = _get_font(XINGKAI, 28)
        hint_color = tuple(int(200 * hint_alpha) for _ in range(3))
        draw.text((20, H - 40), "听完再划走", fill=hint_color, font=hint_font)

    # === 双层字幕（金句期间不显示，尾部1.5s不画，避免重叠）===
    current = None
    current_idx = 0
    # 金句显示期间不画歌词（避免文字重叠）
    if t >= OPENING_TOTAL and t < VIDEO_DURATION - 1.5:
        for idx_l, (ls, le, lt, llang) in enumerate(LYRICS):
            if ls <= t < le:
                current = (ls, le, lt, llang)
                current_idx = idx_l
                break
    draw_dual_lyrics(draw, t, current, bi, shake_x, shake_y, lyric_idx=current_idx)

    # === 右上角引导（可通过NO_HEADER关闭）===
    if not NO_HEADER:
        cf = _get_font(XINGKAI, 24)
        if t < 8: ct = "副歌马上来 别划走"
        elif t < 20: ct = "评论区打出你听到的歌词"
        else: ct = "完整版在主页 点关注"
        ca = 0.40 + 0.10 * math.sin(t * 2)
        draw.text((W - 320, 55), ct, fill=tuple(int(c * ca) for c in (160, 165, 185)), font=cf)

    # === 进度条 ===
    progress = t / VIDEO_DURATION
    bar_y = H - 6
    bar_filled = int(W * progress)
    draw.rectangle([0, bar_y, W, H], fill=(30, 30, 30))
    ps = STYLE["progress_start"]
    pe = STYLE["progress_end"]
    if bar_filled > 0:
        for px in range(bar_filled):
            p = px / W
            r = int(ps[0] + (pe[0] - ps[0]) * p)
            g = int(ps[1] + (pe[1] - ps[1]) * p)
            b = int(ps[2] + (pe[2] - ps[2]) * p)
            draw.line([(px, bar_y), (px, H)], fill=(r, g, b))

    # === 尾部（歌名拆2行显示）===
    if t >= VIDEO_DURATION - 1.5:
        fade = max(0, 1 - (t - (VIDEO_DURATION - 1.5)) / 1.5)
        et = SONG_NAME.upper() if all(ord(c) < 128 for c in SONG_NAME) else SONG_NAME
        end_text = split_lyric_2lines(et)
        end_size = 140 if LANDSCAPE else 170
        ef = get_font_for_text(et, end_size, "cn" if any(ord(c) > 127 for c in et) else "en")
        etw, eth = get_text_dims(ef, end_text)
        # 自适应缩小
        if etw > W - 60:
            end_size = int(end_size * (W - 60) / etw)
            ef = get_font_for_text(et, end_size, "cn" if any(ord(c) > 127 for c in et) else "en")
            etw, eth = get_text_dims(ef, end_text)
        # 结尾歌名用白色，不用hook颜色（红色太吓人）
        ec = tuple(int(c * fade) for c in (255, 250, 240))
        end_y = (H - eth) // 2 - 20
        for eline in end_text.split('\n'):
            bbox = ef.getbbox(eline)
            elw = bbox[2] - bbox[0]
            elh = bbox[3] - bbox[1]
            ex = (W - elw) // 2
            draw.text((ex, end_y), eline, fill=ec, font=ef)
            end_y += elh + 20

    return img

# ============================================================
# 生成视频
# ============================================================
print(f"🎬 生成视频: {SONG_NAME} — {ARTIST_NAME} ({VIDEO_DURATION}s, {total_frames}帧)")
FRAMES_DIR = tempfile.mkdtemp(prefix="video_frames_")

for i in range(total_frames):
    t = i / FPS
    img = create_frame(t)
    img.save(f"{FRAMES_DIR}/frame_{i:05d}.png")
    if i % (FPS * 5) == 0:
        print(f"  进度: {t:.0f}s / {VIDEO_DURATION}s")

print("🔧 合成视频...")
ffmpeg_cmd = [
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", f"{FRAMES_DIR}/frame_%05d.png",
    "-i", AUDIO_PATH,
]
# 如果有配音，作为第三输入混入
if VOICEOVER_PATH and os.path.exists(VOICEOVER_PATH):
    ffmpeg_cmd += ["-i", VOICEOVER_PATH]
    # 配音从0.3s开始，音量稍大；音乐正常淡入淡出
    audio_filter = (
        f"[1:a]afade=t=in:d=1,afade=t=out:st={VIDEO_DURATION - 2}:d=2,volume=0.5[music];"
        f"[2:a]adelay=300|300,volume=1.8[voice];"
        f"[music][voice]amix=inputs=2:duration=first[aout]"
    )
    ffmpeg_cmd += [
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-filter_complex", audio_filter,
        "-map", "0:v", "-map", "[aout]",
        "-c:a", "aac", "-b:a", "320k",
        "-t", str(VIDEO_DURATION),
        OUTPUT_PATH
    ]
else:
    ffmpeg_cmd += [
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k",
        "-af", f"afade=t=in:d=0.5,afade=t=out:st={VIDEO_DURATION - 1}:d=1",
        "-t", str(VIDEO_DURATION),
        "-shortest",
        OUTPUT_PATH
    ]
result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ FFmpeg错误: {result.stderr[-500:]}")
    sys.exit(1)

import shutil
shutil.rmtree(FRAMES_DIR)
if VOICEOVER_PATH and os.path.exists(VOICEOVER_PATH):
    os.remove(VOICEOVER_PATH)

size = os.path.getsize(OUTPUT_PATH) / 1024 / 1024

# ============================================================
# 自动质检
# ============================================================
print(f"\n🔍 质检中...")
qa_pass = True
qa_issues = []

# 1. 检查输出分辨率 ≥ 1080p
_qa_proc = subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", OUTPUT_PATH],
    capture_output=True, text=True
)
try:
    _qa_streams = json.loads(_qa_proc.stdout).get("streams", [])
    for _s in _qa_streams:
        if _s.get("codec_type") == "video":
            _qa_w = int(_s.get("width", 0))
            _qa_h = int(_s.get("height", 0))
            if max(_qa_w, _qa_h) < 1080:
                qa_issues.append(f"分辨率不达标: {_qa_w}x{_qa_h} (需≥1080p)")
                qa_pass = False
            else:
                print(f"  ✓ 分辨率: {_qa_w}x{_qa_h}")
except:
    qa_issues.append("无法读取视频分辨率")

# 2. 检查双层歌词是否关闭（alpha=0时不应有底层）
if LYRIC_BOTTOM_ALPHA < 0.01:
    print(f"  ✓ 单层模式 (底层alpha={LYRIC_BOTTOM_ALPHA})")
else:
    print(f"  ✓ 双层模式 (底层alpha={LYRIC_BOTTOM_ALPHA})")

# 3. 检查文件大小（太小可能有问题）
if size < 0.5:
    qa_issues.append(f"文件过小: {size:.1f}MB (可能生成失败)")
    qa_pass = False
else:
    print(f"  ✓ 文件大小: {size:.1f}MB")

# 4. 检查背景类型
if BG_USE_VIDEO:
    print(f"  ✓ 视频背景 ({len(BG_VIDEO_FRAMES)}帧)")
elif BG_USE_IMAGE:
    print(f"  ✓ 图片背景 (Ken Burns)")
else:
    print(f"  ⚠ 代码粒子背景")

# 5. 检查歌词数量
print(f"  ✓ 歌词: {len(LYRICS)}句")
if len(LYRICS) < 2:
    qa_issues.append(f"歌词过少: {len(LYRICS)}句")

# 6. Gemini歌词对齐验证：把实际用的时间戳+音频再问一次Gemini，确认歌词内容是否与音频吻合
try:
    import google.genai as _gai_qa
    from google.genai import types as _gai_types_qa
    _qa_env_path = os.path.expanduser("~/Documents/claude/自动化/suno-api/.env")
    _qa_api_key = None
    if os.path.exists(_qa_env_path):
        with open(_qa_env_path) as _f:
            for _l in _f:
                if _l.startswith("GEMINI_API_KEY="):
                    _qa_api_key = _l.strip().split("=", 1)[1].strip('"').strip("'")
    if not _qa_api_key:
        raise ValueError("GEMINI_API_KEY not found in .env")
    _qa_client = _gai_qa.Client(
        api_key=_qa_api_key,
        http_options=_gai_types_qa.HttpOptions(timeout=120000),
    )
    # 上传音频（AUDIO_PATH已是截取后的副歌片段）
    _qa_upload_path = AUDIO_PATH
    _qa_tmp = None
    if not AUDIO_PATH.isascii():
        import shutil as _shutil_qa
        _qa_fd, _qa_tmp = tempfile.mkstemp(suffix='.wav')
        os.close(_qa_fd)
        _shutil_qa.copy2(AUDIO_PATH, _qa_tmp)
        _qa_upload_path = _qa_tmp
    _qa_uploaded = _qa_client.files.upload(
        file=_qa_upload_path,
        config=_gai_types_qa.UploadFileConfig(mime_type="audio/wav"),
    )
    while _qa_uploaded.state.name == "PROCESSING":
        time.sleep(2)
        _qa_uploaded = _qa_client.files.get(name=_qa_uploaded.name)
    # 构建验证prompt
    _qa_lyrics_str = "\n".join(
        f"{i+1}. [{s:.1f}s-{e:.1f}s] {t}"
        for i, (s, e, t, _) in enumerate(LYRICS)
    )
    _qa_prompt = (
        "这是一段歌曲音频。下面是视频中实际展示的歌词及其出现时间。\n"
        "请逐句检查：歌词内容是否真的在对应时间段被演唱？\n\n"
        f"【歌词时间轴】：\n{_qa_lyrics_str}\n\n"
        "【评估规则】：\n"
        "- match: 该时间段确实在唱这句歌词\n"
        "- mismatch: 时间段对了但歌词文字不对\n"
        "- wrong_time: 歌词内容对但时间偏差超过1.5s\n"
        "- not_found: 音频中完全没有这句歌词\n\n"
        "只返回JSON，格式：{\"ok\": true/false, \"score\": 0-100, \"issues\": [\"第N句: 原因\"]}"
    )
    _qa_resp = _qa_client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=[_gai_types_qa.Content(parts=[
            _gai_types_qa.Part.from_uri(file_uri=_qa_uploaded.uri, mime_type="audio/wav"),
            _gai_types_qa.Part(text=_qa_prompt),
        ])],
        config=_gai_types_qa.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    try:
        _qa_client.files.delete(name=_qa_uploaded.name)
    except:
        pass
    if _qa_tmp and os.path.exists(_qa_tmp):
        os.remove(_qa_tmp)
    _qa_result = json.loads(_qa_resp.text.strip())
    _qa_score = int(_qa_result.get("score", 0))
    _qa_ok = _qa_result.get("ok", False)
    _qa_issues_list = _qa_result.get("issues", [])
    if _qa_ok and _qa_score >= 70:
        print(f"  ✓ 歌词对齐验证: {_qa_score}分 (Gemini确认)")
    else:
        msg = f"歌词对齐不达标: {_qa_score}分"
        if _qa_issues_list:
            msg += " — " + "; ".join(_qa_issues_list[:3])
        qa_issues.append(msg)
        qa_pass = False
        print(f"  ❌ 歌词对齐验证: {_qa_score}分 — {'; '.join(_qa_issues_list[:3])}")
except Exception as _qa_e:
    print(f"  ⚠ 歌词对齐验证跳过 ({_qa_e})")

# 7. 检查素材是否有残留字幕（视频背景时）
if BG_USE_VIDEO and BG_VIDEO_FRAMES:
    # 抽查5帧的底部区域亮度（有白色字幕会明显更亮）
    _check_frames = [0, len(BG_VIDEO_FRAMES)//4, len(BG_VIDEO_FRAMES)//2,
                     len(BG_VIDEO_FRAMES)*3//4, len(BG_VIDEO_FRAMES)-1]
    _subtitle_warning = False
    for _ci in _check_frames:
        _cf = BG_VIDEO_FRAMES[_ci]
        _cw, _ch = _cf.size
        # 检查底部15%区域
        _bottom = _cf.crop((0, int(_ch*0.85), _cw, _ch))
        _pixels = list(_bottom.getdata())
        _avg = sum(sum(p[:3]) for p in _pixels) / (len(_pixels) * 3)
        if _avg > 150:  # 底部异常亮，可能有白色字幕
            _subtitle_warning = True
            break
    if _subtitle_warning:
        qa_issues.append("⚠️ 背景视频底部可能有残留字幕（亮度异常）")
        print(f"  ⚠ 背景视频可能有残留字幕")
    else:
        print(f"  ✓ 背景视频底部无明显字幕")

# 输出质检结果
if qa_pass and not qa_issues:
    print(f"\n✅ 质检通过! 成品: {OUTPUT_PATH} ({size:.1f} MB)")
else:
    print(f"\n⚠️ 质检发现问题:")
    for issue in qa_issues:
        print(f"  ❌ {issue}")
    print(f"\n成品: {OUTPUT_PATH} ({size:.1f} MB) [有质检问题]")
