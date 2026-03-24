#!/usr/bin/env python3
"""视频风格配置 — 甜美/暗黑/酷飒/青春/经典"""

# 每种风格定义：
#   bg_base: 背景基础色 (R,G,B)
#   bg_gradient: 背景渐变加成系数 (R,G,B) — 从上到下叠加
#   bar_colors: 频谱条颜色梯度 [低频, 中低, 中高, 高频] — 每个是(R,G,B)
#   bar_highlight: 频谱条高光倍率
#   pulse_color: 鼓点脉冲颜色
#   particle_colors: 粒子颜色组 [(R,G,B), ...]
#   particle_type: 粒子类型 "dot" / "heart" / "star" / "spark" / "bubble"
#   lyric_bottom_color: 底层大字颜色 (R,G,B)
#   lyric_bottom_alpha: 底层大字透明度 0~1
#   lyric_top_color: 顶层小字颜色 (R,G,B)
#   lyric_flash_colors: 鼓点闪烁颜色组
#   hook_colors: Hook文字颜色 [主色, 歌名色, 强调色]
#   progress_start: 进度条起始色
#   progress_end: 进度条结束色
#   listen_color: "听完再划走"颜色
#   small_bar_alpha: 顶底小频谱亮度系数

STYLES = {
    "classic": {
        "name": "经典",
        "bg_base": (5, 8, 20),
        "bg_gradient": (4, 8, 18),
        "bar_colors": [
            (30, 50, 200),    # 低频：深蓝
            (40, 140, 255),   # 中低：亮蓝
            (100, 60, 220),   # 中高：紫
            (60, 200, 255),   # 高频：青
        ],
        "bar_highlight": 1.3,
        "pulse_color": (40, 60, 200),
        "particle_colors": [(40, 100, 255), (60, 150, 255), (80, 200, 255)],
        "particle_type": "dot",
        "lyric_bottom_color": (255, 30, 60),
        "lyric_bottom_alpha": 0.50,
        "lyric_top_color": (255, 255, 255),
        "lyric_flash_colors": [(255, 255, 80), (255, 220, 50), (80, 220, 255), (125, 249, 255)],
        "hook_colors": [(255, 252, 248), (255, 220, 50), (255, 55, 55)],
        "progress_start": (60, 100, 255),
        "progress_end": (255, 55, 55),
        "listen_color": (255, 252, 248),
        "small_bar_alpha": 0.4,
    },

    "sweet": {
        "name": "甜美",
        "bg_base": (20, 6, 15),
        "bg_gradient": (12, 4, 10),
        "bar_colors": [
            (200, 80, 140),   # 低频：玫红
            (255, 130, 180),  # 中低：粉
            (220, 120, 255),  # 中高：浅紫
            (255, 180, 220),  # 高频：浅粉
        ],
        "bar_highlight": 1.25,
        "pulse_color": (200, 80, 140),
        "particle_colors": [(255, 150, 200), (255, 180, 220), (220, 140, 255), (255, 200, 230)],
        "particle_type": "heart",
        "lyric_bottom_color": (255, 80, 150),
        "lyric_bottom_alpha": 0.45,
        "lyric_top_color": (255, 245, 250),
        "lyric_flash_colors": [(255, 200, 230), (255, 150, 200), (220, 160, 255), (255, 180, 210)],
        "hook_colors": [(255, 240, 248), (255, 180, 210), (255, 100, 160)],
        "progress_start": (255, 130, 180),
        "progress_end": (220, 100, 255),
        "listen_color": (255, 230, 245),
        "small_bar_alpha": 0.35,
    },

    "dark": {
        "name": "暗黑",
        "bg_base": (5, 2, 5),
        "bg_gradient": (5, 0, 3),
        "bar_colors": [
            (150, 10, 20),    # 低频：暗红
            (200, 30, 40),    # 中低：深红
            (120, 20, 100),   # 中高：暗紫
            (180, 40, 60),    # 高频：血红
        ],
        "bar_highlight": 1.4,
        "pulse_color": (150, 20, 20),
        "particle_colors": [(200, 50, 30), (255, 80, 20), (180, 30, 60), (150, 40, 80)],
        "particle_type": "spark",
        "lyric_bottom_color": (200, 15, 30),
        "lyric_bottom_alpha": 0.55,
        "lyric_top_color": (255, 240, 235),
        "lyric_flash_colors": [(255, 60, 40), (200, 30, 60), (255, 100, 20), (180, 20, 80)],
        "hook_colors": [(240, 230, 225), (200, 160, 50), (255, 40, 40)],
        "progress_start": (150, 20, 30),
        "progress_end": (255, 50, 20),
        "listen_color": (220, 210, 205),
        "small_bar_alpha": 0.3,
    },

    "cool": {
        "name": "酷飒",
        "bg_base": (4, 8, 18),
        "bg_gradient": (2, 6, 14),
        "bar_colors": [
            (20, 80, 180),    # 低频：钢蓝
            (60, 160, 255),   # 中低：冰蓝
            (150, 200, 255),  # 中高：银蓝
            (200, 220, 255),  # 高频：银白
        ],
        "bar_highlight": 1.35,
        "pulse_color": (60, 120, 220),
        "particle_colors": [(100, 180, 255), (180, 210, 255), (200, 230, 255), (150, 200, 240)],
        "particle_type": "shard",
        "lyric_bottom_color": (50, 120, 255),
        "lyric_bottom_alpha": 0.45,
        "lyric_top_color": (240, 248, 255),
        "lyric_flash_colors": [(125, 249, 255), (180, 220, 255), (100, 200, 255), (200, 240, 255)],
        "hook_colors": [(230, 240, 255), (150, 210, 255), (80, 180, 255)],
        "progress_start": (40, 100, 220),
        "progress_end": (180, 220, 255),
        "listen_color": (220, 235, 255),
        "small_bar_alpha": 0.4,
    },

    "youth": {
        "name": "青春",
        "bg_base": (6, 14, 10),
        "bg_gradient": (4, 10, 6),
        "bar_colors": [
            (30, 180, 100),   # 低频：翠绿
            (80, 220, 120),   # 中低：明绿
            (200, 230, 50),   # 中高：黄绿
            (255, 220, 60),   # 高频：明黄
        ],
        "bar_highlight": 1.3,
        "pulse_color": (60, 180, 100),
        "particle_colors": [(100, 230, 150), (200, 255, 100), (255, 240, 80), (150, 255, 180)],
        "particle_type": "bubble",
        "lyric_bottom_color": (60, 200, 100),
        "lyric_bottom_alpha": 0.45,
        "lyric_top_color": (255, 255, 245),
        "lyric_flash_colors": [(255, 255, 80), (100, 255, 150), (200, 255, 100), (80, 230, 180)],
        "hook_colors": [(250, 255, 240), (220, 255, 80), (80, 230, 130)],
        "progress_start": (50, 200, 120),
        "progress_end": (255, 230, 50),
        "listen_color": (240, 255, 240),
        "small_bar_alpha": 0.35,
    },
}


def get_style(name: str) -> dict:
    """获取风格配置，不存在时返回经典风格"""
    return STYLES.get(name, STYLES["classic"])


def bar_color_for_style(style: dict, band_idx: int, n_bands: int, intensity: float):
    """根据风格计算频谱条颜色"""
    colors = style["bar_colors"]
    t = band_idx / max(1, n_bands - 1)

    # 4段插值
    if t < 0.333:
        p = t / 0.333
        c0, c1 = colors[0], colors[1]
    elif t < 0.666:
        p = (t - 0.333) / 0.333
        c0, c1 = colors[1], colors[2]
    else:
        p = (t - 0.666) / 0.334
        c0, c1 = colors[2], colors[3]

    r = int(c0[0] + (c1[0] - c0[0]) * p)
    g = int(c0[1] + (c1[1] - c0[1]) * p)
    b = int(c0[2] + (c1[2] - c0[2]) * p)

    bright = 0.3 + 0.7 * intensity
    return (int(r * bright), int(g * bright), int(b * bright))


def draw_particle(draw, x, y, size, color, ptype):
    """根据类型绘制粒子"""
    if ptype == "heart":
        # 简化心形：两个圆+一个三角
        r = max(1, size)
        draw.ellipse([x - r, y - r, x, y + r // 2], fill=color)
        draw.ellipse([x, y - r, x + r, y + r // 2], fill=color)
        draw.polygon([(x - r, y), (x + r, y), (x, y + r + r // 2)], fill=color)

    elif ptype == "star":
        # 四角星
        r = max(1, size)
        draw.line([(x - r, y), (x + r, y)], fill=color, width=1)
        draw.line([(x, y - r), (x, y + r)], fill=color, width=1)
        r2 = r * 7 // 10
        draw.line([(x - r2, y - r2), (x + r2, y + r2)], fill=color, width=1)
        draw.line([(x + r2, y - r2), (x - r2, y + r2)], fill=color, width=1)

    elif ptype == "spark":
        # 火花：短线段
        r = max(1, size)
        import random
        angle = random.uniform(0, 3.14159 * 2)
        import math
        dx = int(r * math.cos(angle))
        dy = int(r * math.sin(angle))
        draw.line([(x, y), (x + dx, y + dy)], fill=color, width=1)

    elif ptype == "shard":
        # 碎片：小三角
        r = max(1, size)
        draw.polygon([(x, y - r), (x - r, y + r), (x + r, y + r // 2)], fill=color)

    elif ptype == "bubble":
        # 气泡：空心圆
        r = max(2, size)
        draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=1)

    else:  # dot
        r = max(1, size)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
