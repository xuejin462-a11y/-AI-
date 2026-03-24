#!/usr/bin/env python3
"""
推歌视频构建器：
1. 调用 gen_video_v2.py 生成歌词正片（hook overlay 已嵌入）
2. ffmpeg 叠加 TTS 旁白到 0-3s，做 audio ducking
"""

import os, subprocess, tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

GEN_VIDEO_SCRIPT = Path.home() / "Documents/claude/自动化/daily-video/gen_video_v2.py"

EMOTION_TO_STYLE = {
    "伤感/失恋":     {"STYLE_NAME": "dark",    "BG_TYPE": "sinian"},
    "思念/暗恋":     {"STYLE_NAME": "classic",  "BG_TYPE": "sinian"},
    "治愈/释怀":     {"STYLE_NAME": "youth",    "BG_TYPE": "zhiyu"},
    "愤怒/执念":     {"STYLE_NAME": "cool",     "BG_TYPE": "fennu"},
    "甜蜜/浪漫":     {"STYLE_NAME": "sweet",    "BG_TYPE": "sweet"},
    "孤独/深夜":     {"STYLE_NAME": "dark",     "BG_TYPE": "sinian"},
    "情感丰富/古风": {"STYLE_NAME": "classic",  "BG_TYPE": "guqin"},
}

def build_video(
    song_name: str,
    artist: str,
    audio_path: str,
    lyrics_raw: str,
    emotion: str,
    hook_text: str,
    tts_wav: str,
    output_path: str,
) -> str:
    style_cfg = EMOTION_TO_STYLE.get(emotion, {"STYLE_NAME": "classic", "BG_TYPE": "sinian"})

    raw_video = tempfile.mktemp(suffix=".mp4")
    env = os.environ.copy()
    env.update({
        "SONG_NAME": song_name,
        "ARTIST_NAME": artist,
        "AUDIO_PATH": audio_path,
        "LYRICS_RAW": lyrics_raw,
        "OUTPUT_PATH": raw_video,
        "VIDEO_DURATION": "90",
        "STYLE_NAME": style_cfg["STYLE_NAME"],
        "BG_TYPE": style_cfg["BG_TYPE"],
        "HOOK_OVERLAY_TEXT": hook_text,
        "HOOK_OVERLAY_DURATION": "4.0",
        "USE_GEMINI": "true",
        "LANDSCAPE": "false",
    })

    print(f"生成歌词视频: {song_name}")
    result = subprocess.run(
        ["python3", str(GEN_VIDEO_SCRIPT)],
        env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"gen_video_v2.py 失败:\n{result.stderr[-2000:]}")
    print("歌词视频生成完成")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", tts_wav,
        "-filter_complex",
        (
            "[0:a]volume=0:enable='between(t,0,1.5)',"
            "volume=0.2:enable='between(t,1.5,3)',"
            "volume=1.0:enable='gt(t,3)'[bgm];"
            "[1:a]atrim=0:3,asetpts=PTS-STARTPTS[narr];"
            "[bgm][narr]amix=inputs=2:duration=first[aout]"
        ),
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]

    print(f"混音合并中...")
    r2 = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if r2.returncode != 0:
        raise RuntimeError(f"ffmpeg 混音失败:\n{r2.stderr[-1000:]}")

    Path(raw_video).unlink(missing_ok=True)
    print(f"最终视频: {output_path}")
    return output_path

if __name__ == "__main__":
    print("video_builder.py 已加载，使用 tuige_main.py 进行完整测试")
