"""
停損距離在空頭樣本上的重驗（2026-10-16）
═══════════════════════════════════════════════════════════════════════════

★ 要驗證的問題（照「先講目的再動手」那條通則）
   `停損 10%` 是本專案**唯一一條因回測而變更的正式規則**
   （2026-08-27，由 8% 改成 10%）。但那次校準有兩個現在已知的問題：

   ① 跑在**自選股**上 ⇒ 含倖存者偏誤。2026-09-24 量到同一套規則
      自選股 alpha +2.44% vs 全市場 -0.32%，**差 2.76pp**。
   ② 樣本**全在多頭**（2024-07~2026-08 指數 +102%）。那一節自己就寫著
      「真的崩盤時 10% 會比 8% 每檔多賠 2 個百分點」——**從未驗證**。

   現在三件工具都有了：全市場 512 檔、2018~2026 含三個空頭年、配對設計。

★ 事前預期（先寫下再跑，照策略F／D 的慣例）
   主預期：**alpha 的峰值會從 10% 往外移，或整條曲線變平測不出來。**
   理由：10/07 的結構測試已經量到「(c) 只有停損那組在多數年份貢獻極小」、
   「(f) 無停損 vs (e) 有停損全期分不出來（10/20、p=1.000）」。
   ⇒ 我認為「測不出來」的機率更高。

   反方向的可能：空頭年會把「寬停損」罰得比多頭重。若 2018／2022
   單獨看出現「越寬越差」，那就是 8/27 那次因為沒有空頭樣本
   而**系統性高估了寬停損**。

★ 設計：只動一個維度
   其餘（大盤階梯、65 分門檻、續抱、10 日週期、5 檔、真隨機排序、
   同一 seed 配對）**完全不動**，用 `simulate(stop_ratio=...)`
   這個 2026-10-16 新增的參數——預設 None 時與改版前**位元級相同**，
   所以不需要對帳（「不要有第二份實作」那條通則）。

⚠️ 限制（引用任何數字時必須一起講）
   1. **除權息無法調整**（陷阱50）⇒ 絕對 alpha 系統性低估。
      而**停損距離越寬、持有越久 ⇒ 被低估得越多** ← 這個偏誤的方向
      對「寬停損」不利，與 8/27 那次「多頭 beta 讓寬停損看起來更好」相反。
   2. **未調整收盤價**（陷阱49）⇒ 分割日會有假停損。全市場宇宙 3 檔／8 事件。
      ⚠️ 這一題測的正是停損 ⇒ 假停損會直接汙染「停損率」那一欄。
   3. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）。
   4. 只有上市股；上櫃無籌碼資料，不在宇宙內。
   5. **配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」。**
   6. 2016~2017 已裁掉（陷阱51 限制第 5 條）。

用法
   python3 -u backtest_stop_distance.py              # per-trade + 配對（100 條）
   python3 -u backtest_stop_distance.py pertrade     # 只跑 per-trade（快）
   python3 -u backtest_stop_distance.py paired seeds=100 seedbase=8000
"""
import sys, random, statistics as stt

import backtest_portfolio_slots as P
from backtest_market_ladder import load, sign_test   # ★ 不另寫一份

# ── 受測的停損距離 ───────────────────────────────────────────────
#   與 8/27 那次（`backtest_vol_stop.py`）**刻意用同一組值**，
#   這樣兩次的曲線形狀可以直接對照。
STOPS = [
    ('8%（8/27 之前的舊值）', 0.92),
    ('★10%（現行正式規則）',  0.90),
    ('12%',                   0.88),
    ('15%',                   0.85),
    ('25%',                   0.75),
    ('幾乎不停損',             0.00),   # stop=0 ⇒ low <= 0 永遠不成立
]

def _corporate_actions(cache):
    """
    🚨 2026-10-16 新增。相鄰收盤比值落在 [0.65, 1.5] 之外 ⇒ 判定為公司行為
    （分割／減資／大額配股）。**刻意不排除「跨多日缺口」**——那正是
    陷阱49 原始掃描漏掉 81%（21/26 檔次）的原因：**分割換發必然伴隨停止交易**，
    那個缺口不是雜訊，是公司行為的指紋。

    用途：`最大單筆` 那一欄必須排除跨過這些日期的交易。
    實測不排除會把 `幾乎不停損` 的最大單筆記成 **-90.5%**（1:10 分割的假崩盤），
    真值是 **-49.0%**（2020 COVID 連續跌停）。
    ⚠️ 有停損的組不受影響——停損本來就把單筆封頂。
    """
    ca = {}
    for code, st_ in cache['stocks'].items():
        pr = st_['prices']
        for i in range(1, len(pr)):
            c0, c1 = pr[i - 1].get('close'), pr[i].get('close')
            if c0 and c1 and not (0.65 <= c1 / c0 <= 1.5):
                ca.setdefault(code, set()).add(pr[i]['date'])
    return ca


def _spans_ca(t, ca):
    d = ca.get(t['code'])
    return bool(d) and any(t['entry_date'] < x <= t['exit_date'] for x in d)


SEED_BASE = 7000
N_SEEDS   = 100          # 10/16 的教訓：20 條在這個效果量級上沒有解析度
BEAR_YEARS = ('2018', '2020', '2022')


# ══════════════ ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）══════════════
def run_pertrade(cache):
    tpx = cache['tpx_close']
    print('=' * 96)
    print('【① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）')
    print('=' * 96)
    print('''
  ⚠️ **必須看 alpha，不能看原始報酬**（8/27 那次最重要的教訓）：
     原始報酬會一路升到 25%，但那多出來的是大多頭的 beta
     （停損越寬、持有越久、吃到越多市場漲幅），不是策略貢獻。
''')
    ca = _corporate_actions(cache)
    print(f'  ★ 公司行為事件：{sum(len(v) for v in ca.values())} 檔次 / {len(ca)} 檔'
          f'（`最大單筆` 已排除跨過這些日期的交易——見 _corporate_actions 的 docstring）')
    print(f'  {"停損":<22}{"筆數":>8}{"報酬":>9}{"同期大盤":>10}'
          f'{"alpha":>9}{"扣成本":>9}{"停損率":>8}{"勝率":>8}{"最大單筆":>10}')
    print('  ' + '-' * 94)

    out = {}
    for label, sr in STOPS:
        _, tr = P.simulate(cache, lambda c, d, s: (c,), None, label, stop_ratio=sr)
        st_ = P.stat(tr, tpx)
        if not st_:
            print(f'  {label:<22}（無交易）')
            continue
        # ⚠️ 排除①公司行為 ②「回測結束」（那段不經過停損檢查，見 CLAUDE.md）
        _cl = [t for t in tr if not _spans_ca(t, ca) and t['exit_reason'] != '回測結束']
        worst = min((t['pnl'] for t in _cl), default=min(t['pnl'] for t in tr))
        out[label] = {'trades': tr, 'st': st_, 'worst': worst}
        print(f'  {label:<22}{st_["n"]:>8,}{st_["ret"]:>+8.2f}%{st_["mkt"]:>+9.2f}%'
              f'{st_["alpha"]:>+8.2f}%{st_["alpha"]-0.47:>+8.2f}%'
              f'{st_["stop"]:>7.1f}%{st_["win"]:>7.1f}%{worst:>+9.1f}%')

    # ── 雜訊帶（9/17 立的標準前置動作）──
    base = out.get('★10%（現行正式規則）')
    if base:
        import copy
        rnd = random.Random(12345)
        pnl = [(t['pnl'], t) for t in base['trades']]
        ns  = min(len(x['trades']) for x in out.values())
        samp = []
        for _ in range(600):
            sub = [pnl[rnd.randrange(len(pnl))][1] for _ in range(ns)]
            s = P.stat(sub, tpx)
            samp.append(s['alpha'])
        samp.sort()
        lo, hi = samp[int(.05 * len(samp))], samp[int(.95 * len(samp))]
        alphas = [v['st']['alpha'] for v in out.values()]
        rng = max(alphas) - min(alphas)
        print(f'''
  雜訊帶（從現行 10% 那組重抽 n={ns:,}，600 次）：{lo:+.2f}% ~ {hi:+.2f}%（帶寬 {hi-lo:.2f}pp）
  六組 alpha 全距：{rng:.2f}pp
  ⇒ {"★ 全距超出雜訊帶 ⇒ 可以解讀" if rng > hi - lo else "⚪ 全距在雜訊帶內 ⇒ **不可解讀**"}''')

    # ── 逐年 alpha：這是本次的重點 ──
    print('\n' + '=' * 96)
    print('【★ 逐年 alpha（依進場年）——8/27 那次完全沒有的東西')
    print('=' * 96)
    years = sorted({t['entry_date'][:4] for v in out.values() for t in v['trades']})
    hdr = ''.join(f'{lb.replace("（8/27 之前的舊值）","").replace("（現行正式規則）","").replace("★",""):>12}'
                  for lb, _ in STOPS)
    print(f'  {"年":<8}{hdr}')
    print('  ' + '-' * (8 + 12 * len(STOPS)))
    for y in years:
        star = ' ★空頭' if y in BEAR_YEARS else ''
        row = f'  {y + star:<8}'
        for lb, _ in STOPS:
            if lb not in out:
                row += f'{"—":>12}'; continue
            sub = [t for t in out[lb]['trades'] if t['entry_date'][:4] == y]
            s = P.stat(sub, tpx) if sub else None
            row += f'{s["alpha"]:>+11.2f}%' if s else f'{"—":>12}'
        print(row)

    for tag, pick in (('★ 三個空頭年合計', lambda y: y in BEAR_YEARS),
                      ('   其他六年合計',   lambda y: y not in BEAR_YEARS)):
        row = f'  {tag:<8}'
        for lb, _ in STOPS:
            if lb not in out:
                row += f'{"—":>12}'; continue
            sub = [t for t in out[lb]['trades'] if pick(t['entry_date'][:4])]
            s = P.stat(sub, tpx) if sub else None
            row += f'{s["alpha"]:>+11.2f}%' if s else f'{"—":>12}'
        print(row)
    return out


# ══════════════ ② 5 檔配置・配對比較 ══════════════
def run_paired(cache):
    tpx = cache['tpx_close']
    print('\n' + '=' * 96)
    print(f'【② 5 檔配置・配對比較（{N_SEEDS} 條，seed {SEED_BASE}~{SEED_BASE+N_SEEDS-1}）')
    print('=' * 96)
    print('''
  ⚠️ 排序鍵用**真隨機**（每檔一個固定隨機偏好），而且對 `sorted()` 指派
     ——2026-10-16 的 bug：少了 sorted() 會讓同一個 seed 在不同快取上
     把隨機偏好配給不同股票，配對設計的「同一組運氣」前提就破了。
''')
    runs = {}
    for label, sr in STOPS:
        per = []
        for sd in range(N_SEEDS):
            rnd  = random.Random(SEED_BASE + sd)
            pref = {c: rnd.random() for c in sorted(cache['stocks'])}
            _, tr = P.simulate(cache, lambda c, d, s, _p=pref: (_p[c],),
                               5, label, stop_ratio=sr)
            s = P.stat(tr, tpx)
            per.append(s['alpha'] if s else 0.0)
        runs[label] = per
        print(f'  {label:<22}中位 alpha {stt.median(per):+.2f}%'
              f'　範圍 {min(per):+.2f}% ~ {max(per):+.2f}%')

    degen = [lb for lb, v in runs.items() if len(set(round(x, 9) for x in v)) == 1]
    if degen:
        print(f'\n  🚨 **配對檢定無效**：{degen} 的 {N_SEEDS} 個 seed 給出完全相同的 alpha'
              f'\n     ⇒ 5 檔上限從未綁定、隨機排序不起作用。**p 不可讀。**')

    cur = '★10%（現行正式規則）'
    PAIRS = [('★★ 10% vs 8%（8/27 那次改的方向）', cur, '8%（8/27 之前的舊值）')] + \
            [(f'   10% vs {lb}', cur, lb) for lb, _ in STOPS
             if lb not in (cur, '8%（8/27 之前的舊值）')]

    print(f'\n  {"配對":<34}{"Δ中位":>10}{"勝場":>9}{"平手":>7}{"p":>9}  判定')
    print('  ' + '-' * 82)
    for nm, a, b in PAIRS:
        if a not in runs or b not in runs:
            continue
        diffs = [runs[a][i] - runs[b][i] for i in range(N_SEEDS)]
        w, n, ties, p = sign_test(diffs)
        mark = '✅' if (p < 0.05 and w > n - w) else ('❌' if p < 0.05 else '⚪')
        print(f'  {nm:<34}{stt.median(diffs):>+9.2f}pp{w:>6}/{n:<3}{ties:>6}'
              f'{p:>9.3f}  {mark}')
    print('''
  判讀：✅ = 現行 10% 顯著較好　❌ = 現行 10% 顯著較差　⚪ = 測不出來
''')
    return runs


def main():
    global SEED_BASE, N_SEEDS
    for a in sys.argv[1:]:
        if a.startswith('seedbase='):
            SEED_BASE = int(a.split('=', 1)[1]); print(f'★ seed base = {SEED_BASE}')
        if a.startswith('seeds='):
            N_SEEDS = int(a.split('=', 1)[1]);   print(f'★ 條數 = {N_SEEDS}')
    pos = [a for a in sys.argv[1:] if '=' not in a]
    arg = pos[0] if pos else 'all'

    print('=' * 96)
    print('停損距離重驗：全市場 + 三個空頭年 + 配對設計（2026-10-16）')
    print('=' * 96)
    cache = load()          # ★ 阻斷式：三個空頭年沒全在就 sys.exit

    if arg in ('all', 'pertrade'):
        run_pertrade(cache)
    if arg in ('all', 'paired'):
        run_paired(cache)

    print('=' * 96)
    print('''限制（引用任何上述數字時必須一起講）
  1. **除權息無法調整**（陷阱50）⇒ 絕對 alpha 系統性低估，
     而**停損越寬、持有越久 ⇒ 被低估越多** ← 偏誤方向對寬停損不利。
  2. **未調整收盤價**（陷阱49）⇒ 分割日會有假停損，直接汙染「停損率」那一欄。
     `最大單筆` 已排除公司行為與「回測結束」；**停損率那一欄沒有排除**。
  3. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）。
  4. 只有上市股；上櫃無籌碼資料，不在宇宙內。
  5. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。
  6. 2016~2017 已裁掉（陷阱51 限制第 5 條）。''')
    print('=' * 96)


if __name__ == '__main__':
    main()
