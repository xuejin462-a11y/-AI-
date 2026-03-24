#!/usr/bin/env python3
"""抖音实时热搜数据获取 — 免费API，无需key，每3分钟更新"""

import json, urllib.request, os
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trending_cache.json")
API_URL = "https://v.api.aa1.cn/api/douyin-hot/index.php?aa1=hot"


def fetch_trending(use_cache_minutes=30):
    """获取抖音实时热搜，带本地缓存

    Returns:
        {
            "update_time": "2026-03-16 18:28:23",
            "trending": [{"word": "...", "position": 1, "hot_value": 12345}, ...],  # 热搜榜50条
            "rising": [{"word": "..."}, ...],  # 实时上升热点
        }
    """
    # 检查缓存
    if os.path.exists(CACHE_FILE) and use_cache_minutes > 0:
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            cached_time = datetime.strptime(cache["fetch_time"], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - cached_time).total_seconds() < use_cache_minutes * 60:
                print(f"  热搜缓存命中（{cache['fetch_time']}）")
                return cache["data"]
        except Exception:
            pass

    # 调用API
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8").strip()
        # API 可能返回前后空白或多余数据，用 raw_decode 只取第一个 JSON 对象
        decoder = json.JSONDecoder()
        raw, _ = decoder.raw_decode(content)

        data_section = raw.get("data", {})
        word_list = data_section.get("word_list", [])
        trending_list = data_section.get("trending_list", [])
        update_time = data_section.get("active_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        result = {
            "update_time": update_time,
            "trending": [
                {"word": w.get("word", ""), "position": w.get("position", 0),
                 "hot_value": w.get("hot_value", 0)}
                for w in word_list if w.get("word")
            ],
            "rising": [
                {"word": w.get("word", ""), "video_count": w.get("video_count", 0)}
                for w in trending_list if w.get("word")
            ],
        }

        # 写缓存
        with open(CACHE_FILE, "w") as f:
            json.dump({"fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "data": result},
                      f, ensure_ascii=False, indent=2)

        print(f"  热搜获取成功: {len(result['trending'])}条榜单 + {len(result['rising'])}条上升热点")
        return result

    except Exception as e:
        print(f"  热搜获取失败: {e}")
        # 尝试返回过期缓存
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE) as f:
                    cache = json.load(f)
                print(f"  使用过期缓存（{cache['fetch_time']}）")
                return cache["data"]
            except Exception:
                pass
        return None


def match_song_to_trending(song_name, artist_name, lyrics, theme, trending_data):
    """匹配歌曲与热搜话题，返回可关联的热点

    Returns:
        [{"word": "热搜词", "match_reason": "关联理由"}, ...]
    """
    if not trending_data:
        return []

    # 构建歌曲关键词池
    song_keywords = set()
    song_keywords.add(song_name)
    song_keywords.add(artist_name)
    if theme:
        song_keywords.update(theme.replace("，", " ").replace("、", " ").split())

    # 情感/场景关键词（从歌词提取高频意象）
    import re
    emotion_words = {"思念", "失恋", "孤独", "治愈", "释怀", "青春", "毕业", "校园",
                     "深夜", "回忆", "故乡", "春天", "夏天", "秋天", "冬天", "下雨",
                     "分手", "暗恋", "心动", "成长", "打工", "漂泊", "异地", "梦",
                     "爱情", "婚姻", "家庭", "父母", "亲情", "友情", "旅行", "自由"}
    lyric_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', lyrics[:500]))
    song_keywords.update(lyric_words & emotion_words)

    matches = []
    all_topics = trending_data.get("trending", []) + trending_data.get("rising", [])

    for topic in all_topics:
        word = topic.get("word", "")
        # 直接匹配
        for kw in song_keywords:
            if len(kw) >= 2 and kw in word:
                matches.append({"word": word, "match_reason": f"歌曲关键词「{kw}」命中"})
                break
        # 情感场景匹配
        for ew in emotion_words:
            if ew in word and ew in lyrics:
                matches.append({"word": word, "match_reason": f"情感场景「{ew}」关联"})
                break

    # 去重
    seen = set()
    unique = []
    for m in matches:
        if m["word"] not in seen:
            seen.add(m["word"])
            unique.append(m)

    return unique[:5]  # 最多返回5条


def get_trending_tags(trending_data, limit=5):
    """从热搜中提取适合做抖音标签的话题词"""
    if not trending_data:
        return []
    return [t["word"] for t in trending_data.get("trending", [])[:limit]]


# === 命令行测试 ===
if __name__ == "__main__":
    data = fetch_trending(use_cache_minutes=0)  # 强制刷新
    if data:
        print(f"\n更新时间: {data['update_time']}")
        print(f"\n热搜榜 TOP 20:")
        for t in data["trending"][:20]:
            print(f"  #{t['position']:2d} [{t['hot_value']:>10}] {t['word']}")
        print(f"\n实时上升热点:")
        for r in data["rising"]:
            print(f"  - {r['word']}")
