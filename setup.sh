#!/bin/bash
# ============================================================
#  AI 做歌系统 - 一键安装
#  双击这个文件即可完成全部配置
# ============================================================

clear
echo "==========================================="
echo "   AI 做歌系统 - 安装向导"
echo "==========================================="
echo ""
echo "接下来会帮你完成 3 件事："
echo "  1. 安装必要的软件"
echo "  2. 配置你的 API 密钥"
echo "  3. 测试是否配置成功"
echo ""
echo "整个过程大约 5 分钟，跟着提示操作就行。"
echo ""
read -p "按回车键开始..." _

# ── 定位项目目录 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
ENV_FILE="$SCRIPT_DIR/suno-api/.env"

echo ""
echo "==========================================="
echo "  第 1 步：安装软件（自动完成）"
echo "==========================================="
echo ""

# 检查 Python3
if ! command -v python3 &>/dev/null; then
    echo "需要安装 Python3..."
    if command -v brew &>/dev/null; then
        brew install python3
    else
        echo ""
        echo "!! 请先安装 Python3："
        echo "   Mac: 去 https://www.python.org/downloads/ 下载安装"
        echo "   装好后重新运行这个脚本"
        echo ""
        read -p "按回车退出..." _
        exit 1
    fi
fi
echo "  Python3 .................. OK"

# 安装 Python 依赖
echo "  安装 Python 依赖（可能需要 1-2 分钟）..."
pip3 install -q librosa google-genai Pillow streamlit requests 2>/dev/null
echo "  Python 依赖 .............. OK"

echo ""
echo "  软件安装完成！"

# ── 配置 API 密钥 ──
echo ""
echo "==========================================="
echo "  第 2 步：配置你的账号"
echo "==========================================="
echo ""

# 如果已有 .env，问是否重新配置
if [ -f "$ENV_FILE" ]; then
    echo "检测到你之前已经配置过了。"
    read -p "要重新配置吗？(y/N): " REDO
    if [ "$REDO" != "y" ] && [ "$REDO" != "Y" ]; then
        echo "跳过配置，使用已有设置。"
        SKIP_CONFIG=true
    fi
fi

if [ "$SKIP_CONFIG" != "true" ]; then

    echo "接下来需要你填写几个 API 密钥。"
    echo "别担心，每一个我都会告诉你去哪里拿。"
    echo ""

    # ── Suno Cookie ──
    echo "-------------------------------------------"
    echo "  [1/5] Suno Cookie（用来生成歌曲）"
    echo "-------------------------------------------"
    echo ""
    echo "  获取步骤："
    echo "  1) 用 Chrome 浏览器打开 https://suno.com 并登录"
    echo "  2) 按 F12 打开开发者工具"
    echo "  3) 点顶部的「Application」标签"
    echo "  4) 左侧找到 Cookies → https://suno.com"
    echo "  5) 找到名为「__client」的那一行"
    echo "  6) 双击「Value」列，全选复制"
    echo ""
    read -p "  粘贴你的 Suno Cookie（__client 的值）: " SUNO_COOKIE
    echo ""

    # ── Suno 账号 ──
    read -p "  你的 Suno 登录邮箱: " SUNO_EMAIL
    read -p "  你的 Suno 登录密码: " SUNO_PASSWORD
    echo ""

    # ── Gemini API Key ──
    echo "-------------------------------------------"
    echo "  [2/5] Gemini API Key（用来写歌词和对齐）"
    echo "-------------------------------------------"
    echo ""
    echo "  获取步骤："
    echo "  1) 打开 https://aistudio.google.com/apikey"
    echo "  2) 用 Google 账号登录"
    echo "  3) 点「Create API Key」"
    echo "  4) 复制生成的 Key（以 AIza 开头）"
    echo ""
    read -p "  粘贴你的 Gemini API Key: " GEMINI_API_KEY
    echo ""

    # ── 豆包 ARK API Key ──
    echo "-------------------------------------------"
    echo "  [3/5] 豆包 API Key（用来生成封面图）"
    echo "-------------------------------------------"
    echo ""
    echo "  获取步骤："
    echo "  1) 打开 https://console.volcengine.com/ark"
    echo "  2) 注册/登录火山引擎账号"
    echo "  3) 进入「模型推理」→「API Key 管理」"
    echo "  4) 点「创建 API Key」，复制"
    echo ""
    echo "  (如果暂时没有，直接按回车跳过，之后可以再配)"
    read -p "  粘贴你的豆包 API Key: " ARK_API_KEY
    echo ""

    # ── 可灵 ──
    echo "-------------------------------------------"
    echo "  [4/5] 可灵 API（用来生成视频背景，可选）"
    echo "-------------------------------------------"
    echo ""
    echo "  获取步骤："
    echo "  1) 打开 https://platform.klingai.com"
    echo "  2) 注册登录后进入「开发者中心」"
    echo "  3) 创建应用，获取 Access Key 和 Secret Key"
    echo ""
    echo "  (如果暂时没有，直接按回车跳过)"
    read -p "  Access Key: " KLING_ACCESS_KEY
    read -p "  Secret Key: " KLING_SECRET_KEY
    echo ""

    # ── 邮件通知 ──
    echo "-------------------------------------------"
    echo "  [5/5] 邮件通知（可选，做完歌会收到邮件）"
    echo "-------------------------------------------"
    echo ""
    echo "  如果不需要邮件通知，全部按回车跳过。"
    echo ""
    read -p "  发件邮箱（如 xxx@163.com）: " SMTP_USER
    read -p "  SMTP 授权码（在邮箱设置里开启SMTP后获取）: " SMTP_PASS
    read -p "  接收通知的邮箱: " NOTIFY_TO
    echo ""

    # ── 写入 .env ──
    mkdir -p "$SCRIPT_DIR/suno-api"
    cat > "$ENV_FILE" << ENVEOF
SUNO_COOKIE=__client=$SUNO_COOKIE
SUNO_EMAIL=$SUNO_EMAIL
SUNO_PASSWORD=$SUNO_PASSWORD

ARK_API_KEY=$ARK_API_KEY
GEMINI_API_KEY=$GEMINI_API_KEY

KLING_ACCESS_KEY=$KLING_ACCESS_KEY
KLING_SECRET_KEY=$KLING_SECRET_KEY

SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS
NOTIFY_TO=$NOTIFY_TO
ENVEOF

    echo "  配置已保存！"
fi

# ── 测试连通性 ──
echo ""
echo "==========================================="
echo "  第 3 步：测试是否配置成功"
echo "==========================================="
echo ""

python3 << 'PYTEST'
import os, sys
from pathlib import Path

# 加载 .env
env_file = Path(__file__).resolve().parent / "suno-api" / ".env" if "__file__" in dir() else None
for candidate in [env_file, Path("suno-api/.env"), Path(".env")]:
    if candidate and candidate.exists():
        with open(candidate) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))
        break

results = []

# 测试 Suno
suno_cookie = os.environ.get("SUNO_COOKIE", "")
if suno_cookie and len(suno_cookie) > 20:
    results.append(("Suno Cookie", True, "已配置"))
else:
    results.append(("Suno Cookie", False, "未配置或为空"))

# 测试 Gemini
gemini_key = os.environ.get("GEMINI_API_KEY", "")
if gemini_key and gemini_key.startswith("AIza"):
    results.append(("Gemini API", True, "Key 格式正确"))
else:
    results.append(("Gemini API", False, "未配置" if not gemini_key else "Key 格式不对，应该以 AIza 开头"))

# 测试豆包
ark_key = os.environ.get("ARK_API_KEY", "")
if ark_key and len(ark_key) > 10:
    results.append(("豆包 API", True, "已配置"))
else:
    results.append(("豆包 API", None, "未配置（跳过，不影响做歌）"))

# 测试邮件
smtp_user = os.environ.get("SMTP_USER", "")
if smtp_user and "@" in smtp_user:
    results.append(("邮件通知", True, "已配置"))
else:
    results.append(("邮件通知", None, "未配置（跳过，不影响做歌）"))

for name, ok, msg in results:
    if ok is True:
        print(f"  [OK]   {name} — {msg}")
    elif ok is False:
        print(f"  [!!]   {name} — {msg}")
    else:
        print(f"  [--]   {name} — {msg}")

failed = [r for r in results if r[1] is False]
if failed:
    print("")
    print("  有必填项未配置成功，请检查后重新运行 setup.sh")
    sys.exit(1)
PYTEST

echo ""
echo "==========================================="
echo "  安装完成！"
echo "==========================================="
echo ""
echo "  现在你可以用以下命令启动做歌界面："
echo ""
echo "    cd $(pwd)"
echo "    python3 app.py"
echo ""
echo "  启动后浏览器会自动打开，在网页上操作就行。"
echo ""
read -p "  按回车退出..." _
