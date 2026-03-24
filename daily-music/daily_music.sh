#!/bin/zsh
# ─────────────────────────────────────────────────────────────────
# 每日音乐全流程主控脚本（合并版）
# 阶段一：抓取热榜 + 邮件推送团队
# 阶段二：做歌（热歌×热点Cover×5 + 对标成名曲×热点Cover×5）
# 阶段三：邮件通知执行结果
#
# launchd 调用: 每天 18:00 自动执行
# 手动运行: zsh ~/Documents/claude/自动化/daily-music/daily_music.sh
# ─────────────────────────────────────────────────────────────────

# ── 环境初始化 ──────────────────────────────────────────────────
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.npm-global/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export LANG="zh_CN.UTF-8"
# 加载 .env 配置
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../suno-api/.env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="${SCRIPT_DIR}/.env"
fi
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key value; do
        # 跳过注释和空行
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        # 去掉引号
        value=$(echo "$value" | sed 's/^["'"'"']//;s/["'"'"']$//')
        export "$key=$value"
    done < "$ENV_FILE"
fi

# 代理（仅在 .env 中配置了时才设置）
[ -n "$HTTP_PROXY" ] && export http_proxy="$HTTP_PROXY"
[ -n "$HTTPS_PROXY" ] && export https_proxy="$HTTPS_PROXY"
[ -n "$NO_PROXY" ] && export no_proxy="$NO_PROXY"

# Claude CLI 使用 Max 订阅 OAuth 认证，不需要 API Key
# 清除嵌套会话标记，防止 Claude CLI 误判为嵌套调用
unset CLAUDECODE

SCRIPT_DIR="$HOME/Documents/claude/自动化/daily-music"
MONITOR_DIR="$HOME/music_chart_monitor"
LOG_DIR="$SCRIPT_DIR/logs"
# 支持手动指定日期：zsh daily_music.sh 2026-03-08
# 不传参数则自动取当天日期
TODAY=${1:-$(date +%Y-%m-%d)}
SKIP_PHASE1=${2:-""}  # 传任意第二参数则跳过阶段一
LOG_FILE="$LOG_DIR/$TODAY.log"

# SMTP（从 .env 加载，如未配置则留空）
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
NOTIFY_TO="${NOTIFY_TO:-}"

mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Documents/claude/输出文档/歌曲/$TODAY/cover"
mkdir -p "$HOME/Documents/claude/输出文档/歌曲/$TODAY/original"

# 记录各阶段状态
PHASE1_STATUS="❌ 未执行"
PHASE2_STATUS="❌ 未执行"

# ── 异常告警邮件函数 ──────────────────────────────────────────
# 用法：send_alert "卡住的阶段" "原因" "你需要做什么"
send_alert() {
    local stage="$1"
    local reason="$2"
    local action="$3"
    echo "🚨 发送异常告警邮件: $stage" | tee -a "$LOG_FILE"
    python3 -c "
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

today = '$TODAY'
time_now = datetime.now().strftime('%H:%M:%S')
stage = '''$stage'''
reason = '''$reason'''
action = '''$action'''

# 读取最近日志
log_path = os.path.expanduser(f'~/Documents/claude/自动化/daily-music/logs/{today}.log')
log_tail = ''
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        log_tail = f.read()[-2000:]

body = f'''
<html><body style=\"font-family: -apple-system, sans-serif; padding: 20px;\">
<h2 style=\"color: #e74c3c;\">🚨 每日音乐任务异常告警 - {today}</h2>
<p>告警时间：{time_now}</p>

<h3>卡在哪个环节</h3>
<p style=\"font-size: 16px; font-weight: bold;\">{stage}</p>

<h3>原因</h3>
<p>{reason}</p>

<h3 style=\"color: #e67e22;\">你需要做什么</h3>
<p style=\"font-size: 15px; background: #fff3cd; padding: 12px; border-radius: 6px;\">{action}</p>

<hr>
<details>
<summary>最近日志（最后2000字符）</summary>
<pre style=\"font-size: 11px; background: #f5f5f5; padding: 10px; overflow-x: auto;\">{log_tail if log_tail else '日志为空'}</pre>
</details>
</body></html>
'''

msg = MIMEMultipart('alternative')
msg['Subject'] = f'🚨 [每日音乐任务] {today} 异常告警 - {stage}'
msg['From'] = '$SMTP_USER'
msg['To'] = '$NOTIFY_TO'
msg.attach(MIMEText(body, 'html', 'utf-8'))

try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login('$SMTP_USER', '$SMTP_PASS')
    server.sendmail('$SMTP_USER', '$NOTIFY_TO', msg.as_string())
    server.quit()
    print('🚨 异常告警已发送')
except Exception as e:
    print(f'❌ 异常告警发送失败: {e}')
" 2>&1 | tee -a "$LOG_FILE"
}

echo "=== 每日音乐全流程启动 $TODAY $(date +%H:%M:%S) ===" | tee "$LOG_FILE"

# ═══════════════════════════════════════════════════════════════
# 开工通知邮件
# ═══════════════════════════════════════════════════════════════
echo "[0] 发送开工通知邮件..." | tee -a "$LOG_FILE"
python3 -c "
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

today = datetime.now().strftime('%Y-%m-%d')
time_now = datetime.now().strftime('%H:%M:%S')

body = f'''
<html><body style=\"font-family: -apple-system, sans-serif; padding: 20px;\">
<h2>每日音乐任务开始执行</h2>
<p>日期：{today}</p>
<p>启动时间：{time_now}</p>
<p>即将执行：</p>
<ol>
<li>抓取6大音乐榜单 + 4大热点平台</li>
<li>团队邮件推送</li>
<li>热歌×热点 Cover × 5</li>
<li>对标成名曲×热点 Cover × 5</li>
</ol>
<p>完成后会再发一封执行报告。</p>
</body></html>
'''

from email.mime.multipart import MIMEMultipart
msg = MIMEMultipart('alternative')
msg['Subject'] = f'[每日音乐任务] {today} 开始执行'
msg['From'] = '$SMTP_USER'
msg['To'] = '$NOTIFY_TO'
msg.attach(MIMEText(body, 'html', 'utf-8'))

try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login('$SMTP_USER', '$SMTP_PASS')
    server.sendmail('$SMTP_USER', '$NOTIFY_TO', msg.as_string())
    server.quit()
    print('✅ 开工通知已发送')
except Exception as e:
    print(f'⚠️ 开工通知发送失败: {e}')
" 2>&1 | tee -a "$LOG_FILE"

# ═══════════════════════════════════════════════════════════════
# 阶段一：抓取热榜 + 邮件推送团队
# ═══════════════════════════════════════════════════════════════
INPUT_FILE="$SCRIPT_DIR/today_input.json"

if [ -n "$SKIP_PHASE1" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "━━━ 阶段一：已跳过（手动补跑模式，使用已有数据）━━━" | tee -a "$LOG_FILE"
    PHASE1_STATUS="⏭️ 跳过（补跑模式）"
else
    echo "" | tee -a "$LOG_FILE"
    echo "━━━ 阶段一：榜单监控 + 团队邮件推送 ━━━" | tee -a "$LOG_FILE"

    # Step 1.1: 运行榜单监控脚本（抓取+发团队邮件）
    echo "[1.1] 运行 music_chart_monitor.py..." | tee -a "$LOG_FILE"
    cd "$MONITOR_DIR" && python3 music_chart_monitor.py 2>&1 | tee -a "$LOG_FILE"
    MONITOR_EXIT=$?

    if [ $MONITOR_EXIT -eq 0 ]; then
        echo "[1.1] ✅ 榜单监控+团队邮件推送完成" | tee -a "$LOG_FILE"
        PHASE1_STATUS="✅ 成功"
    else
        echo "[1.1] ⚠️ 榜单监控执行异常（exit=$MONITOR_EXIT），继续执行后续流程" | tee -a "$LOG_FILE"
        PHASE1_STATUS="⚠️ 异常（exit=$MONITOR_EXIT）"
    fi

    # Step 1.2: 抓取做歌用数据
    echo "[1.2] 运行 fetch_charts.py 生成 today_input.json..." | tee -a "$LOG_FILE"
    cd "$SCRIPT_DIR" && python3 fetch_charts.py 2>&1 | tee -a "$LOG_FILE"
    FETCH_EXIT=$?

    if [ $FETCH_EXIT -ne 0 ]; then
        echo "[1.2] ❌ fetch_charts.py 失败（exit=$FETCH_EXIT）" | tee -a "$LOG_FILE"
        PHASE1_STATUS="$PHASE1_STATUS | fetch_charts ❌"
    fi
fi
if [ ! -f "$INPUT_FILE" ]; then
    echo "[1.2] ❌ today_input.json 不存在，做歌流程无法启动" | tee -a "$LOG_FILE"
    PHASE2_STATUS="❌ 数据缺失，跳过"
    send_alert "阶段一：数据抓取失败" \
        "today_input.json 不存在，fetch_charts.py 可能运行失败或未生成数据文件。做歌流程无法启动。" \
        "1. 检查网络连接是否正常<br>2. 手动运行: cd ~/Documents/claude/自动化/daily-music && python3 fetch_charts.py<br>3. 确认生成了 today_input.json 后，补跑做歌: zsh ~/Documents/claude/自动化/daily-music/daily_music.sh $TODAY skip"
else

# ═══════════════════════════════════════════════════════════════
# 阶段 1.5：环境自检 + 知识库更新
# ═══════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG_FILE"
echo "━━━ 阶段 1.5：环境自检 + 知识库更新 ━━━" | tee -a "$LOG_FILE"

# [1.5.1] 验证外部 API 可用性 + 更新可用模型名
echo "[1.5.1] 验证 API 可用性 & 模型名..." | tee -a "$LOG_FILE"
python3 << 'SELFCHECK_EOF' 2>&1 | tee -a "$LOG_FILE"
import json, os, urllib.request

env_path = os.path.expanduser("~/Documents/claude/自动化/suno-api/.env")
env = {}
with open(env_path) as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

# 1) 检查豆包文本模型
print("  [豆包文本] 检查可用模型...")
try:
    req = urllib.request.Request(
        "https://ark.cn-beijing.volces.com/api/v3/models",
        headers={"Authorization": f"Bearer {env['ARK_API_KEY']}"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        models = json.loads(resp.read())["data"]
    active_text = [m for m in models if m.get("status") != "Shutdown"
                   and "seed-2-0-pro" in m["id"]]
    if active_text:
        best = sorted(active_text, key=lambda x: x["created"], reverse=True)[0]
        print(f"  ✅ 最新豆包文本模型: {best['id']}")
    else:
        # 降级找 1-5-pro
        fallback = [m for m in models if "1-5-pro-32k" in m["id"]
                    and m.get("status") != "Shutdown"]
        if fallback:
            best = sorted(fallback, key=lambda x: x["created"], reverse=True)[0]
            print(f"  ⚠️ seed-2.0-pro 不可用，降级: {best['id']}")
        else:
            print("  ❌ 无可用豆包文本模型")
except Exception as e:
    print(f"  ❌ 豆包API检查失败: {e}")

# 2) 检查豆包图片模型
try:
    active_img = [m for m in models if "seedream" in m["id"]
                  and m.get("status") != "Shutdown"]
    if active_img:
        best_img = sorted(active_img, key=lambda x: x["created"], reverse=True)[0]
        print(f"  ✅ 最新豆包图片模型: {best_img['id']}")
except:
    pass

# 3) 检查 Suno 直连
print("  [Suno] 验证连通性...")
try:
    import sys; sys.path.insert(0, os.path.expanduser("~/Documents/claude/自动化/suno-api"))
    from suno_client import SunoClient
    client = SunoClient()
    credits = client.get_credits()
    print(f"  ✅ Suno 连通，剩余积分: {credits}")
except Exception as e:
    print(f"  ❌ Suno 连接失败: {e}")

# 4) 检查 Gemini
print("  [Gemini] 验证连通性...")
try:
    proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    proxy = urllib.request.ProxyHandler({"https": proxy_url} if proxy_url else {})
    opener = urllib.request.build_opener(proxy)
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={env['GEMINI_API_KEY']}"
    req = urllib.request.Request(url)
    with opener.open(req, timeout=15) as resp:
        gmodels = json.loads(resp.read())
    img_models = [m["name"] for m in gmodels.get("models", [])
                  if "image" in m["name"].lower() or "flash" in m["name"].lower()]
    print(f"  ✅ Gemini 连通，可用模型 {len(gmodels.get('models',[]))} 个")
except Exception as e:
    print(f"  ❌ Gemini 连接失败: {e}")

print("  自检完成")
SELFCHECK_EOF

# [1.5.2] 更新 Suno 最佳实践（每周一执行，用 Claude 搜索社区最新技巧）
DOW=$(date +%u)  # 1=周一
if [ "$DOW" -eq 1 ]; then
    echo "[1.5.2] 每周一更新 Suno 最佳实践..." | tee -a "$LOG_FILE"
    unset CLAUDECODE
    /Users/xuejin/.npm-global/bin/claude --dangerously-skip-permissions -p "
搜索 Suno V5 最新的 prompt 最佳实践、metatags 更新、社区技巧（2026年），
然后对比 ~/Documents/claude/知识库/Suno音乐创作/Suno交互最佳实践.md 的内容，
如果有新发现则更新该文件，标注更新日期。
只更新有实质性变化的部分，不要重写整个文件。
如果没有新发现就不修改文件。
" 2>&1 | tee -a "$LOG_FILE"
    echo "[1.5.2] ✅ Suno 最佳实践更新完成" | tee -a "$LOG_FILE"
else
    echo "[1.5.2] 非周一，跳过 Suno 最佳实践更新" | tee -a "$LOG_FILE"
fi

# [1.5.3] 月度主题歌曲规划（每月1号执行）
DOM=$(date +%d)  # 01-31
MONTH_NUM=$(date +%m)
MONTH_NAME=$(date +%B)  # English month name
MONTHLY_BRIEF="$HOME/Documents/claude/输出文档/歌曲/$TODAY/original/monthly_themes.json"
if [ "$DOM" -eq "01" ]; then
    echo "[1.5.3] 每月1号：生成月度主题歌曲规划..." | tee -a "$LOG_FILE"
    run_claude "MONTHLY_THEMES" "
你需要为本月（${MONTH_NUM}月）规划3类主题歌曲，输出为 JSON。

读取：
- ~/Documents/claude/知识库/Suno音乐创作/五位音乐人.md

==============================
月度主题歌曲规划
==============================

第一类：月份主题（1首）
  围绕${MONTH_NUM}月的季节特征、氛围、情感色调写一首歌。
  例：3月→春天/万物复苏/暗恋萌芽，7月→盛夏/毕业季/热烈，12月→年终/冬日/温暖回忆
  要有具体场景和画面感，不要泛泛的季节描写。

第二类：星座主题（1首）
  本月对应星座的性格特质+情感故事。
  月份→星座映射：1月摩羯/水瓶，2月水瓶/双鱼，3月双鱼/白羊，4月白羊/金牛，
  5月金牛/双子，6月双子/巨蟹，7月巨蟹/狮子，8月狮子/处女，9月处女/天秤，
  10月天秤/天蝎，11月天蝎/射手，12月射手/摩羯
  选当月主要星座（占比更大的那个），围绕该星座典型性格写歌。
  歌词要让该星座的人听了有共鸣，但不要堆砌星座刻板印象。

第三类：节日主题（1-3首，视本月节日数量而定）
  列出本月所有重要节日（含传统节日、国际节日、网络节日），每个节日一首歌。
  例：3月→妇女节/植树节/白色情人节，5月→母亲节/520，10月→国庆/重阳/万圣
  每首围绕节日情感核心写歌，要有年轻人视角，不要官方/正式/说教。

每首歌分配一位音乐人（5位轮流），选与主题风格最搭的。

输出JSON到：$MONTHLY_BRIEF
格式：
{
  \"month\": ${MONTH_NUM},
  \"themes\": [
    {
      \"type\": \"月份主题/星座主题/节日主题\",
      \"theme_name\": \"三月·春醒\",
      \"description\": \"围绕XX写歌的方向说明\",
      \"musician\": \"音乐人\",
      \"vocalGender\": \"f或m\",
      \"suggested_mood\": \"温暖/治愈/...\",
      \"group\": \"月度主题\"
    }
  ]
}
"
    if [ -f "$MONTHLY_BRIEF" ]; then
        echo "[1.5.3] ✅ 月度主题规划已生成" | tee -a "$LOG_FILE"
    else
        echo "[1.5.3] ⚠️ 月度主题规划未生成，不影响主流程" | tee -a "$LOG_FILE"
    fi
else
    echo "[1.5.3] 非月初，跳过月度主题规划" | tee -a "$LOG_FILE"
fi

# ═══════════════════════════════════════════════════════════════
# 阶段二：做歌（Claude Code CLI — 单次调用模式）
# ═══════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG_FILE"
echo "━━━ 阶段二：做歌全流程（单次调用模式） ━━━" | tee -a "$LOG_FILE"

CLAUDE_BIN="/Users/xuejin/.npm-global/bin/claude"
OUTPUT_DIR="$HOME/Documents/claude/输出文档/歌曲/$TODAY"
BRIEF_FILE="$OUTPUT_DIR/original/production_brief.json"
SONG_SUCCESS=0
SONG_FAIL=0
STATS_FILE="$LOG_DIR/$TODAY-token-stats.csv"
echo "step,duration_sec,output_chars,exit_code" > "$STATS_FILE"

# ── 计时+统计函数 ──
# 用法: run_claude "步骤名" "prompt内容..."
# 结果保存在 LAST_CLAUDE_OUTPUT 和 LAST_CLAUDE_EXIT
run_claude() {
    local step_name="$1"
    shift
    local start_ts=$(date +%s)
    unset CLAUDECODE
    LAST_CLAUDE_OUTPUT=$($CLAUDE_BIN --dangerously-skip-permissions -p "$@" 2>&1)
    LAST_CLAUDE_EXIT=$?
    local end_ts=$(date +%s)
    local duration=$((end_ts - start_ts))
    local out_chars=${#LAST_CLAUDE_OUTPUT}
    echo "$step_name,$duration,$out_chars,$LAST_CLAUDE_EXIT" >> "$STATS_FILE"
    echo "$LAST_CLAUDE_OUTPUT" | tee -a "$LOG_FILE"
    local mins=$((duration / 60))
    local secs=$((duration % 60))
    echo "[STATS] $step_name: ${mins}m${secs}s, output=${out_chars}chars, exit=$LAST_CLAUDE_EXIT" | tee -a "$LOG_FILE"
}

# ── 错误处理函数 ──
check_claude_exit() {
    local exit_code=$1
    local stage_name=$2
    if [ $exit_code -ne 0 ]; then
        LAST_LOG=$(tail -20 "$LOG_FILE" 2>/dev/null)
        if echo "$LAST_LOG" | grep -qi "credit balance is too low\|authentication_error\|401"; then
            send_alert "阶段二：Claude CLI 认证失败（$stage_name）" \
                "OAuth token 过期或认证异常（exit=$exit_code）。" \
                "1. 设置代理后运行 claude，执行 /login 重新授权<br>2. 补跑: <code>zsh ~/Documents/claude/自动化/daily-music/daily_music.sh $TODAY skip</code>"
            return 1
        elif echo "$LAST_LOG" | grep -qi "ECONNREFUSED\|proxy\|network\|timeout"; then
            send_alert "阶段二：网络/代理连接失败（$stage_name）" \
                "Claude CLI 无法连接（exit=$exit_code）。" \
                "1. 确认 Clash 正在运行且监听 127.0.0.1:7897<br>2. 补跑: <code>zsh ~/Documents/claude/自动化/daily-music/daily_music.sh $TODAY skip</code>"
            return 1
        fi
    fi
    return 0
}

# ══════════════════════════════════════════════════════════════
# [2-A] STEP A + A.5：话题推演 + 制作简报（独立调用 #1）
# ══════════════════════════════════════════════════════════════
echo "[2-A] 话题推演 + 制作简报..." | tee -a "$LOG_FILE"

run_claude "STEP_A_A5" "
读取以下文件：
- ~/Documents/claude/自动化/daily-music/today_input.json
- ~/Documents/claude/知识库/音乐创作/五位音乐人.md
- ~/Documents/claude/知识库/音乐创作/歌曲存档.md
- ~/Documents/claude/自动化/suno-api/.env

==============================
STEP A：话题推演 + 故事框架
==============================
基于 topics 字段 和 douyin_trending 字段中的热点词条，推演出 10 个「歌曲故事框架」。
每个框架必须包含：主题、情绪、人物关系、场景切口、可写歌角度、适配歌曲风格。
推演逻辑：每个热点至少1-2个框架，覆盖不同情绪色调。
特别注意 douyin_trending 中的热门电视剧/电影/综艺/CP，这些是最高优先级素材。
写入：~/Documents/claude/输出文档/歌曲/$TODAY/original/story_frames.md

==============================
STEP A.5：今日制作简报（6首原创歌曲分配）
==============================
今日所有歌曲均为【原创歌曲模式】：写全新歌词，参考曲只提供旋律灵感（cover-inspo），歌词100%原创。

【6首歌的分配方案】

▶ 分组A：多榜热歌参考（2首）
  参考曲来源：today_input.json 的 multi_chart_hits 字段，按上榜数量从多到少选取
  选歌偏好：副歌有明显爆发（BPM 90-130），避免民谣/慢板（BPM<80）/纯说唱/古风
  故事灵感：从 STEP A 故事框架中选与参考曲情绪最匹配的

▶ 分组B：对标成品曲参考（2首）
  参考曲来源：五位音乐人.md 中各音乐人的「Cover选歌优先级」成名曲库
  选曲逻辑：选与当日故事框架情绪最契合的，每位音乐人均衡轮流
  故事灵感：从 STEP A 故事框架中选，情绪优先匹配该音乐人的受众画像

▶ 分组C：影视综热点驱动（2首）
  数据源：today_input.json 的 douyin_trending 字段（6品类：热门电视剧/电影/综艺/CP/文案/歌曲）
  选题逻辑：
    1. 从热门电视剧/电影/综艺 top3 中，选出最有话题性的影视IP
    2. 从热门CP/文案中，挑选能成为歌词主题的情感梗
    3. 参考曲从 cover_candidates 或 multi_chart_hits 中选旋律适配的
  歌词要求（⚠️ 最重要！）：
    - 【绝对禁止】出现任何真实人名/角色名/艺人名
    - 【绝对禁止】血腥暴力意象（砧板/血/刃/棺材/屠夫等）
    - 热点植入方式：提炼情感内核，不复述剧情！
    - 歌词面向普罗大众，不需要看过原剧也能完全理解和共鸣
  每首额外标注：source_ip 字段（如「逐玉」「白蛇传1924」）

⚠️ 音色一致性硬规则：Style Prompt 人声标签一字不改，编曲骨架可微调，禁区词绝不出现。
⚠️ 6首歌中5位音乐人尽量均衡覆盖，不要全给同一人。

【文件命名规范】
- 所有歌曲文件夹：原创-{音乐人}-{歌名 待Phase3生成后填写}/
  分组C有 source_ip 的：原创-{音乐人}-{歌名}-{来源IP}/（如：原创-屿川-玉碎-逐玉/）
- WAV文件：原创-{音乐人}-{歌名}-1.wav

【输出要求】
除了 story_frames.md，还必须输出结构化 JSON 到：
~/Documents/claude/输出文档/歌曲/$TODAY/original/production_brief.json

JSON 格式（严格遵守！）：
{
  \"songs\": [
    {
      \"index\": 1,
      \"group\": \"多榜热歌\",
      \"reference_song\": \"参考原曲名\",
      \"reference_artist\": \"原歌手\",
      \"reference_source\": \"多榜热歌 / 对标成品曲 / 影视综热点\",
      \"musician\": \"音乐人\",
      \"vocalGender\": \"f或m\",
      \"style_prompt\": \"完整Style Prompt（≤200字符）\",
      \"story_direction\": \"故事方向/情感切入点（1-2句）\",
      \"source_ip\": \"来源影视IP（仅分组C填写，如逐玉/白蛇传1924，其他留空）\",
      \"frame_id\": 1
    },
    ...分组A 2首 + 分组B 2首 + 分组C 2首 = 共6首
    如果今天是每月1号且存在 monthly_themes.json，替换分组B的2首为月度主题歌曲：
    月度主题（2首，仅每月1号）：group=\"月度主题\"，theme_name作为story_direction，
    参考曲从cover_candidates中选风格匹配的。
  ]
}
"

STEP_A_EXIT=$LAST_CLAUDE_EXIT
check_claude_exit $STEP_A_EXIT "STEP A+A.5" || { PHASE2_STATUS="⚠️ 异常"; }

if [ ! -f "$BRIEF_FILE" ]; then
    echo "[2-A] ❌ production_brief.json 未生成，做歌无法继续" | tee -a "$LOG_FILE"
    PHASE2_STATUS="❌ 制作简报生成失败"
    send_alert "阶段二：制作简报生成失败" \
        "production_brief.json 不存在，STEP A+A.5 可能执行失败。" \
        "检查日志: cat ~/Documents/claude/自动化/daily-music/logs/$TODAY.log"
else

# ══════════════════════════════════════════════════════════════
# [2-B] 分批制作歌曲（每批3首，共2批，每批独立上下文）
# ══════════════════════════════════════════════════════════════
SONG_COUNT=$(python3 -c "import json; d=json.load(open('$BRIEF_FILE')); print(len(d['songs']))")
BATCH_SIZE=3
TOTAL_BATCHES=$(( (SONG_COUNT + BATCH_SIZE - 1) / BATCH_SIZE ))
echo "[2-B] 分批制作: 共${SONG_COUNT}首, 每批${BATCH_SIZE}首, ${TOTAL_BATCHES}批" | tee -a "$LOG_FILE"

BATCH_PIDS=()
for BATCH_IDX in $(seq 1 $TOTAL_BATCHES); do
    BATCH_START=$(( (BATCH_IDX - 1) * BATCH_SIZE + 1 ))
    BATCH_END=$(( BATCH_IDX * BATCH_SIZE ))
    if [ $BATCH_END -gt $SONG_COUNT ]; then
        BATCH_END=$SONG_COUNT
    fi
    BATCH_COUNT=$(( BATCH_END - BATCH_START + 1 ))

    echo "" | tee -a "$LOG_FILE"
    echo "[2-B] ━━━ 第${BATCH_IDX}批: 第${BATCH_START}-${BATCH_END}首 (共${BATCH_COUNT}首，并行启动) ━━━" | tee -a "$LOG_FILE"

    BATCH_LOG="$LOG_DIR/$TODAY-batch${BATCH_IDX}.log"

    (
        unset CLAUDECODE
        _BATCH_START_TS=$(date +%s)
        $CLAUDE_BIN --dangerously-skip-permissions -p "
你正在执行每日音乐生产流程中的【原创歌曲制作 第${BATCH_IDX}批】，本批处理第${BATCH_START}到第${BATCH_END}首歌（共${BATCH_COUNT}首），逐首执行。
所有歌曲均为「原创歌曲模式」：写全新歌词，用参考曲做旋律灵感（cover-inspo），Suno 用 cover_generate(cover_type=\"inspired_by\") 生成。

╔══════════════════════════════════════════════════════════════╗
║  🚨🚨🚨 最高优先级规则（每首歌都必须遵守，违反=重做）🚨🚨🚨  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. 歌词必须有间奏和气口！严禁把歌词写满！                      ║
║     - Phase 1.5 分析原曲结构后，原曲有间奏的地方必须标[Interlude] ║
║     - 原曲有气口/停顿的地方必须保留（用逗号暗示）                ║
║     - 歌词密度不得超过原曲，段落数/行数严格跟随原曲               ║
║     - 重复段标[Chorus Repeat]不写新内容                         ║
║                                                              ║
║  2. 歌曲时长必须2-4分钟！                                      ║
║     - 歌词量对应120-240秒                                       ║
║     - kie.ai生成后检查wav时长，<2分钟=ERROR必须重新生成          ║
║     - 总字数≤原曲110%，但不能太短导致歌曲不到2分钟              ║
║                                                              ║
║  3. 所有文件必须存在对应歌曲文件夹内！                           ║
║     - 每首歌第一步：mkdir并cd到歌曲文件夹                       ║
║     - 禁止在cover/根目录留任何文件                              ║
║                                                              ║
║  4. 每首歌写完歌词后必须执行8维自检+原词查重                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

==============================
第一步：读取知识库（只读一次）
==============================
- ~/Documents/claude/自动化/suno-api/.env（API Keys）
- ~/Documents/claude/输出文档/歌曲/$TODAY/original/production_brief.json（今日制作简报，含所有歌曲信息）
- ~/Documents/claude/知识库/音乐创作/歌词prompt生成SOP.md（写词模板+8维评分+比稿流程）
- ~/Documents/claude/知识库/音乐创作/Suno交互最佳实践.md（Style Prompt公式+提交检查表）
- ~/Documents/claude/知识库/音乐创作/歌曲命名指南.md（歌名六大模式）
- ~/Documents/claude/知识库/音乐创作/生成后评估与迭代SOP.md（Phase 5 质检完整流程）

==============================
第二步：逐首制作（Phase 0.5 → Phase 6）
==============================
从 production_brief.json 中读取 songs 数组，只处理第${BATCH_START}到第${BATCH_END}首（index从1开始）。
每首歌完成后输出「原创 #N: {歌名} ✅ 完成」或「原创 #N: {歌名} ❌ 失败: 原因」。

输出目录：~/Documents/claude/输出文档/歌曲/$TODAY/cover/

——— 每首歌的完整流程 ———

Phase 0.5：选歌可行性预检
  搜索词：\"歌名 歌手名 karaoke instrumental\"，检查3个结果标题
  标题必须含歌名+歌手名关键词，否则跳过（输出 skip.txt 说明原因后继续下一首）

Phase 1：搜索原曲音频 → 下载 → 截取副歌（仅用于结构分析，不再上传）
  搜索优先级：karaoke伴奏 → 钢琴演奏 → 翻唱(兜底)
  截取：librosa RMS定位chorus，从chorus_start-5s取90s
  三重验证：max_rms≥全曲60% + onset密度≥平均80% + 有效≥80s

Phase 1.5：原曲歌词结构分析（⚠️ 极重要！写词质量的根基！）
  获取原曲歌词 → 分析以下全部内容（不可跳过任何一项）：
  1. 逐行音节数 → 生成音节约束模板（±2字弹性，不超120%）
  2. 歌曲结构图谱：Verse/Pre-Chorus/Chorus/Bridge/Outro 各有几段、每段几行
  3. 间奏位置和时长（哪些地方没有人声，必须标记 [Interlude]）
  4. 气口位置（句与句之间的停顿/换气处，用逗号暗示）
  5. 重复段落（哪些Chorus是重复的 → 标 [Chorus Repeat] 不写新内容）
  6. 每行最长字数 → 新歌词单行不得超过原曲最长行+2字
  7. 总字数 → 新歌词总字数不得超过原曲110%
  8. 韵脚方案：每段用什么韵母（提前规划，不要写完才发现散韵）
  9. Chorus高音位标注：哪些音节是高音/长音（用于后续韵母约束）

  【结构约束硬规则（违反=重写）】：
  - 原曲几个Verse就写几个，几行就写几行（±1行容差）
  - 原曲有 [Interlude]/哼唱/器乐间奏 → 新歌词必须保留，不能填满
  - 原曲有气口/停顿 → 新歌词必须保留（逗号暗示气口，省略号暗示拖长）
  - 原曲后半段重复Chorus → 标 [Chorus Repeat]，不写全新歌词
  - 原曲没有Bridge就不加Bridge，没有Outro就不加Outro
  - 歌词密度≤原曲（新歌词不能比原曲更密集）
  - 🚫 绝对禁止照搬原曲歌词内容！只参考结构和长度，内容必须100%原创
  - 逐句查重：任何一句与原词相似度>30%（含同义替换/换个别字）→ 重写

Phase 2：写歌词（Claude + Gemini 比稿 → 8维评分 → 逐段合并最优）
  必须同时满足 Phase 1.5 的结构约束 + 下面的所有规则！

  【⚠️ 写词前必须确认 Phase 1.5 输出完整】
  开始写之前，先打印确认：段落数/行数/间奏位置/气口位置/总字数上限/韵脚方案/高音位
  如果 Phase 1.5 有任何遗漏，先补完再写词。

  【歌词红线 — 违反任何一条直接重写！】

  【A. 内容禁令】
  - 🚫 禁止出现任何真实人名/角色名/艺人名（樊长玉/许仙/白素贞/鹿晗等全禁）
  - 🚫 禁止品牌名/商品名入词（老干妈/星巴克等，歌词不是广告）
  - 🚫 禁止血腥暴力意象（砧板染血/屠户/刃/棺材/杀/死等全禁）
  - 🚫 禁止荒谬场景（旷工100天/屠户女儿等不符合现实逻辑的设定）
  - 🚫 禁止在歌词中引用播放量/数据（「两亿次点头」「千万人在看」）
  - 🚫 禁止无意义口癖词（baby/darling/oh yeah 等空洞填充词，除非是Hook核心）
  - 🚫 禁止连续3句以上相同句式开头（6句连续「谁...」= 机械感）
  - 🚫 禁止励志海报句（「收伞也能走出来」「就算XX也能盛开」= 无张力）
  - 🚫 禁止库存套话（「千年修行留不住」「断桥的雨替我哭」= 毫无辨识度）
  - 🚫 禁止滥俗表达/网络烂梗（「被爱情撞了一下腰」「心在流浪」= 百度搜到10万+条结果的一律禁用）
  - 🚫 禁止概念硬凹（「笑容不在售后范围」「浪漫加进购物车」= 爱情硬套电商概念，空洞无感）
  - 🚫 禁止俗套语气词填充（Oh honey/Oh baby/Na na na = 偷懒填音节）

  【B. 热点→歌词转化规则】
  - 必须先理解原故事的真实结局和情感走向，不能篡改！
    例：白蛇传 = 被迫分离（不是互相分手），雷峰塔 = 镇压（不是灯亮了）
    正确转化：写「被迫分开的不甘/明知不能爱还是飞蛾扑火/为爱付出代价」
  - 语言质感必须匹配故事调性：唯美爱情→唯美歌词，不能用粗糙语言
  - 提炼情感内核，不复述剧情：白蛇传→跨越阻碍的爱/等待/不被允许的心动
  - 歌词面向普罗大众，任何人不需要看过原作也能完全理解和共鸣
  - 每首歌必须有态度/价值观（「所以呢？」测试：只留Chorus能看出态度吗？不能=不合格）

  【C. 可唱性与韵律硬规则】
  - 音节数精确匹配原曲（中文1字=1音节）
  - Chorus高音位/长音位必须用开口韵母：-a/-ai/-ao/-ang/-iang/-uang
  - 高音位禁用第三声，用一声或四声
  - 段内韵脚必须统一，不允许散韵/半押凑合（押韵是硬性要求不是可选项）
  - 逗号暗示气口，省略号暗示拖长，段落间必须空行

  【D. 写作标准】
  - 一首歌只用1-2个核心意象深入展开，不要风雨花海月星全上
  - 禁用万能情感词：回忆/遗憾/永远/离开/一切 最多出现1次
  - 每句必须有意象转化，用物件状态暗示情绪（物代情），不直述
  - 常识校验：咖啡用杯不用碗，现实中这个场景存在吗？
  - 适当中英混搭（英文锚点有意义，不是随便塞baby/darling）
  - 控制歌词量对应120-240s（成品必须2-4分钟，不能太短！）
  - 主题聚焦：一首歌一个情绪切面，不要爱恨离愁梦全塞

  【E. 多音字处理（⚠️ 必须执行）】
  - 歌词中所有多音字必须标注拼音，防止Suno误读
  - 标注方式：直接用拼音替代该字，不要写成「字(pinyin)」的形式
    ✅ 正确：「今夜 jue 不回头」
    ❌ 错误：「今夜 觉(jue) 不回头」「今夜 觉（jué）不回头」
  - 常见多音字：觉(jiao/jue) 了(le/liao) 得(de/dei) 还(hai/huan) 重(chong/zhong) 乐(le/yue)

  【F. 写完必须执行的8维自检（每首歌都要！）】
  写完歌词后，逐项检查以下8个维度，不合格的立即重写再输出：
  1. 可唱性：逐行数音节，是否和原曲旋律音符数一致？
  2. 高音位韵母：Chorus每个高音位是 -a/-ao/-ang/-ai 吗？
  3. 押韵质量：每段句尾韵母是否统一？有无半押凑合？
  4. 情感共鸣：有没有直述情绪（我很孤独/你很重要）？有没有励志海报句？每段是否有矛盾/张力？
  5. Hook记忆度：Chorus最核心那句，哼一遍能记住吗？
  6. 口语自然度：有没有书面腔/古风腔（此刻/思绪万千/心中涌起）？
  7. 故事完整性：Verse铺垫→Chorus爆发→Bridge转折，情感弧线完整吗？各段讲同一个故事吗？
  8. 上下文丝滑度：相邻句场景/意象/人称一致吗？有无突兀跳跃？

  【G. 原词查重（一票否决，在自检之后执行）】
  - 逐句对比原曲歌词，检查是否照搬/近似
  - 完全相同 → 直接打回重写
  - 近似表达（同义替换/换个别字/同一比喻换皮）→ 打回重写
  - 仅结构相似但用词完全不同 → 通过
  - ⚠️ 查重不通过的歌词，无论Scorecard多高分，一律重写

Phase 3：歌名生成
  豆包API（ARK_API_KEY，doubao-seed-2-0-pro-260215）生成10候选 → Claude 8维评分选Top1
  歌名要求网感、抖音传播力、2-5字为主

Phase 4：Suno V5 直连生成（cover-inspo 模式）
  调用方式：python3 ~/Documents/claude/自动化/suno-api/suno_client.py（已封装，自动刷新token）
  模型：chirp-crow（Suno V5，固定，不允许降级）
  ⚠️ 原创歌曲模式必须使用 cover_generate(cover_type=\"inspired_by\")，不能用 custom_generate！
  提交前必检：Style Prompt人声=原文？禁区词=0？歌词视角=性别？style长度≤200字符？

  完整调用流程：
    from suno_client import SunoClient
    client = SunoClient()

    # Step1: 上传参考曲（Phase 1 已截取好的90s片段）
    upload_id = client.upload_audio(ref_audio_90s_path)

    # Step2: cover-inspo 生成（inspo_generate，旋律以参考曲为灵感，歌词全新）
    ids = client.inspo_generate(
        upload_id=upload_id,
        description=style_prompt,   # Style Prompt → gpt_description_prompt 字段
        title=title,
        lyrics=lyrics,              # 新写的完整歌词 → prompt 字段
    )
    clips = client.wait_for_clips(ids, timeout=400)
    path = client.download_clip(clips[0], out_dir=song_dir, filename=\"歌名_v1\")
  API响应：clips[].audio_url（直连CDN，自动优先下载 WAV）

  或直接用 CLI（适合手动补跑单首）：
    python3 ~/Documents/claude/自动化/suno-api/suno_client.py inspo \\
      --audio ref_audio_90s.wav --description \"$style\" \\
      --title \"歌名\" --lyrics \"歌词\" --out \"$song_dir\"

  🚨 下载后立即检查时长：
  - librosa.load检查wav时长
  - <120秒(2分钟) = ERROR，必须重新生成（可能是歌词太短）
  - 120-240秒 = 正常
  - >300秒 = WARNING，可能歌词太长

Phase 5：生成后评估（ERROR才迭代）
  ⚠️ 必须完整执行所有步骤，不能只跑librosa基础检测就跳过！
  5.0 基础质量(librosa) → 5.0b 歌词存在性(demucs分离人声→Whisper转录→字数≥歌词30%否则ERROR) → 5.1 发音(Whisper ASR,CER>15%=ERROR) → 5.2 人声(demucs,SNR<5dB=ERROR) → 5.3 贴合度(onset vs syllable,<60%=ERROR)
  只有ERROR触发迭代，WARNING仅记录

Phase 6：封面图生成（2主题 × 2模型 = 4张）
  豆包(中文prompt,width=1024,height=1024) + Gemini NB2(英文prompt,需代理127.0.0.1:7897)
  风格：小红书调性，唯美/可爱/高级感
  豆包末尾加「画面干净唯美，无任何文字水印logo，高清摄影风，小红书调性」
  NB2末尾加「NO text NO people NO watermark NO letters NO logos」

——— 通用规则 ———

【歌词文件规范】
歌词文件（lyrics_final.md）开头必须包含元信息：正式歌名/参考曲/演唱者/故事方向/Style Prompt/歌名候选Top3

【失败处理】
Suno生成失败 → 换词重试1次 → 仍失败 → 输出 fail.txt 说明原因后跳过该首，继续下一首
Style Prompt超200字符 → 立即裁剪后重提交，不计入失败次数

【文件命名规范】
- 无 source_ip：原创-{音乐人}-{正式歌名}/
- 有 source_ip（分组C影视综热点）：原创-{音乐人}-{正式歌名}-{source_ip}/
- WAV文件：原创-{音乐人}-{歌名}-1.wav

【🚨 文件存放硬规则 — 绝不允许散落文件！】
每首歌的所有文件（音频/歌词/封面/中间产物）必须全部存在对应歌曲文件夹内。
⚠️ 开始处理每首歌时，第一步就是 mkdir 并 cd 到该歌曲文件夹，之后所有操作都在该文件夹内完成。
⚠️ 任何下载/生成的文件如果路径不在歌曲文件夹内 = 严重错误，立即移到正确位置。
⚠️ 禁止在 cover/ 根目录下留任何文件（临时文件也不行，用完立即删除或移入歌曲文件夹）。

【每首歌输出目录结构】
~/Documents/claude/输出文档/歌曲/$TODAY/cover/原创-{音乐人}-{正式歌名}[-{source_ip}]/
  ├── ref_audio_90s.wav         ← 参考曲截取片段（上传后可删）
  ├── lyrics_claude.md
  ├── lyrics_gemini_raw.md
  ├── lyrics_final.md
  ├── 原创-{音乐人}-{歌名}-1.wav
  ├── 原创-{音乐人}-{歌名}-2.wav
  ├── cover_{主题1}_doubao.png
  ├── cover_{主题1}_nb.png
  ├── cover_{主题2}_doubao.png
  └── cover_{主题2}_nb.png

全部完成后输出汇总：每首歌的状态（✅/❌）+ 问题记录。
" > "$BATCH_LOG" 2>&1
        _BATCH_LOCAL_EXIT=$?
        _BATCH_END_TS=$(date +%s)
        echo "$_BATCH_LOCAL_EXIT" > "$BATCH_LOG.exit"
        _BATCH_CHARS=$(wc -c < "$BATCH_LOG" 2>/dev/null || echo 0)
        echo "SONGS_BATCH${BATCH_IDX},$((${_BATCH_END_TS}-${_BATCH_START_TS})),${_BATCH_CHARS},$_BATCH_LOCAL_EXIT" >> "${STATS_FILE}.batch${BATCH_IDX}"
    ) &
    BATCH_PIDS+=($!)
    echo "[2-B] 第${BATCH_IDX}批已启动 (PID=${BATCH_PIDS[-1]})" | tee -a "$LOG_FILE"

done  # 批次循环结束

# ── 等待所有并行批次完成 ──
echo "[2-B] 等待 ${#BATCH_PIDS[@]} 个并行批次完成..." | tee -a "$LOG_FILE"
for _BATCH_W in $(seq 1 $TOTAL_BATCHES); do
    wait "${BATCH_PIDS[$(( _BATCH_W - 1 ))]}"
    _BLOG="$LOG_DIR/$TODAY-batch${_BATCH_W}.log"
    _BEXIT=$(cat "$_BLOG.exit" 2>/dev/null || echo 1)
    echo "" | tee -a "$LOG_FILE"
    echo "[2-B] ━━━ 第${_BATCH_W}批完整输出 ━━━" | tee -a "$LOG_FILE"
    cat "$_BLOG" 2>/dev/null | tee -a "$LOG_FILE"
    _BSTATS="${STATS_FILE}.batch${_BATCH_W}"
    [ -f "$_BSTATS" ] && cat "$_BSTATS" >> "$STATS_FILE" && rm -f "$_BSTATS"
    check_claude_exit "$_BEXIT" "第${_BATCH_W}批歌曲制作" || { PHASE2_STATUS="⚠️ 异常"; }
    echo "[2-B] 第${_BATCH_W}批完成 (exit=$_BEXIT)" | tee -a "$LOG_FILE"
done

# 全部批次完成后统计
SONG_RESULTS=$(python3 -c "
import os
base = os.path.expanduser('~/Documents/claude/输出文档/歌曲/$TODAY/cover/')
success = 0
fail = 0
if os.path.exists(base):
    for d in os.listdir(base):
        full = os.path.join(base, d)
        if not os.path.isdir(full) or d in ('temp_lyrics','temp_audio','demucs_out'):
            continue
        wavs = [f for f in os.listdir(full) if f.endswith('.wav') and not f.startswith('ref') and not f.startswith('raw') and not f.startswith('instrumental') and not f.startswith('segment')]
        if wavs:
            success += 1
        elif os.path.exists(os.path.join(full, 'lyrics_final.md')):
            fail += 1
print(f'{success} {fail}')
" 2>/dev/null || echo "0 0")
SONG_SUCCESS=$(echo $SONG_RESULTS | cut -d' ' -f1)
SONG_FAIL=$(echo $SONG_RESULTS | cut -d' ' -f2)
echo "[2-B] 全部完成: 成功${SONG_SUCCESS}首, 失败${SONG_FAIL}首" | tee -a "$LOG_FILE"


# ══════════════════════════════════════════════════════════════
# [2-D] STEP D：归档（独立调用 #12）
# ══════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG_FILE"
echo "[2-D] 归档到歌曲存档..." | tee -a "$LOG_FILE"

run_claude "STEP_D_归档" "
读取以下文件：
- ~/Documents/claude/知识库/Suno音乐创作/歌曲存档.md
- ~/Documents/claude/输出文档/歌曲/$TODAY/original/production_brief.json

扫描 ~/Documents/claude/输出文档/歌曲/$TODAY/cover/ 下所有子目录，
对每个目录：
1. 检查是否有 lyrics_final.md（读取元信息头）
2. 检查是否有 .wav 文件（计数）
3. 检查是否有 cover_*.png（计数）

将所有成功的歌曲追加到歌曲存档.md，格式：

## $TODAY 原创歌曲批次

### 分组A：多榜热歌参考
| # | 文件夹 | 参考曲 | 歌名 | 演唱者 | vocalGender | Style Prompt | 状态 |

### 分组B：对标成品曲参考
| # | 文件夹 | 参考曲 | 歌名 | 演唱者 | vocalGender | Style Prompt | 状态 |

### 分组C：影视综热点驱动
| # | 文件夹 | 来源IP | 参考曲 | 歌名 | 演唱者 | vocalGender | Style Prompt | 状态 |

输出目录：~/Documents/claude/输出文档/歌曲/$TODAY/cover/
"

echo "[2-D] 归档完成" | tee -a "$LOG_FILE"

# 汇总状态
if [ $SONG_SUCCESS -ge 8 ]; then
    PHASE2_STATUS="✅ 成功（${SONG_SUCCESS}首完成，${SONG_FAIL}首失败）"
elif [ $SONG_SUCCESS -ge 1 ]; then
    PHASE2_STATUS="⚠️ 部分完成（${SONG_SUCCESS}首完成，${SONG_FAIL}首失败）"
else
    PHASE2_STATUS="❌ 全部失败"
    send_alert "阶段二：做歌全部失败" \
        "10首歌全部制作失败，无成功产出。" \
        "查看日志: cat ~/Documents/claude/自动化/daily-music/logs/$TODAY.log"
fi

fi  # end of production_brief.json check

echo "[2] 做歌完成: $PHASE2_STATUS" | tee -a "$LOG_FILE"

# ── Token 统计报告 ──
echo "" | tee -a "$LOG_FILE"
echo "━━━ Token 消耗统计 ━━━" | tee -a "$LOG_FILE"
if [ -f "$STATS_FILE" ]; then
    python3 -c "
import csv
with open('$STATS_FILE') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_dur = 0
total_chars = 0
print(f'{'步骤':<30s} {'耗时':>8s} {'输出字符':>10s} {'~输出Token':>10s} {'状态':>6s}')
print('-' * 70)
for r in rows:
    dur = int(r['duration_sec'])
    chars = int(r['output_chars'])
    est_tokens = int(chars * 0.4)  # 中英混合约0.4 token/char
    total_dur += dur
    total_chars += chars
    mins = dur // 60
    secs = dur % 60
    status = '✅' if r['exit_code'] == '0' else '❌'
    print(f\"{r['step']:<30s} {mins:>3d}m{secs:02d}s {chars:>10,} {est_tokens:>10,} {status:>6s}\")

print('-' * 70)
est_total_output = int(total_chars * 0.4)
total_mins = total_dur // 60
total_secs = total_dur % 60
print(f\"{'合计':<30s} {total_mins:>3d}m{total_secs:02d}s {total_chars:>10,} {est_total_output:>10,}\")
print(f'')
print(f'总耗时: {total_mins}分{total_secs}秒')
print(f'估算总输出Token: ~{est_total_output:,}')
print(f'调用次数: {len(rows)}')
print(f'成功: {sum(1 for r in rows if r[\"exit_code\"]==\"0\")} / 失败: {sum(1 for r in rows if r[\"exit_code\"]!=\"0\")}')
" 2>&1 | tee -a "$LOG_FILE"
fi

fi  # end of today_input.json check

# ═══════════════════════════════════════════════════════════════
# 阶段三：邮件通知执行结果
# ═══════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG_FILE"
echo "━━━ 阶段三：发送执行报告通知 ━━━" | tee -a "$LOG_FILE"

python3 -c "
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

today = '$TODAY'
time_now = datetime.now().strftime('%H:%M:%S')

# 读取日志
log_path = os.path.expanduser(f'~/Documents/claude/自动化/daily-music/logs/{today}.log')
log_content = ''
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        log_content = f.read()

# 统计输出文件 + 逐首状态
output_dir = os.path.expanduser(f'~/Documents/claude/输出文档/歌曲/{today}/cover')
wav_count = 0
cover_dirs = []
song_details = []  # 每首歌详情
if os.path.exists(output_dir):
    for d in sorted(os.listdir(output_dir)):
        full = os.path.join(output_dir, d)
        if not os.path.isdir(full) or d.startswith('.'):
            continue
        cover_dirs.append(d)
        # 统计该歌曲的文件
        files = os.listdir(full)
        wavs = [f for f in files if f.endswith('.wav')]
        pngs = [f for f in files if f.endswith('.png')]
        lyrics = [f for f in files if 'lyrics' in f and f.endswith('.md')]
        wav_count += len(wavs)
        # 判断状态
        if len(wavs) > 0 and len(pngs) >= 2:
            status = '✅ 完成'
        elif len(wavs) > 0:
            status = '⚠️ WAV有但封面不全'
        else:
            status = '❌ 无WAV'
        song_details.append(f'<tr><td>{d}</td><td>{status}</td><td>{len(wavs)}</td><td>{len(pngs)}</td><td>{len(lyrics)}</td></tr>')

# 统计模型调用情况（从日志提取）
kie_calls = log_content.count('suno_client') if log_content else 0
kie_success = log_content.count('clip_ids') if log_content else 0
gemini_calls = log_content.count('gemini') if log_content else 0
doubao_calls = log_content.count('doubao') if log_content else 0
whisper_calls = log_content.count('whisper') + log_content.count('Whisper') if log_content else 0

songs_ok = sum(1 for d in song_details if '✅' in d)
songs_total = len(cover_dirs)

body = f'''
<html><body style=\"font-family: -apple-system, sans-serif; padding: 20px;\">
<h2>每日音乐任务执行报告 - {today}</h2>
<p>完成时间：{time_now}</p>

<h3>📊 总览</h3>
<table style=\"border-collapse: collapse; margin: 10px 0;\">
<tr><td style=\"padding: 4px 12px; font-weight: bold;\">交付歌曲</td><td>{songs_ok} / {songs_total} 首</td></tr>
<tr><td style=\"padding: 4px 12px; font-weight: bold;\">WAV文件</td><td>{wav_count} 个</td></tr>
<tr><td style=\"padding: 4px 12px; font-weight: bold;\">阶段一</td><td>{'$PHASE1_STATUS'}</td></tr>
<tr><td style=\"padding: 4px 12px; font-weight: bold;\">阶段二</td><td>{'$PHASE2_STATUS'}</td></tr>
</table>

<h3>🎵 逐首状态</h3>
<table style=\"border-collapse: collapse; width: 100%; font-size: 13px;\">
<tr style=\"background: #f0f0f0;\"><th style=\"padding: 6px; text-align: left;\">歌曲</th><th>状态</th><th>WAV</th><th>封面</th><th>歌词</th></tr>
{''.join(song_details) if song_details else '<tr><td colspan=\"5\">无产出</td></tr>'}
</table>

<h3>🔧 模型调取情况</h3>
<table style=\"border-collapse: collapse; font-size: 13px;\">
<tr><td style=\"padding: 4px 12px;\">Suno 直连</td><td>约 {kie_calls} 次调用，{kie_success} 次提交成功</td></tr>
<tr><td style=\"padding: 4px 12px;\">Gemini (写词/图片)</td><td>约 {gemini_calls} 次调用</td></tr>
<tr><td style=\"padding: 4px 12px;\">豆包 (歌名/封面)</td><td>约 {doubao_calls} 次调用</td></tr>
<tr><td style=\"padding: 4px 12px;\">Whisper (质检ASR)</td><td>约 {whisper_calls} 次调用</td></tr>
</table>

<h3>📁 输出目录</h3>
<p>~/Documents/claude/输出文档/歌曲/{today}/</p>

<hr>
<details>
<summary>点击查看完整日志（最后3000字符）</summary>
<pre style=\"font-size: 11px; background: #f5f5f5; padding: 10px; overflow-x: auto;\">{log_content[-3000:] if log_content else '日志为空'}</pre>
</details>
</body></html>
'''

msg = MIMEMultipart('alternative')
phase2 = '$PHASE2_STATUS'
status_icon = '✅' if '成功' in phase2 else '⚠️'
status_text = '成功' if '成功' in phase2 else '异常'
msg['Subject'] = f'{status_icon} [每日音乐任务] {today} | 交付 {songs_ok}/{songs_total}首 WAV {wav_count}个'
msg['From'] = '$SMTP_USER'
msg['To'] = '$NOTIFY_TO'
msg.attach(MIMEText(body, 'html', 'utf-8'))

try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login('$SMTP_USER', '$SMTP_PASS')
    server.sendmail('$SMTP_USER', '$NOTIFY_TO', msg.as_string())
    server.quit()
    print('✅ 通知邮件已发送到 $NOTIFY_TO')
except Exception as e:
    print(f'❌ 通知邮件发送失败: {e}')
" 2>&1 | tee -a "$LOG_FILE"

echo "=== 全流程完成 $(date +%H:%M:%S) ===" | tee -a "$LOG_FILE"
