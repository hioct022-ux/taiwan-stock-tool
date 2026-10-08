#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibrate_signal4.py — 回填 2018 之後，重新校準 Signal 4 的滾動百分位切點

════════════════════════════════════════════════════════════════════════
為什麼需要這一支（陷阱51 的待辦第 3 步）
════════════════════════════════════════════════════════════════════════

2026-10-07 把 S4 從「絕對張數門檻」改成「滾動百分位」之後，
切點 95/85/70 的**實際觸發率**量到：

    ±3分 11.6%（目標 5%）　≥±2分 21.6%（15%）　≥±1分 38.7%（30%）

當時**刻意不動切點**，理由寫在 `indicators.py`：
`chips` 只有 258 天，**300 日視窗從來沒填滿過**（60→258 一路膨脹），
那個觸發率不具代表性。

回填 2018 之後（約 2,100 個交易日）視窗才真正是 trailing 300，
**現在才有資格校準**。

════════════════════════════════════════════════════════════════════════
這支腳本做四件事
════════════════════════════════════════════════════════════════════════

  ① 用**真正填滿的 trailing 300 視窗**量現行切點的觸發率
  ② 搜尋能打中 5/15/30% 的切點，**並且逐年檢查**
  ③ ★ 量級漂移有沒有被消掉
     🚨 **第一版的判準「逐年全距 <10pp」是錯的，2026-10-08 已更正。**
        理由：純抽樣雜訊（p=30%、n≈240/年）標準誤就有 2.96pp
        ⇒ 9 年的期望全距約 9.2pp；而且真實的市場波動本來就會讓
        極端日的密度逐年不同（2020 COVID／2026 真的多、2025 真的平靜）。
        **「全距小」本來就不該是期待。**
        正解是看 ① corr(量級, 觸發率) ② **同量級年份的對照**（後者才決定性）。
  ④ 投信那一項分開校準（它只有 ±1 分，級距不同）

**只報告、不改檔案。** 看完數字再決定要不要動 `PCT_HI/MID/LO`
—— 照陷阱34 的教訓，校準過的數字要寫進文件、說明用哪段資料算的。

⚠️ 跑之前必須先完成：
    python3 backfill_futures_finmind.py --apply     （S3）
    python3 backfill_market_signals.py --apply      （S4／S2）
  否則 `chips` 仍只有 258 天，量出來的東西跟 10/07 當天一樣沒有代表性。

用法：
    python3 calibrate_signal4.py
    python3 calibrate_signal4.py --window 250      # 換視窗長度看穩定性
"""
import os
import sys
import statistics as st
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_chips_market_series
from indicators import PCT_HI, PCT_MID, PCT_LO, PCT_MIN_N

WINDOW = 300
if '--window' in sys.argv:
    WINDOW = int(sys.argv[sys.argv.index('--window') + 1])

# 設計目標（陷阱34 立的原則，沿用）
TARGET = {'hi': 5.0, 'mid': 15.0, 'lo': 30.0}   # ±3分 / ≥±2分 / ≥±1分 的天數佔比


def pct_of(value, hist):
    """|value| 在 |hist| 中的百分位（與 indicators.pct_rank_score 同一算法）。"""
    h = [abs(x) for x in hist if x is not None]
    if not h:
        return None
    a = abs(value)
    return sum(1 for x in h if x <= a) / len(h) * 100


def build(series, col, window):
    """回傳 [(date, value, pct), ...]，pct 只用「該日及之前」的視窗算（不偷看未來）。"""
    out, hist = [], []
    for r in series:
        v = r[col] or 0
        h = (hist + [v])[-window:]
        p = pct_of(v, h) if len(h) >= PCT_MIN_N else None
        out.append((r['date'], v, p))
        hist = h
    return out


def rates(rows, hi, mid, lo):
    """回傳 (±3分%, ≥±2分%, ≥±1分%, 可評分天數)"""
    ps = [p for _, _, p in rows if p is not None]
    n = len(ps) or 1
    return (sum(1 for p in ps if p >= hi) / n * 100,
            sum(1 for p in ps if p >= mid) / n * 100,
            sum(1 for p in ps if p >= lo) / n * 100,
            len(ps))


def search(rows):
    """搜尋能打中 TARGET 的切點（直接取分位，不用迴圈逼近）。"""
    ps = sorted(p for _, _, p in rows if p is not None)
    if not ps:
        return None
    def cut(target_pct):
        # 要讓「百分位 ≥ X」的天數佔 target_pct%，X 就是 ps 的 (100-target) 分位
        idx = int(len(ps) * (1 - target_pct / 100))
        return ps[min(max(idx, 0), len(ps) - 1)]
    return cut(TARGET['hi']), cut(TARGET['mid']), cut(TARGET['lo'])


def main():
    series = get_chips_market_series()
    if not series:
        print('❌ chips 沒有資料')
        return
    n_days = len(series)
    print('Signal 4 滾動百分位切點校準')
    print(f'資料：{n_days} 個交易日　{series[0]["date"]} ~ {series[-1]["date"]}')
    print(f'視窗：trailing {WINDOW} 日　最小樣本 {PCT_MIN_N} 日')

    if n_days < WINDOW * 1.5:
        print(f'''
🚨 **資料不足，現在校準沒有意義。**
   只有 {n_days} 天，而視窗要 {WINDOW} 天 ⇒ 視窗大部分時間填不滿、一路膨脹，
   量出來的觸發率與 2026-10-07 當天一樣不具代表性（那次就是 258 天）。

   先完成回填：
     python3 backfill_futures_finmind.py --apply
     python3 backfill_market_signals.py --apply --only s4
''')
        return

    for label, col, is_tri in (('外資', 'foreign_net', True),
                               ('投信', 'trust_net', False)):
        rows = build(series, col, WINDOW)
        r3, r2, r1, n = rates(rows, PCT_HI, PCT_MID, PCT_LO)
        print('\n' + '=' * 72)
        print(f'【{label}】可評分 {n} 天（暖身期 {n_days - n} 天不計分）')
        print('=' * 72)
        print(f'  現行切點 {PCT_HI}/{PCT_MID}/{PCT_LO} 的實際觸發率：')
        print(f'    ±3分 {r3:>5.1f}%（目標 {TARGET["hi"]}%）'
              f'　≥±2分 {r2:>5.1f}%（{TARGET["mid"]}%）'
              f'　≥±1分 {r1:>5.1f}%（{TARGET["lo"]}%）')
        # 2026-10-07 的基準，供對照
        if label == '外資':
            print('    （2026-10-07 在 258 天／膨脹視窗上量到 11.6 / 21.6 / 38.7%）')

        s = search(rows)
        if s:
            c3, c2, c1 = s
            print(f'\n  ★ 要打中 {TARGET["hi"]}/{TARGET["mid"]}/{TARGET["lo"]}% 的切點：'
                  f'**{c3:.1f} / {c2:.1f} / {c1:.1f}**')
            v3, v2, v1, _ = rates(rows, c3, c2, c1)
            print(f'    驗算：{v3:.1f} / {v2:.1f} / {v1:.1f}%')

        # ★ 尺度不變性的實證：逐年觸發率
        print(f'\n  ★ 逐年觸發率（改用百分位的全部理由就在這一欄）：')
        print(f'    {"年":<6}{"可評分":>7}{"±3分":>8}{"≥±2分":>8}{"≥±1分":>8}'
              f'{"外資絕對值中位":>14}')
        by_year = defaultdict(list)
        for d, v, p in rows:
            by_year[d[:4]].append((d, v, p))
        for y in sorted(by_year):
            yr = by_year[y]
            a3, a2, a1, ny = rates(yr, PCT_HI, PCT_MID, PCT_LO)
            if ny < 30:
                print(f'    {y:<6}{ny:>7}   （樣本不足，不解讀）')
                continue
            med = st.median([abs(v) for _, v, _ in yr])
            print(f'    {y:<6}{ny:>7}{a3:>7.1f}%{a2:>7.1f}%{a1:>7.1f}%{med:>14,.0f}')

        yrs = [y for y in sorted(by_year)
               if rates(by_year[y], PCT_HI, PCT_MID, PCT_LO)[3] >= 30]
        if len(yrs) >= 3:
            import math
            r1s = [rates(by_year[y], PCT_HI, PCT_MID, PCT_LO)[2] for y in yrs]
            meds = [st.median([abs(v) for _, v, _ in by_year[y]]) for y in yrs]
            ns = [rates(by_year[y], PCT_HI, PCT_MID, PCT_LO)[3] for y in yrs]

            def pearson(a, b):
                ma, mb = st.mean(a), st.mean(b)
                num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
                den = (sum((x - ma) ** 2 for x in a)
                       * sum((y - mb) ** 2 for y in b)) ** .5
                return num / den if den else 0.0

            rng = max(r1s) - min(r1s)
            se = math.sqrt(0.30 * 0.70 / st.mean(ns)) * 100
            r = pearson(meds, r1s)
            print(f'\n    ≥±1分 逐年全距：{rng:.1f}pp（{min(r1s):.1f}% ~ {max(r1s):.1f}%）')
            print(f'    量級中位數 {min(meds):,.0f} ~ {max(meds):,.0f}'
                  f'（差 {max(meds)/max(min(meds),1):.1f} 倍）')
            print(f'\n    ① 純抽樣雜訊的期望全距 ≈ 3.1×SE = {3.1*se:.1f}pp'
                  f'（p=30%、n≈{st.mean(ns):.0f}/年）'
                  f'　⇒ 實測是雜訊的 {rng/(3.1*se):.1f} 倍')
            print(f'    ② corr(量級, 觸發率) = **{r:+.3f}**（n={len(yrs)}）')

            # ③ 同量級年份的對照 —— 決定性的那一項
            pairs = sorted(((abs(meds[i] - meds[j]) / max(meds[i], meds[j]),
                             yrs[i], meds[i], r1s[i], yrs[j], meds[j], r1s[j])
                            for i in range(len(yrs)) for j in range(i + 1, len(yrs))))
            print(f'\n    ③ ★ 同量級年份對照（量級最接近的一對，這項才決定性）：')
            d, ya, ma_, ra, yb, mb_, rb = pairs[0]
            print(f'       {ya} 量級 {ma_:>9,.0f} → {ra:.1f}%')
            print(f'       {yb} 量級 {mb_:>9,.0f} → {rb:.1f}%')
            print(f'       量級只差 {d*100:.1f}%，觸發率差 **{abs(ra-rb):.1f}pp**')
            print(f'''
    ⇒ 怎麼讀（🚨 不要只看全距，第一版那個判準是錯的）：
       • 若 ③ 顯示「量級幾乎相同但觸發率差很多」
         ⇒ **量級不是決定因素**，百分位把漂移消掉了，剩下的是真實波動差異
       • 若 ② 的 r 很高（>0.85）**且** ③ 顯示同量級年份觸發率也接近
         ⇒ 那才是漂移沒消掉，要回頭想別的做法
       ⚠️ 量級與波動度本身互相混淆（波動大的年份絕對流量也大），
         n={len(yrs)} 分不開 ⇒ 不可宣稱「完全消除」，只能說「不是主要驅動因素」''')
        if not is_tri:
            print('\n  ⚠️ 投信只有 ±1 分，所以只有「≥±1分」那一欄需要打中 30%；'
                  '±3/±2 的欄位對它沒有意義。')

    print('\n' + '=' * 72)
    print('【下一步】')
    print('=' * 72)
    print('''
  若建議切點與現行值差距明顯（例如 ≥3pp），就更新 indicators.py：
      PCT_HI, PCT_MID, PCT_LO = <新值>
  並在該處註解寫明「用哪段資料、多少天、哪一天算的」—— 陷阱34 的教訓是
  **校準過的數字若沒記來源，日後沒人知道它還適用不適用**。

  改完之後要跑的驗證：
    1. python3 indicators.py                （單元測試仍須全過）
    2. 比對新舊大盤評分在 2018／2020／2022 的差異
    3. 才重測策略D''')


if __name__ == '__main__':
    main()
