#!/usr/bin/env python3
"""Melody全量下载 — 拉取所有歌曲，下载WAV，保存歌词+艺人名"""

import json, os, subprocess, sys, urllib.request, time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 路径 ===
BASE_DIR = os.path.expanduser("~/Documents/claude/自动化/daily-music")
LIBRARY_DIR = os.path.expanduser("~/Documents/claude/melody-library")
WAV_DIR = os.path.join(LIBRARY_DIR, "wav")
LYRICS_DIR = os.path.join(LIBRARY_DIR, "lyrics")
SONGS_JSON = os.path.join(LIBRARY_DIR, "songs.json")
RHYTHM_POOL = os.path.join(BASE_DIR, "rhythm_pool.json")
DOWNLOADED_IDS = os.path.join(BASE_DIR, "melody_downloaded_ids.txt")
VIDEO_DONE_IDS = os.path.join(os.path.expanduser("~/Documents/claude/自动化/daily-video"), "video_done_ids.txt")

API_BASE = "https://melody.panshi-gy.netease.com/api"

def fetch_artists():
    """拉取全部艺人映射"""
    artist_map = {}  # 内部id → artist_name
    page = 1
    while True:
        url = f"{API_BASE}/artist/list?page={page}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        artists = data.get("artists", [])
        if not artists:
            break
        for a in artists:
            artist_map[a["id"]] = a["artist_name"].strip()
        if len(artist_map) >= data.get("total", 0):
            break
        page += 1
    return artist_map

def fetch_all_songs():
    """拉取全部歌曲"""
    all_songs = []
    page = 1
    while True:
        url = f"{API_BASE}/song/list?page={page}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        songs = data.get("songs", [])
        if not songs:
            break
        all_songs.extend(songs)
        total = data.get("total", 0)
        unique = len({s["id"] for s in all_songs})
        if unique >= total:
            break
        page += 1
    # 去重
    return list({s["id"]: s for s in all_songs}.values())

def safe_filename(name):
    """清理文件名"""
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '；']:
        name = name.replace(ch, '_')
    return name.strip()

def download_wav(url, dest):
    """下载WAV文件"""
    try:
        r = subprocess.run(["curl", "-sL", "-o", dest, url], capture_output=True, timeout=180)
        size = os.path.getsize(dest) if os.path.exists(dest) else 0
        if size > 10000:  # > 10KB
            return size
        else:
            if os.path.exists(dest):
                os.remove(dest)
            return 0
    except Exception as e:
        print(f"    下载失败: {e}")
        return 0

def main():
    print(f"{'='*60}")
    print(f"Melody 全量下载 — {date.today().isoformat()}")
    print(f"{'='*60}\n")

    # Step 1: 清空旧数据
    print("Step 1: 清空旧数据...")
    for f in [RHYTHM_POOL, DOWNLOADED_IDS, VIDEO_DONE_IDS]:
        if os.path.exists(f):
            os.remove(f)
            print(f"  已删除: {f}")
    print()

    # Step 2: 创建目录
    os.makedirs(WAV_DIR, exist_ok=True)
    os.makedirs(LYRICS_DIR, exist_ok=True)
    print(f"存储目录: {LIBRARY_DIR}")

    # Step 3: 拉取艺人映射
    print("\nStep 2: 拉取艺人映射...")
    artist_map = fetch_artists()
    print(f"  共 {len(artist_map)} 个艺人:")
    for aid, name in sorted(artist_map.items()):
        print(f"    {aid:3d} → {name}")

    # Step 4: 拉取全部歌曲
    print("\nStep 3: 拉取全部歌曲...")
    all_songs = fetch_all_songs()
    print(f"  共 {len(all_songs)} 首歌曲")

    # Step 5: 准备下载任务
    print(f"\nStep 4: 准备 {len(all_songs)} 首歌曲...")

    # 先准备所有歌曲的元数据和文件路径
    tasks = []
    for song in sorted(all_songs, key=lambda x: x["id"]):
        song_id = song["id"]
        song_name = song.get("song_name", "未命名").strip()
        artist_id = song.get("artist_id")
        artist_name = artist_map.get(artist_id, "未分配") if artist_id else "未分配"
        nos_url = song.get("nos_url", "")
        original_lyric = song.get("original_lyric", "") or ""
        suno_lyric = song.get("suno_lyric", "") or ""

        safe_artist = safe_filename(artist_name)
        safe_song = safe_filename(song_name)
        base_name = f"{safe_artist}-{safe_song}"
        wav_path = os.path.join(WAV_DIR, f"{base_name}.wav")

        # 保存歌词（不耗时，直接做）
        lyric_text = original_lyric.strip() or suno_lyric.strip()
        lyric_path = ""
        if lyric_text:
            lyric_path = os.path.join(LYRICS_DIR, f"{base_name}.txt")
            with open(lyric_path, "w", encoding="utf-8") as f:
                f.write(f"歌名: {song_name}\n")
                f.write(f"艺人: {artist_name}\n")
                f.write(f"━━━━━━━━━━━━━━━━━━━━\n\n")
                f.write(lyric_text)

        tasks.append({
            "song": song, "song_name": song_name, "artist_name": artist_name,
            "artist_id": artist_id, "nos_url": nos_url,
            "original_lyric": original_lyric, "suno_lyric": suno_lyric,
            "wav_path": wav_path, "lyric_path": lyric_path, "base_name": base_name,
        })

    print(f"  歌词已全部保存到 {LYRICS_DIR}")

    # 并行下载WAV（8线程）
    to_download = [t for t in tasks if t["nos_url"] and not (os.path.exists(t["wav_path"]) and os.path.getsize(t["wav_path"]) > 10000)]
    already = len([t for t in tasks if t["nos_url"] and os.path.exists(t["wav_path"]) and os.path.getsize(t["wav_path"]) > 10000])
    no_url = len([t for t in tasks if not t["nos_url"]])

    print(f"\n  已存在: {already}首, 需下载: {len(to_download)}首, 无URL: {no_url}首")
    print(f"  开始并行下载 (8线程)...\n")

    failed = []
    done_count = [0]

    def download_task(task):
        size = download_wav(task["nos_url"], task["wav_path"])
        done_count[0] += 1
        if done_count[0] % 20 == 0:
            print(f"  进度: {done_count[0]}/{len(to_download)}")
        return task["base_name"], size

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_task, t): t for t in to_download}
        for future in as_completed(futures):
            name, size = future.result()
            if size == 0:
                failed.append(name)

    print(f"  下载完成! 失败: {len(failed)}首")

    # 构建记录
    song_records = []
    success = 0
    for t in tasks:
        wav_exists = os.path.exists(t["wav_path"]) and os.path.getsize(t["wav_path"]) > 10000
        song_records.append({
            "id": t["song"]["id"],
            "name": t["song_name"],
            "artist_name": t["artist_name"],
            "artist_id": t["artist_id"],
            "nos_url": t["nos_url"],
            "original_lyric": t["original_lyric"],
            "suno_lyric": t["suno_lyric"],
            "album_cover": t["song"].get("album_cover", ""),
            "voice_gender": t["song"].get("voice_gender", ""),
            "genre_tag": t["song"].get("genre_tag_name", ""),
            "song_id": t["song"].get("song_id"),
            "wav_path": t["wav_path"] if wav_exists else "",
            "lyric_path": t["lyric_path"],
        })
        if wav_exists:
            success += 1

    # Step 6: 保存歌曲库JSON
    print(f"\nStep 5: 保存歌曲库...")
    with open(SONGS_JSON, "w", encoding="utf-8") as f:
        json.dump({"total": len(song_records), "updated": date.today().isoformat(), "songs": song_records}, f, ensure_ascii=False, indent=2)
    print(f"  {SONGS_JSON}")

    # Step 7: 重建rhythm_pool.json（供视频任务使用）
    print("\nStep 6: 重建 rhythm_pool.json...")
    pool_songs = [s for s in song_records if s["nos_url"] and s["original_lyric"].strip()]
    with open(RHYTHM_POOL, "w", encoding="utf-8") as f:
        json.dump({"pool": pool_songs}, f, ensure_ascii=False, indent=2)
    print(f"  {len(pool_songs)} 首有音频+歌词的歌曲入池")

    # 汇总
    print(f"\n{'='*60}")
    print(f"完成! 成功: {success}, 失败: {len(failed)}")
    print(f"WAV存储: {WAV_DIR}")
    print(f"歌词存储: {LYRICS_DIR}")
    print(f"歌曲库: {SONGS_JSON}")
    print(f"视频池: {RHYTHM_POOL} ({len(pool_songs)}首)")
    if failed:
        print(f"\n失败列表:")
        for f_name in failed:
            print(f"  - {f_name}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
