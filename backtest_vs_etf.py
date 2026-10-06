"""
策略 vs 買進持有 ETF —— 資金曲線對照（2026-10-05 進版控）

═══ 背景 / 要驗證的問題 ═══
使用者：「這幾個月選股一直不順，指數漲卻選不到合適股，是不是直接買 ETF 效果好？」

這個問題**之前從來沒有被真正測過**。既有回測全部是 **per-trade alpha**
（「持有那 10 天 vs 同期指數」），而那個指標**看不到最關鍵的一塊——空手時間**。

在一個六個月漲 50% 的市場裡，沒進場的日子是巨大的機會成本，
但 per-trade alpha 完全不計入：它只比較「有進場的那幾天」。
所以「策略 vs 買進持有」必須用**資金曲線**比，不能用平均每筆報酬比。

═══ 這支腳本與既有回測的分工 ═══
| | 既有 (`backtest_portfolio_slots.py`) | 本支 |
|---|---|---|
| 指標 | 每筆交易的 alpha | **整段資金曲線** |
| 看得到空手成本 | ❌ | ✅ |
| 看得到最大回檔 | ❌ | ✅ |
| 交易成本 | 事後手算扣 0.47% | ✅ 逐筆計入曲線 |

═══ 資金模型（必須講清楚，否則數字沒有意義）═══
**N 格等權 + 現金不計息。**
  • 資本切成 N 格，每格 1/N
  • 進場佔用一格，權重 1/N（以**當時**總資產計，即每日再平衡的標準模型）
  • 空著的格子是現金，報酬 0
  • 成本逐筆扣在進出場當天：買 0.0855%、賣 0.3855%（含證交稅）→ 來回 0.471%

**⚠️ 為什麼只跑「限制檔數」的版本：**
`backtest_portfolio_slots.py` 的「不限檔數」基準組（A）**沒有可定義的資金模型**——
同一天可能持 1 檔也可能持 7 檔，每檔該押多少資本無從決定。
per-trade alpha 可以不管這件事，**資金曲線不行**。
所以本支只跑 5 檔／10 檔，並明確標示這是刻意的限制，不是漏掉。

═══ 對照組 ═══
  • 買進持有 0050（主要對照，可投資）
  • 買進持有 0056（近期表現最好的那檔，提醒「選 ETF 同樣是在選」）
  • 買進持有 TAIEX（參考線，**不可投資**，沒有費用也買不到）
  買進持有同樣扣一次買入成本 0.0855%（期末不賣，不扣賣出成本）

═══ 已知限制（讀結論前必須一起看）═══
1. **樣本期間 2024-07~2026-10 指數大漲**（TAIEX 近 6 個月 +49.6%）。
   在這種環境下，任何「有時空手」的策略輸給買進持有幾乎是結構性的，
   **不代表換到橫盤或空頭也會輸**。這是本比較最大的偏誤方向。
2. 基本面 25% 在 2026-05 之前是預設值 50（陷阱44，永久）。
3. 0050 在 2025-06-11~06-17 缺 5 天（全市場價格回填前的舊缺口），
   那一段用「跨過缺口接續」計算，不補假價格。
4. 不計股利。0050／0056 都有配息，**買進持有的真實報酬會比這裡算的更高**
   （0056 近一年殖利率約 7~8%，影響不小）——這一點對買進持有不利地低估。

═══ 使用方式 ═══
  python3 backtest_vs_etf.py market     # 全市場快取（推薦，無後見之明）
  python3 backtest_vs_etf.py            # 自選股快取（⚠️ 含倖存者偏誤，見十五章）

  需要先有快取：
  python3 backtest_portfolio_slots.py cache market
"""
import os
import pickle
import sys
import statistics as stt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_portfolio_slots as P
from config import FEE_RATE, FEE_DISCOUNT, TAX_RATE
from database import get_prices

C_BUY  = FEE_RATE * FEE_DISCOUNT                 # 0.0855%
C_SELL = FEE_RATE * FEE_DISCOUNT + TAX_RATE      # 0.3855%

# ⚠️ 用「日期區間」而不是「最後 N 天」，因為 2026-05 是一條關鍵分界線：
#    `fundamentals` 全部從 2026-05 才開始、`chips` 從 2025-07（且 2026-02 前很稀疏），
#    所以 **2026-05 之前的評分實質上只有技術面在作用**（十五章「一半以上的日子」那節）。
#    把前後段混在一起平均，等於把兩套不同的系統當成同一套在比。
SUB_PERIODS = [
    ('全期間（⚠️ 混了兩套系統）', None,         None),
    ('前段 2024-07~2026-04（只有技術面）', None, '2026-04-30'),
    ('★ 2026-05 起（三項齊全，＝現在的系統）', '2026-05-01', None),
    ('近6個月', '2026-04-06', None),
    ('近3個月', '2026-07-06', None),
]

RANDOM_SEEDS = 20      # 真隨機中性對照要跑幾條


# ── 指標 ─────────────────────────────────────────────────
def _metrics(dates, eq, invested=None):
    """eq 為資金曲線（起始 1.0），回傳總報酬／最大回檔／日波動／在場內比例。"""
    if len(eq) < 2:
        return None
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1]]
    return {
        'ret': (eq[-1] / eq[0] - 1) * 100,
        'mdd': mdd * 100,
        'vol': stt.pstdev(rets) * 100 if len(rets) > 1 else 0.0,
        'inv': (sum(invested) / len(invested) * 100) if invested else 100.0,
        'n_days': len(eq),
    }


# ── 策略資金曲線 ─────────────────────────────────────────
def strategy_curve(cache, trades, slots, cal):
    """
    把 trades 轉成每日組合報酬，再累乘成資金曲線。

    ⚠️ 進出場的時點語意（與 `simulate()` 一致，弄錯會整條曲線偏移）：
      • `entry_price` 是**進場日收盤**（`simulate()` 取 `prices[i+1]['close']`），
        所以部位是「在 entry_date 收盤成立」→ **第一個有報酬的日子是下一個交易日**
      • `exit_price` 在到期出場時是當日收盤，**停損時是停損價（盤中）**
        → 最後一天的報酬要用 `exit_price / 前一日收盤`，不能用收盤價
    """
    stocks = cache['stocks']
    w = 1.0 / slots
    daily = {d: 0.0 for d in cal}      # 當日組合報酬貢獻
    held_cnt = {d: 0 for d in cal}

    for t in trades:
        st_ = stocks.get(t['code'])
        if not st_:
            continue
        idx, pr = st_['idx'], st_['prices']
        i0, i1 = idx.get(t['entry_date']), idx.get(t['exit_date'])
        if i0 is None or i1 is None or i1 <= i0:
            continue
        # 成本：進場日扣買、出場日扣賣（都以 1/N 權重計）
        if t['entry_date'] in daily:
            daily[t['entry_date']] -= w * C_BUY
        if t['exit_date'] in daily:
            daily[t['exit_date']] -= w * C_SELL
        for k in range(i0 + 1, i1 + 1):
            d = pr[k]['date']
            if d not in daily:
                continue
            prev = pr[k - 1]['close']
            if not prev:
                continue
            px = t['exit_price'] if k == i1 else pr[k]['close']
            daily[d] += w * (px / prev - 1)
            held_cnt[d] += 1

    # ⚠️ 迴圈必須含 cal[0]。第一版寫成 `for d in cal[1:]`，
    #    若有部位剛好在第一個日曆日進場，那筆的買入成本會被整個丟掉
    #    （單元測試用「第0天進場」抓到，實務上罕見但沒理由留著）。
    eq, inv = [1.0], []
    for d in cal:
        eq.append(eq[-1] * (1 + daily[d]))
        inv.append(min(held_cnt[d], slots) / slots)
    return eq, inv


# ── 買進持有曲線 ─────────────────────────────────────────
SPLIT_FACTORS = [1/10, 1/5, 1/4, 1/3, 1/2, 2, 3, 4, 5, 10]
SPLIT_LO, SPLIT_HI = 0.65, 1.5      # 台股 ±10%，跨一個缺口日也到不了這個幅度


def _corporate_actions(seq):
    """
    偵測分割／減資／大額配股造成的價格跳動，回傳 {index: 調整倍數}。

    ═══ 為什麼需要這個（2026-10-05 發現，差點讓整個比較無效）═══
    **DB 存的是未調整收盤價。** `0050` 在 2025-06 做了 1:4 分割
    （2025-06-10 收 188.65 → 2025-06-18 收 47.57，正好 ÷3.97），
    第一版直接把相鄰收盤相除，買進持有算出 **-35.85%**——完全是假的。

    做法：相鄰交易日比值落在 [0.65, 1.5] 之外就判定為公司行為，
    再找最接近的整數倍（1/4、1/3、1/2、2…）；
    **對得上就用那個倍數**（0050 → 1/4，還原後那天實際是 +0.84%，合理）；
    **對不上就把整段跳動全部當成公司行為**（該日報酬視為 0%）——
    那是保守選擇：寧可少算一天的真實漲跌，也不要留一個 -75% 的假崩盤。

    ⚠️ 不做自動回填 DB。那是另一件事（要處理除權息還原、影響所有既有回測），
       這裡只在「買進持有基準」這一個用途上就地修正，並把偵測到的事件印出來。
    """
    acts = {}
    for i in range(1, len(seq)):
        r = seq[i][1] / seq[i - 1][1]
        if SPLIT_LO <= r <= SPLIT_HI:
            continue
        best, err = None, 9e9
        for f in SPLIT_FACTORS:
            e = abs(r / f - 1)
            if e < err:
                best, err = f, e
        acts[i] = (best, r) if err <= 0.12 else (r, r)   # 對不上 → 整段當公司行為
    return acts


def buyhold_curve(code, cal, pay_fee=True, verbose=True):
    """
    買進持有的資金曲線，對齊 `cal` 的交易日，**已還原分割／減資**。

    ⚠️ 該檔若某些交易日沒有資料（0050 在 2025-06 缺 5 天，正好就是分割那幾天），
       **跨過缺口接續計算**，不補假價格、也不製造假跳空（陷阱26 的教訓）。
    """
    rows = get_prices(code, days=1200)
    px = {r['date']: r['close'] for r in rows if r['close']}
    seq = [(d, px[d]) for d in cal if d in px]
    if len(seq) < 2:
        return None, None

    acts = _corporate_actions(seq)
    if acts and verbose:
        for i, (f, r) in acts.items():
            _adj = (r / f - 1) * 100
            print(f'  ⚠️ {code} {seq[i][0]} 偵測到公司行為：'
                  f'{seq[i-1][1]} → {seq[i][1]}（倍數 {1/f:.2f}）'
                  f'　還原後當日 {_adj:+.2f}%')

    eq = [1.0 * (1 - (C_BUY if pay_fee else 0))]
    out = {seq[0][0]: eq[0]}
    for i in range(1, len(seq)):
        r = seq[i][1] / seq[i - 1][1]
        if i in acts:
            r = r / acts[i][0]          # 除掉分割倍數，只留真實漲跌
        eq.append(eq[-1] * r)
        out[seq[i][0]] = eq[-1]

    # ⚠️⚠️ 索引基準必須與 `strategy_curve()` 完全一致，否則切子區間會整體偏移一天。
    #
    # 2026-10-06 的實際事故：第一版這裡回傳 `len(cal)` 格（`full[i]` = cal[i] 收盤後的值），
    # 而 `strategy_curve()` 回傳 `len(cal)+1` 格（`eq[0]` = 期初、`eq[i+1]` = cal[i] 收盤後）。
    # `_slice()` 對兩者一視同仁 → 買進持有的子區間**兩端各偏移一天**。
    # 而 2026-05-04 指數剛好 +4.57%：
    #   • 「前段（到 2026-04-30）」多含了 5/04 → ETF 被**高估約 8pp**
    #   • 「2026-05 起」漏掉 5/04        → ETF 被**低估約 4.6pp**
    # 於是「策略贏 0050 七個百分點」裡有 4.6pp 純粹是這個 off-by-one。
    # 全期間剛好不受影響（i0=0、i1=len），所以人工核對 0050 時完全看不出來——
    # **只核對全期間不足以驗證切片邏輯。**
    #
    # 統一後的約定：curve[k] = 「cal[k-1] 收盤後」的淨值，curve[0] = 期初 1.0。
    # 買進持有是在 cal[0] 收盤買進，所以 cal[0] 當天沒有報酬，只付買入成本。
    full, last = [1.0], eq[0]
    for d in cal:
        last = out.get(d, last)
        full.append(last)
    return full, None


def _split_warn_trades(cache, trades, cal):
    """
    回報有幾筆交易「跨過」偵測到的公司行為日——那幾筆的報酬是假的。

    510 檔宇宙裡實測有 3 檔有分割（6669 緯穎 1:3、1808 潤隆、2540 愛山林），
    自選股 0 檔。因為策略有 10% 停損，跨到分割日時會在當天以「假停損」出場，
    所以單筆損失被限制在 -10%，不是 -66%——影響有界但仍是假的，必須揭露。
    """
    stocks = cache['stocks']
    bad = []
    for t in trades:
        st_ = stocks.get(t['code'])
        if not st_:
            continue
        pr, idx = st_['prices'], st_['idx']
        i0, i1 = idx.get(t['entry_date']), idx.get(t['exit_date'])
        if i0 is None or i1 is None:
            continue
        for k in range(i0 + 1, i1 + 1):
            p0, p1 = pr[k - 1]['close'], pr[k]['close']
            if p0 and not (SPLIT_LO <= p1 / p0 <= SPLIT_HI):
                bad.append((t['code'], pr[k]['date'], t['pnl']))
                break
    return bad


def main():
    mkt = 'market' in sys.argv[1:]
    path = P.CACHE_MARKET if mkt else P.CACHE
    if not os.path.exists(path):
        print(f'找不到快取 {path}')
        print('請先執行：python3 backtest_portfolio_slots.py cache' + (' market' if mkt else ''))
        return
    # pickle 來源是本機 `backtest_portfolio_slots.py cache` 自己寫出的檔案
    # （固定路徑 /tmp/_pf_slots_cache*.pkl），不是外部或網路取得的資料，
    # 與既有兩支腳本讀同一份快取的方式一致。
    with open(path, 'rb') as f:
        cache = pickle.load(f)
    cal = cache['tpx_dates']
    print(f'快取：{path}　{len(cache["stocks"])} 檔'
          f'（{"全市場上市普通股" if mkt else "⚠️ 自選股，含倖存者偏誤"}）')
    print(f'期間：{cal[0]} ~ {cal[-1]}　{len(cal)} 個交易日')
    print(f'成本：買 {C_BUY*100:.4f}%　賣 {C_SELL*100:.4f}%　來回 {(C_BUY+C_SELL)*100:.3f}%')

    by_code  = lambda c, d, s: (c,)
    by_score = lambda c, d, s: (-s[c]['score'][d], c)

    # ⚠️⚠️ 「依股票代號」**不是**中性對照——這是 2026-10-06 發現的方法論錯誤。
    #
    # 2026-09-24 在 per-trade 層級用「依代號」當中性組還勉強可以（只比平均報酬）。
    # 但在「5 檔槽位競爭」下它會**持續**把槽位給小代號的股票，
    # 而台股代號前段是水泥／食品／塑膠／紡織／鋼鐵（1xxx）、金融（28xx），
    # 後段才是電子（23xx~8xxx、3xxx、6xxx）。
    # 等於它偷偷變成一個「偏重傳產」的策略——在電子大漲的期間必然墊底。
    # **它與「評分排序」的差距，有多少來自評分、有多少來自產業偏誤，完全分不開。**
    #
    # 正解：**真隨機排序跑多條**（每條給每檔一個固定的隨機偏好，與「代號」同性質
    # 但沒有產業結構），取 5%／中位／95% 當雜訊帶——這才是 2026-09-17 立下的
    # 「比較多組之前先算雜訊帶」那條規矩在資金曲線上的版本。
    # **一條資金曲線只是一個樣本，不是 124 個獨立樣本。**
    def _rand_key(seed):
        import random as _rd
        _r = _rd.Random(seed)
        pref = {c: _r.random() for c in cache['stocks']}
        return lambda c, d, s: (pref[c], c)

    runs = []
    warn = []
    for label, key, slots in [
            ('策略・5檔（評分高→低）',  by_score, 5),
            ('策略・5檔（代號）⚠️有產業偏誤', by_code, 5),
            ('策略・10檔（評分高→低）', by_score, 10),
    ]:
        _, tr = P.simulate(cache, key, slots, label)
        eq, inv = strategy_curve(cache, tr, slots, cal)
        runs.append((label, cal, eq, inv, len(tr)))
        warn.append((label, _split_warn_trades(cache, tr, cal)))

    # ── 真隨機中性對照：跑 RANDOM_SEEDS 條，取分位當雜訊帶 ──
    print(f'\n跑 {RANDOM_SEEDS} 條真隨機排序（5檔）當雜訊帶…', end='', flush=True)
    rnd_eq = []
    for sd in range(RANDOM_SEEDS):
        _, tr = P.simulate(cache, _rand_key(sd), 5, f'rnd{sd}')
        eq, inv = strategy_curve(cache, tr, 5, cal)
        rnd_eq.append((eq, inv))
    print(' 完成')

    print()
    print('公司行為偵測（未調整收盤價造成的假跳動）：')
    for code, nm in [('0050', '買進持有 0050'), ('0056', '買進持有 0056'),
                     ('TAIEX', '加權指數（參考，不可投資）')]:
        eq, _ = buyhold_curve(code, cal, pay_fee=(code != 'TAIEX'))
        if eq:
            runs.append((nm, cal, eq, None, 0))
    for label, bad in warn:
        if bad:
            _s = '、'.join(f'{c}@{d}（該筆報酬 {p:+.1f}%，已失真）' for c, d, p in bad[:4])
            print(f'  ⚠️ {label}：{len(bad)} 筆交易跨過公司行為日 → {_s}')
    if not any(b for _, b in warn):
        print('  ✅ 策略的交易沒有跨過任何公司行為日')

    # ── 輸出 ──
    def _slice(eq, inv, d0, d1):
        """
        依日期切片。⚠️ eq 比 cal 多一格（eq[0] 是期初 1.0），切片要對齊。
        """
        i0 = 0 if not d0 else next((i for i, d in enumerate(cal) if d >= d0), len(cal))
        i1 = len(cal) if not d1 else next((i for i, d in enumerate(cal) if d > d1), len(cal))
        if i1 - i0 < 2:
            return None, None
        return eq[i0:i1 + 1], (inv[i0:i1] if inv else None)

    for pname, d0, d1 in SUB_PERIODS:
        _s, _ = _slice(runs[0][2], None, d0, d1)
        print()
        print('=' * 96)
        print(f'【{pname}】　{d0 or cal[0]} ~ {d1 or cal[-1]}'
              f'（{(len(_s)-1) if _s else 0} 個交易日）')
        print('=' * 96)
        print(f'{"":32}{"總報酬":>10}{"最大回檔":>10}{"日波動":>9}'
              f'{"報酬/回檔":>11}{"在場內":>9}{"筆數":>7}')
        print('-' * 96)
        for label, dates, eq, inv, ntr in runs:
            sub, sinv = _slice(eq, inv, d0, d1)
            m = _metrics(dates, sub, sinv) if sub else None
            if not m:
                continue
            _rr = (m['ret'] / abs(m['mdd'])) if m['mdd'] else float('nan')
            print(f'{label:32}{m["ret"]:>+9.2f}%{m["mdd"]:>+9.2f}%{m["vol"]:>8.2f}%'
                  f'{_rr:>11.2f}{m["inv"]:>8.0f}%{(ntr if ntr else "—"):>7}')
        # 隨機中性對照的分位
        rs = []
        for eq, inv in rnd_eq:
            sub, sinv = _slice(eq, inv, d0, d1)
            m = _metrics(cal, sub, sinv) if sub else None
            if m:
                rs.append(m['ret'])
        if len(rs) >= 5:
            rs.sort()
            lo, mid, hi = rs[int(len(rs)*.05)], rs[len(rs)//2], rs[int(len(rs)*.95)]
            print(f'{"★ 隨機排序 5檔（中性，20條）":32}{mid:>+9.2f}%'
                  f'{"":>10}{"":>9}{"":>11}{"":>9}{"":>7}')
            print(f'    └ 5%~95% 分位：{lo:+.2f}% ~ {hi:+.2f}%'
                  f'　帶寬 {hi-lo:.1f}pp　← 評分排序要贏過 {hi:+.2f}% 才算有訊號')

    print()
    print('※「報酬/回檔」＝總報酬 ÷ 最大回檔絕對值，數字越大代表「每承受 1% 回檔換到幾 % 報酬」。')
    print('※「在場內」＝平均有多少比例的資本實際持股（其餘為現金、報酬 0）。')
    print('※ 買進持有**未計股利**；0056 近一年殖利率約 7~8%，實際報酬會比上表更高。')
    print('※ ⚠️ 樣本期間指數大漲，任何「有時空手」的策略輸給買進持有幾乎是結構性的；')
    print('   這張表不能外推到橫盤或空頭環境。詳見本檔 docstring 的限制說明。')


if __name__ == '__main__':
    main()
