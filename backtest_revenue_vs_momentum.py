#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_revenue_vs_momentum.py — 月營收 YoY 是真資訊，還是動能的代理？

════════════════════════════════════════════════════════════════════════
要驗證的問題（2026-10-07）—— 這是決定前一支結論真偽的那一步
════════════════════════════════════════════════════════════════════════

`backtest_revenue_signal.py` 量到：
    高YoY − 低YoY（產業內、20日）  **+1.98%/月　t = +6.44　n=101**
    除息診斷：其他月 +2.12% ＞ 除息月 +1.72%  ⇒ **不是股利造成的** ✅

**但還有一個可能完全推翻它的解釋：**

> 營收好 → 股價**已經先漲過** → 「高 YoY 組」等於「最近漲過的股票」
> → 20 日前瞻報酬只是在捕捉**動能延續**。

如果是這樣，YoY 就**不是正交的新資訊**，而是技術面 40% 已經在抓的東西
換了個包裝。那整件事會退回原點（而這個專案最核心的發現正是
「評分 100% 的輸入都是已經發生的事」）。

**三層檢定：**

  A. 診斷：corr(YoY 排名, 公布前報酬排名) 有多高？
     → 若本來就幾乎不相關，動能混淆根本不嚴重。

  B. ★ 主檢定：**雙重排序**。先按「公布前報酬」分組，**在組內**再按 YoY 分組。
     ⇒ 比較的是「同樣已經漲過/跌過的股票裡，YoY 高的是否還贏」。
     YoY 若存活 ⇒ 真的是新資訊。

  C. Horse race：Fama-MacBeth 橫斷面迴歸
         ret = a + b1·YoY排名 + b2·前20日報酬排名 + b3·前60日報酬排名
     ⇒ 同時放進去，看誰的係數還活著。這比雙重排序更有效率
       （用到全部資料，不只極端組），兩者互為印證。

════════════════════════════════════════════════════════════════════════
設計決定與理由
════════════════════════════════════════════════════════════════════════

**為什麼排名改用「全市場」而不是「產業內」：**
  前一支實測 產業內 +1.98% vs 全市場 +2.07%——**幾乎相同**
  ⇒ 產業效應不是混淆源。把自由度留給 prior-return 分組，
    避免 5(產業) × 5(prior) × 5(YoY) 把每格切到只剩個位數。

**「公布前報酬」的兩個定義（都測）：**
  • `prior20`：t0 前 20 個交易日 ⇒ **涵蓋公布日前後的反應**
                （真實公布日在次月 1~10 日，t0 是 11 日）
                這正是要控制的「市場已經反應掉的部分」
  • `prior60`：t0 前 60 個交易日 ⇒ 中期動能

**沿用前一支的四道防護（直接 import，不重寫）：**
  ① Fama-MacBeth（月營收全市場同月公布 ⇒ 有效樣本是月數）
  ② 除息：無法調整，但前一支的診斷已排除它是主因
  ③ point-in-time 宇宙（不看 t0 之後任何資訊）
  ④ 公司行為守衛（陷阱49）

判定（事前訂好）：
  B. 雙重排序後 YoY spread 的 t：
       ≥ 2.5 → YoY 在控制動能後仍然有效 ⇒ **真資訊**
       < 2.0 → 消失 ⇒ **動能的代理，歸檔**
  C. 迴歸 b1 的 t 值同標準；若 b1 死而 b2/b3 活 ⇒ 確認是動能。

用法：
    python3 backtest_revenue_vs_momentum.py
"""

import statistics as st
import sys
from collections import defaultdict

try:
    import numpy as np
except ImportError:
    np = None

# 直接沿用前一支的 helper，避免重複實作（陷阱33 的教訓：
# 同一邏輯在多處各寫一份，遲早不同步）
from backtest_revenue_signal import (
    conn, corporate_actions, fm_stats,
    HOLD_PRIMARY, PIT_LOOKBACK_DAYS, PIT_MIN_DAYS, PIT_MIN_TURNOVER, START,
)

PRIOR_GROUPS = 5        # 公布前報酬分幾組
YOY_SPLIT    = 3        # 組內 YoY 取前 1/3 減後 1/3
MIN_CELL     = 10       # 每個 cell 的 1/3 至少這麼多檔


def pct_ranks(rows, key):
    """回傳 {id: 百分位 0~1}，同月橫斷面排名（免疫離群值）。"""
    g = sorted(rows, key=lambda r: r[key])
    n = len(g) - 1
    return {id(r): (i / n if n else 0.5) for i, r in enumerate(g)}


def main():
    if np is None:
        print('⚠️ 沒有 numpy，C 段迴歸會跳過（A、B 仍可跑）')

    c = conn()
    print('月營收 YoY vs 動能　——　YoY 是真資訊還是動能的代理？')

    print('\n掃描公司行為…', end='', flush=True)
    ca, cal, ci = corporate_actions(c)
    print(f' {sum(len(v) for v in ca.values())} 事件 / {len(ca)} 檔')

    mk = dict(c.execute('SELECT code,market FROM stocks').fetchall())

    # ── 月營收 ──
    rev, avail = defaultdict(list), {}
    for y, m, ad, code, yoy in c.execute(
            'SELECT rev_year,rev_month,avail_date,code,yoy_pct FROM monthly_revenue '
            'WHERE yoy_pct IS NOT NULL AND revenue>0'):
        rev[(y, m)].append((code, yoy))
        avail[(y, m)] = ad
    months = sorted(rev)

    # ── 每月需要的四個日期：t0-60、t0-20、t0、t0+20 ──
    plan = []
    for ym in months:
        t0i = next((i for i, d in enumerate(cal) if d >= avail[ym]), None)
        if t0i is None or t0i < 60 or t0i + HOLD_PRIMARY >= len(cal):
            continue
        plan.append({'ym': ym, 'p60': cal[t0i - 60], 'p20': cal[t0i - 20],
                     't0': cal[t0i], 't1': cal[t0i + HOLD_PRIMARY]})
    print(f'可用月份：{len(plan)}（需 t0 前 60 日 + 後 {HOLD_PRIMARY} 日）')

    need = set()
    for p in plan:
        need |= {p['p60'], p['p20'], p['t0'], p['t1']}
    px = defaultdict(dict)
    qs = ','.join('?' * len(need))
    for code, d, close in c.execute(
            f'SELECT code,date,close FROM prices WHERE date IN ({qs}) AND close>0',
            tuple(need)):
        px[d][code] = close
    print(f'載入 {len(need)} 個日期的收盤價')

    # ── point-in-time 宇宙（③）──
    print('計算 point-in-time 宇宙…', end='', flush=True)
    for p in plan:
        i0 = ci[p['t0']]
        lo = cal[max(0, i0 - PIT_LOOKBACK_DAYS)]
        rows = c.execute(
            'SELECT code,COUNT(*) n,AVG(value) av FROM prices '
            'WHERE date>=? AND date<? AND code!=? GROUP BY code HAVING n>=? AND av>=?',
            (lo, p['t0'], 'TAIEX', PIT_MIN_DAYS, PIT_MIN_TURNOVER)).fetchall()
        p['uni'] = {r[0] for r in rows
                    if mk.get(r[0]) == 'TWSE' and len(r[0]) == 4
                    and r[0].isdigit() and not r[0].startswith('00')}
    print(' 完成')

    # ── 建觀察 ──
    obs = {}
    for p in plan:
        out = []
        for code, yoy in rev[p['ym']]:
            if code not in p['uni']:
                continue
            c60, c20, c0, c1 = (px[p['p60']].get(code), px[p['p20']].get(code),
                                px[p['t0']].get(code), px[p['t1']].get(code))
            if not all((c60, c20, c0, c1)):
                continue
            # ④ 公司行為：t0-60 ~ t1 任一處有事件就整筆剔除
            evs = ca.get(code)
            if evs:
                a, b = ci[p['p60']], ci[p['t1']]
                if any(d in ci and a < ci[d] <= b for d in evs):
                    continue
            out.append({'code': code, 'yoy': yoy,
                        'prior20': (c0 / c20 - 1) * 100,
                        'prior60': (c0 / c60 - 1) * 100,
                        'ret': (c1 / c0 - 1) * 100})
        if len(out) >= PRIOR_GROUPS * YOY_SPLIT * MIN_CELL:
            obs[p['ym']] = out
    print(f'有效月份 {len(obs)}　平均每月 '
          f'{st.mean([len(v) for v in obs.values()]):.0f} 檔觀察')

    # ══════════════════════════════════════════════════════════
    print()
    print('=' * 94)
    print('【A 診斷】YoY 排名 與「公布前報酬」排名的相關性')
    print('=' * 94)
    print('    若本來就幾乎不相關 ⇒ 動能混淆不嚴重，B/C 應該會存活')
    for pk, pn in (('prior20', '前20日報酬'), ('prior60', '前60日報酬')):
        cs = []
        for ym, rows in obs.items():
            ry = pct_ranks(rows, 'yoy')
            rp = pct_ranks(rows, pk)
            a = [ry[id(r)] for r in rows]
            b = [rp[id(r)] for r in rows]
            ma, mb = st.mean(a), st.mean(b)
            num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
            if den:
                cs.append(num / den)
        print(f'    corr(YoY, {pn})　逐月平均 {st.mean(cs):+.3f}　'
              f'（最小 {min(cs):+.3f}　最大 {max(cs):+.3f}）')
    print('    ⇒ 參考：|corr| <0.2 算弱、0.2~0.4 中等、>0.4 強')

    # ══════════════════════════════════════════════════════════
    print()
    print('=' * 94)
    print(f'【B ★主檢定】雙重排序：先按公布前報酬分 {PRIOR_GROUPS} 組，'
          f'組內再取 YoY 前後 1/{YOY_SPLIT}')
    print('=' * 94)

    def double_sort(prior_key):
        """回傳 (月度 spread 清單, 每格平均檔數, 各 prior 組的 spread)"""
        series, cells, per_group = [], [], defaultdict(list)
        for ym in sorted(obs):
            rows = sorted(obs[ym], key=lambda r: r[prior_key])
            k = len(rows) // PRIOR_GROUPS
            gs = []
            for gi in range(PRIOR_GROUPS):
                seg = rows[gi * k:(gi + 1) * k] if gi < PRIOR_GROUPS - 1 else rows[gi * k:]
                if len(seg) < YOY_SPLIT * MIN_CELL:
                    continue
                seg = sorted(seg, key=lambda r: r['yoy'])
                j = len(seg) // YOY_SPLIT
                lo = [r['ret'] for r in seg[:j]]
                hi = [r['ret'] for r in seg[-j:]]
                cells.append(j)
                gs.append(st.mean(hi) - st.mean(lo))
                per_group[gi].append(st.mean(hi) - st.mean(lo))
            if len(gs) == PRIOR_GROUPS:
                series.append(st.mean(gs))     # 各 prior 組平均 ⇒ 控制了動能
        return series, cells, per_group

    results = {}
    for pk, pn in (('prior20', '前20日報酬'), ('prior60', '前60日報酬')):
        s, cells, pg = double_sort(pk)
        print(f'\n  ── 控制「{pn}」──　每格 1/{YOY_SPLIT} 平均 {st.mean(cells):.0f} 檔')
        r = fm_stats(s, f'  ★ 組內 高YoY − 低YoY')
        results[pk] = r
        print(f'     各 prior 組分別看（低動能 → 高動能）：')
        for gi in range(PRIOR_GROUPS):
            v = pg.get(gi, [])
            if v:
                tt = st.mean(v) / (st.stdev(v) / len(v) ** 0.5) if len(v) > 2 else 0
                print(f'       第{gi+1}組（{"最弱" if gi==0 else "最強" if gi==PRIOR_GROUPS-1 else "  "}）'
                      f'　{st.mean(v):>+7.2f}%　t={tt:>+5.2f}　n={len(v)}')

    # 對照：沒有控制動能的版本（= 前一支的全市場版）
    print('\n  ── 對照：完全不控制動能（單排序）──')
    plain = []
    for ym in sorted(obs):
        g = sorted(obs[ym], key=lambda r: r['yoy'])
        j = len(g) // YOY_SPLIT
        plain.append(st.mean([r['ret'] for r in g[-j:]])
                     - st.mean([r['ret'] for r in g[:j]]))
    base = fm_stats(plain, '    高YoY − 低YoY（未控制）')

    if base and results.get('prior20'):
        keep = results['prior20']['mean'] / base['mean'] * 100
        print(f'\n  ★ 控制前20日報酬後，spread 保留了 {keep:.0f}%'
              f'（{base["mean"]:+.2f}% → {results["prior20"]["mean"]:+.2f}%）')

    # ══════════════════════════════════════════════════════════
    print()
    print('=' * 94)
    print('【C Horse race】Fama-MacBeth 橫斷面迴歸（三個變數同時放進去）')
    print('=' * 94)
    if np is None:
        print('  （略過：沒有 numpy）')
    else:
        print('    ret = a + b1·YoY排名 + b2·前20日報酬排名 + b3·前60日報酬排名')
        print('    排名一律是同月百分位 0~1 ⇒ 係數可讀成「從最低排到最高的報酬差」')
        coefs = []
        for ym in sorted(obs):
            rows = obs[ym]
            ry = pct_ranks(rows, 'yoy')
            r20 = pct_ranks(rows, 'prior20')
            r60 = pct_ranks(rows, 'prior60')
            X = np.array([[1.0, ry[id(r)], r20[id(r)], r60[id(r)]] for r in rows])
            y = np.array([r['ret'] for r in rows])
            try:
                b, *_ = np.linalg.lstsq(X, y, rcond=None)
                coefs.append(b)
            except Exception:
                pass
        if coefs:
            C = np.array(coefs)
            names = ['截距', '★ YoY 排名', '前20日報酬排名', '前60日報酬排名']
            print(f'\n    {"":<20}{"月數":>5}{"係數":>10}{"SE":>8}{"t":>8}')
            for j, nmj in enumerate(names):
                v = C[:, j]
                m = float(v.mean())
                se = float(v.std(ddof=1) / len(v) ** 0.5)
                t = m / se if se else 0
                vd = ('★ 顯著' if abs(t) >= 2.5 else
                      '⚠️ 邊界' if abs(t) >= 2.0 else '⚪ 不顯著')
                print(f'    {nmj:<20}{len(v):>5}{m:>+9.2f}%{se:>8.2f}{t:>+8.2f}  {vd}')
            print('\n    判讀：b1（YoY）顯著而 b2/b3 不顯著 ⇒ YoY 是更基本的訊號')
            print('          b1 不顯著而 b2/b3 顯著 ⇒ 前一支量到的是動能')

    # ══════════════════════════════════════════════════════════
    print()
    print('=' * 94)
    print('【結論判定】（標準事前訂好，不看數字再找理由）')
    print('=' * 94)
    r = results.get('prior20')
    if r:
        t = abs(r['t'])
        if t >= 2.5:
            print(f'  ✅ YoY 在控制「前20日報酬」後仍然 t={r["t"]:+.2f}'
                  f'　⇒ **不是動能的代理，是真資訊**')
            print(f'     ⚠️ 但這只是「不是動能」。可實施性仍受限：')
            print(f'        • long-only 的 alpha 約是 spread 的一半')
            print(f'        • 每月換倉要付 0.47% 來回成本')
            print(f'        • 上面的數字是「1/{YOY_SPLIT} 組約 {st.mean(cells):.0f} 檔等權」，'
                  f'你持 5 檔 ⇒ 個股雜訊會蓋掉 1pp/月 的優勢（2026-10-05 實測'
                  f'隨機5檔資金曲線帶寬 20~143pp）')
        elif t >= 2.0:
            print(f'  ⚠️ 邊界（t={r["t"]:+.2f}）⇒ 部分是真資訊、部分是動能，需更多樣本')
        else:
            print(f'  ❌ 控制動能後 t={r["t"]:+.2f} ⇒ **前一支量到的主要是動能**，歸檔')
    print("""
  限制（與前一支相同，引用時必須一起講）：
    • 除權息無法調整（exdividend 只有 2026 年、DB 存未調整收盤價）
    • avail_date 是保守估計（次月11日），抓不到公布後 1~2 天的效果
    • 上櫃與 30 檔 KY 股不在宇宙內
    • 空頭樣本僅 2018、2022 兩年""".rstrip())
    c.close()


if __name__ == '__main__':
    main()
