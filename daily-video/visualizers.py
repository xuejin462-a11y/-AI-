#!/usr/bin/env python3
"""6种律动器类型 — bars/circle/wave/ripple/stars/mountain"""

import math, random
from PIL import ImageDraw


def draw_bars(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style):
    """经典频谱条 — 中心对称"""
    bar_area_top = int(H * 0.28)
    bar_area_bottom = int(H * 0.72)
    bar_area_h = bar_area_bottom - bar_area_top
    bar_gap = 6
    bar_w = (W // 2 - bar_gap * (n_bands + 1)) // n_bands
    if bar_w < 8: bar_w = 8
    center_y = (bar_area_top + bar_area_bottom) // 2

    for i in range(n_bands):
        val = min(1.0, band_data[i] + bi * 0.25)
        bar_h = int(val * bar_area_h * 0.45)
        if bar_h < 4: bar_h = 4
        color = bar_color_fn(i, val)
        bx_right = W // 2 + i * (bar_w + bar_gap) + bar_gap
        bx_left = W // 2 - (i + 1) * (bar_w + bar_gap)
        for bx in [bx_left, bx_right]:
            top = center_y - bar_h
            bottom = center_y + bar_h
            draw.rectangle([bx, top, bx + bar_w, bottom], fill=color)
            hl = min(3, bar_h // 4)
            hm = style.get("bar_highlight", 1.3)
            hc = tuple(min(255, int(v * hm)) for v in color)
            draw.rectangle([bx, top, bx + bar_w, top + hl], fill=hc)


def draw_circle(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style):
    """环形频谱 — 频谱条围成圆环"""
    cx, cy = W // 2, int(H * 0.48)
    base_r = 120 + int(40 * rms_val)
    n_bars = n_bands * 2  # 双倍条数更密

    for i in range(n_bars):
        idx = i % n_bands
        val = min(1.0, band_data[idx] + bi * 0.2)
        angle = (i / n_bars) * math.pi * 2 - math.pi / 2
        bar_len = int(val * 180) + 10
        color = bar_color_fn(idx, val)

        x1 = cx + int(base_r * math.cos(angle))
        y1 = cy + int(base_r * math.sin(angle))
        x2 = cx + int((base_r + bar_len) * math.cos(angle))
        y2 = cy + int((base_r + bar_len) * math.sin(angle))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=3)

    # 内圈发光
    pulse_r = base_r - 5 + int(15 * bi)
    pc = style.get("pulse_color", (60, 60, 200))
    pa = 0.3 + 0.3 * bi
    pc_dim = tuple(int(c * pa) for c in pc)
    draw.ellipse([cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r],
                 outline=pc_dim, width=2)


def draw_wave(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style, t=0):
    """波形律动 — 平滑正弦波流动"""
    center_y = int(H * 0.48)
    colors = style.get("bar_colors", [(60, 150, 255)])

    for layer in range(3):
        points = []
        amplitude = 80 + int(120 * rms_val) + int(60 * bi)
        freq = 2.0 + layer * 0.7
        phase = t * 2.5 + layer * 1.2

        for x in range(0, W + 10, 4):
            # 混合多个频率的正弦波
            band_idx = min(int(x / W * n_bands), n_bands - 1)
            band_amp = band_data[band_idx] * amplitude

            y = center_y + int(
                band_amp * math.sin(freq * math.pi * x / W + phase) +
                band_amp * 0.3 * math.sin(freq * 2.1 * math.pi * x / W + phase * 1.5)
            )
            points.append((x, y))

        if len(points) >= 2:
            ci = min(layer, len(colors) - 1)
            base_c = colors[ci]
            alpha = 0.7 - layer * 0.15
            c = tuple(int(v * alpha) for v in base_c)
            draw.line(points, fill=c, width=3 - layer)

    # 中线
    mc = tuple(int(v * 0.15) for v in colors[0])
    draw.line([(0, center_y), (W, center_y)], fill=mc, width=1)


def draw_ripple(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style, t=0):
    """水波纹 — 从中心扩散的同心圆"""
    cx, cy = W // 2, int(H * 0.48)
    pc = style.get("pulse_color", (60, 100, 200))
    colors = style.get("bar_colors", [pc])

    # 生成多个波纹（基于时间）
    n_rings = 8
    max_r = 450

    for i in range(n_rings):
        # 每个波纹从中心扩散出去
        phase = (t * 1.5 + i * 0.4) % 3.0  # 3秒一个周期
        r = int(phase / 3.0 * max_r)
        if r < 10: continue

        # 越远越淡
        fade = max(0, 1 - r / max_r)
        # RMS和鼓点影响粗细和亮度
        width = max(1, int(3 * fade * (0.5 + 0.5 * rms_val + 0.3 * bi)))
        brightness = fade * (0.4 + 0.4 * rms_val + 0.3 * bi)

        # 波纹不是完美圆，根据频谱数据扭曲
        n_points = 60
        points = []
        for j in range(n_points + 1):
            angle = j / n_points * math.pi * 2
            band_idx = int(j / n_points * n_bands) % n_bands
            distortion = 1 + band_data[band_idx] * 0.3
            rx = int(r * distortion * math.cos(angle))
            ry = int(r * distortion * math.sin(angle))
            points.append((cx + rx, cy + ry))

        ci = i % len(colors)
        c = tuple(int(v * brightness) for v in colors[ci])
        if len(points) >= 2:
            draw.line(points, fill=c, width=width)


def draw_stars(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style, t=0):
    """星空律动 — 星星随鼓点脉冲，有连线"""
    pc = style.get("particle_colors", [(200, 220, 255)])

    # 固定星星位置（用种子保证帧间一致）
    n_stars = 40
    random.seed(12345)
    star_positions = [(random.randint(50, W - 50), random.randint(int(H * 0.15), int(H * 0.85)))
                      for _ in range(n_stars)]

    # 每颗星根据对应频段数据脉冲
    for i, (sx, sy) in enumerate(star_positions):
        band_idx = i % n_bands
        val = band_data[band_idx]
        pulse = val * 0.6 + bi * 0.4

        # 星星大小
        base_size = 2
        size = base_size + int(pulse * 6)
        brightness = 0.3 + 0.7 * pulse

        ci = i % len(pc)
        c = tuple(int(v * brightness) for v in pc[ci])

        # 画星星（十字+对角线）
        draw.ellipse([sx - size, sy - size, sx + size, sy + size], fill=c)
        if pulse > 0.5:
            # 光芒
            ray = size + int(pulse * 8)
            rc = tuple(int(v * brightness * 0.5) for v in pc[ci])
            draw.line([(sx - ray, sy), (sx + ray, sy)], fill=rc, width=1)
            draw.line([(sx, sy - ray), (sx, sy + ray)], fill=rc, width=1)

    # 连线（距离近的星星之间画淡线）
    connect_dist = 180 + int(80 * rms_val)
    line_c = tuple(int(v * 0.08) for v in pc[0])
    for i in range(n_stars):
        for j in range(i + 1, min(i + 8, n_stars)):
            dx = star_positions[i][0] - star_positions[j][0]
            dy = star_positions[i][1] - star_positions[j][1]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < connect_dist:
                fade = 1 - dist / connect_dist
                lc = tuple(int(v * fade * 0.12) for v in pc[0])
                draw.line([star_positions[i], star_positions[j]], fill=lc, width=1)


def draw_mountain(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style, t=0):
    """山峰律动 — 频谱化为山脉剪影"""
    colors = style.get("bar_colors", [(60, 100, 200)])
    base_y = int(H * 0.58)  # 山脚位置

    for layer in range(3):
        points = [(0, H)]  # 左下角
        amplitude = 200 + int(150 * rms_val) - layer * 40
        n_points = n_bands * 3

        for i in range(n_points + 1):
            x = int(i / n_points * W)
            band_idx = min(int(i / n_points * n_bands), n_bands - 1)
            val = band_data[band_idx] + bi * 0.15

            # 山的轮廓 = 频谱数据 + 正弦波使轮廓平滑
            offset = layer * 1.3 + t * 0.3
            y = base_y + layer * 30 - int(
                val * amplitude * 0.5 +
                amplitude * 0.3 * math.sin(3 * math.pi * i / n_points + offset)
            )
            y = max(int(H * 0.15), min(base_y + layer * 30, y))
            points.append((x, y))

        points.append((W, H))  # 右下角

        ci = min(layer, len(colors) - 1)
        alpha = 0.5 - layer * 0.12
        c = tuple(int(v * alpha) for v in colors[ci])
        if len(points) >= 3:
            draw.polygon(points, fill=c)

    # 山顶高光（鼓点时闪烁）
    if bi > 0.5:
        hc = tuple(int(v * 0.15 * bi) for v in colors[-1])
        draw.rectangle([0, int(H * 0.15), W, int(H * 0.25)], fill=hc)


# 律动器类型映射
VISUALIZER_TYPES = {
    "bars": draw_bars,
    "circle": draw_circle,
    "wave": draw_wave,
    "ripple": draw_ripple,
    "stars": draw_stars,
    "mountain": draw_mountain,
}


def draw_visualizer(draw, W, H, band_data, n_bands, bi, rms_val,
                    bar_color_fn, style, viz_type="bars", t=0):
    """统一入口：根据类型调用对应律动器"""
    func = VISUALIZER_TYPES.get(viz_type, draw_bars)

    # bars类型不需要t参数
    if viz_type == "bars":
        func(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style)
    else:
        func(draw, W, H, band_data, n_bands, bi, rms_val, bar_color_fn, style, t=t)
