#!/bin/bash
# 台股每日自動抓資料腳本
# 由 macOS cron 在 16:30 呼叫，完全獨立於 Streamlit

PROJECT_DIR="$HOME/台股分析工具"
LOG_FILE="$PROJECT_DIR/data/cron_fetch.log"
PYTHON=$(which python3)

# 切換到專案目錄
cd "$PROJECT_DIR" || exit 1

# 記錄開始時間
echo "=============================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 開始自動抓資料" >> "$LOG_FILE"

# 執行資料抓取
$PYTHON -c "
from scheduler import is_trading_day
from datetime import datetime

if not is_trading_day():
    print('今日非交易日，跳過')
    exit(0)

from fetcher import fetch_all
fetch_all()
print('完成')
" >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 結束" >> "$LOG_FILE"
