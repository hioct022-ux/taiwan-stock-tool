"""
測試除權息資料來源
執行：python3 test_exdiv2.py
"""
import requests, sys, os
from datetime import date, timedelta
requests.packages.urllib3.disable_warnings()
sys.path.insert(0, os.path.expanduser('~/台股分析工具'))

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
today = date.today()

print('【測試1】TWSE TWT49U 逐日查詢（近10個交易日）')
print('='*55)
found_twse = 0
for delta in range(10, -1, -1):
    d = today - timedelta(days=delta)
    if d.weekday() >= 5:
        continue
    url = f'https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&date={d.strftime("%Y%m%d")}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        data = r.json()
        stat = data.get('stat','?')
        rows = data.get('data', [])
        if stat == 'OK' and rows:
            print(f'  ✅ {d}  rows={len(rows)}  第一筆={rows[0][:4]}')
            found_twse += len(rows)
        else:
            print(f'  ❌ {d}  stat={stat}  rows={len(rows)}')
    except Exception as e:
        print(f'  ❌ {d}  錯誤: {e}')

print(f'\nTWSE 合計找到: {found_twse} 筆')

print()
print('【測試2】FinMind TaiwanStockDividend（近30天）')
print('='*55)
try:
    from config_local import FINMIND_TOKEN
    start = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    url = f'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockDividend&start_date={start}&token={FINMIND_TOKEN}'
    r = requests.get(url, timeout=15)
    data = r.json()
    records = data.get('data', [])
    print(f'  rows={len(records)}')
    if records:
        print(f'  第一筆: {records[0]}')
        print(f'  最後筆: {records[-1]}')
except Exception as e:
    print(f'  失敗: {e}')
