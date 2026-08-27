"""
測試除權息資料端點
執行：python3 test_exdiv.py
"""
import requests, json
from datetime import date, timedelta
requests.packages.urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

# 計算近一個月日期範圍
today    = date.today()
one_month_ago = today - timedelta(days=30)
start = one_month_ago.strftime('%Y%m%d')
end   = today.strftime('%Y%m%d')

# 試幾個可能的端點
urls = [
    f'https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&strDate={start}&endDate={end}',
    f'https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json',
    f'https://www.twse.com.tw/exchangeReport/TWT49U?response=json&strDate={start}&endDate={end}',
    f'https://openapi.twse.com.tw/v1/exRight/TWT49U',
]

for url in urls:
    print(f'\nTEST: {url[:80]}...')
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        print(f'  HTTP {r.status_code}')
        if r.status_code == 200:
            try:
                d = r.json()
                stat  = d.get('stat', d.get('status', '?'))
                rows  = len(d.get('data', d if isinstance(d, list) else []))
                fields = d.get('fields', [])
                print(f'  stat={stat} rows={rows}')
                print(f'  fields={fields[:8]}')
                data_sample = d.get('data', d if isinstance(d, list) else [])
                if data_sample:
                    print(f'  first row={data_sample[0]}')
                    print(f'✅ 成功！')
                    break
            except Exception as e:
                print(f'  JSON解析失敗: {e}')
                print(f'  原始: {r.text[:200]}')
    except Exception as e:
        print(f'  連線失敗: {e}')
