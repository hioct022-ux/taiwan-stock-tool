#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_monthly_revenue.py — 從 MOPS 回填全市場月營收（獨立腳本，預設試跑）

════════════════════════════════════════════════════════════════════════
背景／為什麼做這個（2026-10-06）
════════════════════════════════════════════════════════════════════════

2026-09-23 量到：個股評分與**未來**報酬 corr = 0、與**過去** = +0.25 → 它是後照鏡。
而看組成就知道為什麼，且比原本以為的更徹底：

    技術面 40%  = 價格的函數
    籌碼面 35%  = 昨天的成交結果
    基本面 25%  = PE / PB / 殖利率 → **分母是價格、分子一季才動一次**
                  ⇒ 它的「日變動」幾乎也全部來自價格

**⇒ 三面加權裡，真正獨立於價格的成分幾乎是零。這不是調參能解決的。**

月營收是第一個**真正正交**的候選輸入：營運事實、分子自己會動、有明確公布節奏。
`probe_month_revenue.py` + `probe_mops_structure.py`（2026-10-06）已實測確認可用。

**這支只負責拿資料，不測訊號、不碰 `fetcher.py` / `app.py`。**
理由：前六次型態類提案全被否決，訊號測完有效才值得接入系統。

════════════════════════════════════════════════════════════════════════
⚠️ 三個已實測的細節，不可憑直覺改
════════════════════════════════════════════════════════════════════════

1. **編碼是 `cp950`，不是 `big5`。** 實測 `big5` 嚴格解碼**失敗**、`cp950` 成功
   （cp950 是 Big5 的微軟擴充字集）。專案舊程式對 TAIFEX 用
   `big5, errors='ignore'`——**照抄到這裡會靜默丟字**，公司名缺字。

2. **年月守衛必須「先去標籤再 regex」。** `probe_month_revenue.py` 抓不到標題年月，
   是因為對未去標籤的 HTML 做 search（標題文字被標籤切開）。
   去標籤後開頭就是 `上市公司115年8月份(累計與當月)營業收入統計表`。
   ⚠️ **沒有日期守衛的歷史抓取會靜默抓錯月份還回報成功**（陷阱41 的教訓）。

3. **資料列的辨識：11 欄 且 [0] 是 4 碼代號。**
   同一頁有 34 個 `<table>`（一個產業一張），列的欄數有 2（產業標題）、
   4（表頭上層）、10（表頭，**會出現兩次**）、11（資料）。

   欄位對應（實測 2330 那列）：
   ```
   [0] 公司代號  [1] 公司名稱  [2] 當月營收  [3] 上月營收  [4] 去年當月營收
   [5] 上月比較增減(%)  [6] 去年同月增減(%)
   [7] 當月累計營收  [8] 去年累計營收  [9] 前期比較增減(%)  [10] 備註
   ```
   ★ `[4]` 與 `[6]` 直接給了去年同月與 YoY%，**不必自己算、不用擔心基期對不上**。

════════════════════════════════════════════════════════════════════════
🚨 `avail_date`：防 look-ahead 的設計，絕對不要「優化」掉
════════════════════════════════════════════════════════════════════════

**沒有任何來源給逐股公布日。** 兩個看起來像公布日的欄位都不是：

  • FinMind `create_time`：實測 2 月與 3 月營收**共用** `2026-04-21`
    ⇒ 那是 FinMind 批次補寫的時間，不是公司公告日
  • FinMind `date`：= 營收月份的「次月 1 日」（date 2026-09-01 ↔ revenue_month 8）
    而法規是「每月 **10 日前**公布上月營收」⇒ 直接用它等於偷看最多 10 天
  • MOPS 的「出表日期」：是 MOPS 產生報表的日期（實測 115/10/06），與營收月份無關

**所以一律採保守規則：營收月 M 的資料，`avail_date` = (M+1) 月 11 日。**
法規上 10 日前必須公布完，11 日一定全部到位 ⇒ **結構上不可能 look-ahead。**

把它存成**實體欄位**是刻意的——這樣任何查詢都不可能忘記加這個限制。
比「註解提醒要加 10 天」安全得多。

⚠️ **日後若有人想改成用 `date` 欄「這樣不是更早能用嗎」，那一改就是偷看 10 天，
   而且不會報錯、不會有任何跡象。** 這是本檔最容易被破壞的一行。

而這個代價其實不算代價：這個系統本來就是盤後資料、隔日才能動作。
**對它有用的訊號，必須在公布 10 天後還存在**——那是更嚴格、也更貼合實際的檢定。

════════════════════════════════════════════════════════════════════════
⚠️ 日後測訊號時的樣本數陷阱（先寫在這裡，免得被誤用）
════════════════════════════════════════════════════════════════════════

**月營收是「全市場同一個月一起公布」。**
105 個月 × 約 500 檔 ≈ 52,500 筆，但**不是 52,500 個獨立樣本**。
同一個月的所有觀察共享同一個市場狀態，彼此高度相關。

這正是 2026-09-15「量能水位」那次的病根（當時 n=15 實際只有 n≈4）。

**正確設計是 Fama-MacBeth：**
```
每個月  →  算一次「高 YoY 組 − 低 YoY 組」的報酬差
然後    →  檢定那 105 個月度差值的時間序列
有效樣本 = 105 個月
標準誤   = SD(月度差值) / √105
```
**不可以把 52,500 筆 pool 起來算標準誤**，那會把雜訊帶低估一個數量級。

用法：
    python3 backfill_monthly_revenue.py              # 試跑，只報告不寫入
    python3 backfill_monthly_revenue.py --apply      # 實際寫入
    python3 backfill_monthly_revenue.py --apply --from 112 1   # 指定起始民國年月
    python3 backfill_monthly_revenue.py --apply --otc          # 連上櫃一起抓
"""

import re
import sqlite3
import sys
import time
from datetime import datetime

import requests

DB = 'data/stock.db'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
TIMEOUT = 30
SLEEP = 1.2              # MOPS 比 TWSE 寬鬆，但別打太快
FROM_ROC, FROM_MON = 107, 1     # 實測民國107年拿得到；再往前沒驗過
ENCODING = 'cp950'       # ⚠️ 實測：big5 嚴格解碼失敗，必須 cp950


# ══════════════════════════════════════════════════════════════════
# 資料表
# ══════════════════════════════════════════════════════════════════
DDL = '''
CREATE TABLE IF NOT EXISTS monthly_revenue (
    code            TEXT    NOT NULL,
    rev_year        INTEGER NOT NULL,      -- 西元年（營收所屬年）
    rev_month       INTEGER NOT NULL,      -- 營收所屬月
    avail_date      TEXT    NOT NULL,      -- ★ 最早可用日 = 次月11日（防 look-ahead）
    name            TEXT,
    revenue         INTEGER,               -- 當月營收（千元）
    revenue_prev_m  INTEGER,               -- 上月營收
    revenue_last_y  INTEGER,               -- 去年當月營收
    mom_pct         REAL,                  -- 上月比較增減 %
    yoy_pct         REAL,                  -- ★ 去年同月增減 %（MOPS 直接給）
    cum_revenue     INTEGER,               -- 當月累計營收
    cum_last_y      INTEGER,               -- 去年累計營收
    cum_yoy_pct     REAL,                  -- 前期比較增減 %
    market          TEXT,                  -- 'TWSE' | 'TPEx'
    note            TEXT,
    updated_at      TEXT,
    UNIQUE(code, rev_year, rev_month)
);
CREATE INDEX IF NOT EXISTS idx_mrev_avail ON monthly_revenue(avail_date);
CREATE INDEX IF NOT EXISTS idx_mrev_code  ON monthly_revenue(code, rev_year, rev_month);
'''


def fetch(url):
    """
    ⚠️ 刻意**不帶 `verify=False`**，也刻意不留「失敗就關掉驗證」的退路。

    `probe_mops_structure.py`（2026-10-06）實測 mopsov.twse.com.tw 的
    **TLS 驗證完全正常**，所以沒有理由帶一個會關掉驗證的分支——
    那只會在日後真的遇到憑證問題（或中間人）時，讓它靜默通過。

    專案舊程式對 TWSE 一律 `verify=False`，那是沿用下來的習慣；
    新寫的不照抄。若哪天這裡真的噴 SSLError，那本身就是該查的訊號，
    不是該繞過的障礙。
    """
    return requests.get(url, headers=HEADERS, timeout=TIMEOUT)


def _detag(html):
    s = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', s).strip()


def _cells(tr):
    out = []
    for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I):
        c = re.sub(r'<[^>]+>', '', c)
        c = c.replace('&nbsp;', ' ').replace('&amp;', '&')
        out.append(c.strip())
    return out


def _num(s):
    """'514,805,337' → 514805337；'-' / '' → None"""
    if s is None:
        return None
    s = s.replace(',', '').replace('%', '').strip()
    if s in ('', '-', '--', 'N/A'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def avail_date_of(year, month):
    """
    ★ 營收月 (year, month) 的最早可用日 = 次月 11 日。
    理由見檔頭「avail_date」那段——這是防 look-ahead 的核心，不要改。
    """
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    return f'{y:04d}-{m:02d}-11'


def parse_page(html_bytes, want_roc, want_mon):
    """
    回傳 `(rows, status)`，status ∈
        'OK'               解析成功
        'DECODE_FAIL'      編碼錯（不用 errors='ignore' 靜默丟字）
        'NO_TITLE'         抓不到標題年月 ⇒ 守衛無法運作，當失敗
        'YM_MISMATCH:...'  ⚠️ 年月確實不符（陷阱41 那種靜默抓錯月份）
        'NO_DATA'          年月相符但頁面沒有資料列 ⇒ **該月尚未公布，正常**

    ⚠️ `NO_DATA` 必須與 `YM_MISMATCH` 分開（2026-10-06 修）。
       第一版把「0 列」一律歸成「年月不符」，試跑時 115/10 印出
       「年月不符（要求 115年10月，頁面 115年10月）」——自相矛盾。
       真因是 10 月營收要到 11 月才公布，頁面存在但無資料列。

       **不分開的後果比訊息醜陋嚴重得多**：每次跑都會有一兩個月報「年月不符」，
       看起來像守衛壞了 ⇒ 兩週後使用者學會忽略它 ⇒ **真正的年月不符就被混進去
       看不出來**。這正是十九章那條通則（警告的價值來自每次出現都值得行動）。
    """
    try:
        body = html_bytes.decode(ENCODING)
    except UnicodeDecodeError:
        # 寧可標記失敗，也不要 errors='ignore' 靜默丟字
        return [], 'DECODE_FAIL'

    # ── 日期守衛：去標籤後取開頭的第一個「N年N月」 ──
    head = _detag(body[:6000])
    m = re.search(r'(\d{2,3})\s*年\s*(\d{1,2})\s*月', head)
    if not m:
        return [], 'NO_TITLE'
    got_roc, got_mon = int(m.group(1)), int(m.group(2))
    if got_roc != want_roc or got_mon != want_mon:
        # ⚠️ 不符就當失敗，不靜默接受（陷阱41）
        return [], f'YM_MISMATCH:{got_roc}年{got_mon}月'

    west_year = want_roc + 1911
    rows = []
    for tr in re.findall(r'<tr.*?</tr>', body, re.S | re.I):
        cs = _cells(tr)
        if len(cs) != 11:
            continue                 # 2/4/10 欄是產業標題與表頭
        code = cs[0].strip()
        if not re.fullmatch(r'\d{4}[A-Z]?', code):
            continue                 # 濾掉重複出現的表頭列
        rows.append({
            'code': code,
            'name': cs[1].strip(),
            'revenue': _num(cs[2]),
            'revenue_prev_m': _num(cs[3]),
            'revenue_last_y': _num(cs[4]),
            'mom_pct': _num(cs[5]),
            'yoy_pct': _num(cs[6]),
            'cum_revenue': _num(cs[7]),
            'cum_last_y': _num(cs[8]),
            'cum_yoy_pct': _num(cs[9]),
            'note': (cs[10] or '').strip()[:200],
            'rev_year': west_year,
            'rev_month': want_mon,
            'avail_date': avail_date_of(west_year, want_mon),
        })
    return rows, ('OK' if rows else 'NO_DATA')


def months_from(roc, mon):
    """從 (民國roc, mon) 到今天的所有年月。"""
    now = datetime.now()
    end_roc, end_mon = now.year - 1911, now.month
    out = []
    y, m = roc, mon
    while (y, m) <= (end_roc, end_mon):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main():
    apply = '--apply' in sys.argv
    do_otc = '--otc' in sys.argv
    f_roc, f_mon = FROM_ROC, FROM_MON
    if '--from' in sys.argv:
        i = sys.argv.index('--from')
        f_roc, f_mon = int(sys.argv[i + 1]), int(sys.argv[i + 2])

    markets = [('sii', 'TWSE')] + ([('otc', 'TPEx')] if do_otc else [])
    todo = months_from(f_roc, f_mon)

    print(f'月營收回填　{datetime.now():%Y-%m-%d %H:%M}')
    print(f'模式：{"★ 實際寫入 (--apply)" if apply else "試跑（只報告，不寫入）"}')
    print(f'範圍：民國 {f_roc}/{f_mon} ~ 今　共 {len(todo)} 個月'
          f'　市場：{"、".join(m[1] for m in markets)}')
    print(f'編碼：{ENCODING}（實測 big5 會失敗）')
    print(f'avail_date：營收月次月 11 日（防 look-ahead，見檔頭）')
    print(f'預估請求數：{len(todo) * len(markets)}　'
          f'約 {len(todo)*len(markets)*(SLEEP+1.5)/60:.0f} 分鐘')
    print()

    conn = sqlite3.connect(DB)
    if apply:
        conn.executescript(DDL)
        conn.commit()
    else:
        # 試跑也要能查既有狀態
        try:
            conn.execute('SELECT 1 FROM monthly_revenue LIMIT 1')
        except sqlite3.OperationalError:
            print('（monthly_revenue 表尚未建立——試跑不會建，--apply 才會）\n')

    tot_rows = tot_new = 0
    fail, mismatch, nodata, partial = [], [], [], []

    for roc, mon in todo:
        for seg, mkt in markets:
            url = f'https://mopsov.twse.com.tw/nas/t21/{seg}/t21sc03_{roc}_{mon}_0.html'
            try:
                r = fetch(url)
                if r.status_code != 200:
                    fail.append((roc, mon, mkt, f'HTTP {r.status_code}'))
                    print(f'  {roc}/{mon:<2} {mkt:<5} ❌ HTTP {r.status_code}')
                    continue
                rows, status = parse_page(r.content, roc, mon)
                if status != 'OK':
                    if status == 'NO_DATA':
                        # 正常：該月營收尚未公布（例如 10/6 查 10 月營收）
                        nodata.append((roc, mon, mkt))
                        print(f'  {roc}/{mon:<2} {mkt:<5} ⚪ 該月尚未公布（正常）')
                    elif status.startswith('YM_MISMATCH'):
                        mismatch.append((roc, mon, mkt, status.split(':', 1)[1]))
                        print(f'  {roc}/{mon:<2} {mkt:<5} 🚨 年月不符！'
                              f'要求 {roc}年{mon}月，頁面 {status.split(":",1)[1]}'
                              f' → 跳過（守衛生效，**這個要查**）')
                    else:
                        fail.append((roc, mon, mkt, status))
                        print(f'  {roc}/{mon:<2} {mkt:<5} ❌ {status}')
                    continue

                tot_rows += len(rows)
                if apply:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cur = conn.executemany('''
                        INSERT OR REPLACE INTO monthly_revenue
                        (code, rev_year, rev_month, avail_date, name, revenue,
                         revenue_prev_m, revenue_last_y, mom_pct, yoy_pct,
                         cum_revenue, cum_last_y, cum_yoy_pct, market, note, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        [(x['code'], x['rev_year'], x['rev_month'], x['avail_date'],
                          x['name'],
                          int(x['revenue']) if x['revenue'] is not None else None,
                          int(x['revenue_prev_m']) if x['revenue_prev_m'] is not None else None,
                          int(x['revenue_last_y']) if x['revenue_last_y'] is not None else None,
                          x['mom_pct'], x['yoy_pct'],
                          int(x['cum_revenue']) if x['cum_revenue'] is not None else None,
                          int(x['cum_last_y']) if x['cum_last_y'] is not None else None,
                          x['cum_yoy_pct'], mkt, x['note'], now)
                         for x in rows])
                    tot_new += cur.rowcount
                    conn.commit()

                ex = rows[0]
                # ⚠️ 公布中：次月 1~10 日之間資料逐日累積，此時抓到的是**不完整**
                #    且有選擇偏誤的子集（先公布的公司通常業績較好）。
                #    標出來，提醒之後要重抓。
                flag = ''
                if len(rows) < 600:
                    partial.append((roc, mon, mkt, len(rows)))
                    flag = '　⚠️ 公布中，之後要重抓'
                print(f'  {roc}/{mon:<2} {mkt:<5} ✅ {len(rows):>4} 檔'
                      f'　可用日 {ex["avail_date"]}'
                      f'　例：{ex["code"]} YoY {ex["yoy_pct"]}%{flag}')
            except Exception as e:
                fail.append((roc, mon, mkt, f'{type(e).__name__}: {e}'))
                print(f'  {roc}/{mon:<2} {mkt:<5} ❌ {type(e).__name__}: {e}')
            time.sleep(SLEEP)

    print()
    print('=' * 70)
    print(f'解析成功列數　{tot_rows:,}')
    if apply:
        print(f'實際寫入　　　{tot_new:,}')
        n = conn.execute('SELECT COUNT(*) FROM monthly_revenue').fetchone()[0]
        rng = conn.execute('SELECT MIN(rev_year*100+rev_month), '
                           'MAX(rev_year*100+rev_month) FROM monthly_revenue').fetchone()
        nc = conn.execute('SELECT COUNT(DISTINCT code) FROM monthly_revenue').fetchone()[0]
        print(f'表內總列數　　{n:,}　年月範圍 {rng[0]} ~ {rng[1]}　不同股票 {nc:,} 檔')
    else:
        print('（試跑，未寫入。加 --apply 實際執行）')
    print(f'⚪ 尚未公布　　{len(nodata)} 個月'
          + ('（正常，不是漏抓）' if nodata else ''))
    print(f'🚨 年月不符　　{len(mismatch)} 個月'
          + ('　← **這個要查**，守衛擋下了抓錯月份' if mismatch else ''))
    for x in mismatch[:10]:
        print(f'    {x}')
    print(f'❌ 失敗　　　　{len(fail)} 個月')
    for x in fail[:10]:
        print(f'    {x}')

    if partial:
        print()
        print('⚠️ 以下月份抓到的檔數偏少 = **正在公布中，資料不完整**：')
        for roc, mon, mkt, n in partial:
            print(f'    {roc}/{mon} {mkt}：僅 {n} 檔')
        print('''
   次月 1~10 日之間，各公司陸續公布，此時的樣本**有選擇偏誤**
   （先公布的公司通常業績較好）。

   ⇒ 日後接入每日更新時，必須**重抓「當月 + 前兩個月」**，
      不可以用「這個月抓過就跳過」的水位線邏輯——那正是陷阱45 的病根。
      `INSERT OR REPLACE` 已處理覆寫，重抓是安全的。'''.rstrip())
    print('=' * 70)
    conn.close()


if __name__ == '__main__':
    main()
