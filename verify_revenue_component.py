"""
★ 用途：重驗 2026-10-18 那個結論（月營收 YoY「當第四個分項」vs「當篩選門檻」）
═══════════════════════════════════════════════════════════════════
10/16 立的規矩：**要寫進 CLAUDE.md 當結論的配對檢定，至少在兩份獨立快取上跑過。**
那條規矩當初就是靠跨快取比對抓到 `sorted()` bug 的——六個配對有兩個不一致，
立刻知道「同一組運氣」的前提沒成立。

本腳本不做任何新測試，只把 `backtest_revenue_component.py` 的
**5 檔配對那一段**抽出來，讓它能跑在**任意一份快取**上。

★ 為什麼需要這支（而不是直接跑 backtest_revenue_component.py）
───────────────────────────────────────────────────────────────────
`_pf_slots_cache_market.pkl`（`backtest_portfolio_slots.build_cache()` 建的）
**沒有 `rev_rank`**——那支 builder 完全不碰月營收。
但排名**只是一次 SQL 查詢**（`build_revenue_ranks()`），貴的是逐日評分那部分。
⇒ 把排名掛到既有快取上即可，**不必花 20~40 分鐘重建**。

用法：
    python3 -u verify_revenue_component.py                              # 用 rev_filter 快取
    python3 -u verify_revenue_component.py cache=/tmp/_pf_slots_cache_market.pkl
    python3 -u verify_revenue_component.py seedbase=8000 seeds=100
    python3 -u verify_revenue_component.py selftest                     # 見下

★ selftest 模式（驗證「掛排名」這段程式本身）
───────────────────────────────────────────────────────────────────
把一份**已有** rev_rank 的快取，刻意拿掉 rev_rank、再用 DB 掛回去，
兩邊結果**必須完全相同**。這是在驗「掛回去的排名與原本那份一致」，
而不是只驗「程式不會報錯」。
（照 10/07 那條「成對造情境」：只驗一個方向會以為通過，其實可能兩邊都錯。）
"""
import os, pickle, random, sys

import backtest_portfolio_slots as P
import backtest_revenue_component as C
from backtest_revenue_filter import CACHE, START, make_rev_lookup, sign_test

SLOTS = 5
RULES = [('A1   基準：現行策略（限有營收資料）', None, False, 'base'),
         ('B2   篩選門檻：YoY 產業內 ≥ 中位',    None, False, 'b2'),
         ('★G25 第四個分項 w=25%',               0.25, False, 'base'),
         ('★GC25 反向：成長取 (1-百分位)',       0.25, True,  'base')]
PAIRS = [('★★ 第四個分項(w25) vs 篩選門檻(B2)', 2, 1),
         ('第四個分項(w25) vs A1 基準',          2, 0),
         ('篩選門檻(B2) vs A1 基準',             1, 0),
         ('★ 反向(GC25) vs A1 基準',             3, 0),
         ('★ 反向(GC25) vs 第四個分項(w25)',     3, 2)]


def attach_ranks(cache):
    """快取缺 rev_rank 時，從 DB 補上（只是一次 SQL，不重算評分）"""
    if cache.get('rev_rank'):
        return cache, False
    from database import get_conn
    from backtest_revenue_filter import build_revenue_ranks
    conn = get_conn()
    try:
        avail, rank, raw = build_revenue_ranks(conn, sorted(cache['stocks']))
    finally:
        conn.close()
    cache['avail'], cache['rev_rank'], cache['rev_yoy'] = avail, rank, raw
    print(f'  ⚠️ 快取沒有 rev_rank ⇒ 已從 DB 掛上：{len(avail)} 個營收月'
          f'　{avail[0][1]} ~ {avail[-1][1]}　有排名 {len(rank)} 檔')
    return cache, True


def run(cache, seedbase, nseeds, quiet=False):
    tpx, rev_rank = cache['tpx_close'], cache['rev_rank']
    latest_ym = make_rev_lookup(cache)

    def rank_of(c, d):
        ym = latest_ym(d)
        return rev_rank.get(c, {}).get(ym) if ym else None

    def has_rev(c, d):
        ym = latest_ym(d)
        return ym is not None and ym in rev_rank.get(c, {})

    efs = {'base': has_rev,
           'b2': lambda c, d: has_rev(c, d) and (rank_of(c, d) or 0) >= 0.5}

    runs = {}
    for i, (label, w, inv, efk) in enumerate(RULES):
        cc = cache if w is None else C.growth_cache(cache, w, rank_of, invert=inv)
        ef = efs[efk]
        vals = []
        for sd in range(nseeds):
            rnd = random.Random(seedbase + sd)
            pref = {c: rnd.random() for c in sorted(cc['stocks'])}  # ⚠️ sorted（10/16 的 bug）
            _, tr = P.simulate(cc, lambda c, d, s: (pref[c],), SLOTS, label, entry_filter=ef)
            st = P.stat(tr, tpx)
            vals.append(st['alpha'] if st else 0.0)
        if w is not None:
            del cc
        runs[i] = vals
        if not quiet:
            srt = sorted(vals)
            print(f'  {label:<36}中位 alpha {srt[len(srt)//2]:+.2f}%'
                  f'　相異值 {len({round(x,6) for x in vals})}/{nseeds}')
    return runs


def report(runs, nseeds):
    print(f'\n  {"配對":<38}{"Δ中位":>9}{"勝場":>10}{"p":>8}  判定')
    print('  ' + '-' * 78)
    out = []
    for label, ia, ib in PAIRS:
        d = [runs[ia][s] - runs[ib][s] for s in range(nseeds)]
        w, n, ties, p = sign_test(d)
        med = sorted(d)[len(d) // 2]
        v = '❌' if (p < .05 and med < 0) else ('✅' if (p < .05 and med > 0) else '⚪')
        print(f'  {label:<38}{med:>+8.2f}pp{w:>7}/{n:<3}{p:>8.3f}  {v}'
              + (f'　平手 {ties}' if ties else ''))
        out.append((w, n))
    return out


def load(path):
    if not os.path.exists(path):
        print(f'🚨 找不到快取 {path}')
        print('   建快取：python3 -u backtest_revenue_filter.py cache')
        print('   或指定既有的：cache=/tmp/_pf_slots_cache_market.pkl')
        sys.exit(1)
    with open(path, 'rb') as f:
        cache = pickle.load(f)
    n0 = len(cache['tpx_dates'])
    cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
    ds = cache['tpx_dates']
    print(f'快取 {path}')
    print(f'  宇宙 {len(cache["stocks"])} 檔　{ds[0]} ~ {ds[-1]}（{len(ds)} 日'
          f'，已裁掉 {START} 之前的 {n0 - len(ds)} 天）')
    # ★ 阻斷式涵蓋檢查（陷阱51 那條通則：入口就要檢查涵蓋期間，不只檢查檔案存在）
    years = {d[:4] for d in ds}
    miss = [y for y in ('2018', '2020', '2022') if y not in years]
    if miss:
        print(f'🚨 快取沒有涵蓋空頭年 {miss} ⇒ 中止（這個結論需要空頭樣本）')
        sys.exit(1)
    print(f'  ✅ 三個空頭年都在')
    return cache


def main():
    args = sys.argv[1:]
    path = next((a.split('=', 1)[1] for a in args if a.startswith('cache=')), CACHE)
    seedbase = next((int(a.split('=')[1]) for a in args if a.startswith('seedbase=')), 7000)
    nseeds = next((int(a.split('=')[1]) for a in args if a.startswith('seeds=')), 100)

    if 'selftest' in args:
        # 刻意拿掉 rev_rank 再掛回去，兩邊必須完全相同
        n = 5
        cache = load(path)
        if not cache.get('rev_rank'):
            print('🚨 selftest 需要一份本來就有 rev_rank 的快取'); sys.exit(1)
        print(f'\n【selftest】{n} 條，原始快取 vs「拿掉 rev_rank 再從 DB 掛回」')
        a = run(cache, seedbase, n, quiet=True)
        stripped = dict(cache)
        for k in ('rev_rank', 'rev_yoy', 'avail'):
            stripped.pop(k, None)
        stripped, did = attach_ranks(stripped)
        b = run(stripped, seedbase, n, quiet=True)
        same = all(abs(a[i][s] - b[i][s]) < 1e-9 for i in a for s in range(n))
        print(f'  掛排名的程式有被執行到：{"✅" if did else "🚨 沒有（測試無效）"}')
        print(f'  兩邊逐條逐規則完全相同：{"✅ 通過" if same else "🚨 不同 ⇒ 掛排名有 bug"}')
        return

    print('=' * 88)
    print('重驗：月營收 YoY「當第四個分項」vs「當篩選門檻」（2026-10-18 的結論）')
    print('=' * 88)
    cache = load(path)
    cache, _ = attach_ranks(cache)
    print(f'\n【5 檔配置・{nseeds} 條配對（seed {seedbase}~{seedbase + nseeds - 1}）')
    runs = run(cache, seedbase, nseeds)
    report(runs, nseeds)
    print('\n★ 10/18 在 _rev_filter_cache ＋ seed 7000 上的結果（對照用）：')
    print('    第四個分項 vs 篩選門檻  +0.37pp  78/100  p=0.000  ✅')
    print('    第四個分項 vs A1        +0.69pp  92/100  p=0.000  ✅')
    print('    反向 vs 第四個分項      -1.02pp   5/100  p=0.000  ❌')


if __name__ == '__main__':
    main()
