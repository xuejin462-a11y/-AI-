#!/usr/bin/env python3
"""通用歌词卡点视频生成器 — 基于V2b模板，性能优化版"""

import subprocess, os, sys, math, random, json, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# === 参数（由调用方传入）===
SONG_NAME = os.environ.get("SONG_NAME", "未命名")
ARTIST_NAME = os.environ.get("ARTIST_NAME", "未知")
AUDIO_PATH = os.environ.get("AUDIO_PATH", "")
LYRICS_RAW = os.environ.get("LYRICS_RAW", "")
BG_IMG = os.environ.get("BG_IMG", "")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "output.mp4")
VIDEO_DURATION = int(os.environ.get("VIDEO_DURATION", "30"))

if not AUDIO_PATH or not os.path.exists(AUDIO_PATH):
    print(f"❌ 音频文件不存在: {AUDIO_PATH}")
    sys.exit(1)

W, H = 1080, 1920
FPS = 25  # 25fps足够流畅，减少25%帧数
N_BANDS = 24  # 减少频谱条数

# === 字体 ===
XINGKAI = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/13b8ce423f920875b28b551f9406bf1014e0a656.asset/AssetData/Xingkai.ttc"
PINGFANG = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
ARIAL_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

# === 颜色 ===
C_WHITE = (255, 252, 248)
C_GOLD = (255, 220, 50)
C_RED = (255, 55, 55)
C_ORANGE = (255, 150, 30)
C_HOT_YELLOW = (255, 255, 80)
C_CYAN = (80, 220, 255)
C_NEON_GREEN = (57, 255, 20)
C_ELECTRIC_BLUE = (125, 249, 255)

# ============================================================
# Step 1: 音频分析
# ============================================================
print(f"🎵 分析音频: {os.path.basename(AUDIO_PATH)}")
import librosa

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
# Step 2: 歌词自动对齐
# ============================================================
print("📝 解析歌词...")

def parse_lyrics(raw_text, duration, beat_times):
    lines = [l.strip() for l in raw_text.replace('\r\n', '\n').split('\n') if l.strip()]
    lines = [l for l in lines if len(l) >= 2]
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
            if end <= start:
                end = start + 2.0
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

LYRICS = parse_lyrics(LYRICS_RAW, VIDEO_DURATION, BEAT_TIMES)
print(f"  歌词行数: {len(LYRICS)}")

# ============================================================
# Step 3: Hook & 配置
# ============================================================
HOOKS = [
    (0.0, ARTIST_NAME, 100, C_WHITE, "cn" if any(ord(c) > 127 for c in ARTIST_NAME) else "en"),
    (0.6, f"《{SONG_NAME}》", 110, C_GOLD, "cn"),
    (1.5, "戴耳机听", 90, C_WHITE, "cn"),
    (2.3, "🔥", 180, C_RED, "en"),
]
LISTEN_HOOK_START = 3.5
LISTEN_DURATION = 5.0

# ============================================================
# Step 4: 背景图
# ============================================================
BG_S1ENT = None
if BG_IMG and os.path.exists(BG_IMG):
    print(f"🖼️ 加载背景图: {os.path.basename(BG_IMG)}")
    _bg_raw = Image.open(BG_IMG).convert('RGBA')
    bw, bh = _bg_raw.size
    bg_scale = W / bw
    _bg_scaled = _bg_raw.resize((W, int(bh * bg_scale)), Image.LANCZOS)
    BG_S1ENT = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    BG_S1ENT.paste(_bg_scaled, (0, 0))
    enhancer = ImageEnhance.Brightness(BG_S1ENT)
    BG_S1ENT = enhancer.enhance(0.40)
    gradient = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for yy in range(H):
        if yy < int(H * 0.30): a = 50
        elif yy < int(H * 0.50):
            p = (yy - int(H * 0.30)) / (H * 0.20)
            a = int(50 + 160 * p)
        else: a = 210
        grad_draw.line([(0, yy), (W, yy)], fill=(0, 0, 0, a))
    BG_S1ENT = Image.alpha_composite(BG_S1ENT, gradient).convert('RGB')
    print("  背景图处理完成")

BG_FADE_START = 3.0
BG_FADE_END = 6.0

# ============================================================
# Pre-render: 静态背景渐变（避免每帧重绘）
# ============================================================
BG_GRADIENT = Image.new('RGB', (W, H), (5, 8, 20))
_gd = ImageDraw.Draw(BG_GRADIENT)
for y in range(H):
    ratio = y / H
    _gd.line([(0, y), (W, y)], fill=(int(5 + 4 * ratio), int(8 + 8 * ratio), int(25 + 18 * ratio)))

# ============================================================
# 工具函数（优化版）
# ============================================================
_font_cache = {}

def _get_font(path, size, index=0):
    key = (path, size, index)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, size, index=index)
        except:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]

def get_font_for_text(text, size, lang="auto"):
    if lang == "en": return _get_font(IMPACT, size)
    elif lang == "cn": return _get_font(XINGKAI, size)
    elif lang == "mix": return _get_font(PINGFANG, size)
    else:
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return _get_font(IMPACT, size) if ascii_count > len(text) * 0.6 else _get_font(XINGKAI, size)

def beat_intensity(t):
    if not BEAT_TIMES: return 0
    min_dist = min(abs(t - bt) for bt in BEAT_TIMES)
    if min_dist < 0.04: return 1.0
    elif min_dist < 0.13: return max(0, 1 - (min_dist - 0.04) / 0.09)
    return 0

def ease_out_expo(t):
    return 1 if t >= 1 else 1 - pow(2, -10 * t)

def bar_color(band_idx, intensity):
    t = band_idx / max(1, N_BANDS - 1)
    if t < 0.25: r, g, b = 30, 50, 200
    elif t < 0.5: r, g, b = 40, 140, 255
    elif t < 0.75: r, g, b = 100, 60, 220
    else: r, g, b = 60, 200, 255
    bright = 0.3 + 0.7 * intensity
    return (int(r * bright), int(g * bright), int(b * bright))

def get_text_dims(font, text):
    lines = text.split('\n')
    max_w, total_h = 0, 0
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        max_w = max(max_w, w)
        total_h += h + (35 if i < len(lines) - 1 else 0)
    return max_w, total_h

def draw_text_centered(draw, y, text, font, fill, stroke_w=6, en_font=None):
    """使用PIL内置stroke，避免手动循环"""
    lines = text.split('\n')
    cur_y = y
    for line in lines:
        is_en = all(ord(c) < 128 or c in '，。！？' for c in line.replace(' ', ''))
        use_font = en_font if (is_en and en_font) else font
        bbox = use_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        x = (W - lw) // 2
        # 使用PIL内置stroke（一次调用代替几十次循环）
        draw.text((x, cur_y), line, fill=fill, font=use_font,
                  stroke_width=stroke_w, stroke_fill=(0, 0, 0))
        cur_y += lh + 35

def draw_spectrum_bg(draw, img, frame_idx, t, bi):
    """优化版频谱：用rectangle代替逐像素"""
    if frame_idx >= len(BANDS):
        frame_idx = len(BANDS) - 1
    band_data = BANDS[frame_idx]
    rms_val = RMS_LIST[min(frame_idx, len(RMS_LIST)-1)]

    # 鼓点脉冲（简化）
    if bi > 0.4:
        cx, cy = W // 2, H // 2
        r = int(400 * bi)
        a = bi * 0.08
        fc = (int(40 * a), int(60 * a), int(200 * a))
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fc)

    # 频谱条（用rectangle批量绘制）
    bar_area_top = int(H * 0.28)
    bar_area_bottom = int(H * 0.72)
    bar_area_h = bar_area_bottom - bar_area_top
    bar_gap = 6
    bar_w = (W // 2 - bar_gap * (N_BANDS + 1)) // N_BANDS
    if bar_w < 8: bar_w = 8
    center_y = (bar_area_top + bar_area_bottom) // 2

    for i in range(N_BANDS):
        val = min(1.0, band_data[i] + bi * 0.25)
        bar_h = int(val * bar_area_h * 0.45)
        if bar_h < 4: bar_h = 4
        color = bar_color(i, val)
        bx_right = W // 2 + i * (bar_w + bar_gap) + bar_gap
        bx_left = W // 2 - (i + 1) * (bar_w + bar_gap)
        for bx in [bx_left, bx_right]:
            top = center_y - bar_h
            bottom = center_y + bar_h
            draw.rectangle([bx, top, bx + bar_w, bottom], fill=color)
            # 高光顶部
            hl = min(3, bar_h // 4)
            hc = tuple(min(255, int(v * 1.3)) for v in color)
            draw.rectangle([bx, top, bx + bar_w, top + hl], fill=hc)

    # 顶底小频谱
    small_h_max = 40
    small_w = W // (N_BANDS * 2)
    for i in range(N_BANDS):
        val = band_data[i]
        sh = int(val * small_h_max)
        color = bar_color(i, val * 0.4)
        sx = i * small_w * 2 + small_w // 2
        draw.rectangle([sx, 0, sx + small_w, sh], fill=color)
        draw.rectangle([sx, H - sh, sx + small_w, H], fill=color)

    # 粒子（减少数量）
    random.seed(int(t * FPS) * 3 + 77)
    n_p = int(8 + 15 * rms_val)
    for _ in range(n_p):
        px = random.randint(0, W)
        py = random.randint(0, H)
        pr = random.randint(1, 2)
        pb = random.uniform(0.1, 0.4) * (0.5 + 0.5 * rms_val)
        pc = (int(40*pb), int(100*pb), int(255*pb))
        draw.ellipse([px-pr, py-pr, px+pr, py+pr], fill=pc)

    return img, draw

# ============================================================
# 帧生成
# ============================================================
def create_frame(t):
    frame_idx = int(t * FPS)
    img = BG_GRADIENT.copy()
    draw = ImageDraw.Draw(img)
    bi = beat_intensity(t)

    # 频谱背景
    img, draw = draw_spectrum_bg(draw, img, frame_idx, t, bi)

    # 背景图淡入
    if BG_S1ENT and t >= BG_FADE_START:
        if t < BG_FADE_END:
            p = (t - BG_FADE_START) / (BG_FADE_END - BG_FADE_START)
            p = 1 - (1 - p) * (1 - p)
            bg_alpha = p * 0.55
        else:
            bg_alpha = 0.55
        img = Image.blend(img, BG_S1ENT, bg_alpha)
        draw = ImageDraw.Draw(img)

    # 震屏
    random.seed(int(t * FPS) + 42)
    shake_x = int(bi * random.choice([-5,-3,-2,0,2,3,5]))
    shake_y = int(bi * random.choice([-4,-2,0,2,4]))

    # Hook阶段
    if t < 4.0:
        for ht, htxt, hsz, hcol, hlang in HOOKS:
            if t < ht: continue
            age = t - ht
            if age < 0.08:
                p = ease_out_expo(age / 0.08)
                alpha = p
                scale = 1 + 0.7 * (1 - p)
            elif age < 0.7:
                alpha = 1.0
                scale = 1.0
            else:
                alpha = max(0, 1 - (age - 0.7) / 0.3)
                scale = 1.0
            if alpha < 0.02: continue

            font = get_font_for_text(htxt, int(hsz * scale), hlang)
            bbox = font.getbbox(htxt)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (W - tw) // 2 + shake_x
            y_pos = int(H * 0.40 - th // 2) + shake_y
            color = tuple(int(c * alpha) for c in hcol)
            draw.text((x, y_pos), htxt, fill=color, font=font,
                      stroke_width=5, stroke_fill=(0, 0, 0))

    # "听完再划走"
    if LISTEN_HOOK_START <= t < LISTEN_HOOK_START + LISTEN_DURATION:
        age = t - LISTEN_HOOK_START
        if age < 0.3: lh_alpha = age / 0.3
        elif age > LISTEN_DURATION - 0.5: lh_alpha = max(0, (LISTEN_HOOK_START + LISTEN_DURATION - t) / 0.5)
        else: lh_alpha = 1.0
        lh_alpha *= 0.55 + 0.15 * math.sin(age * 2.5)
        if lh_alpha > 0.02:
            lh_font = _get_font(PINGFANG, 38)
            lh_text = "▼ 听完再划走"
            bbox = lh_font.getbbox(lh_text)
            tw = bbox[2] - bbox[0]
            lh_x = (W - tw) // 2
            lh_c = tuple(int(c * lh_alpha) for c in C_WHITE)
            draw.text((lh_x, int(H * 0.28)), lh_text, fill=lh_c, font=lh_font,
                      stroke_width=2, stroke_fill=(0, 0, 0))

    # 歌词
    current = None
    for ls, le, lt, llang in LYRICS:
        if ls <= t < le:
            current = (ls, le, lt, llang)
            break

    if current:
        ls, le, lt, llang = current
        age = t - ls
        dur = le - ls
        raw = lt.replace('\n', '')
        n = len(raw)

        if n <= 4: main_size = 260
        elif n <= 6: main_size = 210
        elif n <= 7: main_size = 170
        elif n <= 10: main_size = 135
        else: main_size = 105

        font = get_font_for_text(raw, main_size, llang)
        en_font = _get_font(IMPACT, main_size) if llang in ("mix", "en") else None

        tw, th = get_text_dims(font, lt)
        if tw > W - 60:
            main_size = int(main_size * (W - 60) / tw)
            font = get_font_for_text(raw, main_size, llang)
            en_font = _get_font(IMPACT, main_size) if llang in ("mix", "en") else None
            tw, th = get_text_dims(font, lt)

        base_y = (H - th) // 2 - 50

        if age < 0.12:
            p = ease_out_expo(age / 0.12)
            scale = 1 + 0.6 * (1 - p)
            alpha = min(1, age / 0.06)
            font = get_font_for_text(raw, int(main_size * scale), llang)
            en_font = _get_font(IMPACT, int(main_size * scale)) if llang in ("mix", "en") else None
            tw, th = get_text_dims(font, lt)
            base_y = (H - th) // 2 - 50
        elif age > dur - 0.2:
            alpha = max(0.05, (le - t) / 0.2)
        else:
            alpha = 1.0

        color_cycle = [C_HOT_YELLOW, C_GOLD, C_CYAN, C_ELECTRIC_BLUE]
        if bi > 0.5:
            beat_idx = sum(1 for bt in BEAT_TIMES if bt <= t)
            flash_c = color_cycle[beat_idx % len(color_cycle)]
            color = tuple(int(c * alpha) for c in flash_c)
        else:
            color = tuple(int(c * alpha) for c in C_HOT_YELLOW)

        draw_text_centered(draw, base_y + shake_y, lt, font, color,
                          stroke_w=7, en_font=en_font)

    # 右上角引导
    cf = _get_font(PINGFANG, 24)
    if t < 8: ct = "副歌马上来 别划走"
    elif t < 20: ct = "评论区打出你听到的歌词"
    else: ct = "完整版在主页 点关注"
    ca = 0.40 + 0.10 * math.sin(t * 2)
    draw.text((W - 320, 55), ct, fill=tuple(int(c*ca) for c in (160,165,185)), font=cf)

    # 进度条
    progress = t / VIDEO_DURATION
    bar_y = H - 6
    bar_filled = int(W * progress)
    draw.rectangle([0, bar_y, W, H], fill=(30, 30, 30))
    if bar_filled > 0:
        # 简化渐变：分3段颜色
        for px in range(bar_filled):
            p = px / W
            r = int(60 + 195 * p)
            g = int(100 * (1 - p))
            b = int(255 * (1 - p * 0.7))
            draw.line([(px, bar_y), (px, H)], fill=(r, g, b))

    # 尾部
    if t >= VIDEO_DURATION - 1.5:
        fade = max(0, 1 - (t - (VIDEO_DURATION - 1.5)) / 1.5)
        ef = _get_font(IMPACT, 170)
        et = SONG_NAME.upper() if all(ord(c) < 128 for c in SONG_NAME) else SONG_NAME
        ec = tuple(int(c * fade) for c in C_RED)
        draw.text(((W - ef.getbbox(et)[2] + ef.getbbox(et)[0]) // 2, int(H * 0.36)),
                  et, fill=ec, font=ef, stroke_width=7, stroke_fill=(0, 0, 0))

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
result = subprocess.run([
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", f"{FRAMES_DIR}/frame_%05d.png",
    "-i", AUDIO_PATH,
    "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "256k",
    "-af", f"afade=t=in:d=2,afade=t=out:st={VIDEO_DURATION-2}:d=2",
    "-t", str(VIDEO_DURATION),
    "-shortest",
    OUTPUT_PATH
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ FFmpeg错误: {result.stderr[-500:]}")
    sys.exit(1)

import shutil
shutil.rmtree(FRAMES_DIR)

size = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
print(f"\n✅ 成品: {OUTPUT_PATH} ({size:.1f} MB)")
