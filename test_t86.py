"""
執行方式：python3 test_t86.py
用來診斷 T86 端點回傳內容
"""
import requests, json, sys
requests.packages.urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

# 取最近幾個交易日測試
from datetime import date, timedelta
test_dates = []
d = date.today()
for _ in range(7):
    if d.weekday() < 5:  # 只取週一～五
        test_dates.append(d.strftime('%Y%m%d'))
    d -= timedelta(days=1)

print('=' * 60)
print('T86 診斷工具')
print('=' * 60)

for date_str in test_dates[:3]:
    for select in ['ALL', 'ALLBUT0999', '']:
        param = f'&selectType={select}' if select else ''
        url = f'https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}{param}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            print(f'\n[date={date_str} selectType={select or "無"}]')
            print(f'  HTTP {r.status_code}')
            if r.status_code == 200:
                try:
                    d = r.json()
                    stat  = d.get('stat', '?')
                    rows  = len(d.get('data', []))
                    title = d.get('title', '')
                    fields = d.get('fields', [])
                    print(f'  stat={stat}, rows={rows}, title={title}')
                    print(f'  fields={fields}')
                    if rows > 0:
                        print(f'  first row={d["data"][0]}')
                        print(f'\n✅ 成功！日期={date_str} selectType={select or "無"}')
                        sys.exit(0)
                except Exception as e:
                    print(f'  JSON解析失敗: {e}')
                    print(f'  原始內容: {r.text[:200]}')
            else:
                print(f'  回應內容: {r.text[:200]}')
        except Exception as e:
            print(f'\n[date={date_str} selectType={select or "無"}] 連線失敗: {e}')

print('\n❌ 所有組合均失敗')
