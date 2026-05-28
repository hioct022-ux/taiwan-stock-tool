# ════════════════════════════════════════
# scheduler.py　自動排程
# 負責每日自動抓取資料
# ════════════════════════════════════════

import time
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import AUTO_FETCH_HOUR, AUTO_FETCH_MINUTE

scheduler = BackgroundScheduler()
_started  = False

# ── 判斷今天是否為交易日 ─────────────────
def is_trading_day():
    today = datetime.now()
    # 週六、週日休市
    if today.weekday() >= 5:
        return False
    # 台灣國定假日（簡易版，主要排除元旦）
    # 完整假日需另外維護，這裡先處理最常見的
    holidays = [
        '01-01',  # 元旦
        '02-28',  # 和平紀念日
        '04-04',  # 兒童節
        '04-05',  # 清明節（約略）
        '05-01',  # 勞動節
        '06-10',  # 端午節（約略）
        '09-28',  # 中秋節（約略）
        '10-10',  # 國慶日
    ]
    today_str = today.strftime('%m-%d')
    if today_str in holidays:
        return False
    return True

# ── 每日排程工作 ─────────────────────────
def daily_job():
    now = datetime.now()
    print(f'\n[排程] {now.strftime("%Y-%m-%d %H:%M")} 開始執行每日更新')

    if not is_trading_day():
        print('[排程] 今日非交易日，跳過更新')
        return

    try:
        from fetcher import fetch_all
        fetch_all()
        print('[排程] 每日更新完成')
    except Exception as e:
        print(f'[排程] 更新失敗：{e}')

    # GitHub 備份（自動推送資料給雲端版使用）
    try:
        from github_sync import sync_to_github, is_github_configured
        if is_github_configured():
            sync_to_github()
            print('[排程] GitHub 備份完成')
        else:
            print('[排程] GitHub 未設定，跳過備份')
    except Exception as e:
        print(f'[排程] GitHub 備份失敗：{e}')

# ── 啟動排程 ────────────────────────────
def start_scheduler():
    global _started
    if _started:
        return

    scheduler.add_job(
        daily_job,
        CronTrigger(
            hour=AUTO_FETCH_HOUR,
            minute=AUTO_FETCH_MINUTE,
            day_of_week='mon-fri'
        ),
        id='daily_fetch',
        replace_existing=True
    )

    scheduler.start()
    _started = True
    print(f'[排程] 已啟動，每個交易日 '
          f'{AUTO_FETCH_HOUR:02d}:{AUTO_FETCH_MINUTE:02d} 自動更新')

# ── 停止排程 ────────────────────────────
def stop_scheduler():
    global _started
    if _started:
        scheduler.shutdown()
        _started = False
        print('[排程] 已停止')

# ── 手動觸發更新 ─────────────────────────
def manual_fetch():
    print('[手動更新] 開始...')
    thread = threading.Thread(target=daily_job)
    thread.daemon = True
    thread.start()
    return thread

# ── 取得下次排程時間 ─────────────────────
def get_next_run():
    if not _started:
        return None
    jobs = scheduler.get_jobs()
    if jobs:
        next_run = jobs[0].next_run_time
        if next_run:
            return next_run.strftime('%Y-%m-%d %H:%M')
    return None

# ── 取得資料狀態 ─────────────────────────
def get_data_status():
    from database import get_last_update, get_conn
    from config import DATA_EXPIRE_DAYS
    import pandas as pd

    last  = get_last_update()
    today = datetime.now().strftime('%Y-%m-%d')

    # 從 prices 表讀取 TWSE 上市股票的實際收盤日
    # 以台積電(2330)為基準：必然是上市股，代表 TWSE 真正更新的最新交易日
    # 避免被上櫃(TPEx)的不同更新時間所干擾（TPEx 盤後更新較快）
    try:
        conn = get_conn()
        row  = conn.execute("SELECT MAX(date) FROM prices WHERE code='2330'").fetchone()
        data_date = row[0] if row and row[0] else None
        if not data_date:   # 首次安裝尚無 2330 時 fallback 到整體 MAX
            row = conn.execute('SELECT MAX(date) FROM prices').fetchone()
            data_date = row[0] if row and row[0] else None
        conn.close()
    except:
        data_date = None

    last_time = last.get('updated_at', '') if last else ''

    if not data_date:
        return {
            'status':    'error',
            'label':     '❌ 尚無資料，請先手動更新',
            'color':     'red',
            'data_date': None,
            'last_time': last_time
        }

    # 計算實際資料落後幾個交易日
    try:
        d1        = pd.Timestamp(data_date)
        d2        = pd.Timestamp(today)
        diff_days = len(pd.bdate_range(d1, d2)) - 1
    except:
        diff_days = 0

    if not is_trading_day():
        # 休市日：資料是上個交易日屬正常
        return {
            'status':    'holiday',
            'label':     f'📅 今日休市　最新收盤：{data_date}',
            'color':     'blue',
            'data_date': data_date,
            'last_time': last_time
        }
    elif data_date == today:
        return {
            'status':    'ok',
            'label':     f'✅ 今日收盤資料已更新　{data_date}',
            'color':     'green',
            'data_date': data_date,
            'last_time': last_time
        }
    elif diff_days <= 1:
        # 交易日但今日資料尚未出現（TWSE 未發布或時間未到）
        return {
            'status':    'pending',
            'label':     f'⏳ TWSE 尚未發布今日資料　最新收盤：{data_date}',
            'color':     'orange',
            'data_date': data_date,
            'last_time': last_time
        }
    elif diff_days <= DATA_EXPIRE_DAYS:
        return {
            'status':    'pending',
            'label':     f'⚠️ 資料落後 {diff_days} 個交易日　最新收盤：{data_date}',
            'color':     'orange',
            'data_date': data_date,
            'last_time': last_time
        }
    else:
        return {
            'status':    'error',
            'label':     f'❌ 資料已過期（落後 {diff_days} 個交易日）　最新收盤：{data_date}',
            'color':     'red',
            'data_date': data_date,
            'last_time': last_time
        }


if __name__ == '__main__':
    print(f'排程設定：每個交易日 '
          f'{AUTO_FETCH_HOUR:02d}:{AUTO_FETCH_MINUTE:02d} 自動更新')
    print('scheduler.py 載入成功')
