#!/bin/zsh
# Melody平台歌曲下载脚本
# 每天20:00运行，下载song_id为空且属于6位指定艺人的歌曲
# 只下载新增内容（已下载的跳过）
# 失败时发邮件通知

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

DESKTOP="$HOME/Desktop"
RECORD_FILE="$HOME/Documents/claude/自动化/daily-music/melody_downloaded_ids.txt"
LOG_FILE="$HOME/Documents/claude/自动化/daily-music/logs/melody-download-$(date +%Y-%m-%d).log"
TODAY=$(date +%Y-%m-%d)

# SMTP（从 .env 加载，如未配置则留空）
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
NOTIFY_TO="${NOTIFY_TO:-}"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$RECORD_FILE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_alert_email() {
    local subject="$1"
    local body="$2"
    python3 << EMAILEOF
import smtplib
from email.mime.text import MIMEText
msg = MIMEText("""$body""", 'plain', 'utf-8')
msg['Subject'] = "$subject"
msg['From'] = "$SMTP_USER"
msg['To'] = "$NOTIFY_TO"
try:
    server = smtplib.SMTP_SSL('smtp.163.com', 465)
    server.login("$SMTP_USER", "$SMTP_PASS")
    server.sendmail("$SMTP_USER", "$NOTIFY_TO", msg.as_string())
    server.quit()
    print('[INFO] Alert email sent')
except Exception as e:
    print(f'[WARN] Email failed: {e}')
EMAILEOF
}

log "=== Melody下载任务开始 ==="

RESULT_FILE="/tmp/melody_download_result_$$.json"
export RESULT_FILE

python3 << 'PYEOF'
import json, os, subprocess, sys, urllib.request

API_BASE = "https://melody.panshi-gy.netease.com/api"
DESKTOP = os.path.expanduser("~/Desktop")
TODAY = __import__('datetime').date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = os.path.join(DESKTOP, f"{TODAY}-待上传")
os.makedirs(OUTPUT_DIR, exist_ok=True)
RECORD_FILE = os.path.expanduser("~/Documents/claude/自动化/daily-music/melody_downloaded_ids.txt")
RESULT_FILE = os.environ.get("RESULT_FILE", "/tmp/melody_download_result.json")
# 从Melody API动态获取全部艺人映射
ARTIST_MAP = {}
_apage = 1
while True:
    _aurl = f"{API_BASE}/artist/list?page={_apage}"
    with urllib.request.urlopen(_aurl, timeout=30) as _aresp:
        _adata = json.loads(_aresp.read())
    _artists = _adata.get("artists", [])
    if not _artists:
        break
    for _a in _artists:
        ARTIST_MAP[_a["id"]] = _a["artist_name"].strip()
    if len(ARTIST_MAP) >= _adata.get("total", 0):
        break
    _apage += 1
print(f"[INFO] 已获取 {len(ARTIST_MAP)} 个艺人映射")
# 只下载5位音乐人的歌曲
TARGET_NAMES = {"树离suliii_", "屿川", "晴日西多士", "S1ent", "靓仔阿辉Rex"}
TARGET_IDS = {aid for aid, name in ARTIST_MAP.items() if name in TARGET_NAMES}
print(f"[INFO] 目标艺人ID: {TARGET_IDS} ({', '.join(TARGET_NAMES)})")

result = {"status": "ok", "total": 0, "success": 0, "failed": [], "error": None}

downloaded = set()
if os.path.exists(RECORD_FILE):
    with open(RECORD_FILE) as f:
        downloaded = {line.strip() for line in f if line.strip()}

all_songs = []
page = 1
try:
    while True:
        url = f"{API_BASE}/song/list?limit=50&page={page}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        songs = data.get("songs", [])
        if not songs:
            break
        all_songs.extend(songs)
        total = data.get("total", 0)
        # API每页固定返回10条，用page翻页
        unique_so_far = len({s["id"] for s in all_songs})
        print(f"  page={page}: +{len(songs)} songs, unique={unique_so_far}/{total}")
        if unique_so_far >= total:
            break
        page += 1
except Exception as e:
    result["status"] = "error"
    result["error"] = f"API请求失败: {e}"
    with open(RESULT_FILE, "w") as f:
        json.dump(result, f)
    print(f"[ERROR] {result['error']}")
    sys.exit(1)

# 去重（API可能返回重复数据）
all_songs = list({s["id"]: s for s in all_songs}.values())
print(f"[INFO] 平台总歌曲数: {len(all_songs)}")

targets = []
for s in all_songs:
    if s.get("song_id") is not None:
        continue
    if str(s["id"]) in downloaded:
        continue
    if s.get("artist_id") not in TARGET_IDS:
        continue
    targets.append(s)

targets = list({s["id"]: s for s in targets}.values())
result["total"] = len(targets)
print(f"[INFO] 待下载新歌: {len(targets)} 首")

if not targets:
    print("[INFO] 没有新歌需要下载")
    with open(RESULT_FILE, "w") as f:
        json.dump(result, f)
    sys.exit(0)

for song in targets:
    name = song["song_name"]
    artist = ARTIST_MAP.get(song["artist_id"], "未分配") if song.get("artist_id") else "未分配"
    base_name = f"{artist}-{name}".replace("/", "_").replace("\\", "_")

    nos_url = song.get("nos_url", "")
    cover_url = song.get("album_cover", "")

    print(f"\n[DOWN] {base_name}")
    ok = True

    if nos_url:
        wav_path = os.path.join(OUTPUT_DIR, f"{base_name}.wav")
        r = subprocess.run(["curl", "-sL", "-o", wav_path, nos_url], capture_output=True, timeout=120)
        size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0
        if size > 1000:
            print(f"  WAV: {size/1024/1024:.1f} MB OK")
        else:
            print(f"  WAV: FAILED (size={size})")
            ok = False

    if cover_url:
        png_path = os.path.join(OUTPUT_DIR, f"{base_name}.png")
        r = subprocess.run(["curl", "-sL", "-o", png_path, cover_url], capture_output=True, timeout=60)
        size = os.path.getsize(png_path) if os.path.exists(png_path) else 0
        if size > 100:
            print(f"  PNG: {size/1024:.0f} KB OK")
        else:
            print(f"  PNG: FAILED (size={size})")
            ok = False

    if ok:
        with open(RECORD_FILE, "a") as f:
            f.write(f"{song['id']}\n")
        result["success"] += 1
    else:
        result["failed"].append(base_name)

print(f"\n[DONE] 成功下载 {result['success']}/{len(targets)} 首")

if result["failed"]:
    result["status"] = "partial_fail"

with open(RESULT_FILE, "w") as f:
    json.dump(result, f)
PYEOF

PYTHON_EXIT=$?

if [ $PYTHON_EXIT -ne 0 ]; then
    log "[ERROR] 脚本执行失败 exit=$PYTHON_EXIT"
    send_alert_email \
        "🚨 [Melody下载] $TODAY 执行失败" \
        "Melody歌曲下载脚本执行失败。\n\n错误退出码: $PYTHON_EXIT\n\n你需要做什么:\n1. 检查日志: $LOG_FILE\n2. 确认 melody.panshi-gy.netease.com 是否可访问\n3. 手动运行: zsh ~/Documents/claude/自动化/daily-music/melody_download.sh"
elif [ -f "$RESULT_FILE" ]; then
    RESULT_STATUS=$(python3 -c "import json; print(json.load(open('$RESULT_FILE'))['status'])")
    RESULT_TOTAL=$(python3 -c "import json; print(json.load(open('$RESULT_FILE'))['total'])")
    RESULT_SUCCESS=$(python3 -c "import json; print(json.load(open('$RESULT_FILE'))['success'])")
    RESULT_FAILED=$(python3 -c "import json; print(','.join(json.load(open('$RESULT_FILE'))['failed']))")
    RESULT_ERROR=$(python3 -c "import json; print(json.load(open('$RESULT_FILE')).get('error',''))")

    if [ "$RESULT_STATUS" = "error" ]; then
        log "[ERROR] $RESULT_ERROR"
        send_alert_email \
            "🚨 [Melody下载] $TODAY API异常" \
            "Melody API请求失败。\n\n错误: $RESULT_ERROR\n\n你需要做什么:\n1. 确认 melody.panshi-gy.netease.com 是否可访问\n2. 手动运行: zsh ~/Documents/claude/自动化/daily-music/melody_download.sh"
    elif [ "$RESULT_STATUS" = "partial_fail" ]; then
        log "[WARN] 部分失败: $RESULT_FAILED"
        send_alert_email \
            "⚠️ [Melody下载] $TODAY 部分失败 | 成功${RESULT_SUCCESS}/${RESULT_TOTAL}" \
            "Melody歌曲下载部分失败。\n\n成功: $RESULT_SUCCESS / $RESULT_TOTAL\n失败歌曲: $RESULT_FAILED\n\n你需要做什么:\n1. 检查日志: $LOG_FILE\n2. NOS链接可能已过期，需在Melody平台重新生成\n3. 手动重试: zsh ~/Documents/claude/自动化/daily-music/melody_download.sh"
    else
        log "[OK] 完成: 新歌${RESULT_SUCCESS}首 (待下载${RESULT_TOTAL}首)"
    fi
    rm -f "$RESULT_FILE"
fi

log "=== Melody下载任务结束 ==="
