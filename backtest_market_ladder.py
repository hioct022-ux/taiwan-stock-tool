#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_market_ladder.py — 大盤評分階梯的**第二次**驗證（2026-10-15）

════════════════════════════════════════════════════════════════════════
要回答的具體問題
════════════════════════════════════════════════════════════════════════

UI 每天告訴使用者的那張階梯（`render_strategy()`）：

| 大盤評分 | 個股門檻 |
|---|---|
| ≥70 | 65 分 |
| 55–69 | 70 分 |
| 45–54 | 75 分 |
| <45 | **停止進場** |

它唯一的驗證是 2026-09-10（十五章「大盤評分門檻階梯的第一次驗證」），
而那次有**三個問題，全部是之後才發現的**：

| | 問題 | 何時發現 |
|---|---|---|
| ① | **S4 法人現貨幾乎是死的**——回測 ±3分觸發率 **0.0%**（讀 `t86_ranking`、
       門檻卻依 `chips` 校準）⇒ net 的分布天生偏窄 | 陷阱51（10/07） |
| ② | 跑在**自選股 74 檔**上，而 87/87 檔都是回測期之後才加入
       ⇒ **含後見之明**（自選股 +2.44% vs 全市場 -0.32%，差 2.76pp） | 10/09~24 |
| ③ | n=242、雜訊帶 2.76pp ⇒ 結論只能是「差距在雜訊範圍，維持現狀」 | 同上 |

**⇒ 本次把三者全部修掉：S4 已修並校準（陷阱51）、全市場 512 檔、
2018~2026 含三個空頭年（2018／2020／2022）、配對設計消掉抽樣運氣。**

════════════════════════════════════════════════════════════════════════
★ 事前預期（先寫下再跑，照策略F／D 的慣例）
════════════════════════════════════════════════════════════════════════

> 「**階梯與『固定 70 分』仍然分不出來，但 `<45 停止進場` 這一格
> 可能第一次測得出效果**——9/10 那次 `<45` 只有 87 天且全在多頭，
> 現在有三個空頭年，而那條規則的價值本來就該在空頭顯現。
>
> **反方向的可能（而且我認為機率更高）：** 10/08 已量到大盤淨值
> **在 2022 觸發率是九年最低、在 2026 大多頭最高**——它是
> **過熱偵測器而不是空頭偵測器**。若是這樣，`<45` 在空頭年根本不會啟動。」

════════════════════════════════════════════════════════════════════════
★ 最關鍵的對照組：E「完全不看大盤、一律 70 分」
════════════════════════════════════════════════════════════════════════

階梯的**平均門檻落在 70 附近**。所以若不設這一組，看到「階梯 alpha 較高」
會直接誤判為「大盤評分有效」——而實際上好處可能全部來自
「門檻整體拉高」，與「隨大盤調整」無關。

這是停損校準那節立的通則：**「按某變數動態調整既有參數」的提案，
必須加測「把該參數直接改成同等平均值的固定值」當對照。**
9/10 那次就是靠這一組才發現「階梯只多 0.26pp、卻少 26% 的進場機會」。

════════════════════════════════════════════════════════════════════════
⚠️ 2016~2017 必須裁掉（陷阱51 限制第 5 條）
════════════════════════════════════════════════════════════════════════

S2/S3/S4 只回填到 2018-01-01，那兩年只有 5 個訊號在跑、淨值天生偏小。
實測快取裡 2016/2017 的 `<45` 比例只有 5.0%／6.2%，而 2018+ 是 20.7%~41.5%
——**差 4~8 倍，混進去等於把兩套不同的系統當成一套。**

⚠️ 沙盒單次工具呼叫約 180 秒上限，而 ①②各約 2~3 分鐘
   ⇒ **分段跑**，不要用 `all`：

    python3 -u backtest_market_ladder.py pertrade   # ① per-trade ＋ 雜訊帶
    python3 -u backtest_market_ladder.py paired     # ② 5檔配對（20 條，最關鍵）
    python3 -u backtest_market_ladder.py year       # ③ 分期間（含空頭年）
    python3 -u backtest_market_ladder.py cand       # ④ 候選充足度
    python3 -u backtest_market_ladder.py bands      # ⑤ 哪一段帶 alpha
    python3 -u backtest_market_ladder.py all        # 全部（本機才跑得完）
"""
import os
import pickle
import random
import statistics as stt
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_portfolio_slots as P

# ⚠️ pickle 的安全性：這些快取是**本腳本家族自己寫到 /tmp 的中間產物**，
#    不是外部輸入 ⇒ 載入無風險。
#    日後若要接受他處提供的快取，必須改成 JSON 或有 schema 的反序列化。
#
# ★ 依序尋找候選快取——本測試**只需要** stocks／market_net／tpx_close／tpx_dates，
#   不需要月營收排名 ⇒ 兩種快取都能用。
CACHE_CANDIDATES = [
    '/tmp/_rev_filter_cache.pkl',        # backtest_revenue_filter.py cache（含月營收）
    '/tmp/_pf_slots_cache_market.pkl',   # backtest_portfolio_slots.py cache market
]
START   = '2018-01-02'                   # 陷阱51 限制第 5 條
N_SEEDS = 20                             # 20 條才有容錯空間（見下方檢定力）

# ★ seed base 可從 CLI 指定：`paired seedbase=8000`
#   理由（2026-10-16 立的規矩）：單一組 20 條在 p≈0.01~0.05 這一帶**實測不穩**
#   ——`sorted()` bug 那次同一對從 2/20 跳到 7/20，structure_bear 重跑有兩欄翻向。
#   ⇒ 要寫進 CLAUDE.md 當結論的配對檢定，必須換 seed base 重跑到結論穩定。
SEED_BASE = 7000
BOOT_N  = 600
BEAR    = {'2018', '2020', '2022'}       # ★ 三個空頭年


def ms_of(net):
    return P.ms_from_net(net)


# ════════════════ 六組規則 ════════════════
def build_rules(market_net):
    """
    ★ 全部走 `simulate(threshold_fn=...)`，**不另寫 simulate**
      ⇒ 10/07 那條「給對照組命名要逐條核對現行規則」的通則，
        最可靠的落實方式是不要有第二份實作。
    """
    def ladder(d):                       # ＝ UI 現行（與 make_ladder_fn 同邏輯）
        ms = ms_of(market_net.get(d, 0))
        if ms >= 70: return 65
        if ms >= 55: return 70
        if ms >= 45: return 75
        return None

    def ladder_noblock(d):               # 階梯但 <45 不封鎖（改用 75）
        ms = ms_of(market_net.get(d, 0))
        if ms >= 70: return 65
        if ms >= 55: return 70
        return 75

    def strategyC(d):                    # 回測長期在驗的那套：net>0 不進場 + 一律65
        return None if market_net.get(d, 0) > 0 else 65

    return [
        ('A 不看大盤・一律 65（基準）',       lambda d: 65),
        ('B 策略C（net>0不進場・一律65）',    strategyC),
        ('C ★現行 UI 階梯',                  ladder),
        ('D 階梯但 <45 不封鎖',              ladder_noblock),
        ('★E 不看大盤・一律 70（關鍵對照）',  lambda d: 70),
        ('F 不看大盤・一律 75',              lambda d: 75),
    ]


BUILD_HINT = '''
  請先建快取（約 20~40 分鐘，一次性）：

      python3 -u backtest_portfolio_slots.py cache market days=2600

  ⚠️ **`days=2600` 不可省略。** `build_cache()` 的預設是 600 天（＝2024-05 起），
     而本測試要 2018~2026 的 2,130 個交易日。少了這個參數，快取會**只有
     600 天、一個空頭年都沒有，而且不報錯**——那正是陷阱51 那條通則
     （「回填歷史之後，grep 全部 days=／[-N:]／LIMIT N」）第四次出現的地方。
'''


def load():
    """
    ★ 阻斷式涵蓋檢查（照陷阱51 對帳、`exdiv.require_coverage()` 的同一個立場）：
      快取若沒涵蓋三個空頭年就 **sys.exit**，不讓它靜默跑出一份
      「看起來正常、但其實只有多頭」的結果。
    """
    path = next((p for p in CACHE_CANDIDATES if os.path.exists(p)), None)
    if path is None:
        print('❌ 找不到任何可用的快取。試過：')
        for p in CACHE_CANDIDATES:
            print(f'     {p}')
        print(BUILD_HINT)
        sys.exit(1)
    print(f'快取：{path}')
    with open(path, 'rb') as f:
        cache = pickle.load(f)

    for k in ('stocks', 'market_net', 'tpx_close', 'tpx_dates'):
        if k not in cache:
            print(f'❌ 快取缺少 `{k}`，不是本測試能用的格式。{BUILD_HINT}')
            sys.exit(1)

    raw = cache['tpx_dates']
    n0 = len(raw)
    cache['tpx_dates'] = [d for d in raw if d >= START]
    ds = cache['tpx_dates']
    if not ds:
        print(f'❌ 快取裡沒有 {START} 之後的資料（範圍 {raw[0]} ~ {raw[-1]}）。{BUILD_HINT}')
        sys.exit(1)

    print(f'宇宙 {len(cache["stocks"])} 檔　{ds[0]} ~ {ds[-1]}（{len(ds)} 個交易日）')
    print(f'（已裁掉 {START} 之前的 {n0 - len(ds)} 天'
          f'——陷阱51 限制第5條：S2/S3/S4 只回填到 2018-01-01）')

    # ★ 阻斷式：三個空頭年必須都在，否則整個測試的前提不成立
    years = {d[:4] for d in ds}
    missing = sorted(BEAR - years)
    if missing:
        print(f'''
🚨 **快取沒有涵蓋這些空頭年：{missing}** ⇒ 本測試的前提不成立，中止。
   本次要回答的問題正是「`<45 停止進場` 在空頭年有沒有用」，
   而快取只有 {min(years)}~{max(years)}。
   **這正是陷阱51 的形狀：資料補好了，但程式只看最近 N 天，而且不報錯。**
{BUILD_HINT}''')
        sys.exit(1)
    print(f'✅ 三個空頭年都在（{sorted(BEAR)}）⇒ 前提成立')
    return cache


def noise_band(trades, tpx, n, reps=BOOT_N, seed=0):
    """從基準組重抽 n 筆 → alpha 的 (5%, 50%, 95%) 分位與帶寬。"""
    if not trades or n <= 0:
        return None
    rnd = random.Random(seed)
    out = []
    for _ in range(reps):
        s = P.stat([trades[rnd.randrange(len(trades))] for _ in range(n)], tpx)
        if s:
            out.append(s['alpha'])
    if len(out) < 50:
        return None
    out.sort()
    lo = out[int(len(out) * 0.05)]
    hi = out[int(len(out) * 0.95)]
    return lo, out[len(out) // 2], hi, hi - lo


def sign_test(diffs):
    """排除平手的符號檢定（10/07「錯誤二」的教訓：平手不能算成輸）。"""
    nz = [x for x in diffs if abs(x) > 1e-12]
    ties = len(diffs) - len(nz)
    if not nz:
        return 0, 0, ties, 1.0
    w = sum(1 for x in nz if x > 0)
    n = len(nz)
    from math import comb
    tail = sum(comb(n, k) for k in range(min(w, n - w) + 1)) / 2 ** n
    return w, n, ties, min(1.0, 2 * tail)


# ════════════════ ① per-trade（不限檔數 ⇒ 排序無關、確定性）════════════════
def run_pertrade(cache):
    tpx = cache['tpx_close']
    rules = build_rules(cache['market_net'])

    print('\n' + '=' * 96)
    print('【① per-trade：不限檔數（排序不影響結果 ⇒ 確定性、n 最大）')
    print('=' * 96)
    print(f'  {"規則":<30}{"筆數":>7}{"報酬":>9}{"同期大盤":>10}'
          f'{"alpha":>9}{"扣成本":>9}{"勝率":>8}{"停損率":>8}')
    print('  ' + '-' * 92)

    res, trs, base = {}, {}, None
    for label, thr in rules:
        _, tr = P.simulate(cache, lambda c, d, s: (c,), None, label,
                           threshold_fn=thr)
        s = P.stat(tr, tpx)
        if not s:
            print(f'  {label:<30}{"— 無交易":>7}')
            continue
        res[label], trs[label] = s, tr
        if label.startswith('A '):
            base = tr
        print(f'  {label:<30}{s["n"]:>7}{s["ret"]:>+8.2f}%{s["mkt"]:>+9.2f}%'
              f'{s["alpha"]:>+8.2f}%{s["alpha"] - 0.47:>+8.2f}%'
              f'{s["win"]:>7.1f}%{s["stop"]:>7.1f}%')

    # ★ 雜訊帶（9/17 立的標準前置動作）
    if base:
        print('\n  ★ 雜訊帶（從 A 基準組重抽，看純運氣能造成多大落差）：')
        worst = 0
        for n in sorted({s['n'] for s in res.values()}):
            capped = n > len(base)
            nb = noise_band(base, tpx, min(n, len(base)))
            if nb:
                lo, _mid, hi, w = nb
                worst = max(worst, w)
                print(f'     n={n:<7} alpha 5~95% {lo:+.2f}% ~ {hi:+.2f}%'
                      f'　帶寬 {w:.2f}pp'
                      + (f'　（已上限至 {len(base)} 筆）' if capped else ''))
        al = [s['alpha'] for s in res.values()]
        spread = max(al) - min(al)
        print(f'\n  各組 alpha 全距 {spread:.2f}pp　vs 最寬雜訊帶 {worst:.2f}pp')
        print('  ⇒ ' + ('⚪ **全距小於雜訊帶，整張表不可解讀**'
                        if spread < worst else '★ 全距超出雜訊帶，可以往下看'))

    # ★★ 決定性的一比：階梯 vs 一律70（階梯的平均門檻就在 70 附近）
    _c, _e = 'C ★現行 UI 階梯', '★E 不看大盤・一律 70（關鍵對照）'
    if _c in res and _e in res:
        c, e = res[_c], res[_e]
        print(f'''
  ★★ 決定性的一比（階梯的平均門檻落在 70 附近）：
     階梯      alpha {c["alpha"]:+.2f}%　n={c["n"]}
     一律 70   alpha {e["alpha"]:+.2f}%　n={e["n"]}
     ⇒ 「隨大盤調整」這一維的邊際貢獻 = {c["alpha"] - e["alpha"]:+.2f}pp，
        而代價是進場機會 {(c["n"]/e["n"] - 1)*100:+.0f}%''')
    return res, trs


# ════════════════ ② 5 檔配置・配對比較 ════════════════
def run_paired(cache):
    tpx = cache['tpx_close']
    rules = build_rules(cache['market_net'])

    print('\n' + '=' * 96)
    print(f'【② 5 檔配置・配對比較（{N_SEEDS} 條，seed {SEED_BASE}~{SEED_BASE+N_SEEDS-1}，同一 seed 用同一組隨機排序）')
    print('=' * 96)
    print(f'''  檢定力（事前就該算——10/07 的教訓：條數不足時問題不是
  「帶寬太寬」而是「檢定力為零」）：
     {N_SEEDS}/{N_SEEDS} → p<0.001　17/{N_SEEDS} → p=0.003　15/{N_SEEDS} → p=0.041
     12/{N_SEEDS} → p=0.503（等於什麼都沒說）

  ⚠️ 排序鍵用**真隨機**（每檔一個固定隨機偏好）——不是股票代號。
     10/05 的教訓：代號排序會持續把槽位給小代號股票，而台股 1xxx 是
     水泥食品塑膠紡織、28xx 金融 ⇒ 它會偷偷變成「偏重傳產」的策略。
''')

    runs = {}
    for label, thr in rules:
        per = []
        for sd in range(N_SEEDS):
            rnd = random.Random(SEED_BASE + sd)
            # 🚨 **必須 sorted()。** `cache['stocks']` 是 dict，順序＝插入順序，
            #    而不同腳本建的快取插入順序不同（`backtest_revenue_filter` 分塊後
            #    `stocks.update()` 合併、`backtest_portfolio_slots` 循序建）。
            #    少了 sorted()，**同一個 seed 在兩份「同宇宙同期間」的快取上
            #    會把隨機偏好配給不同股票** ⇒ 跑出兩組各自合法但彼此獨立的 20 條，
            #    而且看起來像同一個測試。2026-10-16 實際發生過：
            #    「一律70 vs 一律65」一份跑 2/20（p=0.000）、另一份 7/20（p=0.263）。
            pref = {c: rnd.random() for c in sorted(cache['stocks'])}
            _, tr = P.simulate(cache, lambda c, d, s, _p=pref: (_p[c],),
                               5, label, threshold_fn=thr)
            s = P.stat(tr, tpx)
            per.append(s['alpha'] if s else 0.0)
        runs[label] = per
        print(f'  {label:<30}中位 alpha {stt.median(per):+.2f}%'
              f'　範圍 {min(per):+.2f}% ~ {max(per):+.2f}%')

    # 退化配對偵測（10/14 煙霧測試真的觸發過）
    degen = [lb for lb, v in runs.items() if len(set(round(x, 9) for x in v)) == 1]
    if degen:
        print(f'\n  🚨 **配對檢定無效**：{degen} 的 {N_SEEDS} 個 seed 給出完全相同的'
              f' alpha\n     ⇒ 5 檔上限從未綁定、隨機排序不起作用，'
              f'符號檢定讀到的是「同一個數字抄 {N_SEEDS} 次」。**p 不可讀。**')

    PAIRS = [
        ('★★ 階梯 vs 一律70',     'C ★現行 UI 階梯', '★E 不看大盤・一律 70（關鍵對照）'),
        ('   階梯 vs 一律65',      'C ★現行 UI 階梯', 'A 不看大盤・一律 65（基準）'),
        ('   階梯 vs 策略C',       'C ★現行 UI 階梯', 'B 策略C（net>0不進場・一律65）'),
        ('★  <45封鎖的貢獻',       'C ★現行 UI 階梯', 'D 階梯但 <45 不封鎖'),
        ('   一律70 vs 一律65',    '★E 不看大盤・一律 70（關鍵對照）',
                                   'A 不看大盤・一律 65（基準）'),
        ('   一律75 vs 一律70',    'F 不看大盤・一律 75',
                                   '★E 不看大盤・一律 70（關鍵對照）'),
    ]
    print(f'\n  {"配對":<22}{"Δ中位":>10}{"勝場":>9}{"平手":>7}{"p":>9}  判定')
    print('  ' + '-' * 70)
    for nm, a, b in PAIRS:
        if a not in runs or b not in runs:
            continue
        diffs = [runs[a][i] - runs[b][i] for i in range(N_SEEDS)]
        w, n, ties, p = sign_test(diffs)
        mark = '✅' if (p < 0.05 and w > n - w) else ('❌' if p < 0.05 else '⚪')
        print(f'  {nm:<22}{stt.median(diffs):>+9.2f}pp{w:>6}/{n:<3}{ties:>6}'
              f'{p:>9.3f}  {mark}')
    return runs


# ════════════════ ③ 分期間：空頭年是不是真的有差 ════════════════
def run_by_year(trs, cache):
    tpx = cache['tpx_close']
    _c, _e, _d = ('C ★現行 UI 階梯', '★E 不看大盤・一律 70（關鍵對照）',
                  'D 階梯但 <45 不封鎖')
    if not all(k in trs for k in (_c, _e, _d)):
        return
    print('\n' + '=' * 96)
    print('【③ 分期間：★＝空頭年。`<45 停止進場` 的價值本來就該在這裡顯現')
    print('=' * 96)
    print(f'  {"年":<8}{"階梯 n":>8}{"階梯 alpha":>12}{"一律70 alpha":>14}'
          f'{"階梯−70":>10}{"階梯−不封鎖":>13}')
    print('  ' + '-' * 67)
    for y in sorted({t['entry_date'][:4] for t in trs[_c]}):
        row = {}
        for k in (_c, _e, _d):
            sub = [t for t in trs[k] if t['entry_date'][:4] == y]
            row[k] = P.stat(sub, tpx)
        if not all(row.values()):
            continue
        star = ' ★' if y in BEAR else '  '
        print(f'  {y}{star:<6}{row[_c]["n"]:>8}{row[_c]["alpha"]:>+11.2f}%'
              f'{row[_e]["alpha"]:>+13.2f}%'
              f'{row[_c]["alpha"] - row[_e]["alpha"]:>+9.2f}pp'
              f'{row[_c]["alpha"] - row[_d]["alpha"]:>+12.2f}pp')

    bear = [t for t in trs[_c] if t['entry_date'][:4] in BEAR]
    bull = [t for t in trs[_c] if t['entry_date'][:4] not in BEAR]
    for nm, grp in (('★ 三個空頭年合計', bear), ('  其他六年合計', bull)):
        sc = P.stat(grp, tpx)
        se = P.stat([t for t in trs[_e] if (t['entry_date'][:4] in BEAR)
                     == (grp is bear)], tpx)
        sd = P.stat([t for t in trs[_d] if (t['entry_date'][:4] in BEAR)
                     == (grp is bear)], tpx)
        if sc and se and sd:
            print(f'  {nm:<14}{sc["n"]:>8}{sc["alpha"]:>+11.2f}%'
                  f'{se["alpha"]:>+13.2f}%{sc["alpha"] - se["alpha"]:>+9.2f}pp'
                  f'{sc["alpha"] - sd["alpha"]:>+12.2f}pp')

    print('''
  ⇒ 怎麼讀：
     • **空頭年「階梯−不封鎖」明顯 >0** ⇒ `<45 停止進場` 真的在空頭救到人
     • **空頭年也 ≈0** ⇒ 印證 10/08 的發現：大盤淨值是**過熱偵測器**
       不是空頭偵測器（2022 觸發率九年最低 20.7%、2026 大多頭最高 41.5%）''')


# ════════════════ ④ 候選充足度（10/14 立的便宜診斷）════════════════
def run_candidates(cache):
    """
    **為什麼要測這個：** 10/14 測月營收篩選時發現「篩選器的強度有最適點，
    而那個點只有在組合層級測得出來」——per-trade 看不到
    「候選不足導致 5 個槽位填不滿、部位閒置」這件事。
    判斷方法極便宜：印出「單日候選 ≥ 槽位數」的天數比例。

    ⚠️ 2026-10-15 實測結果**推翻了**「門檻拉高到 70 之所以變差是因為候選不足」
    這個假設——一律70 有 98.7% 的日子候選 ≥5 檔。**假設被否決，記錄下來。**
    """
    S, mn, ds = cache['stocks'], cache['market_net'], cache['tpx_dates']
    rules = build_rules(mn)
    print('\n' + '=' * 96)
    print('【④ 候選充足度：單日候選 ≥ 槽位數(5) 的天數比例】')
    print('=' * 96)
    print(f'  {"規則":<30}{"有訊號天數":>11}{"候選中位":>10}{"候選平均":>10}{"單日≥5檔":>14}')
    print('  ' + '-' * 76)
    for lb, thr in rules:
        days, cands = 0, []
        for d in ds:
            t = thr(d)
            if t is None:
                continue
            n = 0
            for st_ in S.values():
                i = st_['idx'].get(d)
                if i is None or i + 1 >= len(st_['prices']):
                    continue
                sc = st_['score'].get(d)
                if sc is not None and sc >= t:
                    n += 1
            if n > 0:
                days += 1
                cands.append(n)
        if cands:
            ge5 = sum(1 for x in cands if x >= 5)
            cands.sort()
            print(f'  {lb:<30}{days:>11}{cands[len(cands)//2]:>10}'
                  f'{sum(cands)/len(cands):>10.1f}{ge5:>8} ({ge5/days*100:4.1f}%)')


# ════════════════ ⑤ 門檻之上，哪一段帶著 alpha ════════════════
def run_bands(cache):
    """
    若「門檻由 65 拉到 70」真的有害，最自然的機制是
    **65–69 這一段本身帶著 alpha，拉到 70 就把它排除掉**。
    ⚠️ 2026-10-15 實測：方向一致（65–69 最高、≥80 最低）但**全距在雜訊帶內**
      ⇒ 機制**沒有被獨立證實**。順手重現了 9/24 的型態：
      `同期大盤` 隨評分單調上升（＝吃到更多 beta），而 alpha 不動。
    """
    tpx = cache['tpx_close']
    noblock = lambda d: 0        # thr 永不為 None ⇒ 完全不看大盤
    bands = [('65–69', lambda s: 65 <= s < 70), ('70–74', lambda s: 70 <= s < 75),
             ('75–79', lambda s: 75 <= s < 80), ('≥80', lambda s: s >= 80)]
    print('\n' + '=' * 96)
    print('【⑤ 門檻之上，哪一段真的帶著 alpha？】（完全不看大盤、不限檔數 ⇒ 確定性）')
    print('=' * 96)
    print(f'  {"評分區間":<10}{"筆數":>8}{"報酬":>9}{"同期大盤":>10}{"alpha":>9}{"勝率":>8}')
    print('  ' + '-' * 54)
    base = None
    for nm, f in bands:
        _, tr = P.simulate(cache, lambda a, b, s: (a,), None, nm,
                           score_filter=f, threshold_fn=noblock)
        s = P.stat(tr, tpx)
        if not s:
            continue
        if nm == '65–69':
            base = tr
        print(f'  {nm:<10}{s["n"]:>8}{s["ret"]:>+8.2f}%{s["mkt"]:>+9.2f}%'
              f'{s["alpha"]:>+8.2f}%{s["win"]:>7.1f}%')
    if base:
        nb = noise_band(base, tpx, min(6000, len(base)))
        if nb:
            print(f'\n  雜訊帶（n≈{min(6000, len(base))}）：'
                  f'{nb[0]:+.2f}% ~ {nb[2]:+.2f}%　帶寬 {nb[3]:.2f}pp')


def main():
    global SEED_BASE, N_SEEDS   # ⚠️ 少了這行，CLI 參數會變成區域變數、靜默無效
    for _a in sys.argv[1:]:
        if _a.startswith('seedbase='):
            SEED_BASE = int(_a.split('=', 1)[1])
            print(f'★ seed base = {SEED_BASE}（預設 7000）')
        if _a.startswith('seeds='):
            N_SEEDS = int(_a.split('=', 1)[1])
            print(f'★ 條數 = {N_SEEDS}（預設 20）⇒ 符號檢定的檢定力隨條數上升')
    _pos = [a for a in sys.argv[1:] if '=' not in a]   # seedbase= 不算位置參數
    arg = _pos[0] if _pos else 'all'
    print('=' * 96)
    print('大盤評分階梯：第二次驗證（S4 已修 + 全市場 + 含空頭年 + 配對設計）')
    print('=' * 96)
    cache = load()

    # 順手印出階梯各段的實際天數——9/10 那次 `≥70` 只有 15 天（2.9%），
    # 當時判定「實質上不存在」。S4 修好後要重新確認這件事還成不成立。
    mn = cache['market_net']
    ds = [d for d in cache['tpx_dates']]
    import collections
    cnt = collections.Counter()
    for d in ds:
        ms = ms_of(mn.get(d, 0))
        cnt['>=70' if ms >= 70 else ('55-69' if ms >= 55 else
                                     ('45-54' if ms >= 45 else '<45'))] += 1
    print(f'\n大盤評分分段（{len(ds)} 個決策日）——'
          f'⚠️ 9/10 那次 `≥70` 只有 15 天（2.9%）、被判「實質上不存在」：')
    for k in ('>=70', '55-69', '45-54', '<45'):
        print(f'   {k:>7}  {cnt[k]:>5} 天 ({cnt[k]/len(ds)*100:5.1f}%)')

    res, trs = (None, None)
    if arg in ('all', 'pertrade', 'year'):
        res, trs = run_pertrade(cache)
    if arg in ('all', 'paired'):
        run_paired(cache)
    if arg in ('all', 'year') and trs:
        run_by_year(trs, cache)
    if arg in ('all', 'cand'):
        run_candidates(cache)
    if arg in ('all', 'bands'):
        run_bands(cache)

    print('\n' + '=' * 96)
    print('''限制（引用任何上述數字時必須一起講）
  1. **除權息無法調整**（陷阱50）⇒ 所有報酬系統性低估，持有期長的被低估最多。
     `exdiv.py` 只能用在「兩組相減」，絕對 alpha 仍是未調整版。
  2. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）⇒ 「65 分」在樣本
     前後段不是同一個篩選器。這讓所有「門檻」類比較天生帶一層雜訊。
  3. **未調整收盤價**（陷阱49）⇒ 分割日會有假停損。
  4. 只有上市股；上櫃無籌碼資料，不在宇宙內。
  5. **配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」**
     ⇒ p<0.05 的意思是「在這段歷史上方向穩定」，不是「換一段歷史也成立」。
  6. 2016~2017 已裁掉（陷阱51 限制第5條）。''')
    print('=' * 96)


if __name__ == '__main__':
    main()
