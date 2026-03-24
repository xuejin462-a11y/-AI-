#!/bin/zsh
# ─────────────────────────────────────────────────────────────────
# 一键激活所有定时任务 + 休眠唤醒
# 在 Mac 终端执行: bash ~/Documents/claude/自动化/daily-music/activate_tasks.sh
# ─────────────────────────────────────────────────────────────────

echo "=== 激活定时任务 ==="

# ── 1. 卸载旧任务（忽略不存在的情况）────────────────────────────
echo "[1/5] 清理旧任务..."
launchctl unload ~/Library/LaunchAgents/com.xuejin.musicchartmonitor.plist 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.xuejin.dailymusic.plist 2>/dev/null

# ── 2. 清理旧 crontab（daily-music 已迁移到 launchd）──────────
echo "[2/5] 清理旧 crontab..."
crontab -l 2>/dev/null | grep -v "daily_music.sh" | crontab - 2>/dev/null

# ── 3. 加载 launchd 任务 ─────────────────────────────────────
echo "[3/5] 加载 launchd 任务..."
launchctl load ~/Library/LaunchAgents/com.xuejin.musicchartmonitor.plist
launchctl load ~/Library/LaunchAgents/com.xuejin.dailymusic.plist

# 验证加载状态
echo "  音乐榜单监控:"
launchctl list | grep musicchart && echo "  ✅ 已加载" || echo "  ❌ 加载失败"
echo "  每日做歌:"
launchctl list | grep dailymusic && echo "  ✅ 已加载" || echo "  ❌ 加载失败"

# ── 4. 设置 pmset 休眠唤醒 ───────────────────────────────────
echo "[4/5] 设置休眠定时唤醒（需要管理员密码）..."
# 每天 11:55 唤醒（给 12:00 榜单监控留 5 分钟余量）
# 每天 17:55 唤醒（给 18:00 做歌任务留 5 分钟余量）
sudo pmset repeat wakeorpoweron MTWRFSU 11:55:00 wakeorpoweron MTWRFSU 17:55:00

echo "  当前 pmset repeat 设置:"
pmset -g sched

# ── 5. 完成 ──────────────────────────────────────────────────
echo ""
echo "[5/5] ✅ 全部完成！"
echo ""
echo "  📋 任务列表:"
echo "    12:00  音乐榜单交叉监控 (launchd)  → 邮件推送"
echo "    18:00  每日做歌系统     (launchd)  → Claude Code 自动执行"
echo ""
echo "  ⏰ 休眠唤醒:"
echo "    11:55  自动唤醒（为 12:00 任务准备）"
echo "    17:55  自动唤醒（为 18:00 任务准备）"
echo ""
echo "  🔍 查看状态:"
echo "    launchctl list | grep -E 'musicchart|dailymusic'"
echo "    pmset -g sched"
echo ""
echo "  📝 查看日志:"
echo "    tail -f ~/music_chart_monitor/monitor.log"
echo "    tail -f ~/Documents/claude/自动化/daily-music/logs/\$(date +%Y-%m-%d).log"
