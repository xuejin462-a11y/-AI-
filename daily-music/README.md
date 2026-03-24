# 每日做歌自动化系统

## 三种歌曲创作模式

---

### 模式一：歌曲二创（cover-sample）

> **触发方式：手动指定**
> **Suno API：** `cover_generate(cover_type="cover")` — 紧跟原曲旋律，换声线/换风格

**适用场景：**
- 指定一首歌，更换音色（换成5位音乐人中某人的声线）
- 改编为 R&B版 / 微醺版 / 倍速版 / 轻电子版 等曲风变体
- 歌词不变，只变风格和声线

**链路：**
```
指定歌曲
    │
    ▼
yt-dlp 下载原曲 → 截取90s副歌段
    │
    ▼
upload_audio() → upload_id
    │
    ▼
cover_generate(cover_type="cover", lyrics="", style=目标风格)
    │
    ▼
wait_for_clips → download_clip → wav
```

**文件夹命名：** `二创-{音乐人}-{歌名}-{风格变体}/`（如 `二创-树离-告白气球-微醺版/`）

**注意：** lyrics 留空，Suno 自动识别原曲歌词。

---

### 模式二：原创歌曲（cover-inspo）

> **触发方式：每日 18:00 自动执行**
> **Suno API：** `inspo_generate()` — 以参考曲为旋律灵感，生成全新歌词

**适用场景：**
- 日常批量产歌，基于热点话题/影视综写故事
- 写全新歌词，参考曲只提供旋律灵感，歌词100%原创
- 匹配5位音乐人的风格和声线

**链路：**
```
每天 18:00 (launchd 自动触发)
    │
    ├─ 数据抓取（fetch_charts.py）
    │   ├─ 6大音乐榜单（Apple/QQ/网易云 热歌+飙升）→ 多榜热歌候选
    │   └─ 4大热点平台（微博/抖音/知乎/B站）→ 话题+影视综素材
    │
    ├─ STEP A：话题推演
    │   基于影视综+热门话题 推演10个故事框架（主题/情绪/人物/场景/歌词角度）
    │
    ├─ STEP A.5：制作简报（人设分配）
    │   6首歌的分配：
    │   ├─ 2首：参考曲来自多榜热歌（BPM 90-130，副歌有爆发）
    │   ├─ 2首：参考曲来自5位音乐人的对标成品曲库
    │   └─ 2首：影视综热点驱动（以当日最火IP为故事灵感）
    │   每首输出：参考曲/音乐人/vocalGender/Style Prompt/故事方向
    │
    ├─ STEP B：歌曲制作（每批3首，共2批）
    │   每首：Phase 0.5→1→1.5→2→3→4→5→6
    │   Phase 4 使用 cover-inspo 模式：
    │   upload_audio(参考曲90s) → inspo_generate(description=style, lyrics=新歌词)
    │
    └─ STEP D：归档
```

**文件夹命名：** `原创-{音乐人}-{歌名}/`（如 `原创-屿川-玻璃心愿/`）

---

### 模式三：金主写歌（inspo_generate 或 custom_generate）

> **触发方式：手动指定**
> **Suno API：** 有参考曲 → `inspo_generate()`；无参考曲 → `custom_generate()`

**适用场景：**
- 为指定金主音乐人定制歌曲
- 先读取 `知识库/音乐创作/金主音乐人服务/{音乐人}.md` 分析其风格
- 按指定创作方向写词

**链路（有参考曲）：**
```
读取金主音乐人知识库
    │
    ▼
确认创作方向（主题/情绪/参考曲）
    │
    ▼
写歌词（同原创模式全套写词规范）
    │
    ▼
upload_audio(参考曲) → inspo_generate(description=style, lyrics=lyrics)
```

**链路（无参考曲）：**
```
读取金主音乐人知识库
    │
    ▼
确认创作方向（主题/情绪）
    │
    ▼
写歌词（同原创模式全套写词规范）
    │
    ▼
custom_generate(lyrics, style, title)
```

**文件夹命名：** `金主-{金主名}-{歌名}/`（如 `金主-朱砂未央-山巅/`）

**当前金主：** 朱砂未央（`知识库/音乐创作/金主音乐人服务/朱砂未央.md`）

---

## 自动化流程详情（模式二）

### 数据架构

```
每天 18:00 (launchd 自动触发)
       │
       ▼
fetch_charts.py
       │
       ├─ 音乐榜单 (6个) ──────────────────────────────────────────┐
       │   Apple Music CN / Global (官方 RSS)                      │
       │   QQ 飙升榜 / 热歌榜 (内部 API)                           │  → multi_chart_hits (多榜命中)
       │   网易云 飙升榜 / 热歌榜 (playlist API)                    │
       │                                                           │
       └─ 热点话题 (4个) ──────────────────────────────────────────┘
           微博话题热榜 (hot_band API)                              │
           抖音热点    (web hot search API，含6品类热榜)             │  → topics + douyin_trending
           知乎热榜    (mobile API)                                 │
           B站影视区   (ranking API rid=11)                        │
               │
               ▼
       today_input.json
               │
               ▼
       daily_music.sh → claude --dangerously-skip-permissions -p
```

### 6首歌分配规则

| 分组 | 数量 | 参考曲来源 | 灵感来源 |
|------|------|-----------|---------|
| 多榜热歌参考 | 2首 | multi_chart_hits (优先多榜命中) | 影视综+热门话题故事框架 |
| 对标成品曲参考 | 2首 | 五位音乐人对标艺人成名曲 | 影视综+热门话题故事框架 |
| 影视综热点驱动 | 2首 | douyin_trending 6品类中的参考 | 当日最火影视IP/CP/文案 |

### 文件结构

```
daily-music/
  fetch_charts.py          数据抓取脚本（榜单 + 热点话题）
  daily_music.sh           总调度脚本（cron 入口，只运行模式二）
  today_input.json         当日数据（每天 18:00 覆盖）
  logs/                    每日执行日志 {date}.log
  README.md                本文件
```

### 输出目录

```
~/Documents/claude/输出文件/歌曲/{date}/
  cover/
    原创-{音乐人}-{歌名}/   ← 每首原创歌曲的完整产出
  original/
    story_frames.md         故事框架（10个）
    production_brief.json   制作简报（6首歌的分配方案）
```

---

## 数据源说明（全部无需 session / cookie / API key）

### 音乐榜单

| 榜单 | 接口类型 | 备注 |
|------|---------|------|
| Apple Music CN | 官方 RSS API | 最稳定，永久免费 |
| Apple Music Global | 官方 RSS API | 英文歌曲来源 |
| QQ 飙升榜 (topid=62) | 内部 API | 只需 Referer |
| QQ 热歌榜 (topid=26) | 内部 API | 只需 Referer |
| 网易云 飙升榜 (id=19723756) | playlist API | 只需 Referer |
| 网易云 热歌榜 (id=3778678) | playlist API | 只需 Referer |

### 热点话题

| 来源 | 接口 | 特点 |
|------|------|------|
| 微博话题热榜 | hot_band API | 有 category 分类，情感/剧集/综艺直接过滤 |
| 抖音热点 | web hot search API | 6品类：热门电视剧/电影/综艺/CP/文案/歌曲 |
| 知乎热榜 | mobile API | 问题标题适合提炼情感主题 |
| B站影视区 | ranking rid=11 | 剧情梗概可做故事框架素材 |

---

## Suno API 模式速查

| 创作模式 | 方法 | task | lyrics |
|---------|------|------|--------|
| 歌曲二创 | `cover_remix()` | `cover` + `is_remix:true` | 留空（原曲词） |
| 原创歌曲 | `inspo_generate()` | `playlist_condition` | 新写歌词 |
| 金主写歌（有参考） | `inspo_generate()` | `playlist_condition` | 新写歌词 |
| 金主写歌（无参考） | `custom_generate()` | — | 新写歌词 |

---

## 手动触发

```bash
# 手动跑模式二全流程
bash ~/Documents/claude/自动化/daily-music/daily_music.sh

# 只跑数据抓取（不触发做歌）
python3 ~/Documents/claude/自动化/daily-music/fetch_charts.py

# 补跑做歌（跳过数据抓取，使用已有 today_input.json）
bash ~/Documents/claude/自动化/daily-music/daily_music.sh 2026-03-19 skip

# 模式一：歌曲二创（手动触发示例）
# 在 Claude 对话中说明：二创 {歌名} {原歌手}，目标风格 {R&B/微醺/倍速}，演唱者 {音乐人}

# 模式三：金主写歌（手动触发示例）
# 在 Claude 对话中说明：为朱砂未央写一首歌，主题 {xxx}，有/无参考曲 {xxx}
```

---

## 选曲规则（模式二 · 参考曲筛选）

**多榜热歌参考（优先）：**
- 评分 = 命中榜数 × 1000 - 平均排名
- 优先 ≥2 个榜单同时命中的歌曲
- 无多榜命中时取各榜 #1

**对标成品曲参考：**
- 从五位音乐人对标艺人的成名曲库中选
- 优先选与当日故事框架情绪最匹配的

**选歌风格硬规则（两类参考曲共用）：**
- 优先：副歌有明显爆发（Verse低→Chorus高），BPM 90-130，有洗脑Hook
- 避免：民谣/慢板叙事（BPM<80）、纯说唱无旋律、古风戏腔、极简编曲

---

## Cron 配置

```
launchd: com.xuejin.dailymusic
时间: 每天 18:00
脚本: /bin/zsh /Users/xuejin/Documents/claude/自动化/daily-music/daily_music.sh
```

查看：`launchctl list | grep xuejin`
