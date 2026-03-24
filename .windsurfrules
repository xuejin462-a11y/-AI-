# AI 做歌系统 — 给 AI 助手的操作指南

你正在帮助一个**不懂技术的运营同学**使用这个 AI 做歌系统。她们不会写代码、不会用终端。你需要替她们完成所有技术操作。

## 首次使用：帮她设置环境

如果项目还没配置过（`suno-api/.env` 不存在），你需要引导她完成配置：

1. 运行 `pip3 install librosa google-genai Pillow streamlit requests`
2. 复制 `cp .env.example suno-api/.env`
3. **逐个问她要 API 密钥**，每个都要告诉她怎么获取：
   - **Suno Cookie**：打开 Chrome → 登录 suno.com → F12 → Application → Cookies → 找 `__client` → 复制 Value
   - **Gemini API Key**：打开 aistudio.google.com/apikey → 登录 Google → Create API Key → 复制（以 AIza 开头）
   - **豆包 API Key**（可选）：打开 console.volcengine.com/ark → 登录 → API Key 管理 → 创建
4. 帮她把密钥填入 `suno-api/.env`
5. 运行 `python3 suno-api/suno_client.py credits` 测试 Suno 是否连通

## 日常使用：她说想法，你来执行

### 她说「我想写一首歌」

1. 问她要：灵感/主题/故事（至少一个）
2. 问她偏好：风格？声线？快歌还是慢歌？（她不说就你来选）
3. 如果她有参考曲文件，让她发给你
4. 按以下步骤执行：

**有参考曲 + 要写新歌词的情况：**
```bash
# 1. 你来写歌词（根据她的灵感写，遵循下面的写词规则）
# 2. 上传参考曲并生成
python3 suno-api/suno_client.py inspo \
  --audio "参考曲路径" \
  --description "风格描述" \
  --title "歌名" \
  --lyrics "你写的歌词" \
  --out ~/Desktop/做歌输出/
```

**有参考曲 + 只换风格/声线（二创）：**
```bash
python3 suno-api/suno_client.py remix \
  --audio "原曲路径" \
  --style "Style Prompt（见下方规则，不超过200字符）" \
  --title "歌名" \
  --out ~/Desktop/做歌输出/
```

**没有参考曲：**
- 告诉她"纯灵感模式目前需要参考曲来生成旋律"
- 建议她找一首风格类似的歌作为参考
- 或者你用 yt-dlp 帮她从 YouTube 下一首参考曲

5. 等待生成完成（通常 2-5 分钟）
6. 把输出的 .wav 文件路径告诉她，让她听

### 她说「帮我做个视频」

```bash
SONG_NAME="歌名" \
ARTIST_NAME="歌手" \
AUDIO_PATH="歌曲文件路径" \
LYRICS_RAW="歌词内容" \
OUTPUT_PATH="输出路径.mp4" \
MOOD_TAG="情绪标签" \
VIDEO_DURATION="30" \
python3 daily-video/gen_video_v2.py
```

情绪标签选择（根据歌的感觉选）：
- A = 伤感/失恋
- B = 思念/暗恋
- C = 治愈/释怀
- D = 愤怒/执念
- E = 甜蜜/浪漫
- F = 孤独/深夜
- G = 古风/情感

### 她说「查一下积分」

```bash
python3 suno-api/suno_client.py credits
```

### 她说「打开做歌网页」

```bash
python3 app.py
```

这会打开一个浏览器网页，她可以在网页上自己操作。

## Style Prompt 规则（写给 Suno 的风格描述）

**严格不超过 200 字符。** 超了会报 400 错误。

格式：`曲风, BPM, 情绪, 乐器1, 乐器2, 人声风格, 制作风格, 排除项`

示例：
```
indie pop ballad, 90 BPM, melancholic nostalgic, piano arpeggios, soft synth pads, breathy airy female vocals, studio quality warm reverb, no aggressive vocals
```

## 写词规则（简要版）

1. **禁止照搬任何现有歌词**，必须 100% 原创
2. 用意象写感情，不要直接说「我很孤独」，要写「窗外的麻雀在电线杆上多嘴」
3. 每首歌一个情绪切面，不要贪多
4. 副歌的高音位用开口韵母：-a, -ai, -ao, -ang
5. 押韵是硬性要求，每段韵脚统一
6. 歌词格式用 `[Verse]` `[Chorus]` `[Bridge]` 等标签分段

## 文件结构

```
suno-api/suno_client.py  — Suno 命令行工具（credits/remix/inspo）
suno-api/.env             — API 密钥配置文件
daily-video/gen_video_v2.py — 视频生成引擎
app.py                    — 网页操作界面
setup.sh                  — 一键安装脚本
```

## 重要注意事项

- **不要修改或删除 suno-api/.env**，里面是用户的密钥
- 做歌输出默认存到 `~/Desktop/做歌输出/`
- Suno 每次生成消耗积分，一次生成 2 个版本
- 如果 Suno 报 422 错误，让用户在浏览器打开 suno.com 点一下页面，然后重试
