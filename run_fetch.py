#!/usr/bin/env python3
# ════════════════════════════════════════
# run_fetch.py　獨立更新腳本
# 每日由 launchd 在背景自動執行，不需要開 Streamlit
# 執行方式：python3 ~/台股分析工具/run_fetch.py
# ════════════════════════════════════════

import sys
import os

# 確保可以 import 專案的模組
sys.path.insert(0, os.path.expanduser('~/台股分析工具'))

from datetime import datetime

def is_trading_day():
    today = datetime.now()
    if today.weekday() >= 5:
        return False
    holidays = ['01-01','02-28','04-04','04-05','05-01','06-10','09-28','10-10']
    return today.strftime('%m-%d') not in holidays

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'\n[run_fetch] {now} 開始執行')

    if not is_trading_day():
        print('[run_fetch] 今日非交易日，跳過')
        return

    # 初始化資料庫
    try:
        from database import init_db
        init_db()
    except Exception as e:
        print(f'[run_fetch] DB 初始化失敗：{e}')
        return

    # 抓取資料
    try:
        from fetcher import fetch_all
        fetch_all()
        print('[run_fetch] 資料抓取完成')
    except Exception as e:
        print(f'[run_fetch] 資料抓取失敗：{e}')

    # 同步到 GitHub
    try:
        from github_sync import sync_to_github, is_github_configured
        if is_github_configured():
            sync_to_github()
            print('[run_fetch] GitHub 同步完成')
        else:
            print('[run_fetch] GitHub 未設定，略過')
    except Exception as e:
        print(f'[run_fetch] GitHub 同步失敗：{e}')

    print(f'[run_fetch] 完成 {datetime.now().strftime("%H:%M")}')

if __name__ == '__main__':
    main()
