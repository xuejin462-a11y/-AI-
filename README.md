# AI 自动化做歌系统

一套基于 AI + Suno + Gemini + 豆包 的全自动音乐创作和短视频生成工作流。

## 它能帮你做什么？

| 能力 | 说明 | 输出 |
|------|------|------|
| **写一首原创歌** | 给一个灵感/主题，AI 写词 + Suno 生成曲 | `.wav` 歌曲 x2 |
| **二创一首歌** | 给一首现有歌，换声线/换风格 | `.wav` 歌曲 x2 |
| **指定参考曲创作** | 以某首歌为旋律灵感，写全新歌词 | `.wav` 歌曲 x2 |
| **批量日产 6 首歌** | 全自动：抓热榜 → 选参考曲 → 写词 → 生成 | 6 首歌 + 封面图 |
| **生成歌词短视频** | 配上动态背景 + 卡点歌词 + hook 金句 | MP4 竖屏视频 |
| **查 Suno 积分** | 一条命令查余额 | 数值 |

---

## 快速开始

### 第 1 步：克隆仓库

```bash
git clone https://github.com/xuejin462-a11y/-AI-.git
cd -AI-
```

### 第 2 步：配置你的账号

```bash
cp .env.example suno-api/.env
```

打开 `suno-api/.env`，填入你自己的 API 密钥：

```env
# Suno（必须）—— 去 suno.com 注册，浏览器 DevTools 复制 __client cookie
SUNO_COOKIE=__client=你的token
SUNO_EMAIL=你的邮箱
SUNO_PASSWORD=你的密码

# 豆包（封面图用）—— 去火山引擎控制台申请
ARK_API_KEY=你的key

# Gemini（写词+歌词对齐用）—— 去 Google AI Studio 申请
GEMINI_API_KEY=你的key

# 邮件通知（可选）
SMTP_USER=你的发件邮箱
SMTP_PASS=你的SMTP授权码
NOTIFY_TO=你的收件邮箱

# 网络代理（能直连 Google/Suno 的不需要配这个）
# HTTP_PROXY=http://127.0.0.1:7897
# HTTPS_PROXY=http://127.0.0.1:7897
```

### 第 3 步：安装 Python 依赖

```bash
pip3 install librosa google-genai volcengine-python-sdk Pillow
```

### 第 4 步：安装 AI 编程助手

系统的核心创作流程（写词、选曲、故事推演）需要一个 **AI 编程助手** 来驱动。你可以选择任意一个：

| 工具 | 安装方式 | 备注 |
|------|---------|------|
| **Claude Code** | `npm install -g @anthropic-ai/claude-code` | 需要 Anthropic 账号 |
| **OpenAI Codex CLI** | `npm install -g @openai/codex` | 需要 OpenAI 账号 |
| **Cursor** | [cursor.com](https://cursor.com) 下载桌面应用 | 图形界面，对新手最友好 |
| **Windsurf** | [codeium.com](https://codeium.com/windsurf) 下载 | 类似 Cursor |
| **GitHub Copilot CLI** | `gh extension install github/gh-copilot` | 需要 Copilot 订阅 |

> **重要：** 不管用哪个工具，核心用法都一样——用自然语言告诉 AI 你要做什么，它会帮你调用脚本、写歌词、生成音乐。

#### 各工具的启动方式

**Claude Code：**
```bash
cd -AI-          # 进入项目目录
claude           # 启动对话
```

**OpenAI Codex CLI：**
```bash
cd -AI-
codex            # 启动对话
```

**Cursor / Windsurf：**
```
用编辑器打开项目文件夹，在内置的 AI 对话框中输入指令
```

---

## 怎么做歌？

不管你用哪个 AI 工具，**操作方式都一样**：用自然语言描述你想做的事。

### 场景 1：我有一个灵感，想写一首歌

打开你的 AI 助手，直接说：

```
帮我写一首歌，主题是「深夜加班后走在空旷马路上的孤独感」，
风格偏 indie pop，女声，参考《漂洋过海来看你》的旋律感觉
```

AI 会自动：
1. 根据你的灵感写完整歌词
2. 把参考曲上传到 Suno
3. 调用 `suno_client.py inspo` 生成 2 个版本
4. 下载 .wav 到本地

#### 灵感可以怎么给？

你不需要很专业，随便怎么描述都行：

| 给什么 | 示例 |
|--------|------|
| **一个情绪** | 「写一首关于释怀的歌，像雨停之后看到彩虹」 |
| **一个场景** | 「凌晨三点的便利店，一个人吃关东煮」 |
| **一个故事** | 「异地恋，她在北京他在成都，高铁 8 小时」 |
| **一个参考曲** | 「参考《晴天》的旋律走向，但歌词要全新的」 |
| **一种风格** | 「古风 + 电子，像《踏山河》那种感觉」 |
| **一种声线** | 「要男声，温柔偏低音，像陈奕迅的感觉」 |
| **以上任意组合** | 「主题是暗恋，场景是大学图书馆，参考《小幸运》，女声清新一点」 |

> 描述越具体，出来的歌越符合预期。但就算只给一句话也能做。

### 场景 2：我想二创一首现有的歌

```
二创《告白气球》，换成 R&B 慢版，女声演唱
```

这会保留原曲旋律，只换风格和声线。

### 场景 3：我想指定参考曲

```
用《晴天》作为旋律参考，写一首关于夏天毕业的歌，
风格 acoustic pop，男声
```

AI 会下载参考曲，截取副歌段，上传到 Suno，然后以它为灵感生成全新的歌。

### 场景 4：我只要歌词

```
帮我写一首歌词，主题是夏天的暗恋，不用生成音频
```

### 场景 5：做一首歌同时做视频

```
帮我写一首歌，主题是「深夜想你」，做完歌之后帮我生成一个抖音短视频
```

### 场景 6：查 Suno 积分

```
查一下 Suno 还剩多少积分
```

---

## 命令行直接调用（不用 AI 助手也能跑）

以下命令不需要 AI 助手，直接在终端执行：

### 查积分

```bash
python3 suno-api/suno_client.py credits
```

### 二创（保留旋律，换风格/声线）

```bash
python3 suno-api/suno_client.py remix \
  --audio /path/to/原曲.mp3 \
  --style "R&B pop ballad, 85 BPM, smooth female vocals, piano, no aggressive" \
  --title "告白气球-R&B版" \
  --out ~/Desktop/output/
```

### 参考曲创作（旋律灵感 + 新歌词）

```bash
python3 suno-api/suno_client.py inspo \
  --audio /path/to/参考曲.mp3 \
  --description "indie pop, 110 BPM, breathy female vocals" \
  --title "深夜便利店" \
  --lyrics "[Verse 1]
收银台的灯一直亮着
关东煮的雾气模糊了玻璃
[Chorus]
没有人等我回家
但至少这碗汤是热的" \
  --out ~/Desktop/output/
```

### 生成歌词短视频

```bash
SONG_NAME="深夜便利店" \
ARTIST_NAME="树离" \
AUDIO_PATH="/path/to/song.wav" \
LYRICS_RAW="歌词内容..." \
OUTPUT_PATH="output.mp4" \
STYLE_NAME="dark" \
MOOD_TAG="A" \
python3 daily-video/gen_video_v2.py
```

---

## 全自动日产（定时任务）

> **注意：** 全自动模式的 `daily_music.sh` 脚本内部调用了 AI 编程助手的命令行。
> 默认调用 `claude`（Claude Code），如果你用其他工具，需要修改脚本中的 `CLAUDE_BIN` 变量。

| 时间 | 任务 | 做什么 |
|------|------|--------|
| 18:00 | 每日做歌 | 抓 6 大榜单 + 4 大热点 → 自动写词 → 生成 6 首歌 |
| 16:00 | 每日视频 | 从曲库选歌 → 匹配热搜 → 生成 4 个短视频 |
| 20:00 | 歌曲下载 | 从 Melody 平台下载目标音乐人新歌 |

手动触发：

```bash
# 做歌
bash daily-music/daily_music.sh

# 做歌（指定日期，跳过数据抓取）
bash daily-music/daily_music.sh 2026-03-24 skip

# 视频
python3 daily-video/daily_video.py
```

### 适配其他 AI 工具

`daily_music.sh` 中有一个 `run_claude()` 函数，负责调用 AI 助手执行创作任务。默认使用 Claude Code CLI：

```bash
# 在 daily_music.sh 中找到这一行，改成你的工具路径：
CLAUDE_BIN="/path/to/your/ai-cli"

# 例如用 OpenAI Codex CLI：
CLAUDE_BIN="codex"
```

`monthly_suno_research.sh` 中也有类似的 `CLAUDE_CMD` 变量，同样需要修改。

---

## Style Prompt 怎么写？

Suno 的风格描述有严格限制：**不超过 200 个字符**。

**黄金公式：**
```
[曲风] + [BPM] + [情绪] + [乐器x2] + [人声风格] + [制作风格] + [排除项]
```

**示例：**
```
indie pop ballad, 90 BPM, melancholic nostalgic, piano arpeggios, soft synth pads, breathy airy female vocals, studio quality warm reverb, no aggressive vocals
```

**常用组件速查：**

| 类别 | 可选值 |
|------|--------|
| 曲风 | indie pop / R&B / folk / acoustic pop / trap pop / lo-fi / cinematic pop |
| 情绪 | melancholic / heartfelt / cheerful / energetic / easygoing / dreamy |
| 乐器 | piano / acoustic guitar / strings / synth pads / 808 bass / light percussion |
| 人声 | breathy female / warm male tenor / sweet clear female / natural male / rap-singing |
| 排除 | no aggressive / no raspy / no dark moody / no belting / no slow ballad |

---

## 视频模版一览（7 套情绪）

| 标签 | 情绪 | 背景效果 | 适合场景 |
|------|------|---------|---------|
| A | 伤感/失恋 | 深色焦散光 | 分手、遗憾 |
| B | 思念/暗恋 | 星空流动 | 深夜想念、暗恋 |
| C | 治愈/释怀 | 暖色焦散 | 释然、温暖 |
| D | 愤怒/执念 | 霓虹脉冲 | 不甘心、执念 |
| E | 甜蜜/浪漫 | 粉色泡泡 | 恋爱、心动 |
| F | 孤独/深夜 | 烟雾氛围 | 独处、失眠 |
| G | 古风/情感 | 墨迹晕染 | 古风、离别 |

---

## 目录结构

```
.
├── .env.example          # 环境变量模板（复制为 suno-api/.env 后使用）
├── README.md             # 本文件
├── daily-music/          # 每日做歌系统
│   ├── daily_music.sh    # 主控脚本（每天18:00自动跑）
│   ├── fetch_charts.py   # 抓取6大音乐榜单 + 4大热点
│   └── ...
├── daily-video/          # 短视频生成系统
│   ├── gen_video_v2.py   # 核心视频引擎（歌词卡点 + 动态背景）
│   ├── daily_video.py    # 每日视频主控
│   └── ...
├── suno-api/             # Suno API 客户端
│   ├── suno_client.py    # 支持 credits / remix / inspo 子命令
│   └── .env              # ← 你的密钥放这里（已 gitignore）
└── tuige/                # 推歌账号系统
    ├── tuige_main.py     # 选歌 → TTS旁白 → 生成视频 → 通知
    └── song_library.csv  # 推歌选题库
```

---

## 常见问题

**Q: 我不会用命令行，能做歌吗？**
A: 能。装一个 Cursor（图形界面），打开项目文件夹，在对话框里用中文描述就行。

**Q: 我用的不是 Claude Code，能跑自动化脚本吗？**
A: 能。把 `daily_music.sh` 里的 `CLAUDE_BIN` 改成你的 AI 工具路径就行。如果你的工具不支持 `-p` 参数传 prompt，需要微调 `run_claude()` 函数。

**Q: Suno 报 422 Token validation failed？**
A: 在浏览器打开 suno.com，随便点一下页面刷新心跳，然后重试。

**Q: Gemini API 连不上？**
A: 如果你的网络需要翻墙，在 `.env` 中配置 `HTTPS_PROXY`。能直连的不需要配。

**Q: Style Prompt 报 400 错误？**
A: 检查长度是否超过 200 字符。

**Q: 怎么添加新的音乐人？**
A: 在知识库中新建对应的 `.md` 文件，包含：风格画像、对标艺人、声线描述、Style Prompt 模板。

**Q: 怎么获取 Suno Cookie？**
A: 打开浏览器 → 登录 suno.com → F12 打开 DevTools → Application → Cookies → 找到 `__client` → 复制整个值到 `.env`。
