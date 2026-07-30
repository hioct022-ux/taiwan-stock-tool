"""
一次性診斷腳本：檢查台指期夜盤資料為何抓不到。
執行後把印出的內容貼給我看，執行完可以刪除這個檔案。
"""
import requests
from datetime import datetime, timedelta

try:
    from config import FINMIND_TOKEN
except ImportError:
    FINMIND_TOKEN = ''

print(f'Token 是否存在：{bool(FINMIND_TOKEN)}')
print(f'Token 前20碼：{FINMIND_TOKEN[:20]}...' if FINMIND_TOKEN else '（無 token）')

if not FINMIND_TOKEN:
    print('❌ 沒有 token，config_local.py 可能被改掉或遺失')
else:
    start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    try:
        r = requests.get(
            'https://api.finmindtrade.com/api/v4/data',
            params={'dataset': 'TaiwanFuturesDaily', 'data_id': 'TX',
                    'start_date': start, 'token': FINMIND_TOKEN},
            timeout=15
        )
        print(f'HTTP 狀態碼：{r.status_code}')
        data = r.json()
        print(f"FinMind status：{data.get('status')}")
        print(f"FinMind msg：{data.get('msg')}")
        rows = data.get('data', [])
        print(f'資料筆數：{len(rows)}')
        if rows:
            print('最新 3 筆原始資料：')
            for row in rows[-3:]:
                print(' ', row)
            latest_date = max(row['date'] for row in rows)
            print(f'\n最新日期：{latest_date}')
            today_ym = datetime.now().strftime('%Y%m')
            print(f'本月（today_ym）：{today_ym}')
            latest_rows = [row for row in rows if row['date'] == latest_date]
            print(f'最新日期的所有 contract_date：{[row["contract_date"] for row in latest_rows]}')
            print(f'trading_session 種類：{set(row["trading_session"] for row in latest_rows)}')
        else:
            print('⚠️ FinMind 回傳空資料（可能額度用完 / 該 dataset 無資料）')
    except Exception as e:
        print(f'❌ 例外錯誤：{type(e).__name__}: {e}')
