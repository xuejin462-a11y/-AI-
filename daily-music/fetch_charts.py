#!/usr/bin/env python3
"""
每日榜单抓取脚本 — 六大音乐榜单 + 热点平台 + 抖音6品类热榜
运行: python3 fetch_charts.py
输出: ~/Documents/claude/自动化/daily-music/today_input.json
"""

import json, ssl, urllib.request, os, re
from datetime import date
from collections import defaultdict

TODAY = str(date.today())
OUT_PATH = os.path.expanduser("~/Documents/claude/自动化/daily-music/today_input.json")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

def fetch(url, extra_headers=None):
    h = {**HEADERS_BASE, **(extra_headers or {})}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
        return json.loads(r.read())


# ── 1. Apple Music（官方 RSS，免费）─────────────────────────────
def fetch_apple(region_code, label, n=30):
    url = f"https://rss.applemarketingtools.com/api/v2/{region_code}/music/most-played/{n}/songs.json"
    data = fetch(url)
    songs = []
    for i, s in enumerate(data["feed"]["results"], 1):
        songs.append({"rank": i, "title": s["name"], "artist": s["artistName"], "source": label})
    print(f"  [{label}] {len(songs)} 首")
    return songs


# ── 2. QQ音乐（内部 API）────────────────────────────────────────
def fetch_qq(topid, label, n=30):
    url = (f"https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"
           f"?topid={topid}&format=json&inCharset=utf-8&outCharset=utf-8&platform=yqq")
    try:
        data = fetch(url, {"Referer": "https://y.qq.com/"})
        songs = []
        for i, item in enumerate(data.get("songlist", [])[:n], 1):
            d = item.get("data", {})
            title = d.get("songname", "")
            artist = "/".join(s.get("name", "") for s in d.get("singer", []))
            if title:
                songs.append({"rank": i, "title": title, "artist": artist, "source": label})
        print(f"  [{label}] {len(songs)} 首")
        return songs
    except Exception as e:
        print(f"  [{label}] 失败: {e}")
        return []


# ── 3. 网易云音乐（playlist API）────────────────────────────────
def fetch_netease(playlist_id, label, n=30):
    url = f"https://music.163.com/api/playlist/detail?id={playlist_id}"
    try:
        data = fetch(url, {"Referer": "https://music.163.com/"})
        tracks = data.get("result", {}).get("tracks", [])[:n]
        songs = []
        for i, t in enumerate(tracks, 1):
            title = t.get("name", "")
            artist = "/".join(a.get("name", "") for a in t.get("artists", []))
            if title:
                songs.append({"rank": i, "title": title, "artist": artist, "source": label})
        print(f"  [{label}] {len(songs)} 首")
        return songs
    except Exception as e:
        print(f"  [{label}] 失败: {e}")
        return []


# ── 4. 微博话题热榜（含分类，优于综合热搜）────────────────────────
# 情感/剧集/综艺 分类直接可用于写歌灵感
WEIBO_SONG_CATEGORIES = {"情感", "剧集", "综艺", "音乐", "娱乐"}

def fetch_weibo_hot(n=50):
    url = "https://weibo.com/ajax/statuses/hot_band?count=50&category=%E6%83%85%E6%84%9F"
    try:
        data = fetch(url, {"Referer": "https://weibo.com/"})
        bands = data.get("data", {}).get("band_list", [])[:n]
        topics = []
        for b in bands:
            cat = b.get("category", "")
            # 多分类用逗号分隔，取第一个
            primary_cat = cat.split(",")[0].strip() if cat else ""
            topics.append({
                "word":     b.get("word", ""),
                "hot":      b.get("num", 0),
                "category": primary_cat,
                "source":   "微博话题"
            })
        print(f"  [微博话题] {len(topics)} 条")
        return topics
    except Exception as e:
        print(f"  [微博话题] 失败: {e}")
        return []


# ── 5. 抖音热点 ──────────────────────────────────────────────────
def fetch_douyin_hot(n=50):
    url = "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383"
    try:
        data = fetch(url, {"Referer": "https://www.douyin.com/"})
        items = data.get("data", {}).get("word_list", [])[:n]
        topics = []
        for item in items:
            topics.append({
                "word":   item.get("word", ""),
                "hot":    item.get("hot_value", 0),
                "label":  item.get("label", 0),   # 5=娱乐 9=生活兴趣
                "source": "抖音热点"
            })
        print(f"  [抖音热点] {len(topics)} 条")
        return topics
    except Exception as e:
        print(f"  [抖音热点] 失败: {e}")
        return []


# ── 6. 知乎热榜 ──────────────────────────────────────────────────
def fetch_zhihu_hot(n=30):
    url = "https://api.zhihu.com/topstory/hot-list?limit=30&reverse_order=0"
    try:
        data = fetch(url, {
            "User-Agent": "osee2unifiedRelease/4.4.0 osee2unifiedReleaseVersion/4.4.0 Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
        })
        items = data.get("data", [])[:n]
        topics = []
        for item in items:
            title   = item.get("target", {}).get("title", item.get("brief", ""))
            hot_str = item.get("detail_text", "")
            topics.append({
                "word":   title,
                "hot":    hot_str,
                "source": "知乎热榜"
            })
        print(f"  [知乎热榜] {len(topics)} 条")
        return topics
    except Exception as e:
        print(f"  [知乎热榜] 失败: {e}")
        return []


# ── 7. B站热门短剧/影视（情节话题适合原创歌曲）────────────────────
# rid=11 番剧/影视区；用标题关键词提取情感向话题
def fetch_bilibili_drama(n=20):
    url = "https://api.bilibili.com/x/web-interface/ranking?rid=11&day=3&arc_type=0"
    try:
        data = fetch(url, {"Referer": "https://www.bilibili.com/", "Cookie": "buvid3=test123"})
        items = data.get("data", {}).get("list", [])[:n]
        topics = []
        for v in items:
            title = v.get("title", "")
            # 提取书名号内容作为话题词
            inner = re.findall(r"《(.+?)》", title)
            word = inner[0] if inner else title[:20]
            topics.append({
                "word":     word,
                "hot":      v.get("play", 0),
                "category": "剧集",
                "source":   "B站影视"
            })
        print(f"  [B站影视] {len(topics)} 条")
        return topics
    except Exception as e:
        print(f"  [B站影视] 失败: {e}")
        return []


# ── 7.5 抖音6品类热榜（最高优先级热点源）──────────────────────────
# 品类：热门CP、热门电视剧、热门电影、热门综艺、热门文案句子、热门歌曲
# 数据源：豆瓣(影视/综艺) + 抖音热搜(CP/文案) + 微博(补充)
# 用于模式零：1-5首影视/热点驱动歌曲

import urllib.parse

def fetch_douban(content_type, tag, label, n=20):
    """豆瓣热门内容 (type=tv/movie, tag=热门/综艺)"""
    url = "https://movie.douban.com/j/search_subjects?" + urllib.parse.urlencode({
        "type": content_type, "tag": tag, "page_limit": n, "page_start": 0
    })
    try:
        data = fetch(url, {"Referer": "https://movie.douban.com/"})
        subjects = data.get("subjects", [])
        result = []
        for i, s in enumerate(subjects, 1):
            result.append({
                "rank": i,
                "word": s.get("title", ""),
                "rate": s.get("rate", ""),
                "hot": n - i,  # 按排名作为热度
                "category": label,
                "source": "豆瓣"
            })
        print(f"  [{label}] {len(result)} 条")
        return result
    except Exception as e:
        print(f"  [{label}] 豆瓣获取失败: {e}")
        return []


def fetch_trending_categories(all_topics):
    """
    汇总6品类热榜。
    - 热门电视剧/电影/综艺: 豆瓣API（稳定可靠）
    - 热门CP/文案: 抖音+微博热搜关键词匹配
    - 热门歌曲: 从音乐榜单汇总
    all_topics: 已抓取的全量热搜话题(微博+抖音+知乎+B站)
    """
    result = {}

    # 1. 豆瓣：热门电视剧、电影、综艺
    print("  [豆瓣数据]")
    result["热门电视剧"] = fetch_douban("tv", "热门", "热门电视剧", 20)
    result["热门电影"]   = fetch_douban("movie", "热门", "热门电影", 20)
    result["热门综艺"]   = fetch_douban("tv", "综艺", "热门综艺", 20)

    # 2. 从热搜中提取热门CP（关键词匹配）
    cp_keywords = ["CP", "cp", "嗑", "甜", "组合", "磕", "官宣", "合体",
                   "同框", "互动", "恋情", "牵手", "告白", "亲密"]
    cp_list = []
    seen_cp = set()
    for t in all_topics:
        word = t.get("word", "")
        if word in seen_cp:
            continue
        if any(kw in word for kw in cp_keywords):
            cp_list.append({**t, "category": "热门CP"})
            seen_cp.add(word)
    def _hot_val(x):
        h = x.get("hot", 0)
        return int(h) if isinstance(h, (int, float)) else 0
    result["热门CP"] = sorted(cp_list, key=lambda x: -_hot_val(x))[:20]
    print(f"  [热门CP] {len(result['热门CP'])} 条")

    # 3. 热门文案（短句 + 非新闻 + 有情感色彩）
    exclude_words = ["政策", "GDP", "官方", "通报", "声明", "两会", "建议",
                     "国务院", "央视", "新闻", "选举", "降准"]
    text_list = []
    seen_text = set()
    for t in all_topics:
        word = t.get("word", "")
        if word in seen_text or len(word) > 20 or len(word) < 3:
            continue
        if any(ex in word for ex in exclude_words):
            continue
        # 文案特征：短小、有情感色彩、非时政
        text_list.append({**t, "category": "热门文案"})
        seen_text.add(word)
    # 按热度排序，取最热的短句作为文案
    result["热门文案"] = sorted(text_list, key=lambda x: -_hot_val(x))[:20]
    print(f"  [热门文案] {len(result['热门文案'])} 条")

    # 4. 热门歌曲（从热搜中提取音乐相关 + 后续会从音乐榜单补充）
    music_keywords = ["歌", "曲", "BGM", "翻唱", "神曲", "旋律", "MV",
                      "唱", "music", "remix", "live"]
    music_list = []
    seen_music = set()
    for t in all_topics:
        word = t.get("word", "")
        if word in seen_music:
            continue
        if any(kw in word.lower() for kw in music_keywords):
            music_list.append({**t, "category": "热门歌曲"})
            seen_music.add(word)
    result["热门歌曲"] = sorted(music_list, key=lambda x: -_hot_val(x))[:20]
    print(f"  [热门歌曲] {len(result['热门歌曲'])} 条")

    return result


# ── 8. 热点话题筛选 ──────────────────────────────────────────────
# 优先级：① 微博情感/剧集分类  ② 抖音娱乐/生活(label 5/9)  ③ 知乎情感类  ④ B站影视
SONG_CATEGORIES = {"情感", "剧集", "综艺", "音乐", "娱乐"}
SONG_KEYWORDS   = [
    "爱情", "分手", "失恋", "暗恋", "告白", "想你", "思念", "孤独",
    "青春", "成长", "毕业", "离开", "回忆", "放下", "治愈", "emo",
    "崩溃", "迷茫", "心动", "喜欢", "陪伴", "失眠", "深夜", "凌晨",
    "不完美", "内耗", "自由", "纯真", "爱", "情",
]
EXCLUDE_KEYWORDS = ["政策", "GDP", "两会", "降准", "时政", "选举", "战争", "疫情", "打疫苗"]

def filter_song_topics(all_topics: list, top_n: int = 5) -> list:
    scored = []
    for t in all_topics:
        word = t["word"]
        cat  = t.get("category", "")
        label = t.get("label", -1)

        # 排除明显不适合
        if any(ex in word for ex in EXCLUDE_KEYWORDS):
            continue

        score = 0
        # 分类加分
        if cat in SONG_CATEGORIES:
            score += 3
        # 抖音娱乐/生活 label
        if label in (5, 9):
            score += 2
        # 关键词加分
        score += sum(1 for kw in SONG_KEYWORDS if kw in word)

        if score > 0:
            scored.append({**t, "match_score": score})

    scored.sort(key=lambda x: -x["match_score"])
    return scored[:top_n]


# ── 8. 多榜命中分析 ──────────────────────────────────────────────
def find_hits(all_charts: dict) -> list:
    hit_map = defaultdict(dict)
    for source, songs in all_charts.items():
        for s in songs:
            key = (s["title"].lower().strip(), s["artist"].lower().strip())
            hit_map[key][source] = {"rank": s["rank"], "title": s["title"], "artist": s["artist"]}

    candidates = []
    for (title_key, artist_key), source_data in hit_map.items():
        # 取原始大小写
        title  = list(source_data.values())[0]["title"]
        artist = list(source_data.values())[0]["artist"]
        ranks  = {src: v["rank"] for src, v in source_data.items()}
        avg    = sum(ranks.values()) / len(ranks)
        candidates.append({
            "title":       title,
            "artist":      artist,
            "chart_count": len(ranks),
            "charts":      ranks,
            "avg_rank":    round(avg, 1),
            "score":       len(ranks) * 1000 - avg   # 命中榜数优先，同分看平均排名
        })

    candidates.sort(key=lambda x: -x["score"])
    return candidates


# ── 主流程 ───────────────────────────────────────────────────────
def main():
    print(f"\n=== 每日榜单抓取 {TODAY} 18:00 ===\n")

    all_charts = {}

    print("[Apple Music]")
    try: all_charts["apple_cn"]     = fetch_apple("cn", "Apple Music CN", 30)
    except Exception as e: print(f"  Apple CN 失败: {e}")
    try: all_charts["apple_global"] = fetch_apple("us", "Apple Music Global", 30)
    except Exception as e: print(f"  Apple Global 失败: {e}")

    print("[QQ音乐]")
    qq_rise = fetch_qq(62, "QQ飙升榜", 30)
    if qq_rise: all_charts["qq_rise"] = qq_rise
    qq_hot  = fetch_qq(26, "QQ热歌榜", 30)
    if qq_hot:  all_charts["qq_hot"] = qq_hot

    print("[网易云]")
    ne_rise = fetch_netease(19723756, "网易云飙升榜", 30)
    if ne_rise: all_charts["ne_rise"] = ne_rise
    ne_hot  = fetch_netease(3778678,  "网易云热歌榜", 30)
    if ne_hot:  all_charts["ne_hot"] = ne_hot

    # ── 热点话题抓取 ────────────────────────────────────────────
    print("\n[热点话题]")
    all_topics = []
    all_topics += fetch_weibo_hot()
    all_topics += fetch_douyin_hot()
    all_topics += fetch_zhihu_hot()
    all_topics += fetch_bilibili_drama()

    # ── 6品类热榜（最高优先级）────────────────────────────────────
    print("\n[6品类热榜 — 模式零数据源]")
    douyin_categories = fetch_trending_categories(all_topics)

    song_topics = filter_song_topics(all_topics, top_n=5)
    print(f"\n[今日话题候选（适合写歌）]")
    for i, t in enumerate(song_topics, 1):
        print(f"  {i}. [{t['source']}] [{t.get('category','')}] {t['word']}")

    # 多榜命中分析
    all_hits = find_hits(all_charts)
    multi    = [h for h in all_hits if h["chart_count"] >= 2]
    single   = [h for h in all_hits if h["chart_count"] == 1]

    print(f"\n[选曲结果]")
    print(f"  多榜命中（≥2榜）: {len(multi)} 首")
    for h in multi[:5]:
        srcs = " + ".join(h["charts"].keys())
        print(f"    ★ 《{h['title']}》- {h['artist']}  [{srcs}]  avg rank {h['avg_rank']}")

    if not multi:
        print("  无多榜命中，将使用各榜 #1 作为候选")

    # 取 Top5 候选：优先多榜命中，不足则用单榜补齐
    top5 = (multi + single)[:5]

    print(f"\n[今日 Top5 Cover 候选]")
    for i, h in enumerate(top5, 1):
        srcs = " + ".join(h["charts"].keys())
        print(f"  {i}. 《{h['title']}》- {h['artist']}  [{srcs}]  avg rank {h['avg_rank']}")

    # ── 热门歌曲补充到音乐榜单 ─────────────────────────────────
    trending_songs = douyin_categories.get("热门歌曲", [])
    if trending_songs:
        dy_chart = []
        for i, s in enumerate(trending_songs, 1):
            dy_chart.append({"rank": i, "title": s["word"], "artist": "", "source": "抖音热歌"})
        all_charts["douyin_hot"] = dy_chart
        print(f"\n[热搜热歌] 补充 {len(dy_chart)} 首到榜单数据")
        # 重新计算多榜命中
        all_hits = find_hits(all_charts)
        multi    = [h for h in all_hits if h["chart_count"] >= 2]
        single   = [h for h in all_hits if h["chart_count"] == 1]
        top5     = (multi + single)[:5]

    # ── 6品类热榜汇总 ────────────────────────────────────────
    print(f"\n[6品类热榜汇总]")
    total_items = sum(len(v) for v in douyin_categories.values())
    print(f"  总计 {total_items} 条 (6品类)")
    for cat, items in douyin_categories.items():
        if items:
            top3 = ", ".join(i["word"] for i in items[:3])
            print(f"  {cat}: {top3}...")

    output = {
        "date":              TODAY,
        "fetch_time":        "18:00",
        "charts_raw":        {k: v for k, v in all_charts.items()},
        "multi_chart_hits":  multi[:10],
        "cover_candidates":  top5,          # 每日 5 首候选
        "topics":            song_topics,   # 适合写歌的热点话题
        "topics_raw":        all_topics,    # 原始全量话题
        "douyin_trending":   douyin_categories,  # 抖音6品类热榜（最高优先级）
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[输出] {OUT_PATH}")


if __name__ == "__main__":
    main()
