"""
★ 要驗證的問題（2026-10-18 那節「下一步」第 1 項）
═══════════════════════════════════════════════════════════════════
10/18 量到月營收當第四個分項時，per-trade alpha 隨權重 w 單調上升到 w=100%，
5 檔配對的中位 alpha 峰值在 w=50%（+3.31%）。**但那兩個數字都不能讀**，因為：

```
均持有天數   A1 14.3 日 → G50 26.6 → G100 42.0      （差 2.9 倍）
同期大盤     +0.97%     → +2.29%   → +4.00%          （差 4 倍）
```

**per-trade alpha 沒有除以持有長度** ⇒ 同一筆交易抱久一點，alpha 自然變大。
而 w 一拉高就是在拉長持有期（高成長股會一直續抱，因為續抱門檻也看總分）。

⇒ 換成**資金曲線**（10/05 立的框架）：總報酬與最大回檔**會正確吃到
持有長度與空手時間**，是對「改變持有期的規則」唯一公平的量尺。

★ 與 10/05 的差別：這次用配對，不是雜訊帶
───────────────────────────────────────────────────────────────────
10/05 跑多條隨機排序取 5~95% 分位，防的是「把一條曲線的運氣當訊號」。
本次更進一步：**同一個 seed 在所有規則之間用同一組隨機偏好**
⇒ 差額只來自規則本身（10/07 立的配對設計）。兩者都做：
  ① 各規則的中位 ＋ 5~95% 分位（看絕對水準與散佈）
  ② 配對符號檢定（看規則之間的差異是否穩定）

★ 資金模型（沿用 `backtest_vs_etf.py`，不另寫一份）
───────────────────────────────────────────────────────────────────
5 格等權、每日再平衡、空格是現金報酬 0、成本逐筆扣在進出場當天
（買 0.0855%／賣 0.3855%）。**刻意不跑「不限檔數」**——那沒有可定義的
資金模型（同一天可能持 1 檔也可能持 7 檔，每檔該押多少無從決定）。

用法（沙盒的背景程序約 10 分鐘會被砍 ⇒ 一條規則一個程序）：
    python3 -u backtest_revenue_component_curve.py rule=A1  seeds=20
    python3 -u backtest_revenue_component_curve.py rule=G50 seeds=20
    python3 -u backtest_revenue_component_curve.py bh            # 買進持有基準
    python3 -u backtest_revenue_component_curve.py combine
"""
import os, pickle, random, sys

import backtest_portfolio_slots as P
import backtest_revenue_component as C
import backtest_vs_etf as V
from backtest_revenue_filter import CACHE, START, make_rev_lookup, sign_test

SLOTS = 5
OUT   = '/tmp/curve_%s_%d.pkl'

# (w, invert, entry_filter)；w=None ⇒ 不改分數
SPECS = {
    'A1':   (None, False, 'base'),      # 基準：現行策略（限有營收資料）
    'B2':   (None, False, 'b2'),        # 篩選門檻：YoY 產業內 ≥ 中位
    'G25':  (0.25, False, 'base'),      # ★ 主規格
    'G35':  (0.35, False, 'base'),
    'G50':  (0.50, False, 'base'),      # ★ per-trade 的 5 檔峰值在這
    'G75':  (0.75, False, 'base'),
    'G100': (1.00, False, 'base'),
    'GC25': (0.25, True,  'base'),      # ★ 反向對照
    # ★★ 中性對照：成長分數換成「每檔一個固定隨機值」——同樣把持有期拉長，
    #    但**完全沒有資訊**。這是本次最關鍵的對照：w 拉高會自動拉長持有期
    #    （15→32→46 天），而樣本期指數 +354% ⇒ 「抱更久」本身就可能解釋一切。
    #    反向對照擋不住這點（GC25 均持有只有 15.9 天，幾乎沒拉長）。
    'R50a': (0.50, False, 'base'),
    'R50b': (0.50, False, 'base'),
    # ★★★ 把上面那個對照修好：固定隨機值**永遠不變** ⇒ 一進場就無限續抱
    #     （實測均持有 80 天 vs 真成長的 32 天）⇒ 它在「持有長度」這一維
    #     **過度矯正**，不是乾淨的對照。改成**每個營收月換一次**，
    #     讓換手頻率與真實 YoY 排名完全一致。
    'M50a': (0.50, False, 'base'),
    'M50b': (0.50, False, 'base'),
}
RAND_GROWTH  = {'R50a': 90000, 'R50b': 90001}     # 固定隨機（持有期過長）
MONTH_GROWTH = {'M50a': 91000, 'M50b': 91001}     # ★ 逐月重抽（頻率對齊）
ORDER = ['A1', 'B2', 'G25', 'G35', 'G50', 'G75', 'G100', 'GC25',
         'R50a', 'R50b', 'M50a', 'M50b']
PAIRS = [('★★ w50 vs w25', 'G50', 'G25'),
         ('★★ w25 vs A1 基準', 'G25', 'A1'),
         ('w25 vs 篩選門檻 B2', 'G25', 'B2'),
         ('★ 反向 GC25 vs w25', 'GC25', 'G25'),
         ('w35 vs w25', 'G35', 'G25'),
         ('w75 vs w50', 'G75', 'G50'),
         ('w100 vs w50', 'G100', 'G50'),
         ('★★ w50 vs 隨機成長a（中性對照）', 'G50', 'R50a'),
         ('★★ w50 vs 隨機成長b', 'G50', 'R50b'),
         ('★ 隨機成長a vs A1（＝純粹「抱更久」的貢獻）', 'R50a', 'A1'),
         ('★★★ w50 vs 逐月隨機a（頻率對齊的對照）', 'G50', 'M50a'),
         ('★★★ w50 vs 逐月隨機b', 'G50', 'M50b'),
         ('★ 逐月隨機a vs A1', 'M50a', 'A1')]


def load():
    if not os.path.exists(CACHE):
        print(f'🚨 找不到快取 {CACHE}'); sys.exit(1)
    with open(CACHE, 'rb') as f:
        cache = pickle.load(f)
    cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
    cal = cache['tpx_dates']
    years = {d[:4] for d in cal}
    miss = [y for y in ('2018', '2020', '2022') if y not in years]
    if miss:                                  # 阻斷式（陷阱51 第四次的教訓）
        print(f'🚨 快取沒有涵蓋空頭年 {miss} ⇒ 中止'); sys.exit(1)
    print(f'快取 {CACHE}　{len(cache["stocks"])} 檔　{cal[0]} ~ {cal[-1]}'
          f'（{len(cal)} 日）　✅ 三個空頭年都在')
    return cache, cal


def main():
    args = sys.argv[1:]
    seedbase = next((int(a.split('=')[1]) for a in args if a.startswith('seedbase=')), 7000)
    nseeds = next((int(a.split('=')[1]) for a in args if a.startswith('seeds=')), 20)

    if 'combine' in args:
        res = {}
        for k in ORDER:
            fp = OUT % (k, seedbase)
            if os.path.exists(fp):
                res[k] = pickle.load(open(fp, 'rb'))
        if not res:
            print('🚨 沒有任何結果檔'); return
        print('=' * 94)
        print('月營收當第四個分項：資金曲線（5 檔等權，2018~2026）')
        print('=' * 94)
        print('🚨 per-trade alpha 對「改變持有長度」的規則天生不公平 ⇒ 本表才是公平的量尺\n')
        print(f'  {"規則":<8}{"總報酬中位":>12}{"5%分位":>11}{"95%分位":>11}'
              f'{"帶寬":>9}{"最大回檔":>10}{"在場內":>8}{"均持有":>8}{"筆數":>8}')
        print('  ' + '-' * 88)
        for k in ORDER:
            if k not in res:
                continue
            r = res[k]
            rets = sorted(x['ret'] for x in r)
            n = len(rets)
            lo, md, hi = rets[max(0, int(n * .05))], rets[n // 2], rets[min(n - 1, int(n * .95))]
            mdd = sorted(x['mdd'] for x in r)[n // 2]
            inv = sum(x['inv'] for x in r) / n
            hd = sum(x['hold'] for x in r) / n
            nt = sum(x['ntr'] for x in r) / n
            print(f'  {k:<8}{md:>+11.2f}%{lo:>+10.2f}%{hi:>+10.2f}%'
                  f'{hi - lo:>8.1f}pp{mdd:>+9.2f}%{inv:>7.1f}%{hd:>8.1f}{nt:>8.0f}')
        bh = OUT % ('BH', seedbase)
        if os.path.exists(bh):
            print()
            for nm, m in pickle.load(open(bh, 'rb')).items():
                print(f'  {nm:<22}總報酬 {m["ret"]:>+9.2f}%　最大回檔 {m["mdd"]:>+7.2f}%')
        print(f'\n  {"配對（看總報酬）":<24}{"Δ中位":>11}{"勝場":>10}{"p":>8}  判定')
        print('  ' + '-' * 66)
        for lab, a, b in PAIRS:
            if a not in res or b not in res:
                continue
            d = [res[a][s]['ret'] - res[b][s]['ret'] for s in range(min(len(res[a]), len(res[b])))]
            w, n, t, p = sign_test(d)
            med = sorted(d)[len(d) // 2]
            v = '❌' if (p < .05 and med < 0) else ('✅' if (p < .05 and med > 0) else '⚪')
            print(f'  {lab:<24}{med:>+10.2f}pp{w:>7}/{n:<3}{p:>8.3f}  {v}'
                  + (f'　平手{t}' if t else ''))
        print('\n  ★ 對照 10/18 的 per-trade 5 檔中位 alpha：'
              'A1 -0.05%／B2 +0.20%／G25 +0.68%／G50 +3.31%／G75 +2.80%／G100 +3.09%')
        return

    cache, cal = load()

    if 'bh' in args:
        out = {}
        for code, nm in [('0050', '買進持有 0050'), ('0056', '買進持有 0056'),
                         ('TAIEX', '加權指數（不可投資）')]:
            eq, _ = V.buyhold_curve(code, cal, pay_fee=(code != 'TAIEX'), days=2600)
            if eq:
                out[nm] = V._metrics(cal, eq)
        with open(OUT % ('BH', seedbase), 'wb') as f:
            pickle.dump(out, f)
        for nm, m in out.items():
            print(f'  {nm:<22}{m["ret"]:>+9.2f}%　回檔 {m["mdd"]:>+7.2f}%　{m["n_days"]} 日')
        return

    rule = next((a.split('=')[1] for a in args if a.startswith('rule=')), None)
    if rule not in SPECS:
        print(f'用法：rule=<{"|".join(ORDER)}> [seeds=20] [seedbase=7000]'); return

    rev_rank, latest_ym = cache['rev_rank'], make_rev_lookup(cache)

    def rank_of(c, d):
        ym = latest_ym(d)
        return rev_rank.get(c, {}).get(ym) if ym else None

    def has_rev(c, d):
        ym = latest_ym(d)
        return ym is not None and ym in rev_rank.get(c, {})

    efs = {'base': has_rev,
           'b2': lambda c, d: has_rev(c, d) and (rank_of(c, d) or 0) >= 0.5}
    w, inv_, efk = SPECS[rule]
    if rule in MONTH_GROWTH:
        # 每 (檔, 營收月) 一個隨機值 ⇒ 換手頻率與真實 YoY 排名一致
        _rg = random.Random(MONTH_GROWTH[rule])
        _fm = {}

        def _mfake(c, d, _rg=_rg, _fm=_fm):
            ym = latest_ym(d)
            if ym is None:
                return None
            k = (c, ym)
            if k not in _fm:
                _fm[k] = _rg.random()
            return _fm[k]
        cc = C.growth_cache(cache, w, _mfake, invert=False)
    elif rule in RAND_GROWTH:
        # 每檔一個固定隨機「成長分數」，與 pref 用不同的 RNG 流（避免相關）
        _rg = random.Random(RAND_GROWTH[rule])
        _fake = {c: _rg.random() for c in sorted(cache['stocks'])}
        cc = C.growth_cache(cache, w, lambda c, d: _fake[c], invert=False)
    elif w is None:
        cc = cache
    else:
        cc = C.growth_cache(cache, w, rank_of, invert=inv_)
    ef = efs[efk]
    didx = {d: i for i, d in enumerate(cal)}

    rows = []
    for sd in range(nseeds):
        rnd = random.Random(seedbase + sd)
        pref = {c: rnd.random() for c in sorted(cc['stocks'])}   # ⚠️ sorted（10/16 的 bug）
        _, tr = P.simulate(cc, lambda c, d, s: (pref[c], c), SLOTS, rule, entry_filter=ef)
        eq, invd = V.strategy_curve(cc, tr, SLOTS, cal)
        m = V._metrics(cal, eq, invd)
        hd = [didx[t['exit_date']] - didx[t['entry_date']] for t in tr
              if t['entry_date'] in didx and t['exit_date'] in didx]
        m['hold'] = sum(hd) / len(hd) if hd else 0
        m['ntr'] = len(tr)
        rows.append(m)
        print(f'  seed {seedbase+sd}　報酬 {m["ret"]:>+9.2f}%　回檔 {m["mdd"]:>+7.2f}%'
              f'　在場內 {m["inv"]:.0f}%　均持有 {m["hold"]:.1f}　{len(tr)} 筆', flush=True)
    with open(OUT % (rule, seedbase), 'wb') as f:
        pickle.dump(rows, f)
    srt = sorted(x['ret'] for x in rows)
    print(f'★ {rule}　總報酬中位 {srt[len(srt)//2]:+.2f}%　'
          f'（{srt[0]:+.2f}% ~ {srt[-1]:+.2f}%）　相異值 {len(set(srt))}/{nseeds}')


if __name__ == '__main__':
    main()
