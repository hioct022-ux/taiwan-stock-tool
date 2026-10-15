#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_exdividend.py — 回填 2018 起的除權息歷史（陷阱50 的待辦）

════════════════════════════════════════════════════════════════════════
為什麼需要這一支
════════════════════════════════════════════════════════════════════════

陷阱50：`exdividend` 表只有 **2026-05-28 ~ 2026-10-29（1,069 列）**，
2018~2025 全部 0 筆。而 `prices` 存的是**未調整收盤價**（陷阱49）
⇒ 2018~2025 的除息既無法調整、也無法排除。

**它不是隨機雜訊，而是與訊號相關的偏誤：**
```
高成長股（電子）    → 殖利率低 → 除息拖累小
低成長股（傳產/金融）→ 殖利率高 → 除息拖累大
```
⇒ 在 6~9 月（佔全年除息 93.6%）的前瞻窗口裡，低成長組被系統性壓低
⇒ 製造假的「高成長組贏」，量級 1~4pp。

2026-10-14 測「現有策略 ＋ 月營收 YoY 篩選」時，這個偏誤是**唯一不利的診斷項目**
（除息月 B2−C +0.99pp ＞ 其他 8 月 +0.87pp，方向與 10/07 相反）。
拿到除息歷史之後才能做「除息調整後報酬」，而那會同時改善**所有**既有回測。

════════════════════════════════════════════════════════════════════════
🚨 參數名的坑：請求是 `startDate`，但回應欄位叫 `strDate`（2026-10-15 實測）
════════════════════════════════════════════════════════════════════════

這是陷阱44 那條通則的再現，但更陰險。實測四種猜法：

| 參數 | 結果 |
|---|---|
| `date=20220601` | ⚪ **靜默忽略**，回傳今天（＝陷阱41／44 的同一個坑，第三次） |
| `strDate=...&endDate=...` | ❌ 報「查詢結束日期小於查詢開始日期」 |
| `queryStartDate=...` | ⚪ 靜默忽略（那是 TAIFEX 的參數名） |
| **`startDate=...&endDate=...`** | **✅ 正確** |

**★ 最值得記的一點：那個錯誤訊息是完全正確的，是我誤判成格式問題。**
`strDate` 被忽略 ⇒ 開始日預設成今天（2026-10-15）⇒ `endDate=2022-06-30`
真的小於開始日 ⇒ 訊息字面上就是對的。我當時以為是民國/西元的格式問題，
又去試了 `1110601`（也被忽略），白繞一圈。

⇒ **看到「參數讀到了但語意不對」的錯誤，先懷疑「是不是只有一個參數被讀到」，
  而不是先懷疑格式。** 判斷方法極便宜：**只傳一個參數**看回應怎麼變
  （本例 `strDate=20220601` 單獨傳 → 回傳今天 ⇒ 立刻知道它被忽略）。

**★ 而從回應欄位名猜請求參數名，是不可靠的。** 回應明明寫
`"strDate":"20261015"`，請求卻要用 `startDate`。
**唯一可靠的辦法是看網頁實際發出的請求**（本次用瀏覽器在同源頁面裡
直接 `fetch()` 測各變體，比點 UI 快得多）。

════════════════════════════════════════════════════════════════════════
成本：整年一次就拿得到 ⇒ 9 次請求、約 1 分鐘
════════════════════════════════════════════════════════════════════════

實測（2026-10-15）：

```
startDate=20220101&endDate=20221231  → OK  1,027 筆  111年01月12日 ~ 111年12月28日
startDate=20180101&endDate=20181231  → OK    825 筆  首筆 107年01月11日
```

⚠️ **整段（2018~2026 一次）會逾時**，所以逐年查。
（TWSE 的 notes 寫「股利資料自民國92年5月5日起開始提供」，
  若日後要更早的歷史，把 `START_YEAR` 往前調即可。）

════════════════════════════════════════════════════════════════════════
守衛（照陷阱41 的教訓，缺一不可）
════════════════════════════════════════════════════════════════════════

1. **逐年核對回傳的 `strDate`/`endDate` 是否等於要求的區間** ——
   不符就當失敗、不寫入。這類 bug 不會拋例外，只會安靜地讓回填失效。
2. **逐列核對 `資料日期` 的年份落在要求的年份內** —— 防「整年請求但
   回傳今天」那種退化（上面 `date=` 那一行就是這樣）。
3. `is_confirmed=1`（TWT49U 是正式資料）⇒ `save_exdividend()` 用
   `INSERT OR REPLACE`，會覆蓋既有的預告資料，這是對的。

用法：
    python3 backfill_exdividend.py            # 試跑，只報告不寫入
    python3 backfill_exdividend.py --apply     # 實際寫入
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from database import save_exdividend, get_conn

URL        = 'https://www.twse.com.tw/rwd/zh/exRight/TWT49U'
START_YEAR = 2018          # S2/S3/S4 只回填到 2018-01-01（陷阱51 限制第5條）
END_YEAR   = 2026
SLEEP      = 1.0           # TWSE 速率限制（陷阱7：批次抓取每筆 ≥0.4s）
HEADERS    = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

APPLY = '--apply' in sys.argv


def parse_tw_date(s):
    """民國『107年01月11日』→ '2018-01-11'。與 fetcher.fetch_exdividend() 同一份邏輯。"""
    m = re.match(r'(\d+)年(\d+)月(\d+)日', str(s).strip())
    if m:
        return f'{int(m.group(1)) + 1911}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}'
    return ''


def clean_num(v):
    try:
        return float(str(v).replace(',', '').strip() or 0)
    except Exception:
        return 0.0


def fetch_year(year):
    """
    回傳 (rows, note)。rows 為空時 note 說明原因。
    ★ 一律核對回傳的 strDate/endDate 等於要求的區間（陷阱41 的守衛）。
    """
    s, e = f'{year}0101', f'{year}1231'
    params = {'response': 'json', 'startDate': s, 'endDate': e}
    data = None
    for attempt in range(3):
        try:
            # ⚠️ 不關 TLS 驗證（既有 fetcher.py 有些地方用了 verify=False，
            #    那是舊債，新寫的不要跟進）
            r = requests.get(URL, params=params, headers=HEADERS, timeout=60)
            if not r.content:
                raise ValueError(f'HTTP {r.status_code} 但內容為空（0 bytes）')
            data = r.json()
            break
        except Exception as ex:
            if attempt < 2:
                time.sleep(5)
                continue
            return [], f'請求失敗：{type(ex).__name__}: {str(ex)[:60]}'

    if not data or data.get('stat') != 'OK':
        return [], f'stat 非 OK：{str(data.get("stat"))[:50] if data else "無回應"}'

    # ★ 守衛①：回傳的區間必須等於要求的區間
    got_s, got_e = str(data.get('strDate', '')), str(data.get('endDate', ''))
    if got_s != s or got_e != e:
        return [], (f'🚨 日期不符！要求 {s}~{e}，回傳 {got_s}~{got_e}'
                    f'（title: {str(data.get("title", ""))[:30]}）'
                    f' ⇒ 判為失敗，不寫入')

    rows, bad_year = [], 0
    for d in data.get('data', []):
        try:
            ex_date = parse_tw_date(d[0])
            if not ex_date:
                continue
            # ★ 守衛②：逐列的年份也要落在要求的年份內
            if not ex_date.startswith(str(year)):
                bad_year += 1
                continue
            code = str(d[1]).strip()
            if not code:
                continue
            rows.append({
                'ex_date': ex_date, 'code': code, 'name': str(d[2]).strip(),
                'prev_close': clean_num(d[3]), 'ref_price': clean_num(d[4]),
                'div_value': clean_num(d[5]), 'div_type': str(d[6]).strip(),
                'is_confirmed': 1,
            })
        except Exception:
            continue
    note = f'{len(rows)} 筆'
    if bad_year:
        note += f'　⚠️ 年份不符而跳過 {bad_year} 列'
    return rows, note


def main():
    print('=' * 76)
    print('回填除權息歷史（TWT49U，逐年查詢）')
    print('=' * 76)
    print(f'期間 {START_YEAR} ~ {END_YEAR}　參數 **startDate/endDate**'
          f'（不是 strDate，見本檔 docstring）')
    print(f'模式：{"★ 實際寫入（--apply）" if APPLY else "試跑（只報告，加 --apply 才寫入）"}')

    conn = get_conn()
    before = conn.execute(
        'SELECT COUNT(*), MIN(ex_date), MAX(ex_date) FROM exdividend').fetchone()
    conn.close()
    print(f'\n回填前：{before[0]:,} 列　{before[1]} ~ {before[2]}')

    total, fails = 0, []
    for y in range(START_YEAR, END_YEAR + 1):
        rows, note = fetch_year(y)
        mark = '✅' if rows else '🚨'
        print(f'  {mark} {y}　{note}')
        if not rows:
            fails.append((y, note))
        elif APPLY:
            save_exdividend(rows)
        total += len(rows)
        time.sleep(SLEEP)

    print('\n' + '=' * 76)
    print(f'共取得 {total:,} 筆　失敗 {len(fails)} 年')
    if fails:
        print('\n🚨 失敗的年份（**不要當成「那年沒有除息」**——那是請求問題）：')
        for y, n in fails:
            print(f'   {y}：{n}')

    # 除息的月份分布（陷阱50 的量化依據，順手驗一次）
    if total:
        print('\n月份分布（驗證「6~9 月佔 93.6%」這個既有數字）：')
        conn = get_conn()
        src = (conn.execute("SELECT substr(ex_date,6,2), COUNT(*) FROM exdividend "
                            "WHERE ex_date >= ? GROUP BY 1",
                            (f'{START_YEAR}-01-01',)).fetchall()
               if APPLY else [])
        conn.close()
        if src:
            tot = sum(c for _, c in src)
            for m, c in sorted(src):
                bar = '█' * int(c / tot * 60)
                star = ' ★' if m in ('06', '07', '08', '09') else ''
                print(f'   {m} 月　{c:>5} 筆（{c/tot*100:>5.1f}%）{bar}{star}')
            jja = sum(c for m, c in src if m in ('06', '07', '08', '09'))
            print(f'   ⇒ 6~9 月合計 **{jja/tot*100:.1f}%**')
        else:
            print('   （試跑模式不查 DB；加 --apply 後會列出）')

    if not APPLY:
        print('\n' + '=' * 76)
        print('這是試跑。確認上面每一年都 ✅ 之後，再跑：')
        print('    python3 backfill_exdividend.py --apply')
        print('=' * 76)
        return

    conn = get_conn()
    after = conn.execute(
        'SELECT COUNT(*), MIN(ex_date), MAX(ex_date) FROM exdividend').fetchone()
    conn.close()
    print(f'\n✅ 回填後：{after[0]:,} 列　{after[1]} ~ {after[2]}'
          f'（新增 {after[0] - before[0]:,} 列）')
    print('''
⚠️ **接下來才是重點：有了資料不等於回測用到了。**
   這與陷阱51 那條通則同一族——**回填本身不會讓既有程式看得到新資料。**
   還要改回測去算「除息調整後報酬」，然後才能重跑：
       python3 -u backtest_revenue_filter.py run     （約 2 分鐘，快取已建好）''')


if __name__ == '__main__':
    main()
