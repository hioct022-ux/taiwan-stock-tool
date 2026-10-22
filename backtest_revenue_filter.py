#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_revenue_filter.py — 「現有策略 ＋ 月營收 YoY 篩選」第一次實測

════════════════════════════════════════════════════════════════════════
要驗證的問題（2026-10-14）
════════════════════════════════════════════════════════════════════════

十五章月營收那節標著「**尚未做**」的兩項之一：

  > 現在測的是「理想化月度換倉組合」，不是「現有策略 + YoY 篩選」，兩者不同。

10/07 的主檢定是 **74 檔等權、每月重排**（Fama-MacBeth，spread +1.98%/月、t=+6.44）。
而現行策略是 **5 檔、10 日週期、續抱、10% 停損、大盤階梯**——完全不同的載具。

★ 事前預期（先寫下來，跑完對照——照策略F／D 那次的慣例）：

  「**可能測得出來，而且這與 10/07 的悲觀結論不衝突。**」

  10/07 說「0.5pp/月 的優勢在 5 檔配置下看不見」，那個 ±8pp/月 的帶寬
  來自**隨機 5 檔的資金曲線**——它量的是「抽到哪幾檔」的運氣。
  而配對設計（同一 seed、同一組排序，只差規則）正好把那個運氣消掉。
  ⇒ 無條件比較看不見、配對比較可能看得見，兩者不矛盾。

  反向因素：YoY 篩選會減少進場機會，而 10/07 量到「**動能最弱那組 YoY
  幾乎沒用**」。現行評分的技術面 40% 已經偏向強動能股
  ⇒ YoY 的增量資訊可能已被吃掉一部分。

════════════════════════════════════════════════════════════════════════
六個對照組（每一組都有存在的理由，不是湊數）
════════════════════════════════════════════════════════════════════════

  A0  現行策略（全宇宙）                    ← 真正的基準
  A1  現行策略（**限當日有營收資料者**）     ← 公平比較的基準，見下
  B1  A1 ＋ YoY > 0
  B2  A1 ＋ YoY ≥ 產業內中位數
  B3  A1 ＋ YoY 產業內**前 1/3**            ← 最接近 10/07 的「高分組」
  ★C  A1 ＋ YoY 產業內**後 1/3**            ← **反向對照，必須有**
  ★D  A1 ＋ 隨機篩掉同比例                  ← 中性對照

**為什麼要 A1（這一條不設會得到假陽性）：** KY 股與部分個股沒有月營收
（十五章已載明 KY 30 檔沒有，實測 1256/1337/… 全 0 筆）。若直接拿
「A0 vs B3」比，那個差異裡混了「排除沒資料的股票」這個完全不同的效果。
A1 把宇宙對齊，B 組才只在 YoY 這一個維度上與它不同。

**為什麼要 ★C（反向對照）：** 若 B3 變好而 C 變差 → 是真訊號。
若兩者一樣 → 是雜訊。這是「必須設無條件基準」那條通則在**方向性**上的版本
（2026-09-01 測「先殺後拉」時，正是反向對照 X/Y 揭露了方向是反的）。

**為什麼要 ★D（隨機篩同比例）：** 任何篩選都會減少交易筆數，而
**筆數變少本身就會改變 alpha 的分布**（9/17 量到 n=85 的雜訊帶 4.37pp）。
D 組讓「篩掉 X% 的交易」這件事本身有對照，B 組的差異才能歸因於 YoY。

════════════════════════════════════════════════════════════════════════
兩個層級的檢定（缺一不可）
════════════════════════════════════════════════════════════════════════

  ① per-trade alpha ＋ bootstrap 雜訊帶（9/24 的框架）
     不限檔數 ⇒ 排序不影響結果 ⇒ 確定性、n 上千、雜訊帶約 0.6pp

  ② 5 檔配置的**配對比較**（10/07 的框架）
     同一 seed 的隨機排序在各規則間完全相同 ⇒ 消掉「抽到哪些股票」的運氣
     判準用符號檢定。⚠️ 先算「N 條之下最小可檢出勝場數」再決定跑幾條：
         6/6 → p=0.031（必須全勝）　15/20 → p=0.041　16/20 → p=0.012

════════════════════════════════════════════════════════════════════════
防 look-ahead（這一節是整支腳本最關鍵的部分）
════════════════════════════════════════════════════════════════════════

`monthly_revenue.avail_date` = 營收月的**次月 11 日** = 最早可用日。
理由見十五章：沒有來源提供逐股公布日，而 2026-10-06 實查 9 月營收當天
只有 176/993 檔已公布 ⇒ 用「次月 1 日」拿到的是「只有 18% 公司、
且偏向先公布者（業績通常較好）」，比單純偷看 10 天**更惡性**。

★ 而 `avail_date` 對所有個股是**同一個規則**（次月11日）
⇒ 任一決策日 d，「最新可用的營收月」對每一檔都相同
⇒ 產業內排名可以**按營收月預先算好**，不必逐日重算。這不是近似，是等價。

════════════════════════════════════════════════════════════════════════
限制（引用任何結果時必須一起講）
════════════════════════════════════════════════════════════════════════

 1. **基本面 25% 在 2026-05 之前是預設值 50**（BWIBBU date 參數無效，陷阱44，永久）
    ⇒ 評分實質是「技術40% + 籌碼35% + 常數」。2026-10-08 回填後籌碼已補到 2018，
      所以是 75% 的權重有真實資料（10/07 做結構測試時籌碼還是 0 天）。
    ⇒ **「65 分」在這段樣本與今天不是同一個篩選器**（9/17 的發現）。
 2. **除權息無法調整**（陷阱50）⇒ 所有報酬系統性低估。
    而本測試的 B 組偏向高成長股（＝低殖利率＝除息拖累小）
    ⇒ **這個偏誤的方向對 B 組有利**，必須在結論裡扣掉（見輸出的診斷段）。
 3. 未調整收盤價（陷阱49）⇒ 分割日會有假停損，3 筆/3450 筆，影響 <0.02pp。
 4. 上櫃不在宇宙內；KY 股沒有月營收。
 5. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。

用法：
    python3 -u backtest_revenue_filter.py cache    # 建快取（約 16~20 分鐘，4 核）
    python3 -u backtest_revenue_filter.py run      # 跑對照
"""
import os
import sys
import math
import pickle
import random
import statistics as stt
from bisect import bisect_right
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ⚠️ pickle 的來源：這份快取**由本腳本自己的 `cache` 子命令寫入 /tmp**，
#    不是外部或網路輸入，與既有的 `backtest_portfolio_slots.py` 同一模式。
#    內容是純 dict/list/float（無自訂類別），改用 JSON 也可以但會大好幾倍、慢很多。
#   快取目錄預設 /tmp，可用 TWSTOOL_CACHE 改成不會被清掉的地方
#   （見 backtest_portfolio_slots.cache_dir() 的說明——2026-10-21 /tmp 被清、
#     一份 20~40 分鐘的快取白建）。
import backtest_portfolio_slots as _P0
_CD = _P0.cache_dir()

CACHE = os.path.join(_CD, '_rev_filter_cache.pkl')

# ★ 2026-10-21：點時間宇宙版的快取**另存一份**，不覆蓋舊的。
#   理由：舊快取是唯一能對帳既有數字的東西（★10%／現行階梯 ⇒ 15,176 筆、
#   alpha +0.31%）。把它蓋掉就再也無法回答「差異是宇宙造成的，還是程式改壞了」。
CACHE_PIT = os.path.join(_CD, '_rev_filter_cache_pit.pkl')

DAYS       = 2600    # 要撈到 2018 之前（TAIEX 實際有 2016-10 起）
# ★ 回測起點**必須 ≥ 2018-01-01**（陷阱51 限制第 5 條）：
#   S2/S3/S4 只回填到 2018-01-01，2016~2017 只有 5 個訊號在跑、
#   淨值天生偏小（實測 max 僅 3，2018+ 是 8~11）⇒ 大盤階梯會系統性偏寬鬆。
#   快取會存整段 TAIEX，但模擬時一律從這一天起算。
START      = '2018-01-02'
PRICE_WIN  = 300     # full_score 的價格視窗；已驗證與整段逐欄相同
SLOTS      = 5       # 配對測試的持股上限（＝使用者實際配置）
N_SEEDS    = 20      # 配對條數（6 條的檢定力是零，見 docstring）
BOOT_N     = 600     # bootstrap 重抽次數


# ════════════════════════════════════════════════════════════════
# 第一段：快取（4 核平行）
# ════════════════════════════════════════════════════════════════
def _one_stock(args):
    """單股的評分與波動度。在子行程執行，每個行程自己開 DB 連線。"""
    code, name = args
    try:
        from database import (get_prices, get_fundamentals, get_chips,
                              get_ownership)
        from scorer import full_score
        import backtest_portfolio_slots as P

        prices = get_prices(code, days=DAYS)
        if len(prices) < P.MIN_HISTORY + P.HOLD_DAYS + 2:
            return None
        fund_all  = get_fundamentals(code, days=DAYS)
        chips_all = get_chips(code, days=DAYS)
        own_raw   = get_ownership(code)
        ownership = {'foreign': own_raw['foreign_pct']} if own_raw else {'foreign': 52}

        score, vol = {}, {}
        for i in range(P.MIN_HISTORY, len(prices) - 1):
            d = prices[i]['date']
            fs = [r for r in fund_all  if r['date'] <= d]
            cs = [r for r in chips_all if r['date'] <= d][-65:]
            r = full_score(prices[max(0, i - PRICE_WIN + 1):i + 1], fs, cs, ownership)
            if r:
                score[d] = r['total_score']
            v = P._vol20([p['close'] for p in prices[max(0, i - 20):i + 1]])
            if v is not None:
                vol[d] = v
        slim = [{'date': p['date'], 'open': p['open'], 'high': p['high'],
                 'low': p['low'], 'close': p['close']} for p in prices]
        return code, {'name': name, 'prices': slim,
                      'idx': {p['date']: k for k, p in enumerate(slim)},
                      'score': score, 'vol': vol}
    except Exception as e:
        print(f'  ⚠️ {code} 失敗：{e}')
        return None


def build_revenue_ranks(conn, codes):
    """
    回傳 (avail, rank)：
      avail = [(avail_date, (year, month)), ...]  升序，所有個股共用
      rank  = {code: {(year, month): 0.0~1.0 產業內百分位}}

    ★ 為什麼能按月預算：`avail_date` 是「營收月的次月 11 日」這條
      對所有個股相同的規則 ⇒ 任一決策日的「最新可用營收月」對每檔都一樣。
      這是等價簡化，不是近似。
    """
    ind = dict(conn.execute(
        "SELECT code, industry FROM stocks WHERE industry IS NOT NULL AND industry != ''"
    ).fetchall())
    rows = conn.execute(
        'SELECT code, rev_year, rev_month, avail_date, yoy_pct FROM monthly_revenue '
        'WHERE yoy_pct IS NOT NULL'
    ).fetchall()

    uni = set(codes)
    by_month = defaultdict(list)          # (y,m) -> [(code, industry, yoy)]
    avail_of = {}
    for code, y, m, av, yoy in rows:
        if code not in uni:
            continue
        g = ind.get(code)
        if not g:
            continue
        by_month[(y, m)].append((code, g, yoy))
        avail_of[(y, m)] = av

    rank = defaultdict(dict)
    raw  = defaultdict(dict)          # {code: {(y,m): 原始 yoy_pct}}
    for ym, items in by_month.items():
        for code, _g, yoy in items:
            raw[code][ym] = yoy
        per_ind = defaultdict(list)
        for code, g, yoy in items:
            per_ind[g].append((code, yoy))
        for g, lst in per_ind.items():
            if len(lst) < 5:              # 產業內樣本太少，排名沒有意義
                continue
            lst.sort(key=lambda x: x[1])
            n = len(lst)
            for k, (code, _) in enumerate(lst):
                rank[code][ym] = k / (n - 1) if n > 1 else 0.5
    avail = sorted((avail_of[ym], ym) for ym in by_month)
    return avail, dict(rank), dict(raw)


# ★ 為什麼要分塊（2026-10-14）：全量是 512 檔 × 7.4s ÷ 4 核 ≈ 950s，
#   而沙盒單次工具呼叫實測上限約 180s（工具說明寫明會被 host cap 壓低）。第一次用 nohup 背景跑，**行程被逾時連帶
#   殺掉、連進度都沒印出來**。改成「每塊 48 檔、各自存檔、最後合併」
#   ⇒ 每塊約 90s，穩穩落在上限內，中斷了只要重跑那一塊。
#   本機執行不受此限，可直接 `cache`（不帶 --chunk）一次跑完。
CHUNK_N  = 48
META     = os.path.join(_CD, '_rev_meta.pkl')
META_PIT = os.path.join(_CD, '_rev_meta_pit.pkl')


def _chunk_path(k, pit=False):
    return os.path.join(_CD, f'_rev_chunk{"_pit" if pit else ""}_{k}.pkl')


def _build_chunk(chunk, meta, pit=False):
    from multiprocessing import Pool
    codes, names = meta['codes'], meta['names']
    ks = (range((len(codes) + CHUNK_N - 1) // CHUNK_N)
          if chunk is None else [chunk])
    for k in ks:
        sub = codes[k * CHUNK_N:(k + 1) * CHUNK_N]
        if not sub:
            print(f'  第 {k} 塊是空的，略過'); continue
        print(f'')
        print(f'第 {k} 塊：{len(sub)} 檔（{sub[0]} ~ {sub[-1]}）4 核平行...')
        out = {}
        with Pool(4) as pool:
            args = [(c, names.get(c, c)) for c in sub]
            for n, res in enumerate(pool.imap_unordered(_one_stock, args, 4), 1):
                if res:
                    out[res[0]] = res[1]
                if n % 32 == 0 or n == len(sub):
                    print(f'    [{n}/{len(sub)}] 已完成 {len(out)} 檔', flush=True)
        with open(_chunk_path(k, pit), 'wb') as f:
            pickle.dump(out, f)
        mb = os.path.getsize(_chunk_path(k, pit)) / 1e6
        print(f'  ✅ 第 {k} 塊已存（{len(out)} 檔、{mb:.0f} MB）')


def _merge(meta, pit=False):
    codes = meta['codes']
    n_chunks = (len(codes) + CHUNK_N - 1) // CHUNK_N
    stocks, missing = {}, []
    for k in range(n_chunks):
        pth = _chunk_path(k, pit)
        if not os.path.exists(pth):
            missing.append(k)
            continue
        with open(pth, 'rb') as f:
            stocks.update(pickle.load(f))
    if missing:
        # 🚨 刻意不合併：合併不完整的快取會讓宇宙悄悄縮小，而結果看起來
        #    完全正常——那正是本專案最常見的靜默失敗（陷阱41/42/45 同族）。
        print(f'🚨 **缺第 {missing} 塊，不合併。**')
        print('   合併不完整的快取會讓宇宙悄悄縮小，而結果看起來完全正常。')
        return
    out = CACHE_PIT if pit else CACHE
    with open(out, 'wb') as f:
        pickle.dump({'market_net': meta['market_net'],
                     'tpx_close': meta['tpx_close'],
                     'tpx_dates': meta['tpx_dates'], 'stocks': stocks,
                     'avail': meta['avail'], 'rev_rank': meta['rev_rank'],
                     'rev_yoy': meta['rev_yoy'],
                     # ★ 2026-10-21：點時間宇宙的逐月成員（只存 106 個月份，
                     #   不存 2,137 天 × 400 檔），用 P.pit_lookup() 展開。
                     'pit_months': meta.get('pit_months'),
                     'universe': 'market_pit' if pit else 'market_long'}, f)
    sp = sum(len(v['score']) for v in stocks.values())
    mb = os.path.getsize(out) / 1e6
    print('')
    print(f'✅ 快取已合併 {out}')
    print(f'   {len(stocks)} / {len(codes)} 檔　{sp:,} 個評分點　{mb:.0f} MB')
    if len(stocks) < len(codes) * 0.9:
        pctv = len(stocks) / len(codes) * 100
        print(f'   ⚠️ 只有 {pctv:.0f}% 的標的建成（其餘歷史筆數不足）')


def build_cache(chunk=None, merge=False, pit=False):
    from multiprocessing import Pool
    from database import get_conn, get_prices
    import backtest_portfolio_slots as P
    import backtest_stocks as bs

    meta_path = META_PIT if pit else META
    print('=' * 72)
    print('建快取：2018 起、全市場、含月營收產業內排名'
          + ('　★點時間宇宙（含已退場股）' if pit else ''))
    print('=' * 72)
    print(f'DAYS={DAYS}　PRICE_WIN={PRICE_WIN}')

    if os.path.exists(meta_path):
        with open(meta_path, 'rb') as f:
            meta = pickle.load(f)
        print(f'（沿用既有 meta：{meta_path}　宇宙 {len(meta["codes"])} 檔）')
        return _merge(meta, pit) if merge else _build_chunk(chunk, meta, pit)

    print('計算大盤訊號（S1–S8 逐日回溯）...')
    market_net = bs._build_market_signals(days=DAYS)
    tpx = get_prices('TAIEX', days=DAYS)
    tpx_close = {p['date']: p['close'] for p in tpx}
    tpx_dates = [p['date'] for p in tpx]
    print(f'  淨值 {len(market_net)} 天　TAIEX {len(tpx_dates)} 天'
          f'　{tpx_dates[0]} ~ {tpx_dates[-1]}')
    if tpx_dates[0] > '2019-01-01':
        print(f'\n🚨 **只到 {tpx_dates[0]}，沒有 2018** ⇒ 回填未完成或 DAYS 不足，中止。')
        return

    conn = get_conn()
    names = dict(conn.execute('SELECT code, name FROM stocks').fetchall())
    pit_months = None
    if pit:
        print('\n計算點時間宇宙（每月重算、上市判準＝有 chips）...')
        pit_months, codes = P.pit_universe(conn)
        sz = [len(m[1]) for m in pit_months]
        print(f'  {len(pit_months)} 個月，月宇宙平均 {sum(sz)/len(sz):.0f} 檔'
              f'（{min(sz)}~{max(sz)}）')
        P.assert_pit_has_delisted(conn, codes)   # 阻斷式，缺了就 sys.exit
    else:
        codes = P.market_universe(conn)
        print(f'\n宇宙：{len(codes)} 檔（上市普通股、日均成交 ≥ '
              f'{P.UNI_MIN_TURNOVER/1e8:.2f} 億）')
    avail, rev_rank, rev_yoy = build_revenue_ranks(conn, codes)
    conn.close()
    print(f'月營收：{len(avail)} 個營收月　{avail[0][1]} ~ {avail[-1][1]}'
          f'　有排名的個股 {len(rev_rank)} 檔')

    meta = {'market_net': market_net, 'tpx_close': tpx_close,
            'tpx_dates': tpx_dates, 'codes': codes, 'names': names,
            'avail': avail, 'rev_rank': rev_rank, 'rev_yoy': rev_yoy,
            'pit_months': pit_months}
    with open(meta_path, 'wb') as f:
        pickle.dump(meta, f)
    print(f'✅ meta 已存 {meta_path}（大盤訊號＋宇宙＋月營收，只算一次）')
    nk = (len(codes) + CHUNK_N - 1) // CHUNK_N
    print(f'接下來分 {nk} 塊建個股快取。')
    return _merge(meta, pit) if merge else _build_chunk(chunk, meta, pit)


# ════════════════════════════════════════════════════════════════
# 第二段：對照測試
# ════════════════════════════════════════════════════════════════
def make_rev_lookup(cache):
    """回傳 latest_ym(date) -> (y,m) | None。用 bisect，O(log n)。"""
    avail = cache['avail']
    ads = [a for a, _ in avail]
    yms = [ym for _, ym in avail]

    def latest_ym(d):
        i = bisect_right(ads, d) - 1
        return yms[i] if i >= 0 else None
    return latest_ym


def noise_band(trades, tpx, n, reps=BOOT_N, seed=0):
    """從基準組重抽 n 筆，回傳 alpha 的 (5%, 50%, 95%) 分位與帶寬。"""
    import backtest_portfolio_slots as P
    if not trades or n <= 0 or n > len(trades):
        return None
    rnd = random.Random(seed)
    out = []
    for _ in range(reps):
        sub = [trades[rnd.randrange(len(trades))] for _ in range(n)]
        s = P.stat(sub, tpx)
        if s:
            out.append(s['alpha'])
    if len(out) < 50:
        return None
    out.sort()
    lo = out[int(len(out) * .05)]
    mid = out[len(out) // 2]
    hi = out[int(len(out) * .95)]
    return lo, mid, hi, hi - lo


def sign_test(diffs):
    """符號檢定。⚠️ 排除平手（10/07 錯誤二：把平手算成輸，會把 null 印成顯著更差）。"""
    nz = [x for x in diffs if abs(x) > 1e-9]
    ties = len(diffs) - len(nz)
    if not nz:
        return 0, 0, ties, 1.0
    w = sum(1 for x in nz if x > 0)
    n = len(nz)
    p = sum(math.comb(n, k) for k in range(w, n + 1)) / 2 ** n
    p = min(1.0, 2 * min(p, sum(math.comb(n, k) for k in range(0, w + 1)) / 2 ** n))
    return w, n, ties, p


def run():
    import backtest_portfolio_slots as P
    if not os.path.exists(CACHE):
        print(f'❌ 找不到 {CACHE}，先跑：python3 -u {sys.argv[0]} cache')
        return
    with open(CACHE, 'rb') as f:
        cache = pickle.load(f)
    # ★ 裁掉 2018 之前（陷阱51 限制第 5 條，見 START 的註解）
    n_before = len(cache['tpx_dates'])
    cache['tpx_dates'] = [d for d in cache['tpx_dates'] if d >= START]
    print(f'（已裁掉 {START} 之前的 {n_before - len(cache["tpx_dates"])} 天'
          f'——S2/S3/S4 只回填到 2018-01-01，之前淨值天生偏小）')
    tpx = cache['tpx_close']
    rev_rank = cache['rev_rank']
    rev_yoy  = cache.get('rev_yoy', {})
    latest_ym = make_rev_lookup(cache)
    ds = cache['tpx_dates']

    print('=' * 92)
    print('現有策略 ＋ 月營收 YoY 篩選')
    print('=' * 92)
    print(f'宇宙 {len(cache["stocks"])} 檔　{ds[0]} ~ {ds[-1]}（{len(ds)} 個交易日）')
    print(f'評分點 {sum(len(v["score"]) for v in cache["stocks"].values()):,}')

    # ── 篩選器 ──
    def has_rev(code, d):
        ym = latest_ym(d)
        return ym is not None and ym in rev_rank.get(code, {})

    def rank_of(code, d):
        ym = latest_ym(d)
        return rev_rank.get(code, {}).get(ym) if ym else None

    def yoy_of(code, d):
        ym = latest_ym(d)
        return rev_yoy.get(code, {}).get(ym) if ym else None

    FILTERS = [
        ('A0 現行策略（全宇宙）',            None),
        ('A1 現行策略（限有營收資料）',       has_rev),
        ('B1 A1＋YoY > 0',                   lambda c, d: (yoy_of(c, d) or -1e9) > 0),
        ('B2 A1＋YoY 產業內 ≥ 中位',         lambda c, d: (rank_of(c, d) or -1) >= 0.5),
        ('B3 A1＋YoY 產業內 前1/3',          lambda c, d: (rank_of(c, d) or -1) >= 2 / 3),
        ('★C A1＋YoY 產業內 後1/3（反向）',   lambda c, d: 0 <= (rank_of(c, d)
                                                              if rank_of(c, d) is not None
                                                              else -1) <= 1 / 3),
    ]

    # ════ ① per-trade（不限檔數 ⇒ 排序無關、確定性）════
    print('\n' + '=' * 92)
    print('【① per-trade：不限檔數（排序不影響結果 ⇒ 確定性、n 最大）')
    print('=' * 92)
    print(f'  {"規則":<30}{"筆數":>7}{"報酬":>9}{"同期大盤":>10}'
          f'{"alpha":>9}{"勝率":>8}{"停損率":>8}')
    print('  ' + '-' * 86)
    res1 = {}
    base_tr = None
    for label, fn in FILTERS:
        _, tr = P.simulate(cache, lambda c, d, s: (c,), None, label, entry_filter=fn)
        s = P.stat(tr, tpx)
        if not s:
            print(f'  {label:<30}{"— 無交易":>7}')
            continue
        res1[label] = s
        if label.startswith('A1'):
            base_tr = tr
        print(f'  {label:<30}{s["n"]:>7}{s["ret"]:>+8.2f}%{s["mkt"]:>+9.2f}%'
              f'{s["alpha"]:>+8.2f}%{s["win"]:>7.1f}%{s["stop"]:>7.1f}%')

    # ★ 中性對照：隨機篩掉與 B3 相同比例
    if 'A1 現行策略（限有營收資料）' in res1 and 'B3 A1＋YoY 產業內 前1/3' in res1:
        keep = res1['B3 A1＋YoY 產業內 前1/3']['n'] / res1['A1 現行策略（限有營收資料）']['n']
        print(f'\n  ★D 中性對照：隨機保留 {keep*100:.0f}%（＝B3 的篩選強度），跑 5 個 seed')
        dn = []
        for sd in range(5):
            rnd = random.Random(9000 + sd)
            def frand(c, d, _r=rnd, _k=keep):
                return has_rev(c, d) and _r.random() < _k
            _, tr = P.simulate(cache, lambda c, d, s: (c,), None, 'D', entry_filter=frand)
            s = P.stat(tr, tpx)
            if s:
                dn.append(s['alpha'])
                print(f'     seed {sd}　n={s["n"]:>6}　alpha {s["alpha"]:+.2f}%')
        if dn:
            print(f'     ⇒ 隨機篩同比例的 alpha：{min(dn):+.2f}% ~ {max(dn):+.2f}%'
                  f'（中位 {stt.median(dn):+.2f}%）')

    # ★ 雜訊帶（9/17 立的標準前置動作）
    if base_tr:
        print('\n  ★ 雜訊帶（從 A1 重抽，看純運氣能造成多大落差）：')
        ns = sorted({s['n'] for s in res1.values()})
        worst = 0
        for n in ns:
            # ⚠️ 重抽是「從基準組有放回地抽 n 筆」，n > 基準組筆數時無法對應
            #    ⇒ 標明已上限，否則不同 n 印出同一個帶寬會看起來像 bug
            capped = n > len(base_tr)
            nb = noise_band(base_tr, tpx, min(n, len(base_tr)))
            if nb:
                lo, mid, hi, w = nb
                worst = max(worst, w)
                print(f'     n={n:<7} alpha 5~95% 分位 {lo:+.2f}% ~ {hi:+.2f}%'
                      f'　帶寬 {w:.2f}pp'
                      + (f'　（已上限至基準組 {len(base_tr)} 筆）' if capped else ''))
        al = [s['alpha'] for s in res1.values()]
        spread = max(al) - min(al)
        print(f'\n  各組 alpha 全距 {spread:.2f}pp　vs 最寬雜訊帶 {worst:.2f}pp')
        print(f'  ⇒ {"⚪ 全距小於雜訊帶，整張表不可解讀" if spread < worst else "★ 全距超出雜訊帶，可以往下看"}')

    # ════ ★ 內建診斷：除權息偏誤（陷阱50 的做法）════
    #
    # 為什麼必須內建而不是事後補：DB 存的是**未調整收盤價**，而 `exdividend`
    # 只有 2026 年（陷阱50）⇒ 2018~2025 的除息既無法調整也無法排除。
    # 而它**與訊號相關、不是隨機雜訊**：
    #     高成長股（電子）→ 殖利率低 → 除息拖累小
    #     低成長股（傳產/金融）→ 殖利率高 → 除息拖累大
    # ⇒ 在 6~9 月（實測佔全年除息的 93.6%）的前瞻窗口裡，
    #   **低 YoY 組會被系統性壓低** ⇒ 製造假的「高 YoY 組贏」，量級 1~4pp。
    #
    # ★ 自我診斷的邏輯（不需要任何額外資料）：
    #   **若效果是股利造成的，除息月的 spread 應該要比其他月更高。**
    #   10/07 的月營收主檢定就是靠這一招排除地雷（實測其他 8 月 +2.12%
    #   ＞ 除息月 +1.72%，方向與假訊號相反 ⇒ 不是股利）。
    print('\n' + '=' * 92)
    print('【★ 內建診斷】除權息偏誤：效果是不是只出現在 6~9 月？')
    print('=' * 92)
    _b3 = 'B3 A1＋YoY 產業內 前1/3'
    _c  = '★C A1＋YoY 產業內 後1/3（反向）'
    _trs = {}
    for lb, fn in FILTERS:
        if lb in (_b3, _c):
            _, _trs[lb] = P.simulate(cache, lambda c, d, s: (c,), None, lb,
                                     entry_filter=fn)
    if len(_trs) == 2:
        print(f'  {"進場月":<14}{"B3 筆數":>9}{"B3 alpha":>11}'
              f'{"C 筆數":>9}{"C alpha":>11}{"B3−C":>10}')
        print('  ' + '-' * 66)
        for seg, mths in (('6~9月（除息月）', {'06', '07', '08', '09'}),
                          ('其他 8 個月',     {'01', '02', '03', '04', '05',
                                              '10', '11', '12'})):
            row = []
            for lb in (_b3, _c):
                sub = [t for t in _trs[lb] if t['entry_date'][5:7] in mths]
                row.append(P.stat(sub, tpx))
            if all(row):
                d_ = row[0]['alpha'] - row[1]['alpha']
                print(f'  {seg:<14}{row[0]["n"]:>9}{row[0]["alpha"]:>+10.2f}%'
                      f'{row[1]["n"]:>9}{row[1]["alpha"]:>+10.2f}%{d_:>+9.2f}pp')
        print('''
  ⇒ 怎麼讀：
     • **除息月的 B3−C 明顯更高** ⇒ 效果主要來自股利 ⇒ 🚨 假訊號
     • **其他 8 月 ≥ 除息月** ⇒ 與假訊號方向相反 ⇒ 地雷沒引爆（10/07 就是這樣）''')

    # ════ ★★ 除息調整後重做同一個診斷（2026-10-15 新增）════
    #
    # 上面那個診斷是「自我診斷」——它在**沒有股利資料**的前提下，
    # 靠「效果有沒有集中在除息月」來反推。現在 `exdividend` 已回填 2018~2026
    # （陷阱52），可以直接把股利加回去，不必再靠反推。
    #
    # 🚨 但只能看「兩組相減」。理由（exdiv.py 有完整說明）：
    #    TAIEX 是價格指數、同樣不含股利 ⇒ 只調整個股那一邊，
    #    alpha 會憑空多出整個市場的殖利率。
    #    而 B3−C 是**兩個 alpha 相減**，市場項精確消掉
    #    ⇒ (個股B3 − 市場) − (個股C − 市場) = 個股B3 − 個股C
    #    ⇒ 基準含不含股利完全不影響這個差值。**這一題剛好只需要個股端。**
    print('\n' + '=' * 92)
    print('【★★ 除息調整後】同一個診斷，但直接把股利加回個股報酬')
    print('=' * 92)
    if len(_trs) == 2:
        import exdiv
        _ok = exdiv.require_coverage(ds[0], ds[-1])
        if not _ok:
            print('\n⇒ 跳過除息調整（資料未回填完整）。上面那個「自我診斷」仍然有效。')
        else:
            _codes = {t['code'] for tr in _trs.values() for t in tr}
            _divs = exdiv.load_dividends(_codes)
            for lb in _trs:
                exdiv.adjust_trades(_trs[lb], _divs)
                print(f'  {lb[:28]:<28}{exdiv.summary_line(_trs[lb])}')

            print(f'\n  {"進場月":<14}{"B3−C 未調整":>14}{"B3−C 除息調整後":>18}'
                  f'{"變化":>10}')
            print('  ' + '-' * 58)
            _flip = {}
            for seg, mths in (('6~9月（除息月）', {'06', '07', '08', '09'}),
                              ('其他 8 個月',     {'01', '02', '03', '04', '05',
                                                  '10', '11', '12'})):
                _d = {}
                for k in ('pnl', 'pnl_div'):
                    row = [P.stat([t for t in _trs[lb]
                                   if t['entry_date'][5:7] in mths], tpx, key=k)
                           for lb in (_b3, _c)]
                    _d[k] = (row[0]['alpha'] - row[1]['alpha']) if all(row) else None
                if _d['pnl'] is not None and _d['pnl_div'] is not None:
                    _flip[seg] = _d['pnl_div']
                    print(f'  {seg:<14}{_d["pnl"]:>+13.2f}pp{_d["pnl_div"]:>+17.2f}pp'
                          f'{_d["pnl_div"] - _d["pnl"]:>+9.2f}pp')

            if len(_flip) == 2:
                _ex = _flip['6~9月（除息月）']
                _ot = _flip['其他 8 個月']
                print(f'\n  ⇒ 調整後：除息月 {_ex:+.2f}pp　vs 其他 8 月 {_ot:+.2f}pp'
                      f'　差 {_ex - _ot:+.2f}pp')
                if _ex <= _ot:
                    print('  ✅ **其他 8 月 ≥ 除息月** ⇒ 診斷翻正，'
                          '10/14 那個「唯一不利的項目」解除')
                else:
                    print('  ⚠️ **除息月仍然較高** ⇒ 把股利加回去之後差距還在，'
                          '不能用股利解釋。\n'
                          '     但注意：股利已經不是原因了，所以要另找解釋'
                          '（例如 6~9 月本身的季節性、或營收公布節奏）。')

            _fs = sum(len(exdiv.suspect_false_stops(tr)) for tr in _trs.values())
            _tot = sum(len(tr) for tr in _trs.values())
            print(f'''
  ⚠️ **仍然沒有處理的事（陷阱49 的同一族）：假停損。**
     除息日的價格跳水會打到 10% 停損，產生一筆不該發生的停損——
     本次 {_tot} 筆裡有 **{_fs} 筆**持有期間遇到 ≥{exdiv.FALSE_STOP_DIV_PCT}% 的除息
     且以停損出場。真正的修法是用**還原股價**跑整個回測，
     那會改動所有既有基準，是另一個題目。**這裡只揭露、不假裝沒事。**''')

    # ════ ★ 內建診斷：分期間（空頭年會不會翻轉）════
    print('\n' + '=' * 92)
    print('【★ 內建診斷】分期間：三個空頭年（2018／2020／2022）方向一致嗎？')
    print('=' * 92)
    if len(_trs) == 2:
        print(f'  {"期間":<22}{"B3 筆數":>9}{"B3 alpha":>11}'
              f'{"C 筆數":>9}{"C alpha":>11}{"B3−C":>10}')
        print('  ' + '-' * 74)
        SEGS = [('2018 ★空頭（-9.2%）',  lambda d: d.startswith('2018')),
                ('2019',                lambda d: d.startswith('2019')),
                ('2020 ★空頭（V轉）',   lambda d: d.startswith('2020')),
                ('2021',                lambda d: d.startswith('2021')),
                ('2022 ★空頭（-22.6%）', lambda d: d.startswith('2022')),
                ('2023',                lambda d: d.startswith('2023')),
                ('2024',                lambda d: d.startswith('2024')),
                ('2025',                lambda d: d.startswith('2025')),
                ('2026',                lambda d: d.startswith('2026'))]
        for nm, f_ in SEGS:
            row = []
            for lb in (_b3, _c):
                sub = [t for t in _trs[lb] if f_(t['entry_date'])]
                row.append(P.stat(sub, tpx))
            if all(row) and min(row[0]['n'], row[1]['n']) >= 15:
                d_ = row[0]['alpha'] - row[1]['alpha']
                print(f'  {nm:<22}{row[0]["n"]:>9}{row[0]["alpha"]:>+10.2f}%'
                      f'{row[1]["n"]:>9}{row[1]["alpha"]:>+10.2f}%{d_:>+9.2f}pp')
            elif all(row):
                print(f'  {nm:<22}{row[0]["n"]:>9}{"（任一組 n<15，不解讀）":>30}')
        print('''
  ⇒ 10/07 的主檢定在空頭年測不出來（2018+2022 的 t=1.52，n=22 月）。
     若這裡三個空頭年方向也一致（B3−C ＞ 0），那是新增的證據；
     **若空頭年翻轉，就與十五章「環境依賴」那一族的發現同性質，必須寫明。**''')

    # ════ ② 5 檔配對（10/07 的框架）════
    print('\n' + '=' * 92)
    print(f'【② 5 檔配置・配對比較（{N_SEEDS} 條，同一 seed 用同一組隨機排序）')
    print('=' * 92)
    minw = next((w for w in range(N_SEEDS, 0, -1)
                 if 2 * sum(math.comb(N_SEEDS, k)
                            for k in range(w, N_SEEDS + 1)) / 2 ** N_SEEDS < 0.05),
                N_SEEDS)
    print(f'  檢定力：{N_SEEDS} 條之下，最少要 **{minw}/{N_SEEDS}** 勝才有 p<0.05')

    curves = {}
    for label, fn in FILTERS:
        per_seed = []
        for sd in range(N_SEEDS):
            rnd = random.Random(sd)
            pref = {c: rnd.random() for c in sorted(cache['stocks'])}   # ★ sorted 必要，見 backtest_market_ladder.py 的註解
            _, tr = P.simulate(cache, lambda c, d, s, _p=pref: (_p[c],),
                               SLOTS, label, entry_filter=fn)
            s = P.stat(tr, tpx)
            per_seed.append(s['alpha'] if s else 0.0)
        curves[label] = per_seed
        _uniq = len({round(x, 6) for x in per_seed})
        _warn = '　🚨 所有 seed 相同（槽位未綁定）' if _uniq == 1 else ''
        print(f'  {label:<30}中位 alpha {stt.median(per_seed):+.2f}%'
              f'　（{min(per_seed):+.2f}% ~ {max(per_seed):+.2f}%）'
              f'　相異值 {_uniq}/{N_SEEDS}{_warn}')

    # 🚨 退化守衛：若各組的 20 個 seed 全給同一個數字，代表 5 檔上限從未綁定
    #    ⇒ 隨機排序不起作用 ⇒ 符號檢定讀到的是「同一個數字抄 20 次」，
    #      會印出 20/20 與 p<0.001，看起來極顯著但其實只有 1 個觀測。
    #    這與 10/07 的「錯誤二」同一族（把退化情形印成顯著），必須明講。
    _degen = [lb for lb, v in curves.items() if len({round(x, 6) for x in v}) == 1]
    if _degen:
        print(f'''
  🚨 **配對檢定無效**：以下組別的 {N_SEEDS} 個 seed 給出完全相同的 alpha
     ⇒ 5 檔上限從未綁定（候選股太少），隨機排序不起作用
     ⇒ 下面的符號檢定是「同一個數字抄 {N_SEEDS} 次」，**p 值不可讀**。''')
        for lb in _degen:
            print(f'       • {lb}')
        print('     （宇宙夠大時這個守衛不會觸發；觸發了就是宇宙或門檻的問題）')

    print('\n  配對比較（Δ = 後者 − 前者，正值 = 篩選有幫助）：')
    pairs = [('B3 A1＋YoY 產業內 前1/3', 'A1 現行策略（限有營收資料）', '★ B3 vs A1'),
             ('B2 A1＋YoY 產業內 ≥ 中位', 'A1 現行策略（限有營收資料）', '  B2 vs A1'),
             ('★C A1＋YoY 產業內 後1/3（反向）', 'A1 現行策略（限有營收資料）', '★ C（反向）vs A1'),
             ('B3 A1＋YoY 產業內 前1/3', '★C A1＋YoY 產業內 後1/3（反向）', '★★ B3 vs C（前後1/3對決）')]
    for a, b, name in pairs:
        if a not in curves or b not in curves:
            continue
        diffs = [x - y for x, y in zip(curves[a], curves[b])]
        w, n, ties, p = sign_test(diffs)
        _bad = (a in _degen) or (b in _degen)
        mark = ('🚨' if _bad else
                '✅' if (p < 0.05 and w > n / 2) else
                '❌' if (p < 0.05) else '⚪')
        print(f'  {name:<34}Δ中位 {stt.median(diffs):+.2f}pp'
              f'　{mark} {w}/{n}　p={p:.3f}'
              + (f'　平手 {ties}' if ties else '')
              + ('　← 退化，p 不可讀' if _bad else ''))

    print('\n' + '=' * 92)
    print('""" 讀這張表之前必須知道的四件事（引用時一起講）')
    print('=' * 92)
    print('''
  1. **基本面 25% 在 2026-05 之前是預設值 50**（陷阱44，永久）⇒ 評分實質是
     「技術40% ＋ 籌碼35% ＋ 常數」。「65 分」在這段樣本與今天不是同一個篩選器。
  2. **除權息無法調整**（陷阱50）。B 組偏向高成長股（低殖利率、除息拖累小）
     ⇒ **這個偏誤的方向對 B 組有利**。若 B3 只小勝，要先懷疑是這個。
  3. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。
  4. ★C（反向）是判真偽的關鍵：**B3 好而 C 差 → 真訊號；兩者一樣 → 雜訊。**
     只看 B3 vs A1 會把「篩掉交易」本身的效果誤認為 YoY 的效果。''')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if cmd == 'cache':
        _ch = (int(sys.argv[sys.argv.index('--chunk') + 1])
               if '--chunk' in sys.argv else None)
        build_cache(chunk=_ch, merge='--merge' in sys.argv,
                    pit='--pit' in sys.argv)
    else:
        run()
