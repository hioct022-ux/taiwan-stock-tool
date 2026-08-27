#!/bin/bash
# 台股分析工具備份腳本
# 每次執行覆蓋上次備份，只保留一份

BACKUP_DIR="$HOME/台股分析工具_backup"
SRC_DIR="$HOME/台股分析工具"

echo "🔄 開始備份..."

mkdir -p "$BACKUP_DIR"

# 完整同步整個專案（排除 .git 資料夾，避免備份 git 歷史）
rsync -a --delete \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  "$SRC_DIR/" "$BACKUP_DIR/"

# 記錄備份時間
date "+%Y-%m-%d %H:%M:%S" > "$BACKUP_DIR/backup_time.txt"

echo "✅ 備份完成：$BACKUP_DIR"
echo "   總大小：$(du -sh "$BACKUP_DIR" | cut -f1)"
echo "   stock.db：$(du -sh "$BACKUP_DIR/data/stock.db" 2>/dev/null | cut -f1)"
echo "   時間：$(cat "$BACKUP_DIR/backup_time.txt")"
