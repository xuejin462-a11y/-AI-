#!/usr/bin/env python3
"""
推歌账号每日自动化主入口
流程：选歌 → 推荐语 → TTS → 生成视频 → 通知
"""

import os, sys, tempfile, traceback
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

sys.path.insert(0, str(BASE))
from song_selector import select_song, mark_used
from recommendation import gen_recommendation
from tts_volc import synthesize
from video_builder import build_video
from notifier import send_notification

OUTPUT_DIR = Path(os.environ.get(
    "TUIGE_OUTPUT_DIR",
    Path.home() / "Documents/claude/输出文件/视频/tuige"
))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = BASE / f"logs/{date.today()}.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def log(msg: str):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def find_audio(song_name: str, artist: str) -> str | None:
    """在 melody-library 中查找音频文件"""
    melody_lib = Path.home() / "Documents/claude/melody-library/wav"
    if not melody_lib.exists():
        return None
    candidates = (
        list(melody_lib.glob(f"*{song_name}*.wav")) +
        list(melody_lib.glob(f"*{song_name}*.mp3")) +
        list(melody_lib.glob(f"*{artist}*.wav")) +
        list(melody_lib.glob(f"*{artist}*.mp3"))
    )
    return str(candidates[0]) if candidates else None

def run():
    log(f"\n{'='*50}")
    log(f"推歌流水线启动: {date.today()}")

    # 1. 选歌
    song = select_song()
    song_name = song["song_name"]
    artist    = song["artist"]
    emotion   = song["emotion"]
    lyrics    = song.get("lyrics", "")
    log(f"今日歌曲: {song_name} - {artist} ({emotion})")

    # 2. 推荐语
    hook_text = gen_recommendation(song_name, artist, emotion)
    log(f"推荐语: {hook_text}")

    # 3. TTS
    tts_path = tempfile.mktemp(suffix=".wav")
    synthesize(hook_text, tts_path)
    log(f"TTS 旁白已生成")

    # 4. 查找音频
    audio_path = find_audio(song_name, artist)
    if not audio_path:
        log(f"未在 melody-library 找到 [{song_name}] 的音频，跳过视频生成")
        send_notification(song_name, artist, hook_text,
                          f"（音频未找到，请手动下载后运行）\n查找路径: ~/Documents/claude/melody-library/wav/")
        return

    log(f"音频: {audio_path}")

    # 5. 生成视频
    today_str   = str(date.today())
    safe_name   = song_name.replace("/", "_").replace(" ", "_")
    output_path = str(OUTPUT_DIR / f"{today_str}-{safe_name}-{artist}.mp4")

    build_video(
        song_name=song_name,
        artist=artist,
        audio_path=audio_path,
        lyrics_raw=lyrics,
        emotion=emotion,
        hook_text=hook_text,
        tts_wav=tts_path,
        output_path=output_path,
    )

    # 6. 标记已用 + 通知
    mark_used(song_name)
    send_notification(song_name, artist, hook_text, output_path)
    log(f"全流程完成: {output_path}")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        msg = f"推歌流水线失败: {e}\n{traceback.format_exc()}"
        print(msg, file=sys.stderr)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg)
        sys.exit(1)
