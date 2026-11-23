"""
核對大盤分析頁的「台指期夜盤漲跌 %」是不是對的（2026-11-23）

app.py 的 _fetch_taiex_futures() 直接拿 FinMind 的 spread / spread_per 當漲跌，
從來沒有自己算過一次。這支把近幾天的近月合約日盤／夜盤原始值印出來，
並用收盤價自己重算，和 FinMind 給的數字並排比對。

用法：cd ~/台股分析工具 ; python3 check_night_futures.py
（不會印出 token）
"""
import requests
from datetime import datetime, timedelta

from config import FINMIND_TOKEN

start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
r = requests.get('https://api.finmindtrade.com/api/v4/data',
                 params={'dataset': 'TaiwanFuturesDaily', 'data_id': 'TX',
                         'start_date': start, 'token': FINMIND_TOKEN}, timeout=30)
d = r.json()
print('FinMind status:', d.get('status'), d.get('msg'), '筆數', len(d.get('data', [])))
rows = [x for x in d.get('data', []) if '/' not in x['contract_date']]

# 每個日期的近月合約（與 app.py 同一套挑法）
by_date = {}
for x in rows:
    by_date.setdefault(x['date'], []).append(x)

prev_day_close = None
for dt in sorted(by_date):
    xs = by_date[dt]
    front = min(x['contract_date'] for x in xs)
    for x in sorted((x for x in xs if x['contract_date'] == front),
                    key=lambda x: x['trading_session'] != 'position'):
        sess = '夜盤' if x['trading_session'] == 'after_market' else '日盤'
        mine = ''
        if prev_day_close:
            mine = f'　自算 vs 前一日盤收 {(x["close"] - prev_day_close) / prev_day_close * 100:+.2f}%'
        print(f'{dt} {front} {sess}  收 {x["close"]:>8}  FinMind spread {x["spread"]:>8} '
              f'({x["spread_per"]:+.2f}%)  結算 {x.get("settlement_price")}  量 {x["volume"]}{mine}')
        if sess == '日盤':
            prev_day_close = x['close']
