#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
清地基：把「倖存者偏誤 × 持有長度」從既有結論裡拆出來（2026-10-21）
═══════════════════════════════════════════════════════════════════════

★ 背景／要驗證的問題（照 2026-08-18 立的規矩，先寫問題再放程式）

10/18 的「資金曲線重評」標了最嚴重的一條限制：

  > 512 檔宇宙是用**全期**日均成交金額 ≥0.5 億篩出來的 ⇒ 期間崩掉／下市／
  > 流動性枯竭的股票根本不在裡面。而本次量到的主要機制正是「**持有變長**」
  > ——**持有越長，從這個偏誤受益越多。**
  > ⇒ 成分①（少換手／抱更久）的 +493pp 有多少是真的、多少是倖存者偏誤，
  >   現有快取分不開。**在那之前，成分① 的量級不可引用。**

而 2026-10-21 動手查之後發現，問題比那段話寫的更基本：

  `market_universe()` 的流動性是用 `UNI_SINCE='2025-09-01'` 起算的
  ⇒ **任何在那之前消失的股票，`n>=180` 必然不成立**，一律被排除；
  而 `market='TWSE'` 又是查**今天的** `stocks` 表。兩個條件都擋。

  實測：`prices` 裡 2018 起的 4 碼普通股 2,040 檔，其中 **73 檔在 `stocks`
  查不到**（21 檔達流動性門檻、18 檔是歷史退場），含 **6452 康友-KY**
  （2020-08 財報造假下市、日均成交 2.89 億、639 個交易日 ⇒ 完全達標，
  但從來沒有出現在任何回測裡）。

  ⚠️ 連帶更正：`backtest_structure_bear.py` 的 `uni_at` 雖然叫
  「point-in-time 宇宙」，成員資格仍然是 `mk.get(code)=='TWSE'`
  ⇒ **10/07 與 10/08 那兩節也漏掉同一批股票**，只做對了「時間」那一半。

★ 本腳本把偏誤拆成兩半，而第一半**不需要重建快取**：

  ┌ 第一半：流動性 look-ahead ────────────────────────────────────┐
  │ 現有 513 檔快取 ＋ `pit_at`（逐月重算的點時間宇宙）            │
  │ ⇒ 擋掉「2018 年就進場買一檔其實要到 2024 才夠流動的股票」      │
  │ **免費**（快取不用動）                                         │
  └───────────────────────────────────────────────────────────────┘
  ┌ 第二半：母體缺失 ──────────────────────────────────────────────┐
  │ 需要含那 359 檔（含 18 檔已退場）的新快取                      │
  │ `python3 -u backtest_revenue_filter.py cache --pit`            │
  └───────────────────────────────────────────────────────────────┘

★ 事前預期（先寫下，照策略F／D 那次的慣例）

  主預期：**第一半（流動性 look-ahead）的影響小、第二半較大但仍有界。**
   ① 第一半只是把「當時還不夠流動」的股票擋在門外，而評分門檻 65 本來就
     偏向成交活絡的強勢股 ⇒ 重疊度高，擋掉的應該不多。
   ② 第二半補進 18 檔已退場股（其中多數是**合併換股**——2311 日月光→
     日月光投控、2448 晶電→富采、2888 新光金→台新新光金、3682 亞太電→
     遠傳——股東有換到對價，不是全損）⇒ 偏誤方向不是單純「贏家才留下」。
     真正的全損只有 6452 康友-KY 一檔。
   ③ 量級上 18 / 594 ≈ 3% 的宇宙 ⇒ 預期 A1 的 alpha 變動在 ±0.1pp 內。
     **若明顯大於這個，要先查是不是哪一檔的價格序列有問題（陷阱49 的假崩盤）。**

  反方向的可能（我認為機率較低）：若「抱更久」的效果在點時間宇宙上明顯縮水，
  那就是 10/18 擔心的交互作用被證實——而那會連帶動搖 10/07 的續抱結論
  （那次的 `uni_at` 也漏掉同一批股票）。

★ 判定標準（事前定好，避免事後挑）
  per-trade 層級先算雜訊帶（9/17 立的標準前置動作）；
  5 檔配對用符號檢定、100 條（10/16 的教訓：20 條在小效果上沒有解析度）。

═══ 使用方式 ═══
  python3 -u backtest_pit_universe.py              # 自動選快取，跑第一半（或兩半）
  python3 -u backtest_pit_universe.py seeds=100    # 配對條數
  python3 -u backtest_pit_universe.py seedbase=8000
"""
import sys, os, pickle, math, random, statistics as stt
from collections import defaultdict

# ⚠️ pickle 的來源：這些快取**由 backtest_revenue_filter.py 的 `cache` 子命令
#    自己寫入 /tmp**，不是外部或網路輸入，內容是純 dict/list/float（無自訂類別）。
#    與既有的 backtest_portfolio_slots.py／backtest_revenue_filter.py 同一模式。

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_portfolio_slots as P
from backtest_revenue_filter import CACHE, CACHE_PIT, START, sign_test

SLOTS     = 5
N_SEEDS   = 100
SEED_BASE = 7000
BOOT_N    = 600
BEAR_YEARS = ('2018', '2020', '2022')


# ════════════════════════════════════════════════════════════════
def load_cache(end=None, start=None):
    """
    優先用點時間快取（含已退場股）；沒有就退用既有快取，**並明講只能測第一半**。
    """
    # ★ 依序找三種候選。`both=True` 代表快取裡含已退場股 ⇒ 兩半都測得到。
    #   ⚠️ 第三個（_pf_slots_cache_market）是**使用者本機那份**——10/16 與 10/18
    #     的交叉驗證就是跑在它上面。它沒有 rev_rank，但本測試不需要月營收。
    for path, both in ((CACHE_PIT, True), (CACHE, False), (P.CACHE_MARKET, False)):
        if os.path.exists(path):
            break
    else:
        print(f'❌ 找不到任何快取（目錄 {P.cache_dir()}）。先跑其中一個：')
        print('   python3 -u backtest_revenue_filter.py cache --pit   '
              '（含已退場股，兩半都能測）')
        print('   python3 -u backtest_revenue_filter.py cache         '
              '（既有宇宙，只能測第一半）')
        print('   python3 -u backtest_portfolio_slots.py cache market days=2600')
        sys.exit(1)

    with open(path, 'rb') as f:
        cache = pickle.load(f)
    n0 = len(cache['tpx_dates'])
    # ★ 裁掉 2018 之前（陷阱51 限制第 5 條）
    cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
    # ★ 2026-10-22 加 `end=`：對帳用。既有數字（15,169~15,176 筆、alpha +0.31%）
    #   是在資料截止 2026-10-14／10-15 時跑的；本快取多了約 6 個交易日
    #   ⇒ 筆數與 alpha 必然不同。**對帳失敗時第一個該排除的就是期間差異**，
    #   而它只需要一個參數就能驗。
    print(f'快取目錄：{P.cache_dir()}'
          + ('' if os.environ.get('TWSTOOL_CACHE')
             else '　⚠️ 預設 /tmp，會被系統清掉；跨天重用請設 TWSTOOL_CACHE'))
    print(f'快取：{os.path.basename(path)}　{len(cache["stocks"])} 檔　'
          f'{cache["tpx_dates"][0]} ~ {cache["tpx_dates"][-1]}'
          f'（裁掉 {START} 之前 {n0 - len(cache["tpx_dates"])} 天）')

    # ★ 阻斷式涵蓋檢查（10/15 立的規矩：入口就要檢查「這份快取涵蓋我需要的期間嗎」，
    #   不能只檢查「檔案存在嗎」）
    yrs = set(d[:4] for d in cache['tpx_dates'])
    miss = [y for y in BEAR_YEARS if y not in yrs]
    if miss:
        print(f'\n🚨 **快取沒有涵蓋空頭年 {miss}** ⇒ 本測試要回答的正是'
              f'「倖存者偏誤在長持有期上的影響」，缺空頭年等於白跑。中止。')
        print('   請用 days=2600 重建（見 backtest_revenue_filter.DAYS）。')
        sys.exit(1)
    print(f'  ✅ 三個空頭年都在（{BEAR_YEARS}）')

    # ★ 守衛**必須在 start/end 裁切之前**跑。
    #   2026-10-22 第一版放在裁切之後 ⇒ `start=2019-01-01`（刻意的 robustness
    #   檢查：2018 的月宇宙只有 192 檔，是價格回填邊界而非 PIT 造成的）
    #   被誤判成「快取建太短」而中止。
    #   ⇒ **守衛問的是「這份快取夠不夠」，不是「這次要跑哪一段」。**
    #     刻意縮短區間是合法的分析選擇，但要**明講少了哪些空頭年**。
    if start:
        before = len(cache['tpx_dates'])
        cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= start]
        print(f'  ★ 起點移到 {start}（去掉前面 '
              f'{before - len(cache["tpx_dates"])} 天）')
    if end:
        before = len(cache['tpx_dates'])
        cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d <= end]
        print(f'  ★ 結束日截到 {end}（去掉尾端 '
              f'{before - len(cache["tpx_dates"])} 天）')
    if start or end:
        yrs2 = set(d[:4] for d in cache['tpx_dates'])
        lost = [y for y in BEAR_YEARS if y not in yrs2]
        print(f'  ⇒ 實際跑 {cache["tpx_dates"][0]} ~ {cache["tpx_dates"][-1]}'
              + (f'　⚠️ **這次少了空頭年 {lost}**，引用時必須講'
                 if lost else '　（三個空頭年仍都在）'))
    return cache, both


def pit_fn_for(cache):
    """
    取得 pit_at。優先用快取裡存的 `pit_months`（新快取）；
    沒有就**從 DB 現算**——這樣既有快取也能測第一半，不必重建。
    """
    months = cache.get('pit_months')
    if months:
        print(f'  點時間宇宙：取自快取（{len(months)} 個月）')
    else:
        from database import get_conn
        conn = get_conn()
        print('  點時間宇宙：快取裡沒有，從 DB 現算（每月一次 GROUP BY）...',
              end='', flush=True)
        months, union = P.pit_universe(conn)
        conn.close()
        print(f' {len(months)} 個月、聯集 {len(union)} 檔')
    sz = [len(m[1]) for m in months]
    print(f'  月宇宙平均 {stt.mean(sz):.0f} 檔（{min(sz)}~{max(sz)}）')
    return P.pit_lookup(months), months


def pref_key(cache, seed):
    """
    真隨機排序鍵。⚠️ **必須 `sorted()`**——10/16 抓到的 bug：
    `{c: rnd.random() for c in cache['stocks']}` 的順序＝dict 插入順序，
    而兩份快取的建構路徑不同（分塊合併 vs 循序）⇒ 同一個 seed 配到不同股票，
    配對設計的「同一組運氣」前提破掉，而數字看起來完全正常。
    """
    rnd = random.Random(seed)
    pref = {c: rnd.random() for c in sorted(cache['stocks'])}
    return lambda c, d, s: pref[c]


def boot_band(trades, tpx_close, n_sub, reps=BOOT_N, seed=99):
    """從基準組重抽 n_sub 筆，回傳 alpha 的 5~95% 分位（9/17 立的標準前置動作）。"""
    rnd = random.Random(seed)
    out = []
    for _ in range(reps):
        sub = [trades[rnd.randrange(len(trades))] for _ in range(n_sub)]
        s = P.stat(sub, tpx_close)
        if s:
            out.append(s['alpha'])
    out.sort()
    return out[int(reps * .05)], out[int(reps * .95)]


# ════════════════════════════════════════════════════════════════
def run(cache, both, seeds, seedbase, quick=False):
    tpx = cache['tpx_close']
    pit, months = pit_fn_for(cache)
    ladder = None                      # None ⇒ simulate 用現行 UI 階梯
    flat65 = lambda d: 65              # 不看大盤、一律 65 分

    gone = set()
    if both:
        from database import get_conn
        conn = get_conn()
        cur = set(r[0] for r in conn.execute('SELECT code FROM stocks'))
        conn.close()
        gone = set(c for c in cache['stocks'] if c not in cur)
        print(f'  快取內「今天已不在 stocks」的檔數：{len(gone)}')

    # ── ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）──
    print()
    print('=' * 78)
    print('① per-trade（不限檔數 ⇒ 排序無關、確定性）')
    print('=' * 78)
    rules = [
        ('L   現行階梯',          dict(threshold_fn=ladder)),
        ('L+P 現行階梯＋點時間',   dict(threshold_fn=ladder, pit_at=pit)),
        ('F   一律65（不看大盤）', dict(threshold_fn=flat65)),
        ('F+P 一律65＋點時間',    dict(threshold_fn=flat65, pit_at=pit)),
    ]
    # ★ 對帳組：把候選限制回**舊宇宙（market_universe 的 513 檔）**、pit_at=None
    #   ⇒ 應該重現既有數字 **15,169~15,176 筆、alpha +0.31%**
    #   （10/14 的 A0 現行策略、10/15 的 C 現行 UI 階梯、10/16 的 ★10% 都是這個數）。
    #   這樣「一次重建」同時給出對帳點與新結果——否則舊快取不見之後
    #   就再也無法回答「差異是宇宙造成的，還是程式改壞了」。
    if both:
        from database import get_conn
        _c = get_conn()
        old_uni = set(P.market_universe(_c))
        # ★ 2026-10-22：對帳對不上之後加的診斷。
        #   `market_universe()` 用 `UNI_SINCE='2025-09-01'` 起算、`n>=UNI_MIN_DAYS`
        #   ⇒ **新上市股會隨時間累積到 180 個交易日而陸續「長進」宇宙**。
        #   所以「今天重建的舊宇宙」≠「10/15 那天的舊宇宙」。
        #   ⇒ 用 market_universe() 當對帳點，本身就是個會漂移的靶。
        first = dict(_c.execute(
            "SELECT code, MIN(date) FROM prices WHERE code!='TAIEX' GROUP BY code"))
        _c.close()
        newish = sorted(c for c in old_uni if first.get(c, '') >= '2025-01-01')
        inter = len(old_uni & set(cache['stocks']))
        print(f'  對帳用的舊宇宙：{len(old_uni)} 檔（在本快取內 {inter} 檔）')
        print(f'  ★ 其中 2025-01 之後才首次有價格的「新股」：{len(newish)} 檔'
              f'{"　" + " ".join(newish[:10]) if newish else ""}')
        stable = old_uni - set(newish)
        rules.insert(1, ('R   對帳：限舊宇宙',
                         dict(threshold_fn=ladder,
                              entry_filter=lambda c, d: c in old_uni)))
        rules.insert(2, ('R2  對帳：舊宇宙剔新股',
                         dict(threshold_fn=ladder,
                              entry_filter=lambda c, d: c in stable)))
        # ★ 第二個對帳點：**不走階梯、一律 65**。
        #   10/15 的階梯那節在舊宇宙上量到 `A 不看大盤・一律 65` = 28,613 筆、
        #   alpha +0.19%。它與 R 共用同一批評分與價格，但**不碰 market_net**
        #   ⇒ 兩個對帳點一起看，就能分辨差異出在「大盤淨值」還是「評分／價格」。
        rules.insert(3, ('R65 對帳：舊宇宙・一律65',
                         dict(threshold_fn=flat65,
                              entry_filter=lambda c, d: c in old_uni)))
    res = {}
    rk = lambda c, d, s: c            # 不限檔數時排序鍵不影響結果
    for lab, kw in rules:
        _, tr = P.simulate(cache, rk, None, lab, **kw)
        s = P.stat(tr, tpx)
        res[lab] = (s, tr)
        print(f'{lab:<24} n={s["n"]:>6,}　alpha {s["alpha"]:+.2f}%　'
              f'扣成本 {s["alpha"]-0.47:+.2f}%　勝率 {s["win"]:.1f}%　'
              f'停損 {s["stop"]:.1f}%')

    alphas = [v[0]['alpha'] for v in res.values()]
    ns = [v[0]['n'] for v in res.values()]
    lo, hi = boot_band(res['L   現行階梯'][1], tpx, min(ns))
    print()
    print(f'  各組 alpha 全距 {max(alphas)-min(alphas):.2f}pp'
          f'　vs 雜訊帶 {hi-lo:.2f}pp（從 L 重抽 n={min(ns):,}、{BOOT_N} 次）')
    print('  ⇒ ' + ('★ 全距超出雜訊帶 ⇒ 可以解讀'
                    if max(alphas) - min(alphas) > hi - lo else
                    '⚪ 全距在雜訊帶內 ⇒ **不可解讀**'))

    # ── 診斷：點時間擋掉了什麼 ──
    print()
    print('② 點時間宇宙擋掉了什麼')
    base = set((t['code'], t['signal_date']) for t in res['L   現行階梯'][1])
    aft  = set((t['code'], t['signal_date']) for t in res['L+P 現行階梯＋點時間'][1])
    blocked = base - aft
    print(f'  被擋掉的進場：{len(blocked)} / {len(base)}'
          f'（{len(blocked)/max(1,len(base))*100:.1f}%）')
    byy = defaultdict(int)
    for _, d in blocked:
        byy[d[:4]] += 1
    tot = defaultdict(int)
    for _, d in base:
        tot[d[:4]] += 1
    print('  逐年：' + '　'.join(
        f'{y} {byy.get(y,0)}/{tot[y]}' for y in sorted(tot)))
    if blocked:
        bt = [t for t in res['L   現行階梯'][1]
              if (t['code'], t['signal_date']) in blocked]
        sb = P.stat(bt, tpx)
        print(f'  ★ 被擋掉那批原本的表現：alpha {sb["alpha"]:+.2f}%'
              f'（n={sb["n"]:,}、勝率 {sb["win"]:.1f}%）'
              f'　← 若明顯為正，代表點時間宇宙擋掉的是**好交易**（＝偏誤的來源）')

    if gone:
        print()
        print('③ 已退場股的貢獻（只有點時間快取才有）')
        for lab in ('L   現行階梯', 'L+P 現行階梯＋點時間'):
            tr = res[lab][1]
            g = [t for t in tr if t['code'] in gone]
            if not g:
                print(f'  {lab:<24} 0 筆')
                continue
            sg = P.stat(g, tpx)
            print(f'  {lab:<24} {sg["n"]:>4} 筆（{sg["n"]/len(tr)*100:.1f}%）'
                  f'　alpha {sg["alpha"]:+.2f}%　勝率 {sg["win"]:.1f}%'
                  f'　最差單筆 {min(t["pnl"] for t in g):+.1f}%')

    # ── ③b 候選數診斷（10/14 立的便宜判準）──
    #   這一項回答的是上次留著當「推論」的那句話：
    #   「5 個槽位本來就不缺候選，所以砍掉 43% 的候選對階梯組幾乎無影響」。
    #   ⚠️ 必須在 **5 檔配置** 下量——per-trade 層級不限檔數，看不到閒置的槽位。
    print()
    print(f'③b 單日候選數（5 檔配置、seed {seedbase}；'
          f'候選＝達標且未持有 ⇒ 「還能再買幾檔可選」）')
    rk0 = pref_key(cache, seedbase)
    print(f'  {"規則":<24}{"有空位天數":>10}{"候選中位":>9}{"≥5檔":>8}{"★槽位滿":>8}')
    for lab, kw in rules:
        rec = []
        P.simulate(cache, rk0, SLOTS, lab,
                   cand_probe=lambda d, n, free: rec.append((n, free)), **kw)
        if not rec:
            print(f'  {lab:<24}{"（無訊號日）":>10}')
            continue
        ns_ = [r[0] for r in rec]
        enough = sum(1 for n, free in rec if n >= free) / len(rec) * 100
        ge5 = sum(1 for n in ns_ if n >= SLOTS) / len(ns_) * 100
        print(f'  {lab:<24}{len(rec):>10,}{stt.median(ns_):>9.0f}'
              f'{ge5:>7.1f}%{enough:>7.1f}%')
    print('  ※ 「有空位天數」＝階梯放行**且當天有空名額**的天數。')
    print('    ⚠️ 它**不可跨規則當成「訊號多寡」比**——守得越滿（換手越少）的規則，')
    print('      本來就越少有空位的日子，這個數字反而更小。')
    print('  ★ 「槽位滿」才是本診斷要的答案：在**有空位的那些天裡**，候選是否')
    print('    足以填滿空出的名額。它低 ⇒ 篩太兇、部位閒置（10/14 量到的機制）。')

    # ── ④ 5 檔配置・配對比較 ──
    if quick:
        print()
        print('（quick 模式：跳過 5 檔配對。對帳用，省時間）')
        return
    print()
    print('=' * 78)
    print(f'④ 5 檔配置・配對比較（{seeds} 條，seed {seedbase}~{seedbase+seeds-1}）')
    print('=' * 78)
    runs = defaultdict(dict)
    for s in range(seedbase, seedbase + seeds):
        rk_s = pref_key(cache, s)
        for lab, kw in rules:
            _, tr = P.simulate(cache, rk_s, SLOTS, lab, **kw)
            st_ = P.stat(tr, tpx)
            runs[lab][s] = st_['alpha'] if st_ else 0.0
        if (s - seedbase + 1) % 20 == 0:
            print(f'  [{s-seedbase+1}/{seeds}]', flush=True)

    print()
    for lab, _ in rules:
        v = sorted(runs[lab].values())
        print(f'  {lab:<24} 中位 alpha {stt.median(v):+.3f}%'
              f'（5~95%：{v[int(seeds*.05)]:+.2f} ~ {v[int(seeds*.95)]:+.2f}）')

    pairs = [('現行階梯＋點時間 vs 現行階梯',
              'L+P 現行階梯＋點時間', 'L   現行階梯'),
             ('一律65＋點時間 vs 一律65',
              'F+P 一律65＋點時間', 'F   一律65（不看大盤）')]
    # ★★ 2026-10-22 補上的那一組——**這才是真正的修正**。
    #   `L+P vs L` 是假問題：L（872 檔固定宇宙、無 PIT）從來不是任何人用過的
    #   基準。歷史上所有數字（10/14~10/18）用的都是 `market_universe()` 的
    #   513 檔固定宇宙 ⇒ 要問「修正倖存者偏誤之後掉多少」，比的必須是
    #   **R（舊宇宙、用今天的流動性挑）vs L+P（點時間、用當時的流動性挑）**。
    #   ⚠️ 這一組不是「只動一個變數」的乾淨配對（成員集合與時變性同時改了），
    #     但那兩者正是同一個錯誤的兩面，分開修沒有意義。
    if 'R   對帳：限舊宇宙' in runs:
        pairs.insert(0, ('★ 點時間 vs 舊宇宙（＝實際的修正）',
                         'L+P 現行階梯＋點時間', 'R   對帳：限舊宇宙'))
    print()
    print(f'  {"配對":<34}{"Δ中位":>9}{"勝場":>10}{"p":>8}  判定')
    for lab, a, b in pairs:
        d = [runs[a][s] - runs[b][s] for s in runs[a]]
        w, n, ties, p = sign_test(d)
        mark = '⚪' if p >= 0.05 else ('✅' if stt.median(d) > 0 else '❌')
        print(f'  {lab:<34}{stt.median(d):+8.2f}pp{w:>7}/{n:<4}{p:>7.3f}  {mark}'
              + (f'（平手 {ties}）' if ties else ''))

    # ── 退化配對偵測（10/14 留下的守衛）──
    for lab, _ in rules:
        v = list(runs[lab].values())
        if len(set(round(x, 9) for x in v)) == 1:
            print(f'\n🚨 **{lab} 的 {seeds} 條 alpha 完全相同** ⇒ 5 檔上限從未綁定'
                  f'／隨機排序沒起作用，符號檢定讀到的是同一個數字抄 N 次，'
                  f'**p 不可讀**。')

    print()
    print('─' * 78)
    if not both:
        print('⚠️ **這次只測了第一半（流動性 look-ahead）。**')
        print('   快取是既有的宇宙，那 18 檔已退場股根本不在裡面 ⇒ 母體缺失那一半沒測到。')
        print('   要測第二半：python3 -u backtest_revenue_filter.py cache --pit')
    print('⚠️ 引用任何上述數字時必須一起講的限制：')
    print('  1. **2018 的月宇宙平均只有 192 檔**（2019 起 265~496）——全市場個股價格')
    print('     只回填到 2018-01-02，前 60 個交易日湊不滿回看窗。那不是 PIT 造成的，')
    print('     **解讀 2018 的差異時要把這兩個原因分開**。')
    print('  2. 除權息未調整（陷阱50）；未調整收盤價（陷阱49，公司行為 24 檔）。')
    print('  3. 基本面 25% 在 2026-05 之前恆為 50（陷阱44，永久）。')
    print('  4. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。')


if __name__ == '__main__':
    args = sys.argv[1:]
    seeds, seedbase, end, start = N_SEEDS, SEED_BASE, None, None
    for a in args:
        if a.startswith('seeds='):
            seeds = int(a.split('=', 1)[1])
        elif a.startswith('seedbase='):
            seedbase = int(a.split('=', 1)[1])
        elif a.startswith('end='):
            end = a.split('=', 1)[1]
        elif a.startswith('start='):
            start = a.split('=', 1)[1]
    cache, both = load_cache(end, start)
    run(cache, both, seeds, seedbase, quick='quick' in args)
