#!/bin/zsh
# ─────────────────────────────────────────────────────────────────
# 月度 Suno 提示词调研与更新
# 每月1号自动执行：调研 Suno 最新最佳实践/新功能 → 更新知识库提示词规范
#
# launchd 调用: 每月1号 10:00
# 手动运行: zsh ~/Documents/claude/自动化/daily-music/monthly_suno_research.sh
# ─────────────────────────────────────────────────────────────────

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

SCRIPT_DIR="$HOME/Documents/claude/自动化/daily-music"
LOG_DIR="$SCRIPT_DIR/logs"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/monthly-research-$TODAY.log"

# SMTP（从 .env 加载，如未配置则留空）
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
NOTIFY_TO="${NOTIFY_TO:-}"

mkdir -p "$LOG_DIR"

echo "=== 月度 Suno 提示词调研启动 $TODAY $(date +%H:%M:%S) ===" | tee "$LOG_FILE"

# ── 开工通知邮件 ──
python3 -c "
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

today = datetime.now().strftime('%Y-%m-%d')
body = f'''
<html><body style=\"font-family: -apple-system, sans-serif; padding: 20px;\">
<h2>🔬 月度 Suno 提示词调研启动 - {today}</h2>
<p>任务内容：</p>
<ul>
<li>调研 Suno 最新最佳实践、新功能、社区经验</li>
<li>对比现有 Style Prompt 规范，识别需要更新的内容</li>
<li>更新知识库：Suno交互最佳实践.md、歌词prompt生成SOP.md</li>
</ul>
<p>预计耗时：10-20分钟</p>
</body></html>
'''
msg = MIMEText(body, 'html', 'utf-8')
msg['Subject'] = f'🔬 [月度调研] {today} Suno提示词调研 - 开始执行'
msg['From'] = '$SMTP_USER'
msg['To'] = '$NOTIFY_TO'
try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login('$SMTP_USER', '$SMTP_PASS')
    server.sendmail('$SMTP_USER', '$NOTIFY_TO', msg.as_string())
    server.quit()
    print('📧 开工通知已发送')
except Exception as e:
    print(f'❌ 通知发送失败: {e}')
" 2>&1 | tee -a "$LOG_FILE"

# ── Claude CLI 执行调研 ──
echo "[1] 启动 Claude CLI 调研..." | tee -a "$LOG_FILE"

CLAUDE_CMD="/Users/xuejin/.npm-global/bin/claude"

RESEARCH_PROMPT="你是每月定期执行的 Suno 提示词调研任务。请完成以下工作：

## 任务
1. **调研 Suno 最新动态**：
   - 搜索 Suno V5/V6 最新功能更新、新增标签、社区发现的最佳实践
   - 搜索来源：howtopromptsuno.com, Reddit r/SunoAI, Medium, Twitter/X
   - 关注：新增的 Meta Tags、Style Prompt 技巧、已废弃的用法、模型版本变化

2. **对比现有规范**：
   - 读取 ~/Documents/claude/知识库/Suno音乐创作/Suno交互最佳实践.md
   - 读取 ~/Documents/claude/知识库/Suno音乐创作/歌词prompt生成SOP.md
   - 识别哪些内容需要更新（新功能/废弃用法/更优写法）

3. **更新知识库**：
   - 直接编辑上述文件，加入新发现的最佳实践
   - 标注更新日期和来源
   - 删除已过时的内容

4. **输出调研报告**：
   - 列出本次发现的所有变化点
   - 标注哪些已更新到知识库
   - 保存报告到 ~/Documents/claude/输出文件/monthly-research/suno-research-$(date +%Y-%m).md

请直接执行，不要问问题。"

$CLAUDE_CMD -p "$RESEARCH_PROMPT" --allowedTools "Read,Write,Edit,Glob,Grep,Bash(readonly:false),WebSearch,WebFetch" 2>&1 | tee -a "$LOG_FILE"
CLAUDE_EXIT=$?

echo "[2] Claude CLI 退出码: $CLAUDE_EXIT" | tee -a "$LOG_FILE"

# ── 交付邮件 ──
REPORT_FILE="$HOME/Documents/claude/输出文件/monthly-research/suno-research-$(date +%Y-%m).md"

python3 -c "
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os

today = datetime.now().strftime('%Y-%m-%d')
exit_code = $CLAUDE_EXIT

# 读取调研报告
report = '（报告文件未找到）'
report_path = os.path.expanduser('$REPORT_FILE')
if os.path.exists(report_path):
    with open(report_path, 'r', encoding='utf-8') as f:
        report = f.read()

# 读取日志尾部
log_path = os.path.expanduser('$LOG_FILE')
log_tail = ''
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        log_tail = f.read()[-3000:]

status = '✅ 成功' if exit_code == 0 else '⚠️ 异常'
icon = '✅' if exit_code == 0 else '⚠️'

body = f'''
<html><body style=\"font-family: -apple-system, sans-serif; padding: 20px;\">
<h2>{icon} 月度 Suno 提示词调研完成 - {today}</h2>
<p>执行状态：{status}</p>

<h3>调研报告</h3>
<pre style=\"font-size: 13px; background: #f5f5f5; padding: 15px; border-radius: 6px; white-space: pre-wrap;\">{report}</pre>

<hr>
<details>
<summary>执行日志（最后3000字符）</summary>
<pre style=\"font-size: 11px; background: #f5f5f5; padding: 10px; overflow-x: auto;\">{log_tail}</pre>
</details>
</body></html>
'''

msg = MIMEText(body, 'html', 'utf-8')
msg['Subject'] = f'{icon} [月度调研] {today} Suno提示词调研 - {status}'
msg['From'] = '$SMTP_USER'
msg['To'] = '$NOTIFY_TO'
try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login('$SMTP_USER', '$SMTP_PASS')
    server.sendmail('$SMTP_USER', '$NOTIFY_TO', msg.as_string())
    server.quit()
    print('📧 交付邮件已发送')
except Exception as e:
    print(f'❌ 交付邮件发送失败: {e}')
" 2>&1 | tee -a "$LOG_FILE"

echo "=== 月度调研完成 $(date +%H:%M:%S) ===" | tee -a "$LOG_FILE"
