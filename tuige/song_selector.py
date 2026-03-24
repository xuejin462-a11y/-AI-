#!/usr/bin/env python3
"""每日选歌：从选题库按情绪轮换选出今日推荐"""

import csv, json, os
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
LIBRARY = BASE / "song_library.csv"
STATE = BASE / "selector_state.json"

EMOTION_CYCLE = [
    "伤感/失恋",
    "思念/暗恋",
    "伤感/失恋",
    "孤独/深夜",
    "思念/暗恋",
    "治愈/释怀",
    "甜蜜/浪漫",
]

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"cycle_index": 0, "last_date": ""}

def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def select_song() -> dict:
    """选出今日歌曲，返回 dict（song_name/artist/emotion/notes/lyrics）"""
    state = load_state()
    today = str(date.today())

    # 防止同一天重复选
    if state.get("last_date") == today and state.get("today_song"):
        return state["today_song"]

    # 按情绪轮换选歌
    cycle_idx = state.get("cycle_index", 0) % len(EMOTION_CYCLE)
    target_emotion = EMOTION_CYCLE[cycle_idx]

    songs = []
    with open(LIBRARY, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["used"].strip().lower() == "false":
                if row["emotion"].strip() == target_emotion:
                    songs.append(row)

    # 如果该情绪已用完，从所有未用歌曲里选
    if not songs:
        with open(LIBRARY, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            songs = [r for r in reader if r["used"].strip().lower() == "false"]

    if not songs:
        raise ValueError("选题库已用完，请补充歌曲")

    chosen = songs[0]

    state["cycle_index"] = (cycle_idx + 1) % len(EMOTION_CYCLE)
    state["last_date"] = today
    state["today_song"] = dict(chosen)
    save_state(state)

    return dict(chosen)

def mark_used(song_name: str):
    """标记歌曲已用"""
    rows = []
    with open(LIBRARY, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    for row in rows:
        if row["song_name"] == song_name:
            row["used"] = "true"

    with open(LIBRARY, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    song = select_song()
    print(f"今日推荐：{song['song_name']} - {song['artist']} ({song['emotion']})")
