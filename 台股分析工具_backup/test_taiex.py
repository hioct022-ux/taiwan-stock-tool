"""
測試大盤指數資料端點
執行：python3 test_taiex.py
"""
import requests, json
from datetime import date, timedelta
requests.packages.urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

today = date.today().strftime('%Y%m%d')
last_month = (date.today() - timedelta(days=30)).strftime('%Y%m%d')

urls = [
    ('TAIEX月資料',  f'https://www.twse.com.tw/rwd/zh/TAIEX/TAIEX?response=json&date={today}'),
    ('TAIEX月資料2', f'https://www.twse.com.tw/rwd/zh/TAIEX/TAIEX?response=json&date={last_month}'),
    ('MI_INDEX',    f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date={today}&type=MS'),
    ('5MINS_HIST',  f'https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date={today}'),
]

for label, url in urls:
    print(f'\n[{label}]')
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        print(f'  HTTP {r.status_code}  len={len(r.text)}')
        if r.status_code == 200 and r.text.strip():
            d = r.json()
            stat = d.get('stat','?')
            # 找資料
            data = d.get('data', d.get('tables', []))
            if isinstance(data, list):
                print(f'  stat={stat}  rows={len(data)}')
                if data:
                    first = data[0] if not isinstance(data[0], dict) else data[0].get('data',[[]])[0]
                    print(f'  fields={d.get("fields",d.get("title",""))}')
                    print(f'  first={first}')
                    print(f'  ✅ 有資料！')
    except Exception as e:
        print(f'  錯誤: {e}')
