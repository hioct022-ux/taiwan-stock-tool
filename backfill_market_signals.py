#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_market_signals.py — 把大盤淨值（S1–S8）所需的三張表回填到 2018

════════════════════════════════════════════════════════════════════════
為什麼要這個（2026-10-07）
════════════════════════════════════════════════════════════════════════

**要重測策略D，而 D 的觸發條件是「大盤淨值 ≥2」。** 逐一查 `_build_market_signals()`
的資料來源後發現：

| 訊號 | 來源 | 2018~2024 |
|---|---|---|
| S1、S5–S8（5 個） | TAIEX 價格 | ✅ 有（2016-10 起） |
| **S2 融資5日趨勢** | `market_margin` | ❌ **2026-05-15 起** |
| **S3 外資期貨** | `futures_institutional` | ❌ **2026-03-02 起** |
| **S4 法人現貨** | `chips` | ❌ **2025-07 起**（2018~2024 為 0） |

缺的那 3 個正好是能把淨值推到 ±8 的（S2 ±2、S3 ±3、S4 ±4）。
**只用 5 個訊號算「部分淨值」會系統性偏小 ⇒ D 觸發次數大幅減少，
那不是「測 D」，是測一個比 D 更保守的東西。**

而 2026-10-07 的結構測試已經用 MA60 代理測過一次（「出清沒有可檢出的
長期報酬代價」），再做一次代理答不了「真正那條規則」。所以只能回填。

════════════════════════════════════════════════════════════════════════
動手前已實測三支 API 的日期參數（陷阱41／44 立的規矩）
════════════════════════════════════════════════════════════════════════

| API | 實測（2026-10-07） |
|---|---|
| TWSE `T86?date=20180103` | → `stat:OK`、`date:20180103` ✅ |
| TWSE `MI_MARGN?date=20180103` | → `107年01月03日 信用交易統計` ✅ |
| TAIFEX `futContractsDate?queryStartDate=2018/01/02` | → 2018/01/02 的臺股期貨法人未平倉確實存在 ✅ |

════════════════════════════════════════════════════════════════════════
設計（每一條都對應一個踩過的坑）
════════════════════════════════════════════════════════════════════════

1. **以 TAIEX 的實際交易日為權威日曆**，逐日比對「應該有 vs 實際有」。
   ⚠️ **不用 `MAX(date)` 當水位線**——陷阱45：水位線看不到「中間的洞」，
   而「今天成功、昨天失敗」正是最常見的失敗形狀。
   ⇒ 本腳本可以隨時中斷後重跑，它會重新算出還缺哪幾天。

2. **日期驗證守衛**：抓回來的資料日期 ≠ 要求的日期就當失敗（陷阱41）。
   `_fetch_*_for_date()` 這些 helper 本來就用回傳內容的日期存檔（正確防禦），
   本腳本另外再比對一次並計數，不讓「靜默成功」發生。

3. **預設試跑**，`--apply` 才真的抓、真的寫。

4. **不碰 `fetch_market_margin_history()`** ——它第 794 行還留著
   `if last and date_std <= last: continue`（陷阱45 的水位線 bug 在那支裡還活著），
   拿它做 2018 回填會整段被跳過。本腳本自己逐日抓。

5. TAIFEX 用**日期區間**查（30 天/次），所以 S3 只要約 70 次請求、3 分鐘。

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════

    python3 backfill_market_signals.py                     # 試跑（只報告缺哪幾天）
    python3 backfill_market_signals.py --probe 2018-01-03  # 只抓一天，驗證流程
    python3 backfill_market_signals.py --apply             # 全部回填（約 2 小時）
    python3 backfill_market_signals.py --apply --only s3   # 只跑台指期（約 3 分鐘）
    python3 backfill_market_signals.py --apply --from 2022-01-01

⚠️ 執行前先備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
⚠️ 跑之前請關掉本機 Streamlit App（避免 SQLite 寫入互卡）
"""
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn, init_db

APPLY = '--apply' in sys.argv
PROBE = None
FROM = '2018-01-01'
ONLY = None

if '--probe' in sys.argv:
    PROBE = sys.argv[sys.argv.index('--probe') + 1]
if '--from' in sys.argv:
    FROM = sys.argv[sys.argv.index('--from') + 1]
if '--only' in sys.argv:
    ONLY = sys.argv[sys.argv.index('--only') + 1].lower()

SLEEP_TWSE = 1.2      # TWSE 速率限制（陷阱7：批次補抓每筆 ≥0.4s，大量補抓用 2s）
SLEEP_TAIFEX = 1.5


# ══════════════════════════════════════════════════════════════════
def trading_days(since):
    """權威交易日日曆 = TAIEX 實際有收盤價的日子（全專案缺口最少的序列）。"""
    conn = get_conn()
    rows = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? AND close>0 ORDER BY date",
        (since,))]
    conn.close()
    return rows


def existing_days(table, where=''):
    conn = get_conn()
    rows = {r[0] for r in conn.execute(
        f'SELECT DISTINCT date FROM {table} WHERE 1=1 {where}')}
    conn.close()
    return rows


def missing_for(table, cal, where=''):
    have = existing_days(table, where)
    return [d for d in cal if d not in have]


# ══════════════════════════════════════════════════════════════════
def run_daily(label, miss, fetch_one, sleep):
    """
    逐日補齊的共用迴圈。

    fetch_one(ymd) 必須回傳 (筆數, 實際日期) —— 實際日期用來做
    陷阱41 的日期驗證守衛（≠ 要求日期就當失敗，不靜默接受）。
    """
    print(f'\n{"="*70}\n【{label}】缺 {len(miss)} 天')
    if not miss:
        print('  完整 ✅')
        return
    print(f'  範圍 {miss[0]} ~ {miss[-1]}')
    if not APPLY:
        est = len(miss) * sleep / 60
        print(f'  試跑：不抓不寫。實際執行約需 {est:.0f} 分鐘')
        return

    ok = empty = mismatch = fail = 0
    t0 = time.time()
    for i, d in enumerate(miss, 1):
        ymd = d.replace('-', '')
        try:
            cnt, actual = fetch_one(ymd)
            if not cnt:
                empty += 1
            elif actual and actual != d:
                # 陷阱41：API 忽略日期參數卻回 200 + 合法資料
                mismatch += 1
                print(f'  ⚠️ {d}：回傳日期是 {actual}，不符 → 視為失敗')
            else:
                ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f'  {d} 失敗：{e}')
        if i % 50 == 0 or i == len(miss):
            el = time.time() - t0
            eta = el / i * (len(miss) - i) / 60
            print(f'  [{i}/{len(miss)}] 成功{ok} 無資料{empty} 日期不符{mismatch} '
                  f'失敗{fail}　已花 {el/60:.1f} 分　剩約 {eta:.0f} 分')
        time.sleep(sleep)
    print(f'  ── 完成：成功 {ok}　查無資料 {empty}　日期不符 {mismatch}　失敗 {fail}')


# ══════════════════════════════════════════════════════════════════
def do_s4(cal):
    """S4 法人現貨 → chips 表。T86 是「一天一個請求拿全市場」。"""
    from fetcher import _fetch_t86_chips_for_date
    # ⚠️ 用 >=500 檔當「這天有完整資料」的判準，與 get_chips_market_series 一致；
    #    只看「有沒有任何一列」會把少數自選股的殘留資料誤判成完整。
    conn = get_conn()
    full = {r[0] for r in conn.execute(
        'SELECT date FROM chips GROUP BY date HAVING COUNT(*)>=500')}
    conn.close()
    run_daily('S4 法人現貨（chips / TWSE T86）',
              [d for d in cal if d not in full],
              _fetch_t86_chips_for_date, SLEEP_TWSE)


def do_s2(cal):
    """S2／S10 大盤融資融券 → market_margin 表。"""
    import requests
    from fetcher import HEADERS, _parse_market_margin_response
    from database import save_market_margin

    def fetch_one(ymd):
        url = ('https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN'
               f'?date={ymd}&selectType=MS&response=json')
        r = requests.get(url, headers=HEADERS, timeout=20)
        js = r.json()
        if js.get('stat') != 'OK':
            return 0, None
        std = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}'
        # `d` 是 _parse_market_margin_response 從回應內容解出的權威日期
        # （陷阱41 通則2：用回傳內容的真實日期存檔，不用請求參數）
        d, result = _parse_market_margin_response(js, std)
        if not result:
            return 0, None
        save_market_margin(d, result)
        return 1, d

    run_daily('S2／S10 大盤融資融券（market_margin / TWSE MI_MARGN）',
              missing_for('market_margin', cal), fetch_one, SLEEP_TWSE)


def do_s3(cal):
    """S3 台指期三大法人 → futures_institutional。TAIFEX 支援日期區間（30天/次）。"""
    import requests
    from fetcher import HEADERS, _parse_futures_csv
    from database import save_futures_institutional

    miss = missing_for('futures_institutional', cal)
    print(f'\n{"="*70}\n【S3 台指期三大法人（TAIFEX，區間查詢）】缺 {len(miss)} 天')
    if not miss:
        print('  完整 ✅')
        return
    print(f'  範圍 {miss[0]} ~ {miss[-1]}')

    # 切成 ≤28 天的區間（TAIFEX 單次上限約 30 天）
    wins, cur = [], [miss[0]]
    for d in miss[1:]:
        a = datetime.strptime(cur[0], '%Y-%m-%d')
        b = datetime.strptime(d, '%Y-%m-%d')
        if (b - a).days >= 28:
            wins.append((cur[0], cur[-1])); cur = [d]
        else:
            cur.append(d)
    wins.append((cur[0], cur[-1]))
    print(f'  切成 {len(wins)} 個區間')
    if not APPLY:
        print(f'  試跑：不抓不寫。實際執行約需 {len(wins)*SLEEP_TAIFEX/60:.0f} 分鐘')
        return

    url = 'https://www.taifex.com.tw/cht/3/futContractsDateDown'
    ok = fail = blank = 0
    for i, (s, e) in enumerate(wins, 1):
        try:
            r = requests.get(url, params={
                'down_type': '1', 'commodity_id': 'TXF',
                'queryStartDate': s.replace('-', '/'),
                'queryEndDate':   e.replace('-', '/'),
            }, headers=HEADERS, timeout=30)
            # _parse_futures_csv 用 CSV 每列自帶的日期當 key（陷阱41 通則2）
            parsed = _parse_futures_csv(r.content) or {}
            if not parsed:
                # ⚠️ 2026-10-07：這一支原本只計「例外」，於是「HTTP 200 但回空白」
                #    會印成「寫入 0 天　失敗區間 0」——**又是一次靜默失敗**。
                #    實測 TAIFEX 下載端點對 2018／2022 都回空白（歷史範圍有限），
                #    而第一版的回報讓它看起來像「沒事發生」。
                blank += 1
                if blank <= 3:
                    print(f'  ⚠️ {s}~{e}：HTTP {r.status_code} 但內容為空'
                          f'（{len(r.content)} bytes）→ 該區間無資料')
            for d, data in parsed.items():
                save_futures_institutional(d, data)
                ok += 1
        except Exception as ex:
            fail += 1
            if fail <= 5:
                print(f'  {s}~{e} 失敗：{ex}')
        if i % 10 == 0 or i == len(wins):
            print(f'  [{i}/{len(wins)}] 已寫入 {ok} 天　空回應 {blank} 區間　例外 {fail}')
        time.sleep(SLEEP_TAIFEX)
    print(f'  ── 完成：寫入 {ok} 天　空回應 {blank} 區間　例外 {fail}')
    if blank and not ok:
        print('  🚨 全部區間都回空白 —— 這些日期在 TAIFEX 下載端點的範圍外，'
              '不是程式錯誤。先跑 probe_futures_history.py 確認邊界。')


# ══════════════════════════════════════════════════════════════════
def main():
    init_db()
    print('大盤淨值（S1–S8）歷史回填')
    print('模式：' + ('★ 實際抓取並寫入' if APPLY else '試跑（只報告，加 --apply 才執行）'))

    cal = trading_days(FROM)
    if not cal:
        print(f'❌ TAIEX 在 {FROM} 之後沒有資料。先跑 backfill_taiex_history.py')
        return
    print(f'交易日日曆（取自 TAIEX）：{len(cal)} 天　{cal[0]} ~ {cal[-1]}')

    if PROBE:
        print(f'\n── PROBE 模式：只處理 {PROBE} ──')
        cal = [PROBE]

    jobs = [('s4', do_s4), ('s2', do_s2), ('s3', do_s3)]
    for key, fn in jobs:
        if ONLY and ONLY != key:
            continue
        fn(cal)

    # ── 收尾：重算覆蓋率，確認真的補齊了 ──
    print(f'\n{"="*70}\n【回填後覆蓋率】')
    conn = get_conn()
    full_chips = {r[0] for r in conn.execute(
        'SELECT date FROM chips GROUP BY date HAVING COUNT(*)>=500')}
    conn.close()
    checks = [
        ('S4 法人現貨', len([d for d in cal if d in full_chips])),
        ('S2 融資融券', len(existing_days('market_margin') & set(cal))),
        ('S3 台指期',   len(existing_days('futures_institutional') & set(cal))),
    ]
    for nm, n in checks:
        print(f'  {nm:<14}{n:>6} / {len(cal)} 天　({n/len(cal)*100:>5.1f}%)'
              + ('　✅' if n >= len(cal) * 0.98 else '　⚠️ 仍有缺口'))

    if APPLY:
        print('''
下一步：
  1. 重新校準 Signal 4 的百分位切點（indicators.PCT_HI/MID/LO）
     —— 現在視窗才真正是 trailing 300，觸發率要重新量
  2. python3 backtest_portfolio_slots.py cache market   （重建全市場快取）
  3. 重測策略D（真觸發條件 + 全市場 + 配對設計 + 空頭年）''')
    else:
        print('\n※ 確認無誤後執行：python3 backfill_market_signals.py --apply')
        print('※ 建議先備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)')


if __name__ == '__main__':
    main()
