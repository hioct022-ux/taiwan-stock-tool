"""
★ 要驗證的問題（十五章月營收那節標著「尚未做」的最後一項）
═══════════════════════════════════════════════════════════════════
月營收 YoY 要「當第四個分項」還是「當篩選門檻」？兩者**不是同一條規則的
兩種寫法**，差別在「能不能互相抵銷」：

  當篩選門檻（2026-10-14 已測，B2：+0.64% alpha）
      評分 ≥ 門檻 **之後再 AND 一道** YoY ≥ 產業內中位
      ⇒ YoY 低就直接排除，評分再高也沒用（AND，不可抵銷）

  當第四個分項（本次）
      成長分數進入加權和，與技術／籌碼／基本面一起算
      ⇒ YoY 低但其他面強 ⇒ 仍可能達標（加權和，可抵銷）
      ⇒ 而且它**同時影響續抱**（續抱門檻也是看總分），篩選門檻那版不會

★ 實作上最重要的判斷：不改篩選邏輯，改「分數本身」
───────────────────────────────────────────────────────────────────
「等比例稀釋現有三面、再加一個權重 w 的新面」在數學上精確等於對舊總分
做加權平均：

    新 = (1-w)×(0.40技 + 0.35籌 + 0.25基) + w×成長
       = (1-w) × 舊總分 + w × 成長分數

⇒ **只需要總分，不需要三個分項**（快取裡沒有分項，重建要 20~40 分鐘）。
⇒ 做法是造一份改過 `score` 的快取，`simulate()` 完全照原樣跑——
   階梯、65 門檻、續抱、10% 停損全不動，**沒有任何新的規則邏輯**
   （「不要有第二份實作」那條通則；10/14 與 10/16 兩次都靠它免除對帳）。

成長分數 = 產業內 YoY 百分位 × 100（0~100，與其他分項同尺度）。
無排名的 (股,日) 給 **50**——`scorer.py` 對「無資料」的既有慣例。
⚠️ 那個慣例本身被 9/17 批評過（「資料缺失」與「資料中性」同分，外部無法區分），
   但本測試所有組的進場都用 `entry_filter=has_rev` 限制在「有營收資料」的
   子集內，與 10/14 的 A1 同一個母體 ⇒ 那個 50 只影響續抱，影響很小。

★ 事前預期（先寫下再跑，照策略F／D／停損那三次的慣例）
───────────────────────────────────────────────────────────────────
主預期：**第四個分項會弱於篩選門檻，甚至測不出效果。** 三個理由：

  ① 10/07 量到**動能交互作用**——動能最弱那組 YoY 幾乎沒用
     （+0.61%、t=+1.42 不顯著）。而「第四個分項」正好會讓
     「技術面弱但 YoY 高」的股票靠成長分補進來，**那正是 YoY 無效的那一組**。
  ② 篩選門檻是 AND，保證「技術強 **且** 成長好」；加權和允許抵銷。
  ③ 10/14 的機制發現（B2＞B3 因為候選不足、槽位填不滿）顯示 5 檔配置
     對候選數量敏感。

反方向的可能（我認為機率較低）：第四個分項**不減少候選**（只重排），
所以不會有填不滿的問題，這一點對它有利；若 YoY 的資訊主要是「排序」
而不是「排除」，它可能反而更好。

★ 必備的對照（缺一個就會誤判，9/17 與 10/14 立的標準前置動作）
───────────────────────────────────────────────────────────────────
  ★GC  反向對照：成長分數改用 (1-百分位)×100 ⇒ 若是雜訊，正反會差不多
  ★ 雜訊帶：從基準組重抽，全距沒超過帶寬就不解讀
  ★ 對帳點：B2 vs A1 必須重現 10/14 的 7,719 筆 / +0.64%

★ 限制（引用任何數字時必須一起講）
───────────────────────────────────────────────────────────────────
  1. 除權息無法調整（陷阱50）⇒ 絕對 alpha 系統性低估
  2. 基本面 25% 在 2026-05 之前恆為 50（陷阱44，永久）
     ⇒ 稀釋前的「舊總分」在樣本前後段不是同一個東西
  3. 未調整收盤價（陷阱49）⇒ 分割日有假停損
  4. 上櫃不在宇宙內；KY 股沒有月營收
  5. 配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」
  6. 2016~2017 已裁掉（陷阱51 限制第 5 條）
"""
import gc as _gc
import math, os, pickle, random, sys
from bisect import bisect_right

import backtest_portfolio_slots as P
from backtest_revenue_filter import CACHE, START, make_rev_lookup, noise_band, sign_test

SLOTS      = 5
SEED_BASE  = 7000
N_SEEDS    = 100
NEUTRAL    = 50.0      # 無營收排名時的成長分數（scorer.py 的既有慣例）


def growth_cache(cache, w, rank_of_fn, invert=False):
    """
    回傳一份**只改 score** 的淺層快取：
        新分 = (1-w)×舊分 + w×成長分數
    其餘欄位共用原物件（prices/idx/vol 都是唯讀，不複製省記憶體）。
    """
    out = dict(cache)
    stocks = {}
    for code, st_ in cache['stocks'].items():
        old = st_['score']
        new = {}
        for d, sc in old.items():
            r = rank_of_fn(code, d)
            g = NEUTRAL if r is None else ((1.0 - r) if invert else r) * 100.0
            new[d] = (1.0 - w) * sc + w * g
        s2 = dict(st_)
        s2['score'] = new
        stocks[code] = s2
    out['stocks'] = stocks
    return out


def main():
    global SEED_BASE, N_SEEDS           # ⚠️ 不寫這行，CLI 參數會靜默無效（10/16 的教訓）
    args = sys.argv[1:]
    for a in args:
        if a.startswith('seedbase='):
            SEED_BASE = int(a.split('=')[1])
        elif a.startswith('seeds='):
            N_SEEDS = int(a.split('=')[1])
    pos = [a for a in args if '=' not in a]

    if not os.path.exists(CACHE):
        print(f'❌ 找不到 {CACHE}，先跑：python3 -u backtest_revenue_filter.py cache')
        return
    with open(CACHE, 'rb') as f:
        cache = pickle.load(f)
    n0 = len(cache['tpx_dates'])
    cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
    print(f'（已裁掉 {START} 之前的 {n0 - len(cache["tpx_dates"])} 天——陷阱51 限制第5條）')

    tpx       = cache['tpx_close']
    rev_rank  = cache['rev_rank']
    latest_ym = make_rev_lookup(cache)
    ds        = cache['tpx_dates']

    def has_rev(code, d):
        ym = latest_ym(d)
        return ym is not None and ym in rev_rank.get(code, {})

    def rank_of(code, d):
        ym = latest_ym(d)
        return rev_rank.get(code, {}).get(ym) if ym else None

    print('=' * 92)
    print('月營收 YoY：當「第四個分項」 vs 當「篩選門檻」')
    print('=' * 92)
    print(f'宇宙 {len(cache["stocks"])} 檔　{ds[0]} ~ {ds[-1]}（{len(ds)} 個交易日）'
          f'　有排名 {len(rev_rank)} 檔')
    print(f'成長分數 = 產業內 YoY 百分位 ×100；無排名給 {NEUTRAL:.0f}（scorer.py 慣例）\n')

    # ── 六組規則 ────────────────────────────────────────────────
    # (label, 用哪份快取, score_filter, entry_filter)
    #   score_filter=None ⇒ 走現行大盤階梯（含 <45 停止進場），完全不動
    base_only = lambda c, d: has_rev(c, d)
    b2_filter = lambda c, d: has_rev(c, d) and (rank_of(c, d) or 0) >= 0.5

    full = 'full' in pos
    # spec：(label, w, invert, entry_filter)。w=None ⇒ 用原快取（不改分數）
    # ⚠️ **刻意不預先建好全部 growth 快取**——9 份 × 512檔 × 2000日 的 dict
    #    會把 3.9GB 記憶體吃光、程序被 OOM 無聲殺掉（看起來像「跑很久」）。
    #    改成用到才建、用完 del。
    SPECS = [
        ('A1 基準：現行策略（限有營收資料）',   None, False, base_only),
        ('B2 篩選門檻：YoY 產業內 ≥ 中位',      None, False, b2_filter),
        ('★G25 第四個分項 w=25%（主規格）',     0.25, False, base_only),
        ('★GC25 反向：成長分數取 (1-百分位)',   0.25, True,  base_only),
    ]
    if full:      # 找峰值用（per-trade 單調上升時必須做——停損那次的教訓）
        SPECS += [('G15 第四個分項 w=15%',       0.15, False, base_only),
                  ('G35 第四個分項 w=35%',       0.35, False, base_only),
                  ('G50 第四個分項 w=50%',       0.50, False, base_only),
                  ('G75 第四個分項 w=75%',       0.75, False, base_only),
                  ('G100 成長取代全部 w=100%',   1.00, False, base_only)]

    def build(w, inv):
        return cache if w is None else growth_cache(cache, w, rank_of, invert=inv)

    didx = {d: i for i, d in enumerate(ds)}

    def hold_days(t):
        a, b = didx.get(t['entry_date']), didx.get(t['exit_date'])
        return (b - a) if (a is not None and b is not None and b > a) else None

    didx = {d: i for i, d in enumerate(ds)}

    def hold_days(t):
        a, b = didx.get(t['entry_date']), didx.get(t['exit_date'])
        return (b - a) if (a is not None and b is not None and b > a) else None

    def cand_stats(cc, ef):
        """單日候選數（10/14 的機制診斷：候選 <5 檔 ⇒ 槽位填不滿）"""
        cnt = []
        for d in ds:
            mn = cc['market_net'].get(d)
            thr = 65
            if mn is not None:
                ms = max(0, min(100, 50 - mn * 5))
                thr = 65 if ms >= 70 else (70 if ms >= 55 else (75 if ms >= 45 else None))
            if thr is None:
                continue
            cnt.append(sum(1 for code, st_ in cc['stocks'].items()
                           if (st_['score'].get(d) or -1) >= thr and ef(code, d)))
        srt = sorted(cnt)
        return (len(cnt), srt[len(srt) // 2],
                sum(1 for v in cnt if v >= SLOTS) / len(cnt) * 100) if cnt else (0, 0, 0)

    print('【① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）')
    print('  🚨 `alpha` 這一欄**不可跨組直接比**——各組持有長度不同，見「均持有」')
    print(f'  {"規則":<34}{"筆數":>8}{"報酬":>9}{"同期大盤":>10}'
          f'{"alpha":>9}{"扣成本":>8}{"停損":>6}{"勝率":>6}'
          f'{"均持有":>7}{"★a/日":>9}{"候選中位":>8}{"≥5檔":>7}')
    print('  ' + '-' * 126)
    rows, alphas = {}, {}
    for label, w, inv, ef in SPECS:
        cc = build(w, inv)
        _, tr = P.simulate(cc, lambda c, d, s: (c,), None, label, entry_filter=ef)
        st_ = P.stat(tr, tpx)
        nd, cmed, c5 = cand_stats(cc, ef)
        if w is not None:
            del cc
        if not st_:
            print(f'  {label:<34}（無交易）'); continue
        hd = [h for h in (hold_days(t) for t in tr) if h]
        mh = sum(hd) / len(hd) if hd else 0
        rows[label] = (st_, tr, mh, cmed, c5)
        alphas[label] = st_['alpha']
        print(f'  {label:<34}{st_["n"]:>8,}{st_["ret"]:>+8.2f}%{st_["mkt"]:>+9.2f}%'
              f'{st_["alpha"]:>+8.2f}%{st_["alpha"] - 0.47:>+7.2f}%'
              f'{st_["stop"]:>5.1f}%{st_["win"]:>5.1f}%{mh:>7.1f}'
              f'{st_["alpha"] / mh if mh else 0:>+8.4f}%{cmed:>8}{c5:>6.1f}%')

    base_tr = rows[SPECS[0][0]][1]
    nmin = min(s['n'] for s, *_ in rows.values())
    nb = noise_band(base_tr, tpx, nmin)
    if nb:
        lo, mid, hi, bw = nb
        rng = max(alphas.values()) - min(alphas.values())
        print(f'\n  雜訊帶（從 A1 重抽 n={nmin:,}）：{lo:+.2f}% ~ {hi:+.2f}%（帶寬 {bw:.2f}pp）')
        print(f'  各組 alpha 全距：{rng:.2f}pp　⇒ '
              f'{"★ 超出雜訊帶 ⇒ 可以解讀" if rng > bw else "⚪ 在雜訊帶內 ⇒ **不可解讀**"}')

    b2 = rows.get(SPECS[1][0], (None,))[0]
    if b2:
        ok = (b2['n'] == 7719) and abs(b2['alpha'] - 0.64) < 0.015
        print(f'\n  ★ 對帳點（10/14 的 B2 = 7,719 筆 / alpha +0.64%）：'
              f'{b2["n"]:,} 筆 / {b2["alpha"]:+.2f}%　'
              f'{"✅ 位元級一致" if ok else "🚨 不一致——先查這個"}')

    print('\n【逐年 alpha（★=空頭年）')
    labs = list(rows)
    print('  年'.ljust(10) + ''.join(f'{l.split(chr(32))[0]:>10}' for l in labs))
    print('  ' + '-' * (8 + 10 * len(labs)))
    bear = {'2018', '2020', '2022'}
    agg = {l: [[], []] for l in labs}
    for y in [str(v) for v in range(2018, 2027)]:
        row = f'  {y}{"★" if y in bear else " "}'.ljust(10)
        for l in labs:
            sub = [t for t in rows[l][1] if t['entry_date'][:4] == y]
            st2 = P.stat(sub, tpx)
            if st2:
                row += f'{st2["alpha"]:>+9.2f}%'
                agg[l][0 if y in bear else 1].extend(sub)
            else:
                row += f'{"—":>10}'
        print(row)
    for i, nm in enumerate(['★三空頭年', '其他六年']):
        row = f'  {nm}'.ljust(10)
        for l in labs:
            st2 = P.stat(agg[l][i], tpx)
            row += f'{st2["alpha"]:>+9.2f}%' if st2 else f'{"—":>10}'
        print(row)

    if 'pertrade' in pos:
        return

    # ── ② 5 檔配置・配對比較 ──────────────────────────────────
    # 🚨 必須在這裡釋放——per-trade 段留著 9 組交易，再疊一份 growth 快取就會
    #    把記憶體吃光、程序被 OOM **無聲**殺掉（看起來像「跑很久」）
    rows.clear()
    base_tr = None
    _gc.collect()

    ix = {l.split(' ')[0].lstrip('★'): i for i, (l, *_) in enumerate(SPECS)}
    want = [('★★ 第四個分項(w25) vs 篩選門檻(B2)', 'G25', 'B2'),
            ('第四個分項(w25) vs A1 基準',            'G25', 'A1'),
            ('篩選門檻(B2) vs A1 基準（對帳 10/14）', 'B2', 'A1'),
            ('★ 反向(GC25) vs A1 基準',              'GC25', 'A1'),
            ('★ 反向(GC25) vs 第四個分項(G25)',      'GC25', 'G25'),
            ('w50 vs w25',                           'G50', 'G25'),
            ('w75 vs w25',                           'G75', 'G25'),
            ('★★ w75 vs 篩選門檻(B2)',               'G75', 'B2')]
    PAIRS = [(l, ix[a], ix[b]) for l, a, b in want if a in ix and b in ix]

    print(f'\n【② 5 檔配置・配對比較（{N_SEEDS} 條，seed {SEED_BASE}~{SEED_BASE+N_SEEDS-1}）')
    runs = {}
    for i, (label, w, inv, ef) in enumerate(SPECS):
        cc = build(w, inv)
        vals = []
        for sd in range(N_SEEDS):
            rnd = random.Random(SEED_BASE + sd)
            pref = {c: rnd.random() for c in sorted(cc['stocks'])}   # ⚠️ sorted（10/16 的 bug）
            _, tr = P.simulate(cc, lambda c, d, s: (pref[c],), SLOTS, label, entry_filter=ef)
            st_ = P.stat(tr, tpx)
            vals.append(st_['alpha'] if st_ else 0.0)
        if w is not None:
            del cc
        runs[i] = vals
        srt = sorted(vals)
        print(f'  {label:<34}中位 alpha {srt[len(srt)//2]:+.2f}%'
              f'　相異值 {len({round(x,6) for x in vals})}/{N_SEEDS}')

    print(f'\n  {"配對":<36}{"Δ中位":>9}{"勝場":>10}{"p":>8}  判定')
    print('  ' + '-' * 76)
    for label, ia, ib in PAIRS:
        d = [runs[ia][s] - runs[ib][s] for s in range(N_SEEDS)]
        w_, n_, ties, p = sign_test(d)
        srt = sorted(d)
        med = srt[len(srt) // 2]
        v = '❌' if (p < .05 and med < 0) else ('✅' if (p < .05 and med > 0) else '⚪')
        print(f'  {label:<36}{med:>+8.2f}pp{w_:>7}/{n_:<3}{p:>8.3f}  {v}'
              + (f'　平手 {ties}' if ties else ''))


if __name__ == '__main__':
    main()
