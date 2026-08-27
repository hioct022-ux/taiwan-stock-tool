#!/bin/bash
# ════════════════════════════════════════
# run.sh　一鍵啟動腳本
# 雙擊或在終端機執行此檔案啟動程式
# ════════════════════════════════════════

echo "================================"
echo "  台股投資分析工具 v2.1"
echo "================================"

# 切換到專案目錄
cd ~/台股分析工具

# 初始化資料庫
echo "初始化資料庫..."
python3 database.py

# 啟動 Streamlit
echo "啟動介面..."
echo "瀏覽器將自動開啟 http://localhost:8501"
echo "按 Control+C 可停止程式"
echo "================================"

streamlit run app.py \
    --server.port 8501 \
    --server.headless false \
    --browser.gatherUsageStats false
