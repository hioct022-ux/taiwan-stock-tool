#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_revenue_signal.py — 月營收 YoY 對未來報酬有預測力嗎？（Fama-MacBeth）

════════════════════════════════════════════════════════════════════════
要驗證的問題（2026-10-07）
════════════════════════════════════════════════════════════════════════

**月營收 YoY 的橫斷面排名，對公布後 20 個交易日的報酬有預測力嗎？**

為什麼值得測（與前六次被否決的提案不同）：

  2026-09-23 量到：個股評分與**未來**報酬 corr = 0、與**過去** = +0.25。
  看組成就知道為什麼，而且比原本以為的更徹底：

      技術面 40%  = 價格的函數
      籌碼面 35%  = 昨天的成交結果
      基本面 25%  = PE / PB / 殖利率 → 分母是價格、分子一季才動一次
                    ⇒ 它的「日變動」幾乎也全部來自價格

  **⇒ 三面加權裡真正獨立於價格的成分幾乎是零。**

  前六次被否決的提案（🎯🔥型態、移動停損、confirm_days、策略F、ER過濾、
  先殺後拉、量能水位、類股占比）**全部都是把價格重新排序**。
  月營收是第一個真正正交的候選：營運事實、分子自己會動。

  文獻上「盈餘／營收意外後的漂移」是少數反覆被重現的異常現象。

════════════════════════════════════════════════════════════════════════
🚨 四個會製造假結論的陷阱，全部處理掉了
════════════════════════════════════════════════════════════════════════

**① 樣本獨立性：月營收是「全市場同一個月一起公布」。**
   104 個月 × 約 1,000 檔 ≈ 10 萬筆，但**不是 10 萬個獨立樣本**。
   同月份所有觀察共享同一個市場狀態。
   這正是 2026-09-15「量能水位」的病根（n=15 實際只有 n≈4）。

   ⇒ **Fama-MacBeth**：每月算一次「高 YoY 組 − 低 YoY 組」的報酬差，
     再檢定那 ~104 個月度差值的時間序列。
     **有效樣本 = 月數，標準誤 = SD(月度差)/√月數。**

**② 🚨 除權息（本次最大的地雷，差一點踩中）**
   `exdividend` 表**只有 2026 年**（1,069 列），2018~2025 全部是 0。
   而 DB 存**未調整收盤價**（陷阱49）⇒ 歷史除息無法調整也無法排除。

   實測：除息集中 **6~9 月佔 93.6%**、平均幅度 **3.91%**。
   而它**與訊號相關**：
       高 YoY（電子）→ 殖利率低 → 拖累小
       低 YoY（傳產/金融）→ 殖利率高 → 拖累大
   ⇒ 會產生**假的「高 YoY 組贏」**，量級 1~4pp，與要找的效果同數量級。

   三道防線：
     (a) **主檢定用「產業內排名」**——同產業除息時點與殖利率接近
     (b) **必做診斷：分 1~12 月各自的 spread**
         → **若訊號只出現在 6~9 月，就知道是股利不是營收**（自我診斷）
     (c) Robustness：排除 6~9 月重跑

**③ 倖存者偏誤：宇宙必須 point-in-time。**
   2026-09-24 的教訓：「回測宇宙的組成時間必須早於回測期間的起點」。
   用「2025-09 起有流動性的 512 檔」去跑 2018 年 = 先看答案再考試。
   ⇒ 每個月**重新**計算宇宙：t0 前 6 個月有 ≥60 個交易日、
     且該窗口日均成交金額 ≥ 0.5 億。**完全不看 t0 之後的任何資訊。**

**④ 公司行為（陷阱49）：** 相鄰交易日比值在 [0.7, 1.3] 之外者視為分割／減資／
   大額除息，**整筆觀察剔除**（不是把報酬設 0——那會留下一個偏誤的觀察）。

════════════════════════════════════════════════════════════════════════
⚠️ 多重檢定：事前指定主檢定，其餘標為次要
════════════════════════════════════════════════════════════════════════

測 2 種訊號 × 2 種排名基準 × 2 種持有期 = 8 組，**那就是 8 次機會**。
不預先指定的話，挑最好看的那組報出去就是資料探勘。

  ★ **主檢定（事前指定）：YoY 水準、產業內排名、20 日持有**
      理由：YoY 水準比加速度簡單（優先測簡單的）；
            產業內排名控制除息與產業效應；
            20 日 ≈ 一個月，與月營收頻率匹配，也接近策略的 10 日持有期。

  其餘 7 組一律標示「次要，僅供參考」，**不可單獨拿出來當結論**。

判定標準（事前訂好）：
  |t| = |mean / SE|
    ≥ 2.5  → 有訊號（但仍要通過「不是只在 6~9 月」的診斷）
    2 ~ 2.5 → 邊界，需更多樣本
    < 2    → 測不出

用法：
    python3 backtest_revenue_signal.py
"""

import sqlite3
import statistics as st
import sys
from collections import defaultdict

DB = 'data/stock.db'

HOLD_PRIMARY = 20          # ★ 主檢定持有交易日數
HOLD_ALT     = 60          # 次要
N_GROUP      = 5           # 五等分
MIN_PER_GROUP = 8          # 每組至少這麼多檔才算該月有效
START        = '2018-01-01'

# point-in-time 宇宙（③）
PIT_LOOKBACK_DAYS = 130    # 約 6 個月的交易日
PIT_MIN_DAYS      = 60
PIT_MIN_TURNOVER  = 5e7    # 日均成交金額 0.5 億

# 公司行為守衛（④）
CA_LO, CA_HI = 0.7, 1.3

IND_NAMES = {
    '01': '水泥', '02': '食品', '03': '塑膠', '04': '紡織', '05': '電機',
    '06': '電器電纜', '08': '玻璃', '09': '造紙', '10': '鋼鐵', '11': '橡膠',
    '12': '汽車', '14': '建材營造', '15': '航運', '16': '觀光', '17': '金融保險',
    '18': '貿易百貨', '20': '其他', '21': '化工', '22': '生技醫療', '23': '油電燃氣',
    '24': '半導體', '25': '電腦週邊', '26': '光電', '27': '通信網路',
    '28': '電子零組件', '29': '電子通路', '30': '資訊服務', '31': '其他電子',
    '32': '文化創意', '33': '農業科技', '34': '電子商務',
}


def conn():
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


# ══════════════════════════════════════════════════════════════════
def corporate_actions(c):
    """
    ④ 回傳 {code: set(日期)}，該日相對前一交易日的比值超出 [0.7,1.3]。
    串流掃描，不把 258 萬列全部留在記憶體。
    """
    cal = [r[0] for r in c.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? ORDER BY date", (START,))]
    ci = {d: i for i, d in enumerate(cal)}
    out, prev = defaultdict(set), {}
    for code, date, close in c.execute(
            "SELECT code,date,close FROM prices WHERE code!='TAIEX' AND date>=? "
            "AND close>0 ORDER BY code,date", (START,)):
        p = prev.get(code)
        if p and p[1] in ci and date in ci and ci[date] - ci[p[1]] <= 2:
            r = close / p[0]
            if r < CA_LO or r > CA_HI:
                out[code].add(date)
        prev[code] = (close, date)
    return out, cal, ci


def fm_stats(vals, label, note=''):
    """Fama-MacBeth：月度差值的平均、標準誤、t 值。"""
    n = len(vals)
    if n < 6:
        print(f'  {label:<34}n={n:<4} 樣本太少')
        return None
    m = st.mean(vals)
    se = st.stdev(vals) / (n ** 0.5)
    t = m / se if se else 0
    win = sum(1 for v in vals if v > 0) / n * 100
    verdict = ('★ 有訊號' if abs(t) >= 2.5 else
               '⚠️ 邊界' if abs(t) >= 2.0 else '⚪ 測不出')
    print(f'  {label:<34}n={n:<4}{m:>+8.2f}%　SE {se:>5.2f}　'
          f't={t:>+6.2f}　月勝率 {win:>3.0f}%　{verdict}{note}')
    return {'n': n, 'mean': m, 'se': se, 't': t, 'win': win, 'vals': vals}


def main():
    c = conn()
    print('月營收 YoY 訊號檢定（Fama-MacBeth）')

    print('\n掃描公司行為（陷阱49）…', end='', flush=True)
    ca, cal, ci = corporate_actions(c)
    print(f' {sum(len(v) for v in ca.values())} 個事件 / {len(ca)} 檔')
    print(f'交易日日曆：{cal[0]} ~ {cal[-1]}　{len(cal)} 天')

    ind = dict(c.execute("SELECT code,industry FROM stocks").fetchall())
    mk = dict(c.execute("SELECT code,market FROM stocks").fetchall())

    # ── 月營收：(year,month) → [(code, yoy)] ──
    rev = defaultdict(list)
    avail = {}
    for y, m, ad, code, yoy in c.execute(
            "SELECT rev_year,rev_month,avail_date,code,yoy_pct FROM monthly_revenue "
            "WHERE yoy_pct IS NOT NULL AND revenue>0"):
        rev[(y, m)].append((code, yoy))
        avail[(y, m)] = ad
    months = sorted(rev)
    print(f'月營收：{len(months)} 個月　{months[0]} ~ {months[-1]}')

    # ── 每月的 t0 / t1 ──
    plan = []
    for ym in months:
        t0i = next((i for i, d in enumerate(cal) if d >= avail[ym]), None)
        if t0i is None:
            continue
        ends = {}
        for h in (HOLD_PRIMARY, HOLD_ALT):
            if t0i + h < len(cal):
                ends[h] = cal[t0i + h]
        if HOLD_PRIMARY in ends:
            plan.append((ym, cal[t0i], ends))
    print(f'可用月份（主檢定 {HOLD_PRIMARY} 日前瞻）：{len(plan)}')

    # ── 只載入需要的日期的收盤價 ──
    need = set()
    for _, t0, ends in plan:
        need.add(t0)
        need.update(ends.values())
    px = defaultdict(dict)
    qs = ','.join('?' * len(need))
    for code, d, close in c.execute(
            f"SELECT code,date,close FROM prices WHERE date IN ({qs}) AND close>0",
            tuple(need)):
        px[d][code] = close
    print(f'載入 {len(need)} 個日期的收盤價')

    # ── point-in-time 宇宙（③）──
    print('計算 point-in-time 宇宙…', end='', flush=True)
    pit = {}
    for ym, t0, _ in plan:
        i0 = ci[t0]
        lo = cal[max(0, i0 - PIT_LOOKBACK_DAYS)]
        rows = c.execute(
            "SELECT code,COUNT(*) n,AVG(value) av FROM prices "
            "WHERE date>=? AND date<? AND code!='TAIEX' GROUP BY code "
            "HAVING n>=? AND av>=?", (lo, t0, PIT_MIN_DAYS, PIT_MIN_TURNOVER)).fetchall()
        pit[ym] = {r[0] for r in rows
                   if mk.get(r[0]) == 'TWSE' and len(r[0]) == 4
                   and r[0].isdigit() and not r[0].startswith('00')}
    print(f' 平均 {st.mean([len(v) for v in pit.values()]):.0f} 檔/月'
          f'（{min(len(v) for v in pit.values())} ~ {max(len(v) for v in pit.values())}）')

    # ── 逐月建觀察 ──
    # obs[ym] = [(code, yoy, yoy_accel, ret20, ret60, industry)]
    yoy_hist = defaultdict(dict)      # code → {(y,m): yoy}  給加速度用
    for ym in months:
        for code, yoy in rev[ym]:
            yoy_hist[code][ym] = yoy

    def prev_ym(ym, k):
        y, m = ym
        for _ in range(k):
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        return (y, m)

    obs = {}
    for ym, t0, ends in plan:
        uni = pit[ym]
        rows = []
        for code, yoy in rev[ym]:
            if code not in uni:
                continue
            p0 = px[t0].get(code)
            if not p0:
                continue
            # ④ 公司行為：窗口內有事件就整筆剔除
            evs = ca.get(code)
            rr = {}
            bad = False
            for h, t1 in ends.items():
                if evs:
                    a, b = ci[t0], ci[t1]
                    if any(d in ci and a < ci[d] <= b for d in evs):
                        if h == HOLD_PRIMARY:
                            bad = True
                        continue
                p1 = px[t1].get(code)
                if p1:
                    rr[h] = (p1 / p0 - 1) * 100
            if bad or HOLD_PRIMARY not in rr:
                continue
            # YoY 加速度：本月 YoY − 前 3 月 YoY 平均
            prevs = [yoy_hist[code].get(prev_ym(ym, k)) for k in (1, 2, 3)]
            prevs = [x for x in prevs if x is not None]
            accel = yoy - st.mean(prevs) if len(prevs) == 3 else None
            rows.append({'code': code, 'yoy': yoy, 'accel': accel,
                         'ret': rr, 'ind': ind.get(code, '')})
        if len(rows) >= N_GROUP * MIN_PER_GROUP:
            obs[ym] = rows

    print(f'有效月份：{len(obs)}　平均每月 {st.mean([len(v) for v in obs.values()]):.0f} 檔觀察')

    # ══════════════════════════════════════════════════════════
    def spread_series(key, within_industry, hold):
        """
        每月算一次「高分組 − 低分組」的平均報酬差。
        within_industry=True → 排名在**產業內**做（②(a) 的防線）。
        """
        out = []
        for ym in sorted(obs):
            rows = [r for r in obs[ym]
                    if r.get(key) is not None and hold in r['ret']]
            if len(rows) < N_GROUP * MIN_PER_GROUP:
                continue
            if within_industry:
                scored = []
                by_ind = defaultdict(list)
                for r in rows:
                    by_ind[r['ind']].append(r)
                for g in by_ind.values():
                    if len(g) < N_GROUP:          # 太小的產業無法分組
                        continue
                    g2 = sorted(g, key=lambda r: r[key])
                    for i, r in enumerate(g2):
                        scored.append((i / (len(g2) - 1), r))   # 產業內百分位
                if len(scored) < N_GROUP * MIN_PER_GROUP:
                    continue
                scored.sort(key=lambda x: x[0])
            else:
                g2 = sorted(rows, key=lambda r: r[key])
                scored = [(i / (len(g2) - 1), r) for i, r in enumerate(g2)]
            k = len(scored) // N_GROUP
            lo = [r['ret'][hold] for _, r in scored[:k]]
            hi = [r['ret'][hold] for _, r in scored[-k:]]
            if len(lo) >= MIN_PER_GROUP and len(hi) >= MIN_PER_GROUP:
                out.append((ym, st.mean(hi) - st.mean(lo),
                            st.mean(hi), st.mean(lo),
                            st.mean([r['ret'][hold] for _, r in scored])))
        return out

    print()
    print('=' * 96)
    print('【主檢定（事前指定）】YoY 水準・產業內排名・20 日持有')
    print('=' * 96)
    print(f'  {"":<34}{"月數":<6}{"月度差":>8}{"":>8}{"":>8}{"":>12}')
    pri = spread_series('yoy', True, HOLD_PRIMARY)
    R = fm_stats([x[1] for x in pri], '★ 高YoY − 低YoY（產業內）')

    if pri:
        print(f'\n  參考：高分組平均 {st.mean([x[2] for x in pri]):+.2f}%　'
              f'低分組 {st.mean([x[3] for x in pri]):+.2f}%　'
              f'全體（無條件基準）{st.mean([x[4] for x in pri]):+.2f}%')

    print()
    print('=' * 96)
    print('🚨【必做診斷】分月份看 spread —— 若只出現在 6~9 月，就是股利不是營收')
    print('=' * 96)
    print('    （除息集中 6~9 月佔 93.6%、平均 3.91%，而它與 YoY 反向相關）')
    bym = defaultdict(list)
    for ym, s, *_ in pri:
        # ym 是營收月；實際持有期在次月 11 日起 ⇒ 用「次月」當日曆月
        cm = 1 if ym[1] == 12 else ym[1] + 1
        bym[cm].append(s)
    print(f'\n  {"持有期所在月":<14}{"月數":>5}{"平均 spread":>13}{"":>4}')
    div_m, non_m = [], []
    for m in range(1, 13):
        v = bym.get(m, [])
        if not v:
            continue
        isdiv = m in (6, 7, 8, 9)
        (div_m if isdiv else non_m).extend(v)
        bar = ('█' if st.mean(v) > 0 else '░') * min(28, int(abs(st.mean(v)) * 8))
        print(f'  {m:>2} 月　　　　　{len(v):>5}{st.mean(v):>+12.2f}%  '
              f'{"← 除息月" if isdiv else "        "} {bar}')
    print()
    if div_m and non_m:
        fm_stats(div_m, '  6~9 月（除息月）')
        fm_stats(non_m, '  其他 8 個月')
        print(f'\n  判讀：若「除息月」明顯 > 「其他月」⇒ 訊號很可能是股利造成的假象。')
        print(f'        若兩者接近 ⇒ 訊號不是股利造成的。')

    print()
    print('=' * 96)
    print('【次要，僅供參考——不可單獨當結論】')
    print('=' * 96)
    for key, kn in (('yoy', 'YoY水準'), ('accel', 'YoY加速度')):
        for wi, wn in ((True, '產業內'), (False, '全市場')):
            for h in (HOLD_PRIMARY, HOLD_ALT):
                if key == 'yoy' and wi and h == HOLD_PRIMARY:
                    continue      # 這是主檢定，上面已報
                s = spread_series(key, wi, h)
                fm_stats([x[1] for x in s], f'{kn}・{wn}・{h}日')

    print()
    print('=' * 96)
    print('【分期間穩定性】主檢定拆三段（避免只對單一期間有效）')
    print('=' * 96)
    for lo, hi, lab in ((2018, 2020, '2018-2020'), (2021, 2023, '2021-2023'),
                        (2024, 2026, '2024-2026')):
        v = [s for ym, s, *_ in pri if lo <= ym[0] <= hi]
        fm_stats(v, f'  {lab}')

    print()
    print('=' * 96)
    print('【空頭 vs 多頭】★ 這是回填 2018 歷史後第一次能做的拆分')
    print('=' * 96)
    print('    2018（年報酬 -9.2%、回檔 -15.8%）與 2022（-22.6%、-31.6%）')
    bear = [s for ym, s, *_ in pri if ym[0] in (2018, 2022)]
    bull = [s for ym, s, *_ in pri if ym[0] not in (2018, 2022)]
    fm_stats(bear, '  空頭年（2018, 2022）')
    fm_stats(bull, '  其餘年份')

    print()
    print('=' * 96)
    print('【限制】引用任何上面的數字時必須一起講')
    print('=' * 96)
    print("""
  1. 🚨 **除權息無法調整**：`exdividend` 只有 2026 年、DB 存未調整收盤價。
     主檢定用產業內排名控制，並附上分月份診斷——但那是控制，不是消除。
  2. `avail_date` 是**保守估計**（營收月次月 11 日）。真實公布日在 1~10 日之間，
     所以如果效果只存在於公布後 1~2 天，這個設計抓不到。
     但那也抓不到實際操作（本系統是盤後資料、隔日才能動作）。
  3. 上櫃不在宇宙內（T86 不含上櫃）；**KY 股 30 檔沒有月營收**（MOPS 列在另一區段）。
  4. 只有上市普通股、日均成交 ≥0.5億。冷門股的成交價不現實。
  5. 測了 8 組 ⇒ 只有★主檢定可當結論，其餘是次要。""".rstrip())
    c.close()


if __name__ == '__main__':
    main()
