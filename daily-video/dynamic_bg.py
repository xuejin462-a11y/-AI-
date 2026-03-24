#!/usr/bin/env python3
"""
动态背景生成器 V6 — 纯色底 + 跳跃线律动器
设计原则：
  1. 纯色背景，突出歌词
  2. 底部/顶部细线频谱律动，有节奏感但不喧宾夺主
  3. 鼓点时线条跳跃更明显
"""

import math, random
import numpy as np
from PIL import Image, ImageDraw


def _solid_bg(W, H, color):
    """纯色背景"""
    img = Image.new('RGB', (W, H), color)
    return img


def _draw_freq_lines(draw, W, H, t, bi, rms, band_data, line_color, position="bottom"):
    """跳跃线律动器 — 频谱驱动的细线在顶部/底部跳动

    position: "bottom" 底部, "top" 顶部, "both" 上下都有
    """
    n_bands = len(band_data) if band_data else 24

    def _draw_one_line(base_y, direction, alpha_mult=1.0):
        """direction: -1=向上跳, 1=向下跳"""
        # 主线（频谱驱动）
        points = []
        max_amp = 80 + int(120 * rms) + int(60 * bi)
        for x in range(0, W + 4, 4):
            bi_x = min(int(x / W * n_bands), n_bands - 1)
            val = band_data[bi_x] if bi_x < n_bands else 0.3
            # 加一点正弦波让线条更流畅
            smooth = 0.3 * math.sin(4 * math.pi * x / W + t * 1.5)
            jump = (val + smooth * val) * max_amp * direction
            y = base_y + int(jump)
            points.append((x, y))

        if len(points) >= 2:
            # 主线
            c = tuple(int(v * (0.6 + 0.4 * rms) * alpha_mult) for v in line_color)
            draw.line(points, fill=c, width=2)

            # 鼓点时加一条更亮的细线（微偏移）
            if bi > 0.3:
                bright_points = []
                for x, y in points:
                    offset = int(direction * bi * 15)
                    bright_points.append((x, y + offset))
                bc = tuple(min(255, int(v * (0.8 + 0.5 * bi) * alpha_mult)) for v in line_color)
                draw.line(bright_points, fill=bc, width=1)

        # 基线（细横线）
        base_c = tuple(int(v * 0.15 * alpha_mult) for v in line_color)
        draw.line([(0, base_y), (W, base_y)], fill=base_c, width=1)

    if position in ("bottom", "both"):
        _draw_one_line(int(H * 0.82), -1)  # 底部，向上跳
    if position in ("top", "both"):
        _draw_one_line(int(H * 0.18), 1, alpha_mult=0.6)  # 顶部，向下跳，稍暗


# ============================================================
# 各风格：纯色底 + 不同色调跳跃线
# ============================================================

def draw_bokeh_warm(img, draw, W, H, t, bi, rms, band_data):
    """暖色调（抒情/情歌/流行）— 深灰紫底 + 淡紫跳跃线"""
    result = _solid_bg(W, H, (22, 16, 30))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (160, 100, 200), "both")
    return result


def draw_bokeh_sweet(img, draw, W, H, t, bi, rms, band_data):
    """甜美风（爱情）— 深玫红底 + 粉色跳跃线"""
    result = _solid_bg(W, H, (28, 14, 22))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (220, 100, 160), "both")
    return result


def draw_starfield(img, draw, W, H, t, bi, rms, band_data):
    """民谣/清新 — 深蓝底 + 蓝白跳跃线"""
    result = _solid_bg(W, H, (12, 16, 32))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (100, 150, 220), "both")
    return result


def draw_ink_wash(img, draw, W, H, t, bi, rms, band_data):
    """古风 — 墨色底 + 淡金跳跃线"""
    result = _solid_bg(W, H, (20, 18, 24))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (180, 160, 100), "both")
    return result


def draw_neon_pulse(img, draw, W, H, t, bi, rms, band_data):
    """电子/舞曲 — 深黑底 + 霓虹紫蓝跳跃线"""
    result = _solid_bg(W, H, (10, 8, 20))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (140, 80, 255), "both")
    return result


def draw_hiphop_glitch(img, draw, W, H, t, bi, rms, band_data):
    """嘻哈/说唱 — 深黑底 + 红色跳跃线"""
    result = _solid_bg(W, H, (18, 8, 10))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (220, 50, 50), "both")
    return result


def draw_jazz_smoke(img, draw, W, H, t, bi, rms, band_data):
    """爵士/R&B — 深棕底 + 暖金跳跃线"""
    result = _solid_bg(W, H, (24, 18, 14))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (200, 160, 90), "both")
    return result


def draw_rock_fire(img, draw, W, H, t, bi, rms, band_data):
    """摇滚 — 深黑红底 + 火红跳跃线"""
    result = _solid_bg(W, H, (20, 6, 8))
    d = ImageDraw.Draw(result)
    _draw_freq_lines(d, W, H, t, bi, rms, band_data, (240, 60, 30), "both")
    return result


# ============================================================
# V5 旧版 bokeh 粒子背景（对比用）
# ============================================================
_glow_cache = {}

def _glow_circle(radius):
    if radius in _glow_cache:
        return _glow_cache[radius]
    y, x = np.ogrid[-radius:radius, -radius:radius]
    dist = np.sqrt(x * x + y * y).astype(np.float32)
    mask = np.clip(1.0 - (dist / radius) ** 1.8, 0, 1)
    _glow_cache[radius] = mask
    return mask

def _add_glow(arr, cx, cy, radius, color, brightness=1.0):
    H, W = arr.shape[:2]
    mask = _glow_circle(radius)
    sz = radius * 2
    x1, y1 = cx - radius, cy - radius
    x2, y2 = x1 + sz, y1 + sz
    sx, sy = max(0, -x1), max(0, -y1)
    ex, ey = sz - max(0, x2 - W), sz - max(0, y2 - H)
    dx1, dy1 = max(0, x1), max(0, y1)
    dx2, dy2 = min(W, x2), min(H, y2)
    if dx2 <= dx1 or dy2 <= dy1:
        return
    patch = mask[sy:ey, sx:ex]
    for c in range(3):
        arr[dy1:dy2, dx1:dx2, c] = np.clip(
            arr[dy1:dy2, dx1:dx2, c] + patch * color[c] * brightness, 0, 255
        ).astype(np.uint8)

def _gradient_bg(W, H, top, mid, bottom):
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    mid_y = H // 2
    for y in range(H):
        if y < mid_y:
            p = y / mid_y
            arr[y, :] = tuple(int(top[i] + (mid[i] - top[i]) * p) for i in range(3))
        else:
            p = (y - mid_y) / max(1, H - mid_y)
            arr[y, :] = tuple(int(mid[i] + (bottom[i] - mid[i]) * p) for i in range(3))
    return arr

class _Particles:
    def __init__(self, n, W, H, seed=42, speed=0.3, size_range=(150, 320)):
        random.seed(seed)
        self.W, self.H = W, H
        self.ps = []
        for _ in range(n):
            self.ps.append({
                'x': random.uniform(-80, W + 80),
                'y': random.uniform(-80, H + 80),
                'vx': random.uniform(-speed, speed),
                'vy': random.uniform(-speed * 0.3, speed * 0.3),
                'size': random.randint(size_range[0], size_range[1]),
                'phase': random.uniform(0, math.pi * 2),
                'ci': random.randint(0, 99),
            })
    def update(self):
        for p in self.ps:
            p['x'] += p['vx']
            p['y'] += p['vy']
            if p['x'] < -250: p['x'] = self.W + 200
            if p['x'] > self.W + 250: p['x'] = -200
            if p['y'] < -250: p['y'] = self.H + 200
            if p['y'] > self.H + 250: p['y'] = -200

_bw_v5 = None

def draw_bokeh_v5(img, draw, W, H, t, bi, rms, band_data):
    """V5旧版: 紫粉渐变 + bokeh粒子"""
    global _bw_v5
    if _bw_v5 is None:
        _bw_v5 = _Particles(12, W, H, seed=100, speed=0.3, size_range=(150, 320))
    _bw_v5.update()
    arr = _gradient_bg(W, H, (65, 20, 80), (40, 15, 60), (75, 30, 50))
    colors = [(200, 100, 180), (180, 80, 160), (220, 130, 200)]
    for p in _bw_v5.ps:
        breath = 0.5 + 0.5 * math.sin(t * 1.2 + p['phase'])
        energy = breath * (0.4 + 0.3 * rms + 0.2 * bi)
        r = int(p['size'] * energy * 0.6)
        if r < 40: continue
        c = colors[p['ci'] % len(colors)]
        _add_glow(arr, int(p['x']), int(p['y']), r, c, brightness=energy * 0.6)
    if bi > 0.3:
        _add_glow(arr, W // 2, H // 2, int(200 * bi), (180, 100, 160), brightness=0.2 * bi)
    return Image.fromarray(arr)


def draw_solid_black(img, draw, W, H, t, bi, rms, band_data):
    """纯黑背景，无律动线，让歌词完全突出"""
    return Image.new('RGB', (W, H), (8, 6, 12))


# ============================================================
BG_TYPES = {
    "solid": draw_solid_black,
    "bokeh_v5": draw_bokeh_v5,
    "bokeh_warm": draw_bokeh_warm,
    "bokeh_sweet": draw_bokeh_sweet,
    "starfield": draw_starfield,
    "ink_wash": draw_ink_wash,
    "neon_pulse": draw_neon_pulse,
    "hiphop_glitch": draw_hiphop_glitch,
    "jazz_smoke": draw_jazz_smoke,
    "rock_fire": draw_rock_fire,
}

GENRE_TO_BG = {
    "抒情": "bokeh_warm", "情歌": "bokeh_warm", "ballad": "bokeh_warm",
    "甜美": "bokeh_sweet", "爱情": "bokeh_sweet", "sweet": "bokeh_sweet",
    "民谣": "starfield", "清新": "starfield", "folk": "starfield",
    "古风": "ink_wash", "国风": "ink_wash", "chinese": "ink_wash",
    "电子": "neon_pulse", "舞曲": "neon_pulse", "edm": "neon_pulse", "dance": "neon_pulse",
    "说唱": "hiphop_glitch", "嘻哈": "hiphop_glitch", "hiphop": "hiphop_glitch", "rap": "hiphop_glitch",
    "爵士": "jazz_smoke", "r&b": "jazz_smoke", "jazz": "jazz_smoke", "soul": "jazz_smoke",
    "摇滚": "rock_fire", "朋克": "rock_fire", "rock": "rock_fire",
    "流行": "bokeh_warm", "pop": "bokeh_warm",
}

def draw_dynamic_bg(img, draw, W, H, t, bi, rms, band_data, bg_type="bokeh_warm"):
    func = BG_TYPES.get(bg_type, draw_bokeh_warm)
    return func(img, draw, W, H, t, bi, rms, band_data)

def recommend_bg(genre_tag: str) -> str:
    for key, bg in GENRE_TO_BG.items():
        if key in genre_tag.lower().strip():
            return bg
    return "bokeh_warm"
