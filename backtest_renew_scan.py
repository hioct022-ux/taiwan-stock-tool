"""
★ 目的（2026-10-23）—— 直接測「放寬續抱條件」
═══════════════════════════════════════════════════════════════════
兩條獨立的路都指向同一件事：**「抱更久」本身就是效果來源。**

| 何時 | 證據 |
|---|---|
| 2026-10-07 | 續抱 (e vs d)：換手 1,102 → 57 次、純成本拖累 -64.6% → -5.3%、**Δ報酬 +169pp、20/20** |
| 2026-10-18 | **R50a：一個完全沒有資訊的隨機數**，只要同樣拉長持有期 ⇒ vs A1 **+493pp、20/20** |

而 10/18 那節的「下一步」第 1 項就是本測試：

> **直接放寬續抱條件。如果主要效果來自「抱更久」，那不需要月營收也拿得到，
> 而且不必動 `scorer.py`。**

⇒ 這是整個專案裡**最便宜的候選改動**：`RENEW_THRESHOLD` 一個數字，
不碰評分邏輯、不碰進場規則、不需要新資料來源。

★★ 本測試的三個必要設計（缺任何一個結論就不能讀）
───────────────────────────────────────────────────────────────────
① **主量尺是資金曲線，不是 per-trade alpha。**
   放寬續抱會改變持有長度，而 per-trade alpha **沒有除以持有天數**
   ⇒ 抱久一點 alpha 自然變大（10/18 的教訓：`同期大盤` 那一欄
   從 +0.97% 升到 +4.00%，4 倍）。per-trade 表仍然印，但只當診斷。

② **中性對照必須在「持有長度」這一維對齊。**
   `renew=('rand', p, salt)`：到期時以固定機率 p 續抱、**完全不看資訊**。
   這樣「抱更久」與「依評分抱更久」才分得開。
   ⚠️ 10/18 的 R50（每檔一個固定隨機值）**在這一維過度矯正**
   （均持有 80 天 vs 真成長的 32 天）⇒ 本次改用機率，並**自動挑
   持有長度最接近的那一組**來配對，挑選依據會整張印出來。

③ **每個對照跑兩個隨機實現。**
   10/18 實測 M50a vs A1 是 18/20 ✅ 而 M50b vs A1 是 14/20 ⚪，
   兩者自己就差 +105pp ⇒ **單一隨機實現的噪音足以決定判定。**

★ 事前預期（先寫下，照策略F／D 的慣例）
───────────────────────────────────────────────────────────────────
主預期：**放寬續抱會提高資金曲線報酬，但扣掉同持有長度的隨機對照之後
       剩下的「依評分續抱」貢獻會很小、甚至測不出來。**
  理由：2026-09-23 已量到評分與未來報酬 corr=0（與過去 +0.25）
  ⇒ 「評分 ≥65 才續抱」這個條件本身應該沒有鑑別度，
  真正做功的是「少換手、少付 0.47% 來回成本」。
  10/07 的機制拆解也支持：成本解釋了 169pp 裡的約 59pp，
  而剩下的被歸給「避開砍掉正在漲的那幾檔」——那一項**從未被
  與「隨機也抱著不動」的對照分開過**，這次才會分開。

反方向的可能（我認為機率較低但不低到可以忽略）：
  `'profit'` 那一條**不是純粹的「抱更久」**，它帶了一個動能條件
  （仍獲利才續抱），而 10/07 的續抱代理用的正是它、量到 +169pp。
  若 `'profit'` 顯著優於同持有長度的隨機對照，那代表
  **「讓賺的跑、把賠的砍掉」有獨立貢獻**——那會是個真發現。

★ 已知限制（引用任何數字時必須一起講）
───────────────────────────────────────────────────────────────────
1. **宇宙的倖存者偏誤已修（2026-10-21/22，陷阱55），但若跑在舊快取上
   則未修** ⇒ 而本測試的主機制正是「持有變長」，**持有越長受益越多**
   ⇒ 一定要用點時間快取（`cache --pit`），腳本會印它用的是哪一份。
2. 除權息未調整（陷阱50）；未調整收盤價（陷阱49，公司行為 24 檔）。
3. 基本面 25% 在 2026-05 之前恆為 50（陷阱44，永久）
   ⇒ 而本測試測的正是「評分門檻」，這層雜訊無法消除。
4. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。
5. 5 檔等權、每日再平衡、現金不計息（沿用 `backtest_vs_etf.py`，不另寫）。

用法
───────────────────────────────────────────────────────────────────
    python3 -u backtest_renew_scan.py pertrade nopair       # ① 只算持有長度（給 rule=auto 用）
    python3 -u backtest_renew_scan.py pertrade              # ① ＋ ② 配對 alpha（慢）
    python3 -u backtest_renew_scan.py curve rule=auto       # ② 資金曲線（只跑配得上的對照，可中斷續跑）
    python3 -u backtest_renew_scan.py curve bh              #    買進持有基準
    python3 -u backtest_renew_scan.py curve combine         # ③ 彙整＋自動配對
可選：seeds=20　seedbase=7000　end=YYYY-MM-DD　start=YYYY-MM-DD
"""
import os, pickle, random, statistics as stt, sys

import backtest_portfolio_slots as P
import backtest_vs_etf as V
from backtest_pit_universe import SLOTS, boot_band, load_cache, pit_fn_for, pref_key
from backtest_revenue_filter import sign_test

# pickle 只讀寫**本腳本自己產生**的結果檔（在 P.cache_dir() 內），
# 不來自外部來源 ⇒ 與專案其餘回測腳本一致。
OUT = os.path.join(P.cache_dir(), 'renew_%s_%d.pkl')
COST = 0.47          # 來回成本（買 0.0855% + 賣 0.3855%）

# 規則 → simulate(renew=?)
#   ★ 真規則
REAL = {
    'N65': None,            # ← 現行（＝對帳點，renew=None 位元級不變）
    'N60': 60,
    'N55': 55,
    'N50': 50,
    'N45': 45,
    'N40': 40,
    # ★ 2026-10-24 加 N35/N30：N40 是唯一兩個隨機實現一致的正面結果
    #   （+87.71／+54.87pp、66/100 與 69/100）。機制假設是
    #   「**只砍掉評分最差的那些**」——若成立，門檻再往下降到某一點
    #   優勢應該會開始消失（因為連該砍的都不砍了）。
    #   這三個門檻就是去找那個轉折點在哪。
    'N35': 35,
    'N30': 30,
    'PRF': 'profit',        # 到期時仍獲利就續抱（10/07 的續抱代理）
}
#   ★★ 中性對照：以固定機率續抱、完全不看資訊。兩個 salt ＝ 兩個隨機實現。
#   ⚠️ p 的梯子要夠長：到期每 10 日一次 ⇒ 期望續抱次數 = p/(1-p)
#     ⇒ p=0.5 約 20 日、0.9 約 100 日、0.98 約 500 日（再被停損截短）。
#     合成資料實測 `'profit'` 的均持有是 **357 日**（樣本期指數大漲 ⇒
#     到期時幾乎都還獲利）⇒ 沒有 0.95/0.98 就配不到對照。
RAND_P = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.995)
CTRL = {f'R{int(p*1000):03d}{s}': ('rand', p, f'renew-{int(p*1000)}-{s}')
        for p in RAND_P for s in ('a', 'b')}
#   ★★★ 決定性的對照（2026-10-24 加）：用**別人的評分**當續抱依據。
#     `('rand', p)` 只對齊了「平均持有長度」，沒對齊「出場時機的分布」
#     ——固定危險率會隨機砍掉正在複利的贏家，而真規則的出場是罕見事件。
#     打亂版把分布／自相關／橫斷面全部保留，只拿掉「屬於這一檔」這件事。
#     ⇒ 它與同門檻的真規則**直接可比，不需要持有長度配對**（這是它最大的好處）。
#     ⚠️ 2026-10-24 實測推翻了「不需要持有長度配對」這個假設：**同門檻的打亂版
#       系統性地抱得更短**（N65 14.9→11.3 日、N50 31.9→20.9、N40 65.0→41.0、
#       N30 205.3→151.7，短 24~37%，兩個超過 GAP_MAX）。
#       機制：進場條件是「**自己的**評分 ≥ 階梯門檻」，而評分有持續性
#       ⇒ 到期時自己的評分仍偏高、很少跌破續抱門檻；別人的評分是從
#       **無條件分布**抽的 ⇒ 更容易跌破 ⇒ 出場更多、抱更短。
#     ⇒ 所以要把打亂版的門檻**往下調**來補回持有長度。這裡給一道梯子，
#       由 `pair_list()` 依實測持有長度自動挑最接近的兩個（與 R 系列同一套做法），
#       不手動校準——手動挑一個值等於多一個自由度。
SHUF_T = (65, 58, 50, 45, 40, 36, 32, 30, 25, 20)
SHUF = {f'S{t}{s}': ('shuffle', t, f'shuf-{t}-{s}')
        for t in SHUF_T for s in ('a', 'b')}
RULES = {**REAL, **CTRL, **SHUF}
ORDER = list(REAL) + list(CTRL) + list(SHUF)
LABEL = {k: f'{k} 放寬到 {v}' for k, v in REAL.items() if isinstance(v, int)}
LABEL['N65'] = 'N65 ★現行（續抱門檻 65）'
LABEL['PRF'] = "PRF 獲利就續抱（'profit'）"
LABEL.update({k: f'{k} ☆中性對照 p={v[1]:.1%}（無資訊）' for k, v in CTRL.items()})
LABEL.update({k: f'{k} ★★★打亂版 門檻 {v[1]}（用別人的評分）' for k, v in SHUF.items()})


def build(cache, pit):
    """跑所有規則的 per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）。"""
    out = {}
    for k in ORDER:
        _, tr = P.simulate(cache, lambda c, d, s: (c,), None, k,
                           pit_at=pit, renew=RULES[k])
        out[k] = tr
        print(f'  {k:<5}{len(tr):>7} 筆', flush=True)
    return out


def hold_days(cache, trades):
    didx = {d: i for i, d in enumerate(cache['tpx_dates'])}
    h = [didx[t['exit_date']] - didx[t['entry_date']] for t in trades
         if t['entry_date'] in didx and t['exit_date'] in didx]
    return stt.mean(h) if h else 0


# ════════════════════════════════════════════════════════════════
def mode_pertrade(cache, pit, seeds, seedbase, nopair=False):
    tpx = cache['tpx_close']
    print('\n① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）')
    print('  🚨 這張表**不是本測試的答案**——per-trade alpha 沒有除以持有天數，')
    print('     而放寬續抱就是在拉長持有期。真正的量尺是 ② 的資金曲線。')
    print('     `★a/日` 那一欄做了粗略正規化，但仍不等於資金曲線。\n')
    runs = build(cache, pit)

    print(f'\n  {"規則":<30}{"筆數":>8}{"報酬":>9}{"同期大盤":>10}{"alpha":>9}'
          f'{"扣成本":>9}{"停損":>8}{"勝率":>8}{"均持有":>8}{"★a/日":>10}')
    print('  ' + '-' * 109)
    stats, holds = {}, {}
    for k in ORDER:
        s = P.stat(runs[k], tpx)
        if not s:
            continue
        hd = hold_days(cache, runs[k])
        stats[k], holds[k] = s, hd
        print(f'  {LABEL[k]:<30}{s["n"]:>8,}{s["ret"]:>+8.2f}%{s["mkt"]:>+9.2f}%'
              f'{s["alpha"]:>+8.2f}%{s["alpha"]-COST:>+8.2f}%{s["stop"]:>7.1f}%'
              f'{s["win"]:>7.1f}%{hd:>8.1f}{s["alpha"]/hd if hd else 0:>+9.4f}%')

    nmin = min(s['n'] for s in stats.values())
    lo, hi = boot_band(runs['N65'], tpx, nmin)
    rng = max(s['alpha'] for s in stats.values()) - min(s['alpha'] for s in stats.values())
    print(f'\n  各組 alpha 全距 {rng:.2f}pp　vs 雜訊帶 {hi-lo:.2f}pp'
          f'（從 N65 重抽 n={nmin:,}、600 次）')
    print(f'  ⇒ {"★ 超出雜訊帶 ⇒ 可以解讀" if rng > hi - lo else "⚪ 在雜訊帶內 ⇒ 不可解讀"}')

    print('\n  ★★ 持有長度對照表（決定後續要拿哪幾組對照去配對）')
    print(f'    {"":<5}{"均持有":>8}　{"★★★打亂版（同機制）":<34}{"固定機率（無資訊）"}')
    for k in REAL:
        if k not in holds:
            continue
        cells = []
        for fam in (SHUF, CTRL):
            pick = nearest(holds, k, fam)
            cells.append('、'.join(
                f'{c}（{holds[c]:.1f}{"" if r <= GAP_MAX else f" 🚨{r:.0%}"}）'
                for c, r in pick) or '（無）')
        print(f'    {k:<5}{holds[k]:>8.1f}　{cells[0]:<34}{cells[1]}')
    print(f'    ⚠️ 差距 >{GAP_MAX:.0%} 標 🚨 ⇒ 不算「同持有長度」，那一列不給判定。')
    print('    ★ 打亂版同門檻會抱得更短（進場條件選在自己的評分上、而評分有持續性）')
    print('      ⇒ 要靠**降低打亂版的門檻**把持有長度補回來，所以才有那道梯子。')

    if nopair:
        # ★ 只要 ① 的持有長度表（給 `curve rule=auto` 用）就停。
        #   2026-10-24 加：打亂版的梯子有 20 條，而「要挑哪幾條」必須先知道
        #   持有長度 ⇒ 雞生蛋。① 是確定性的、一個規則一次 simulate，很便宜；
        #   ② 是 seeds × 規則數，貴得多。先跑 ① 存下 holds 就好。
        print('\n（nopair：跳過 ② 配對，持有長度已存檔，可直接跑 curve rule=auto）')
        with open(OUT % ('PT', seedbase), 'wb') as f:
            pickle.dump({'per': {}, 'holds': holds}, f)
        return

    # ② 5 檔配置・配對（per-trade alpha 版，只當診斷；主結論看資金曲線）
    #   ★ 只跑「真規則 ＋ 配得上的對照」——其餘對照只是 ① 的持有長度梯子，
    #     跑進來只會讓 100 條配對變慢好幾倍。
    sub = matched(holds)
    print(f'\n② 5 檔配置・配對（{seeds} 條，seed {seedbase}~{seedbase+seeds-1}）')
    print('  ⚠️ 同樣是 per-trade alpha ⇒ 對「改變持有長度」的規則不公平。')
    print(f'  只跑 {len(sub)} 組：{" ".join(sub)}\n')
    per = {k: [] for k in sub}
    for sd in range(seeds):
        rk = pref_key(cache, seedbase + sd)
        for k in sub:
            _, tr = P.simulate(cache, rk, SLOTS, k, pit_at=pit, renew=RULES[k])
            s = P.stat(tr, tpx)
            per[k].append(s['alpha'] if s else 0.0)
        if (sd + 1) % 10 == 0:
            print(f'    {sd+1}/{seeds} 條', flush=True)
    print(f'\n  {"規則":<30}{"中位 alpha":>12}')
    for k in sub:
        v = sorted(per[k])
        print(f'  {LABEL[k]:<30}{v[len(v)//2]:>+11.3f}%')
    print_pairs(per, holds, 'pp')
    with open(OUT % ('PT', seedbase), 'wb') as f:
        pickle.dump({'per': per, 'holds': holds}, f)


GAP_MAX = 0.30        # 持有長度差超過這個比例 ⇒ 不算「同持有長度」


def nearest(holds, k, family, n=2):
    """
    從 `family` 裡挑出持有長度最接近 `k` 的 n 個，回傳 [(代號, 差距比例), ...]。

    ★ 兩個對照家族（R 固定機率、S 打亂評分）**共用這一支**。
      2026-10-24 的教訓正是「同一條規則散在多處、只改一處」第三次出現
      ——S 家族當初是硬寫死的同門檻配對、連守衛都沒套（見 `pair_list`）。
    """
    if k not in holds or not holds[k]:
        return []
    cand = sorted((abs(holds[c] - holds[k]), c) for c in family if c in holds)[:n]
    return [(c, gap / holds[k]) for gap, c in cand]


def matched(holds):
    """真規則 ＋ 兩個家族各自持有長度最接近的對照（去重、保持順序）。"""
    out = [k for k in REAL if k in holds] or list(REAL)
    for k in list(out):
        for fam in (SHUF, CTRL):
            for c, _ in nearest(holds, k, fam):
                if c not in out:
                    out.append(c)
    return out


def pair_list(holds):
    """
    真規則之間 ＋ 每個真規則 vs 兩個家族中持有長度最接近的各兩個對照。

    🚨 2026-10-24 補的守衛（**兩個家族都要套**）：
       `combine` 只會看到「這一輪實際跑過」的規則，所以「最接近者」
       可能差了一倍以上。
       ① **R 家族**第一版沒檢查 ⇒ 10/23 那輪 N65（14.9 日）被配到
         R800（33 日、2.2 倍），印出一個 21/100、p=0.000 的強結論而它無效。
       ② **S 家族（打亂版）第一版是硬寫死的同門檻配對、連守衛都沒套**，
         理由寫「出場機制完全相同所以不需要持有長度配對」——
         **那個理由被實測否證**：同門檻的打亂版系統性抱得更短
         （24~37%，兩個超過 GAP_MAX）。
       ⇒ **守衛要放在每一個會做配對的地方，不能只放在其中一個。**
         現在兩個家族都走 `nearest()`，結構上不可能再漏掉。
    """
    # 「vs 現行」那幾列自動生成——加新門檻時不必記得來補一行
    out = [(f'{k} vs N65 現行', k, 'N65') for k in REAL if k != 'N65']
    if not holds:
        return out
    for k in REAL:                       # 含 N65：現行規則本身贏得過對照嗎？
        for fam, lab in ((SHUF, '打亂版・同持有長度'), (CTRL, '固定機率・同持有長度')):
            for c, r in nearest(holds, k, fam):
                tag = (f'★★★ {k} vs {c}（{lab}）' if r <= GAP_MAX else
                       f'🚨 {k} vs {c}（持有長度差 {r:.0%} ⇒ **不可讀**）')
                out.append((tag, k, c))
    return out


def print_pairs(res, holds, unit, getter=None):
    g = getter or (lambda k, s: res[k][s])
    print(f'\n  {"配對":<40}{"Δ中位":>11}{"勝場":>10}{"p":>8}  判定')
    print('  ' + '-' * 82)
    for lab, a, b in pair_list(holds):
        if a not in res or b not in res:
            continue
        n = min(len(res[a]), len(res[b]))
        d = [g(a, s) - g(b, s) for s in range(n)]
        w, nn, t, p = sign_test(d)
        med = sorted(d)[len(d) // 2]
        if lab.startswith('🚨'):          # 持有長度配不上 ⇒ 不給判定，免得被引用
            v = '—'
        else:
            v = ('❌' if (p < .05 and med < 0) else
                 '✅' if (p < .05 and med > 0) else '⚪')
        print(f'  {lab:<40}{med:>+10.2f}{unit}{w:>7}/{nn:<3}{p:>8.3f}  {v}'
              + (f'　平手{t}' if t else ''))


# ════════════════════════════════════════════════════════════════
def mode_curve(cache, pit, args, seeds, seedbase):
    cal = cache['tpx_dates']

    if 'bh' in args:
        out = {}
        for code, nm in (('0050', '買進持有 0050'), ('0056', '買進持有 0056'),
                         ('TAIEX', '加權指數（不可投資）')):
            eq, _ = V.buyhold_curve(code, cal, pay_fee=(code != 'TAIEX'), days=2600)
            if eq:
                out[nm] = V._metrics(cal, eq)
        with open(OUT % ('BH', seedbase), 'wb') as f:
            pickle.dump(out, f)
        for nm, m in out.items():
            print(f'  {nm:<22}{m["ret"]:>+9.2f}%　回檔 {m["mdd"]:>+7.2f}%')
        return

    if 'combine' in args:
        return combine(seedbase)

    rule = next((a.split('=')[1] for a in args if a.startswith('rule=')), None)
    if rule == 'auto':
        # ★ 只跑「6 個真規則 ＋ 真的配得上的那幾個對照」，省掉一半的時間。
        #   需要先跑過 pertrade（它會把持有長度存起來）。
        fp = OUT % ('PT', seedbase)
        if not os.path.exists(fp):
            print('🚨 rule=auto 需要先跑 pertrade（它會算出各規則的持有長度）')
            return
        todo = matched(pickle.load(open(fp, 'rb'))['holds'])
        print(f'  rule=auto ⇒ 跑 {len(todo)} 組：{" ".join(todo)}')
    else:
        todo = ORDER if rule == 'all' else ([rule] if rule in RULES else None)
    if not todo:
        print(f'用法：rule=auto（推薦）／rule=all／rule=<{"|".join(ORDER)}>')
        return

    didx = {d: i for i, d in enumerate(cal)}
    for k in todo:
        fp = OUT % (k, seedbase)
        if os.path.exists(fp):
            print(f'  {k} 已有結果，跳過（要重跑請刪 {fp}）')
            continue
        rows = []
        for sd in range(seeds):
            rk = pref_key(cache, seedbase + sd)
            _, tr = P.simulate(cache, rk, SLOTS, k, pit_at=pit, renew=RULES[k])
            eq, invd = V.strategy_curve(cache, tr, SLOTS, cal)
            m = V._metrics(cal, eq, invd)
            h = [didx[t['exit_date']] - didx[t['entry_date']] for t in tr
                 if t['entry_date'] in didx and t['exit_date'] in didx]
            m['hold'] = stt.mean(h) if h else 0
            m['ntr'] = len(tr)
            rows.append(m)
        with open(fp, 'wb') as f:
            pickle.dump(rows, f)
        srt = sorted(x['ret'] for x in rows)
        print(f'★ {LABEL[k]:<30}報酬中位 {srt[len(srt)//2]:>+9.2f}%　'
              f'（{srt[0]:+.1f}% ~ {srt[-1]:+.1f}%）　'
              f'均持有 {stt.mean([x["hold"] for x in rows]):.1f}　'
              f'相異值 {len(set(srt))}/{seeds}', flush=True)


def combine(seedbase):
    res = {}
    for k in ORDER:
        fp = OUT % (k, seedbase)
        if os.path.exists(fp):
            res[k] = pickle.load(open(fp, 'rb'))
    if not res:
        print('🚨 沒有任何結果檔，先跑 curve rule=all')
        return
    print('=' * 104)
    print('放寬續抱條件：資金曲線（5 檔等權）')
    print('=' * 104)
    print('🚨 絕對數字不可解讀（帶寬極大），只有配對差值可讀。\n')
    print(f'  {"規則":<30}{"報酬中位":>11}{"5%":>10}{"95%":>11}{"帶寬":>9}'
          f'{"回檔":>9}{"在場內":>8}{"均持有":>8}{"筆數":>8}')
    print('  ' + '-' * 102)
    holds = {}
    for k in ORDER:
        if k not in res:
            continue
        r = res[k]
        rets = sorted(x['ret'] for x in r)
        n = len(rets)
        lo, md, hi = rets[max(0, int(n * .05))], rets[n // 2], rets[min(n - 1, int(n * .95))]
        mdd = sorted(x['mdd'] for x in r)[n // 2]
        holds[k] = stt.mean([x['hold'] for x in r])
        print(f'  {LABEL[k]:<30}{md:>+10.2f}%{lo:>+9.2f}%{hi:>+10.2f}%'
              f'{hi-lo:>8.1f}pp{mdd:>+8.2f}%'
              f'{stt.mean([x["inv"] for x in r]):>7.1f}%{holds[k]:>8.1f}'
              f'{stt.mean([x["ntr"] for x in r]):>8.0f}')
    bh = OUT % ('BH', seedbase)
    if os.path.exists(bh):
        print()
        for nm, m in pickle.load(open(bh, 'rb')).items():
            print(f'  {nm:<22}總報酬 {m["ret"]:>+10.2f}%　最大回檔 {m["mdd"]:>+7.2f}%')

    print('\n【總報酬】')
    print_pairs(res, holds, 'pp', getter=lambda k, s: res[k][s]['ret'])
    print('\n【最大回檔的絕對值（負值＝更淺＝更好）】')
    print_pairs(res, holds, 'pp', getter=lambda k, s: -abs(res[k][s]['mdd']))
    print('\n  ★ 解讀順序：先看「真規則 vs 現行」有沒有效果，')
    print('    再看「vs 同持有長度的無資訊對照」——後者才是「依評分續抱」的淨貢獻。')
    print('    ⚠️ 兩個對照實現（a／b）判定不一致 ⇒ 條數不足，不可下結論（10/16 的規矩）。')


# ════════════════════════════════════════════════════════════════
def main():
    args = sys.argv[1:]
    seeds = next((int(a.split('=')[1]) for a in args if a.startswith('seeds=')), None)
    seedbase = next((int(a.split('=')[1]) for a in args if a.startswith('seedbase=')), 7000)
    end = next((a.split('=')[1] for a in args if a.startswith('end=')), None)
    start = next((a.split('=')[1] for a in args if a.startswith('start=')), None)

    if 'curve' in args and 'combine' in args:
        return combine(seedbase)

    cache, both = load_cache(end=end, start=start)
    if not both:
        print('\n⚠️ **這份快取沒有已退場股（陷阱55）**。本測試的主機制正是')
        print('   「持有變長」，而持有越長從倖存者偏誤受益越多 ⇒ 效果會被高估。')
        print('   建議先跑：python3 -u backtest_revenue_filter.py cache --pit')
    pit, _ = pit_fn_for(cache)

    if 'curve' in args:
        mode_curve(cache, pit, args, seeds or 20, seedbase)
    else:
        # ② 的預設只給 20 條——它是 per-trade alpha，本來就不是本測試的答案，
        #   花 100 條在一把不公平的尺上不划算。要加條數請傳 seeds=100。
        mode_pertrade(cache, pit, seeds or 20, seedbase, nopair='nopair' in args)


if __name__ == '__main__':
    main()
