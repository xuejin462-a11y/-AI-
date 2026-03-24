#!/usr/bin/env python3
"""评估Melody歌曲的律动适配度 — 全量/增量模式"""

import requests, json, os, sys, tempfile, time, numpy as np

API_URL = "https://melody.panshi-gy.netease.com/api/song/list"
POOL_FILE = os.path.expanduser("~/Documents/claude/自动化/daily-music/rhythm_pool.json")
DONE_FILE = os.path.expanduser("~/Documents/claude/自动化/daily-music/video_done_ids.txt")
THRESHOLD = 85  # 律动评分门槛

def load_pool():
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE) as f:
            return json.load(f)
    return {"evaluated_ids": [], "pool": []}

def save_pool(data):
    with open(POOL_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_done_ids():
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE) as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def fetch_all_songs():
    """拉取全部歌曲"""
    songs, page = [], 1
    while True:
        resp = requests.get(API_URL, params={"page": page}, timeout=15)
        data = resp.json()
        batch = data.get("songs", [])
        songs.extend(batch)
        print(f"  第{page}页: +{len(batch)}首 (累计{len(songs)}/{data.get('total', '?')})")
        if len(batch) < 10:
            break
        page += 1
        time.sleep(0.3)
    return songs

def analyze_rhythm(audio_path):
    import librosa
    y, sr = librosa.load(audio_path, sr=22050, duration=120)
    duration = len(y) / sr

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    if hasattr(tempo, '__len__'):
        tempo = float(tempo[0])
    beat_times = librosa.frames_to_time(beats, sr=sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    beat_strengths = onset_env[beats] if len(beats) > 0 else np.array([0])
    beat_clarity = float(np.mean(beat_strengths))

    if len(beat_times) > 2:
        intervals = np.diff(beat_times)
        rhythm_stability = 1.0 - min(1.0, float(np.std(intervals) / (np.mean(intervals) + 1e-6)))
    else:
        rhythm_stability = 0.0

    rms = librosa.feature.rms(y=y)[0]
    if len(rms) > 10:
        rms_sorted = np.sort(rms)
        top_20 = np.mean(rms_sorted[-len(rms_sorted)//5:])
        bottom_20 = np.mean(rms_sorted[:len(rms_sorted)//5]) + 1e-6
        energy_contrast = min(5.0, float(top_20 / bottom_20))
    else:
        energy_contrast = 1.0

    onsets = librosa.onset.onset_detect(y=y, sr=sr)
    onset_density = len(onsets) / duration if duration > 0 else 0

    S = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = freqs < 250
    bass_energy = float(np.sum(S[bass_mask, :] ** 2))
    total_energy = float(np.sum(S ** 2)) + 1e-6
    bass_ratio = bass_energy / total_energy

    return {
        "bpm": round(tempo, 1),
        "beat_clarity": round(beat_clarity, 2),
        "rhythm_stability": round(rhythm_stability, 3),
        "energy_contrast": round(energy_contrast, 2),
        "onset_density": round(onset_density, 2),
        "bass_ratio": round(bass_ratio, 3),
        "duration": round(duration, 1),
    }

def compute_rhythm_score(m):
    score = 0
    bpm = m["bpm"]
    if 100 <= bpm <= 140:
        score += 40
    elif 80 <= bpm < 100 or 140 < bpm <= 160:
        score += 25
    elif 60 <= bpm < 80 or 160 < bpm <= 180:
        score += 10
    else:
        score += 5
    score += min(20, m["beat_clarity"] * 8)
    score += m["rhythm_stability"] * 15
    score += min(10, (m["energy_contrast"] - 1) * 5)
    od = m["onset_density"]
    if 2.0 <= od <= 5.0:
        score += 10
    elif 1.0 <= od < 2.0 or 5.0 < od <= 7.0:
        score += 6
    else:
        score += 2
    score += min(5, m["bass_ratio"] * 20)
    return round(min(100, score), 1)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    pool_data = load_pool()
    evaluated_ids = set(str(i) for i in pool_data["evaluated_ids"])

    print("=" * 60)
    print(f"Melody歌曲律动评估 (模式: {mode}, 门槛: {THRESHOLD}分)")
    print(f"已评估: {len(evaluated_ids)}首, 池中: {len(pool_data['pool'])}首")
    print("=" * 60)

    # 拉歌曲
    print("\n拉取歌曲列表...")
    all_songs = fetch_all_songs()

    # 筛选未评估的
    new_songs = [s for s in all_songs if str(s["id"]) not in evaluated_ids and s.get("nos_url")]
    print(f"\n总计 {len(all_songs)} 首, 未评估且有音频: {len(new_songs)} 首")

    if not new_songs:
        print("没有新歌曲需要评估")
        _print_summary(pool_data)
        return

    # 逐首分析
    success, fail = 0, 0
    for i, song in enumerate(new_songs):
        sid = song["id"]
        name = song["song_name"]
        print(f"\n[{i+1}/{len(new_songs)}] {name} (id={sid})")

        tmp_path = None
        try:
            resp = requests.get(song["nos_url"], timeout=60)
            if resp.status_code != 200:
                print(f"  下载失败: HTTP {resp.status_code}")
                fail += 1
                pool_data["evaluated_ids"].append(sid)
                continue

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            metrics = analyze_rhythm(tmp_path)
            rhythm_score = compute_rhythm_score(metrics)
            os.unlink(tmp_path)
            tmp_path = None

            pool_data["evaluated_ids"].append(sid)
            success += 1

            print(f"  BPM={metrics['bpm']}  鼓点={metrics['beat_clarity']}  "
                  f"稳定={metrics['rhythm_stability']}  对比={metrics['energy_contrast']}  "
                  f"→ {rhythm_score}分", end="")

            if rhythm_score >= THRESHOLD:
                # 收集歌曲信息入池
                artist_map = {2: "屿川", 3: "晴日西多士", 6: "喱普酱", 7: "S1ent", 8: "树离suliii_", 11: "靓仔阿辉"}
                pool_data["pool"].append({
                    "id": sid,
                    "name": name,
                    "artist_id": song.get("artist_id"),
                    "artist_name": artist_map.get(song.get("artist_id"), f"artist_{song.get('artist_id')}"),
                    "genre": song.get("genre_tag_name", ""),
                    "nos_url": song["nos_url"],
                    "original_lyric": song.get("original_lyric", ""),
                    "rhythm_score": rhythm_score,
                    "metrics": metrics,
                })
                print(" ★ 入池")
            else:
                print(" ✗ 不达标")

            # 每10首保存一次防中断丢失
            if success % 10 == 0:
                save_pool(pool_data)

        except Exception as e:
            print(f"  分析失败: {e}")
            fail += 1
            pool_data["evaluated_ids"].append(sid)
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    save_pool(pool_data)
    print(f"\n本轮: 成功{success}首, 失败{fail}首")
    _print_summary(pool_data)

def _print_summary(pool_data):
    done_ids = get_done_ids()
    pool = pool_data["pool"]
    available = [s for s in pool if str(s["id"]) not in done_ids]

    print("\n" + "=" * 60)
    print(f"歌曲池总览: {len(pool)}首入池, {len(available)}首可用(未做视频)")
    print("=" * 60)

    available.sort(key=lambda x: x["rhythm_score"], reverse=True)
    for i, s in enumerate(available[:20]):
        print(f"  {i+1}. [{s['rhythm_score']:5.1f}] {s['name']} — {s['artist_name']} "
              f"(BPM={s['metrics']['bpm']}, {s['genre']})")

    if len(available) > 20:
        print(f"  ... 还有 {len(available)-20} 首")

if __name__ == "__main__":
    main()
