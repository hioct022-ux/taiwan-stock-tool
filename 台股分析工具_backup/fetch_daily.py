#!/usr/bin/env python3
# ════════════════════════════════════════
# fetch_daily.py　每日收盤後自動抓資料
# 由 macOS launchd 在收盤後呼叫（14:30 Taiwan time）
# 不需要 Streamlit 啟動，可獨立在背景執行
# ════════════════════════════════════════

import sys
import os
import logging
from datetime import datetime

# 設定路徑
BASE_DIR = os.path.expanduser('~/台股分析工具')
sys.path.insert(0, BASE_DIR)

# 設定 log 檔（存在 data/ 目錄下）
LOG_PATH = os.path.join(BASE_DIR, 'data', 'auto_fetch.log')
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 同時輸出到終端機（方便除錯）
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)


def is_trading_day():
    today = datetime.now()
    # 週六、週日
    if today.weekday() >= 5:
        return False
    # 台灣常見國定假日（固定日期，農曆假日需另外維護）
    holidays = [
        '01-01',  # 元旦
        '02-28',  # 和平紀念日
        '04-04',  # 兒童節
        '05-01',  # 勞動節
        '06-10',  # 端午節（約略）
        '09-28',  # 中秋節（約略）
        '10-10',  # 國慶日
    ]
    if today.strftime('%m-%d') in holidays:
        return False
    return True


def main():
    logging.info('=== 台股分析工具每日自動更新 開始 ===')

    if not is_trading_day():
        logging.info('今日為非交易日，跳過更新')
        sys.exit(0)

    try:
        from fetcher import fetch_all
        fetch_all()
        logging.info('=== 每日自動更新 完成 ===')
    except Exception as e:
        logging.error(f'更新失敗：{e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
