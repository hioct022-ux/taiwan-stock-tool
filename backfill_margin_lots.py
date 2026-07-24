"""
一次性補齊 market_margin 表的 margin_lots 欄位（張，融資餘額）。
修正 Signal 10「融資賣出比例」單位錯誤（原本誤用 margin_balance 億元當分母）。
執行後可刪除此檔案。
"""
import time
from datetime import datetime, timedelta
from fetcher import _parse_market_margin_response, HEADERS
from database import save_market_margin
import requests

updated = 0
for days_back in range(0, 20):
    d = datetime.now() - timedelta(days=days_back)
    if d.weekday() >= 5:
        continue
    ymd = d.strftime('%Y%m%d')
    url = f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=MS&response=json'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        date_str, result = _parse_market_margin_response(r.json(), d.strftime('%Y-%m-%d'))
        if date_str and result:
            save_market_margin(date_str, result)
            print(f'{date_str}: margin_sell={result["margin_sell"]:,} 張　'
                  f'margin_lots={result["margin_lots"]:,} 張　'
                  f'margin_balance={result["margin_balance"]:,} 億元　'
                  f'→ 正確比例={result["margin_sell"]/result["margin_lots"]*100 if result["margin_lots"] else 0:.2f}%')
            updated += 1
    except Exception as e:
        print(f'{ymd} 失敗：{e}')
    time.sleep(0.3)

print(f'\n共補正 {updated} 筆')
