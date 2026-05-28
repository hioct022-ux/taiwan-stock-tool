"""
完整診斷 T86 抓取＋儲存流程
執行：python3 test_t86_full.py
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/台股分析工具'))

import requests
requests.packages.urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

# ── 1. 確認資料庫日期 ──
from database import get_latest_price_date, get_t86_last_date, init_db
init_db()
twse_date = get_latest_price_date('2330')
last_t86  = get_t86_last_date()
print(f'[DB] TWSE最新日期（2330）: {twse_date}')
print(f'[DB] T86最後日期: {last_t86}')

if last_t86 and twse_date and last_t86 >= twse_date:
    print('=> 已有最新資料，清除後重新測試...')
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM t86_ranking')
    conn.commit()
    conn.close()
    print('=> 已清除 t86_ranking')

# ── 2. 抓資料 ──
if not twse_date:
    print('ERROR: 無法取得 TWSE 日期，請先更新收盤資料')
    sys.exit(1)

date_str = twse_date.replace('-', '')
url = f'https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL'
print(f'\n[HTTP] GET {url}')

try:
    resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
    print(f'[HTTP] status={resp.status_code}')
    data = resp.json()
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)

print(f'[JSON] stat={data.get("stat")} rows={len(data.get("data",[]))}')

rows_raw = data.get('data', [])
if not rows_raw:
    print('ERROR: 無資料列')
    sys.exit(1)

# ── 3. 解析前5筆 ──
print(f'\n[解析] 前5筆原始資料：')
for r in rows_raw[:5]:
    print(f'  {r}')

def clean_num(s):
    if not s or s in ('--', '-', '', 'X'):
        return 0.0
    try:
        return float(str(s).replace(',', '').replace('+', '').strip())
    except:
        return 0.0

def shares_to_lots(val):
    return int(clean_num(val) / 1000)

parsed = []
skipped = 0
for r in rows_raw:
    code = str(r[0]).strip()
    name = str(r[1]).strip()
    if not code or not code.isdigit():
        skipped += 1
        continue
    if len(r) < 12:
        skipped += 1
        continue
    fb    = shares_to_lots(r[2])
    fs    = shares_to_lots(r[3])
    fn    = shares_to_lots(r[4])
    tb    = shares_to_lots(r[8])
    ts    = shares_to_lots(r[9])
    tn    = shares_to_lots(r[10])
    dn    = shares_to_lots(r[11])
    total = shares_to_lots(r[18]) if len(r) > 18 else (fn + tn + dn)
    parsed.append({'code':code,'name':name,
                   'foreign_net':fn,'trust_net':tn,
                   'dealer_net':dn,'total_net':total})

print(f'\n[解析] 有效股票={len(parsed)} 筆，過濾掉={skipped} 筆')

# ── 4. 顯示投信買超前10 ──
by_trust = sorted(parsed, key=lambda x: x['trust_net'], reverse=True)
print(f'\n[投信買超 Top10]')
for i, r in enumerate(by_trust[:10], 1):
    print(f'  #{i} {r["code"]} {r["name"]:10s} 投信淨={r["trust_net"]:+,}張')

# ── 5. 存入 DB ──
from database import save_t86_ranking
save_t86_ranking(twse_date, parsed)
print(f'\n[DB] 已儲存 {len(parsed)} 筆到 t86_ranking')

# ── 6. 從 DB 讀回驗證 ──
from database import get_t86_ranking
rows_db, date_db = get_t86_ranking(sort_by='trust_net', top=5)
print(f'\n[DB驗證] 從DB讀回投信買超Top5（日期={date_db}）:')
for i, r in enumerate(rows_db, 1):
    print(f'  #{i} {r["code"]} {r["name"]:10s} 投信淨={r["trust_net"]:+,}張')

print('\n✅ 全部完成！請重新整理 Streamlit 後點「法人買超排行榜」')
