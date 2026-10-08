#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_futures_finmind.py — 用 FinMind 回填台指期三大法人未平倉（S3）到 2018

════════════════════════════════════════════════════════════════════════
為什麼需要這一支（2026-10-07）
════════════════════════════════════════════════════════════════════════

要重測策略D 必須有完整的大盤淨值（S1–S8）。S4／S2 已確認可用 TWSE 回填到
2018，但 S3 卡住——`probe_futures_history.py` 實測結果：

    TAIFEX futContractsDateDown 的歷史邊界 ≈ **2023-10-09 ~ 2023-10-19**
      2018 ❌　2019 ❌　2020 ❌　2021 ❌　2022 ❌　2023-09 ❌
      2023-10-19 ✅　2024 ✅　2025 ✅　2026 ✅
    ⇒ **TAIFEX 完全拿不到任何空頭年**（2018／2020／2022）

    FinMind：
      TaiwanFuturesInstitutionalInvestors   2018 ❌（0 列）／2022 ✅
      ★ TaiwanFutOptInstitutionalInvestors  2018 ✅／2022 ✅  ← 用這個
      TaiwanOptionInstitutionalInvestors    都 ❌

🚨 順帶記錄我在這題上犯的錯（與陷阱41 同一類）：
   先前用 `futContractsDate`（HTML 頁）要求 2018/01/02，頁面回了一張有數字的
   表格，我就宣告「TAIFEX 有 2018 資料」。但那頁自己標著「**日期2026/10/07**」
   ——它**忽略日期參數、回傳最新資料**。我拿陷阱41 的規矩去檢查別人的程式，
   自己卻沒核對回傳日期。**「有資料」與「有你要的那天的資料」是兩件事。**

════════════════════════════════════════════════════════════════════════
★ 對帳是強制的、而且會阻斷寫入（陷阱42 的教訓）
════════════════════════════════════════════════════════════════════════

混用兩個來源最危險的不是「抓不到」，而是「抓到了但定義不同」。
陷阱42（上櫃快照被蓋上錯誤日期）就是「跨來源借資料」造成的最嚴重汙染。

所以本腳本**一定先對帳**：拿 2024~2026（TAIFEX 與 FinMind 都有）的重疊期間，
逐日比對 foreign_net / trust_net / dealer_net。**相符率不到門檻就拒絕寫入。**

  • 完全相等的比例 ≥ 95%  → 放行
  • 否則印出前幾筆差異、直接中止，不寫任何一列

這比「事後補一個 robustness check」可靠——事後補的那個，通常是結果
不如預期時才會想起來做。

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════

    python3 backfill_futures_finmind.py              # 只對帳 + 報告缺哪幾天
    python3 backfill_futures_finmind.py --apply       # 對帳通過才回填
    python3 backfill_futures_finmind.py --to 2023-10-01   # 自訂回填終點

⚠️ 預設只回填到 **2023-10-01**（TAIFEX 邊界之前），之後的日期沿用 TAIFEX 既有資料，
   避免同一段期間兩個來源互相覆蓋。
"""
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from database import get_conn, init_db, save_futures_institutional, get_futures_institutional

APPLY = '--apply' in sys.argv
FROM = '2018-01-01'
TO = '2023-10-01'          # TAIFEX 邊界之前；之後用 TAIFEX 既有資料
if '--from' in sys.argv:
    FROM = sys.argv[sys.argv.index('--from') + 1]
if '--to' in sys.argv:
    TO = sys.argv[sys.argv.index('--to') + 1]

DATASET = 'TaiwanFutOptInstitutionalInvestors'
DATA_ID = 'TX'
API = 'https://api.finmindtrade.com/api/v4/data'
MATCH_MIN = 95.0           # 對帳相符率門檻（%）
SLEEP = 1.5

# FinMind 的身份別字樣可能有變體，全部對映到 DB 欄位前綴
ROLE_MAP = {
    '自營商': 'dealer', '自營商(避險)': 'dealer', '自營': 'dealer',
    '投信': 'trust',
    '外資': 'foreign', '外資及陸資': 'foreign', '外資自營商': 'foreign',
}


def token():
    try:
        from config import FINMIND_TOKEN
        return FINMIND_TOKEN or ''
    except Exception:
        return ''


def fetch(start, end, tok):
    """回傳 {date: {foreign_long, foreign_short, foreign_net, ...}}"""
    r = requests.get(API, params={
        'dataset': DATASET, 'data_id': DATA_ID,
        'start_date': start, 'end_date': end, 'token': tok}, timeout=60)
    js = r.json()
    if js.get('status') != 200:
        raise RuntimeError(f'FinMind status={js.get("status")} msg={js.get("msg")}')
    out, unknown = {}, set()
    for row in js.get('data') or []:
        d = row.get('date')
        role = ROLE_MAP.get((row.get('institutional_investors') or '').strip())
        if not d or not role:
            if row.get('institutional_investors'):
                unknown.add(row['institutional_investors'])
            continue
        lo = int(row.get('long_open_interest_balance_volume') or 0)
        sh = int(row.get('short_open_interest_balance_volume') or 0)
        e = out.setdefault(d, {})
        # 同一身份別可能出現多列（例如自營商自行買賣＋避險）⇒ 累加
        e[f'{role}_long'] = e.get(f'{role}_long', 0) + lo
        e[f'{role}_short'] = e.get(f'{role}_short', 0) + sh
    for d, e in out.items():
        for role in ('foreign', 'trust', 'dealer'):
            e.setdefault(f'{role}_long', 0)
            e.setdefault(f'{role}_short', 0)
            e[f'{role}_net'] = e[f'{role}_long'] - e[f'{role}_short']
    return out, unknown


def reconcile(tok):
    """
    ★ 強制對帳：拿 TAIFEX 既有資料（2024~2026）逐日比對 FinMind。
    回傳 (通過與否, 相符率, 比對天數)
    """
    print('=' * 72)
    print('【★ 強制對帳】FinMind vs TAIFEX（重疊期間）')
    print('=' * 72)
    have = {r['date']: r for r in get_futures_institutional(days=5000)}
    if not have:
        print('  ❌ DB 裡沒有任何 TAIFEX 資料可對帳 → 中止')
        return False, 0.0, 0
    ds = sorted(have)
    # 取最近 120 個已有的交易日當對帳樣本
    sample = ds[-120:]
    s, e = sample[0], sample[-1]
    print(f'  對帳樣本：{len(sample)} 天（{s} ~ {e}）')
    try:
        fm, unknown = fetch(s, e, tok)
    except Exception as ex:
        print(f'  ❌ FinMind 取數失敗：{ex} → 中止')
        return False, 0.0, 0
    if unknown:
        print(f'  ⚠️ 未對映的身份別（會被忽略）：{sorted(unknown)}')

    both = [d for d in sample if d in fm]
    print(f'  兩邊都有的日期：{len(both)} 天')
    if len(both) < 30:
        print('  ❌ 重疊不足 30 天，無法判定 → 中止')
        return False, 0.0, len(both)

    cols = ['foreign_net', 'trust_net', 'dealer_net']
    exact = 0
    diffs = []
    for d in both:
        a, b = have[d], fm[d]
        if all((a.get(c) or 0) == b[c] for c in cols):
            exact += 1
        else:
            diffs.append((d, {c: ((a.get(c) or 0), b[c]) for c in cols
                               if (a.get(c) or 0) != b[c]}))
    rate = exact / len(both) * 100
    print(f'\n  三欄（外資/投信/自營商淨額）完全相等：{exact} / {len(both)}'
          f'　= **{rate:.1f}%**　（門檻 {MATCH_MIN}%）')
    if diffs:
        print(f'  不符 {len(diffs)} 天，前 5 筆：')
        for d, dd in diffs[:5]:
            txt = '　'.join(f'{c}: TAIFEX {x:+,} vs FinMind {y:+,}'
                            for c, (x, y) in dd.items())
            print(f'    {d}  {txt}')
    ok = rate >= MATCH_MIN
    print(f'\n  ⇒ {"✅ 對帳通過，可以混用" if ok else "❌ 對帳未通過 —— 拒絕寫入"}')
    if not ok:
        print('''
  兩個來源的定義不同時**絕對不能混用**（陷阱42：跨來源借資料造成本專案
  最嚴重的一次汙染）。可能的原因：
    • FinMind 的 data_id='TX' 與 TAIFEX 的「臺股期貨」範圍不同
      （例如含不含小型臺指 MTX、微型臺指）
    • 自營商是否含避險部位
    • 口數 vs 契約金額欄位抓錯
  先把差異查清楚再動手，不要調低 MATCH_MIN 硬過。''')
    return ok, rate, len(both)


def main():
    init_db()
    tok = token()
    if not tok:
        print('❌ config_local.py 沒有 FINMIND_TOKEN')
        return

    print(f'FinMind 台指期三大法人回填　dataset={DATASET}　data_id={DATA_ID}')
    print('模式：' + ('★ 實際抓取並寫入' if APPLY else '試跑（只對帳 + 報告）'))
    print()

    ok, rate, n = reconcile(tok)
    if not ok:
        return

    # ── 算缺哪幾天（以 TAIEX 交易日為權威日曆，不用 MAX(date) 水位線／陷阱45）──
    conn = get_conn()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? AND date<? AND close>0 "
        "ORDER BY date", (FROM, TO))]
    have = {r[0] for r in conn.execute('SELECT DISTINCT date FROM futures_institutional')}
    conn.close()
    miss = [d for d in cal if d not in have]

    print('\n' + '=' * 72)
    print(f'【回填範圍】{FROM} ~ {TO}（TAIFEX 邊界之前）')
    print('=' * 72)
    print(f'  交易日 {len(cal)} 天　已有 {len(cal)-len(miss)} 天　缺 {len(miss)} 天')
    if not miss:
        print('  完整 ✅')
        return
    print(f'  缺漏範圍 {miss[0]} ~ {miss[-1]}')

    # 切半年一段（降低請求數；FinMind 支援日期區間）
    wins, cur = [], datetime.strptime(miss[0], '%Y-%m-%d')
    end = datetime.strptime(miss[-1], '%Y-%m-%d')
    while cur <= end:
        nxt = min(cur + timedelta(days=182), end)
        wins.append((cur.strftime('%Y-%m-%d'), nxt.strftime('%Y-%m-%d')))
        cur = nxt + timedelta(days=1)
    print(f'  切成 {len(wins)} 個區間（半年/次）⇒ 約 {len(wins)*SLEEP/60:.1f} 分鐘')

    if not APPLY:
        print('\n※ 對帳已通過。執行：python3 backfill_futures_finmind.py --apply')
        print('※ 建議先備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)')
        return

    want = set(miss)
    wrote = blank = fail = 0
    for i, (s, e) in enumerate(wins, 1):
        try:
            fm, _ = fetch(s, e, tok)
            if not fm:
                blank += 1
                print(f'  ⚠️ {s}~{e}：FinMind 回 0 列')
            for d, data in fm.items():
                # 只寫我們確實缺的日期，不覆蓋 TAIFEX 既有資料
                if d in want:
                    save_futures_institutional(d, data)
                    wrote += 1
        except Exception as ex:
            fail += 1
            print(f'  {s}~{e} 失敗：{ex}')
        print(f'  [{i}/{len(wins)}] {s}~{e}　累計寫入 {wrote} 天'
              f'　空回應 {blank}　失敗 {fail}')
        time.sleep(SLEEP)

    # ── 收尾驗證 ──
    conn = get_conn()
    have2 = {r[0] for r in conn.execute('SELECT DISTINCT date FROM futures_institutional')}
    conn.close()
    still = [d for d in cal if d not in have2]
    print(f'\n  ── 完成：寫入 {wrote} 天　空回應 {blank} 區間　失敗 {fail}')
    print(f'  回填後覆蓋：{len(cal)-len(still)} / {len(cal)} 天'
          f'（{(len(cal)-len(still))/len(cal)*100:.1f}%）'
          + ('　✅' if len(still) <= len(cal) * 0.02 else f'　⚠️ 仍缺 {len(still)} 天'))
    print(f'''
下一步：
  1. python3 backfill_market_signals.py --apply --only s4   （約 37 分）
  2. python3 backfill_market_signals.py --apply --only s2   （約 41 分）
  3. 重新校準 Signal 4 的百分位切點（indicators.PCT_HI/MID/LO）
  4. 重測策略D（真觸發條件 + 全市場 + 配對設計 + 空頭年）''')


if __name__ == '__main__':
    main()
