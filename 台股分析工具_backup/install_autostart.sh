#!/bin/bash
# ════════════════════════════════════════
# install_autostart.sh　安裝開機自動排程
# 每天收盤後（15:30）自動抓資料
#
# 使用方式：
#   chmod +x ~/台股分析工具/install_autostart.sh
#   ~/台股分析工具/install_autostart.sh
# ════════════════════════════════════════

set -e

PLIST_LABEL="com.twstock.daily-fetch"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FETCH_SCRIPT="${SCRIPT_DIR}/fetch_daily.py"
LOG_DIR="${SCRIPT_DIR}/data"

echo "================================"
echo "  台股分析工具 自動排程安裝"
echo "================================"

# 確保 data 目錄存在
mkdir -p "$LOG_DIR"

# 偵測 python3 路徑（按優先順序）
PYTHON3=""
for p in \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/usr/bin/python3" \
    "$(which python3 2>/dev/null)"
do
    if [ -x "$p" ]; then
        PYTHON3="$p"
        break
    fi
done

if [ -z "$PYTHON3" ]; then
    echo "❌ 找不到 python3，請確認 Python 已安裝"
    exit 1
fi

echo "✅ 使用 Python：$PYTHON3"
echo "✅ 腳本路徑：$FETCH_SCRIPT"
echo "✅ plist 路徑：$PLIST_PATH"

# 確保 LaunchAgents 目錄存在
mkdir -p "$HOME/Library/LaunchAgents"

# 建立 plist 檔案
cat > "$PLIST_PATH" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <!-- 執行程式 -->
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON3}</string>
        <string>${FETCH_SCRIPT}</string>
    </array>

    <!-- 週一到週五 15:30 執行（收盤後資料上線） -->
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
    </array>

    <!-- 工作目錄 -->
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <!-- Log 輸出 -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/auto_fetch.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/auto_fetch_error.log</string>

    <!-- 環境變數 -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>LANG</key>
        <string>zh_TW.UTF-8</string>
    </dict>
</dict>
</plist>
PLIST_EOF

echo "✅ plist 檔案已建立"

# 卸載舊版（如果存在）
if launchctl list | grep -q "$PLIST_LABEL" 2>/dev/null; then
    echo "  移除舊版排程..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# 載入新版
launchctl load "$PLIST_PATH"
echo "✅ 排程已啟動"

echo ""
echo "================================"
echo "  安裝完成！"
echo ""
echo "  排程時間：週一到週五 15:30 自動更新"
echo "  Log 檔案：${LOG_DIR}/auto_fetch.log"
echo ""
echo "  常用指令："
echo "  查看狀態：launchctl list | grep twstock"
echo "  手動測試：python3 ${FETCH_SCRIPT}"
echo "  查看 log：tail -f ${LOG_DIR}/auto_fetch.log"
echo "  移除排程：launchctl unload ${PLIST_PATH}"
echo "================================"
