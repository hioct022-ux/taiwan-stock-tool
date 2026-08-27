"""
一次性回填：修正 chips 表的投信/自營商欄位（欄位索引錯誤造成的污染）。

舊版 fetch_chips() 誤用欄位：
  trust_net  ← [13] 自營商賣出股數（永遠正值）→ 投信永遠「買超」
  dealer_net ← [7]  外資自營商買賣超（多數 0）→ 自營商永遠 0

本腳本重新向 TWSE T86 抓取近 N 個交易日，用正確索引覆寫。
執行：python3 backfill_chips_fix.py [天數，預設60]
執行後可刪除此檔案。
"""
import sys, time
from datetime import datetime, timedelta
import requests
from fetcher import HEADERS, clean_num
from database import save_chips, get_conn

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def fix_one_day(date_yyyymmdd, date_std):
    url = (f'https://www.twse.com.tw/rwd/zh/fund/T86'
           f'?date={date_yyyymmdd}&selectType=ALLBUT0999&response=json')
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        data = r.json()
    except Exception as e:
        print(f'  {date_std} 請求失敗：{e}')
        return 0
    if data.get('stat') != 'OK' or not data.get('data'):
        return 0

    n = 0
    for row in data['data']:
        try:
            code = row[0].strip()
            save_chips(code, date_std, {
                'foreign_buy':  round(clean_num(row[2]) / 1000),
                'foreign_sell': round(clean_num(row[3]) / 1000),
                'foreign_net':  round(clean_num(row[4]) / 1000),
                'trust_buy':    round(clean_num(row[8]) / 1000),
                'trust_sell':   round(clean_num(row[9]) / 1000),
                'trust_net':    round(clean_num(row[10]) / 1000),
                'dealer_buy':   round((clean_num(row[12]) + clean_num(row[15])) / 1000),
                'dealer_sell':  round((clean_num(row[13]) + clean_num(row[16])) / 1000),
                'dealer_net':   round(clean_num(row[11]) / 1000),
                'margin_balance': 0,
                'short_balance':  0,
            })
            n += 1
        except Exception:
            pass
    return n


# 取 DB 中已有 chips 資料的日期（只修正這些日期，不新增）
conn = get_conn()
dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM chips WHERE date >= date('now', ?) ORDER BY date DESC",
    (f'-{DAYS} days',)).fetchall()]
conn.close()

print(f'準備修正 {len(dates)} 個交易日的 chips 資料（近 {DAYS} 天）...\n')
total = 0
for d in dates:
    ymd = d.replace('-', '')
    n = fix_one_day(ymd, d)
    if n:
        print(f'  {d}：{n} 檔已修正')
        total += n
    time.sleep(0.6)   # TWSE 速率限制

print(f'\n共修正 {total} 筆')

# 驗證
conn = get_conn()
last = conn.execute('SELECT MAX(date) FROM chips').fetchone()[0]
row = conn.execute(
    'SELECT COUNT(*), SUM(CASE WHEN trust_net>0 THEN 1 ELSE 0 END), '
    'SUM(CASE WHEN trust_net<0 THEN 1 ELSE 0 END), '
    'SUM(trust_net), SUM(dealer_net), SUM(foreign_net) '
    'FROM chips WHERE date=?', (last,)).fetchone()
conn.close()
print(f'\n驗證 {last}：共 {row[0]} 檔')
print(f'  投信買超 {row[1]} 家 / 賣超 {row[2]} 家　（修正前應為 賣超 0 家）')
print(f'  市場合計：外資 {row[5]:,} 張　投信 {row[3]:,} 張　自營 {row[4]:,} 張')
print('  （自營商不再全為 0、投信有買有賣，即代表修正成功）')
