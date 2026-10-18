"""一條規則一個程序：跑 100 條 5 檔配對，結果存 pickle。
沙盒的背景程序約 10 分鐘就會被砍，9 條規則一起跑必然跑不完。"""
import pickle, random, sys
import backtest_portfolio_slots as P
import backtest_revenue_component as C
from backtest_revenue_filter import CACHE, START, make_rev_lookup

NAME = sys.argv[1]
W    = None if sys.argv[2] == 'none' else float(sys.argv[2])
INV  = sys.argv[3] == 'inv'
EF   = sys.argv[4]          # base | b2
SB, NS = int(sys.argv[5]), int(sys.argv[6])

with open(CACHE, 'rb') as f:
    cache = pickle.load(f)
cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
tpx, rev_rank = cache['tpx_close'], cache['rev_rank']
latest_ym = make_rev_lookup(cache)

def rank_of(code, d):
    ym = latest_ym(d)
    return rev_rank.get(code, {}).get(ym) if ym else None

def has_rev(code, d):
    ym = latest_ym(d)
    return ym is not None and ym in rev_rank.get(code, {})

ef = has_rev if EF == 'base' else (lambda c, d: has_rev(c, d) and (rank_of(c, d) or 0) >= 0.5)
cc = cache if W is None else C.growth_cache(cache, W, rank_of, invert=INV)

vals = []
for sd in range(NS):
    rnd = random.Random(SB + sd)
    pref = {c: rnd.random() for c in sorted(cc['stocks'])}     # ⚠️ sorted（10/16 的 bug）
    _, tr = P.simulate(cc, lambda c, d, s: (pref[c],), 5, NAME, entry_filter=ef)
    st = P.stat(tr, tpx)
    vals.append(st['alpha'] if st else 0.0)

with open(f'/tmp/pair_{NAME}_{SB}.pkl', 'wb') as f:
    pickle.dump(vals, f)
srt = sorted(vals)
print(f'{NAME}　中位 alpha {srt[len(srt)//2]:+.2f}%　相異值 {len(set(vals))}/{NS}')
