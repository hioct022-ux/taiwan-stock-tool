"""
組合層級回測：「同時最多持 N 檔 + 依某個鍵挑選」到底有沒有用（2026-09-17）

═══ 背景 / 要驗證的問題 ═══
使用者提問：「若採大盤應許進場，以最高分最高波動的持股購入 5 檔，相信系統而進場，
結果會如何？」

這句話其實包含**三個互相獨立的元素**，必須分開測，否則會把三者的效果混在一起：

  A. 大盤評分四段門檻階梯　→ 已測（2026-09-10，alpha +2.33%，結論「維持現狀」）
  B. **同時最多持 5 檔**　　→ **從沒測過**。正好就是十五章「單日進場集中度」那則
                              標著「尚未設計對策」的風險（2026-08-14 單日進場 15 檔、
                              整批平均 -4.28%）。5 檔上限就是那個對策。
  C. **波動度當排序鍵**　　→ 相關性測過（corr(vol,損益)=0.053，幾乎無關），
                              但「拿它當排序鍵挑股」沒測過。已知高波動組勝率最低
                              （50.4%/53.3%/44.0%），先驗不佳。

═══ 為什麼要另外寫腳本（不改 backtest_stocks.py）═══
`_run_backtest()` 是 **per-stock 迴圈**——每檔股票各自跑完整條時間軸、各自持有。
這個結構**無法表達「同時最多持 N 檔」**，因為那是組合層級的限制，需要在
「同一個時間點」比較所有候選股。所以改成兩段式：

  第一段（本檔 build_cache）：逐股逐日算出評分與波動度，存成快取。
        評分不依賴組合狀態，所以可以先算完。這段最貴（~87檔 × ~500日 full_score）。
  第二段（simulate）：依日期重播，維護一個 ≤N 檔的投資組合，
        每天先處理出場、再用剩餘空位從候選中依排序鍵挑股。

═══ 對照組設計（關鍵）═══
依十五章立下的規矩——**「按某變數挑選」必須加測一個中性對照，把該變數換掉**，
否則會把「5檔上限」的效果誤記在「排序鍵」頭上：

  A 基準：現行階梯，**無檔數上限**（＝ 2026-09-10 Q3 的那 242 筆）
  B 5檔 + 依評分高→低
  C 5檔 + 依評分高→低，同分再依波動高→低   ← 最貼近使用者提案
  D 5檔 + 純依波動高→低
  E 5檔 + 純依波動低→高（反向對照）
  F 5檔 + **依股票代號排序**（中性對照：測「5檔上限」本身的貢獻，與排序鍵無關）

**F 是整份腳本最重要的一組。** 若 B~E 都跟 F 差不多，代表有效的是「限檔數」
而不是「怎麼挑」——就跟停損校準那次「vol×3.0 vs 固定10%」一模一樣。

═══ 使用方式 ═══
  python3 backtest_portfolio_slots.py cache    # 第一段，建快取（慢，數分鐘）
  python3 backtest_portfolio_slots.py          # 第二段，跑六組對照（快）

  sandbox 環境請先把 *.py 與 data/stock.db 複製到 /tmp 再跑（FUSE+SQLite 極慢）。
"""
import sys, os, pickle, statistics as stt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_stocks as bs
from database import (get_watchlist, get_prices, get_fundamentals,
                      get_chips, get_ownership)
from scorer import full_score

CACHE        = '/tmp/_pf_slots_cache.pkl'
CACHE_MARKET = '/tmp/_pf_slots_cache_market.pkl'

# ── 全市場宇宙的篩選條件（2026-09-23 新增，見下方 build_cache 的說明）──
UNI_MIN_TURNOVER = 5e7      # 近一年日均成交金額 ≥ 5,000 萬元
UNI_SINCE        = '2025-09-01'
UNI_MIN_DAYS     = 180


def market_universe(conn, min_turnover=UNI_MIN_TURNOVER):
    """
    全市場回測用的標的宇宙：上市普通股 + 流動性門檻。

    ⚠️ 三道篩選都是刻意的：
      1. `market='TWSE'` —— 籌碼（T86）不含上櫃，放上櫃進來會讓 35% 權重
         變成預設值 50，重演 2026-09-17 那個「同一個 65 分在不同子樣本
         指的不是同一件事」的坑。
      2. 4 碼數字且非 `00` 開頭 —— 排除 ETF、權證、特別股、存託憑證。
         ETF 的評分沒有意義（籌碼與基本面欄位語意不同）。
      3. 日均成交金額門檻 —— 冷門股的回測成交價不現實（掛單就跑掉），
         把它們算進 alpha 等於在統計一批永遠買不到的交易。
         實測分布：中位數 0.36 億，≥0.5 億剩 510 檔。
    """
    mk = dict(conn.execute("SELECT code, market FROM stocks").fetchall())
    rows = conn.execute(
        "SELECT code, AVG(value) av, COUNT(*) n FROM prices "
        "WHERE date>=? AND code!='TAIEX' GROUP BY code HAVING n>=?",
        (UNI_SINCE, UNI_MIN_DAYS)).fetchall()
    return sorted(r[0] for r in rows
                  if r[1] and r[1] >= min_turnover
                  and mk.get(r[0]) == 'TWSE'
                  and len(r[0]) == 4 and r[0].isdigit()
                  and not r[0].startswith('00'))

MIN_HISTORY     = bs.MIN_HISTORY
HOLD_DAYS       = bs.HOLD_DAYS
STOP_LOSS_RATIO = bs.STOP_LOSS_RATIO
RENEW_THRESHOLD = bs.SCORE_THRESHOLD      # 續抱門檻固定 65，與策略C 一致

# 現行 UI 四段階梯（與 backtest_market_score.BUCKETS 同一份規則）
def ms_from_net(net):
    return max(0, min(100, 50 - net * 5))

def make_ladder_fn(market_net):
    """回傳 threshold_fn(date) -> int | None，None = 該日停止進場。"""
    def fn(d):
        ms = ms_from_net(market_net.get(d, 0))
        if ms >= 70: return 65
        if ms >= 55: return 70
        if ms >= 45: return 75
        return None
    return fn


def _vol20(closes):
    """近20日日報酬標準差。⚠️ 刻意用 close 反推，不信任 change_pct（陷阱35）。"""
    if len(closes) < 21:
        return None
    rets = [(closes[i] - closes[i-1]) / closes[i-1] * 100
            for i in range(len(closes) - 20, len(closes)) if closes[i-1]]
    return stt.pstdev(rets) if len(rets) >= 2 else None


# ════════════════ 第一段：建快取 ════════════════
def build_cache(universe='watchlist'):
    """
    universe='watchlist' → 87 檔自選股（原行為，存 CACHE）
    universe='market'    → 全市場上市普通股（存 CACHE_MARKET）

    ═══ 為什麼要有 market 模式（2026-09-23）═══
    現行回測 n=243，**雜訊帶 2.76pp**——任何小於它的真實效果都看不見。
    9/17 測「65 分門檻」、9/23 測「大盤評分」與「評分的領先性」，
    三次都卡在同一件事：**分不出是效果還是運氣**。

    樣本數 = 時間 × 標的數。時間那一維走不通（實測 0.47 筆/交易日，
    要壓到 1.5pp 還要 8.1 年）。標的數則可以立刻放大 6 倍。

    而且對「評分能不能挑出好股」這個問題，**用全市場比用自選股更對**——
    自選股是已經人工精選過的，等於在一群好學生裡面比高下。

    前置條件（2026-09-23 當天完成）：`backfill_prices_history.py`
    補了 439 個交易日的全市場價格（56 萬列），否則全市場股票只有 87 天歷史，
    `pos_250`/`ma240` 會靜默退化（陷阱32）。
    """
    print('計算大盤訊號（S1–S8 逐日回溯）...')
    market_net = bs._build_market_signals()
    tpx = get_prices('TAIEX', days=600)
    tpx_close = {p['date']: p['close'] for p in tpx}
    tpx_dates = [p['date'] for p in tpx]

    if universe == 'market':
        from database import get_conn
        conn = get_conn()
        codes = market_universe(conn)
        names = dict(conn.execute("SELECT code, name FROM stocks").fetchall())
        conn.close()
        wl = [{'code': c, 'name': names.get(c, c)} for c in codes]
        out_path = CACHE_MARKET
        print(f'宇宙：全市場上市普通股，日均成交 ≥ {UNI_MIN_TURNOVER/1e8:.2f} 億 → {len(wl)} 檔')
    else:
        wl = get_watchlist()
        out_path = CACHE

    stocks = {}
    print(f'逐股逐日計算評分與波動度（{len(wl)} 檔）...')
    for n, s in enumerate(wl, 1):
        code, name = s['code'], s['name']
        prices    = get_prices(code, days=600)
        if len(prices) < MIN_HISTORY + HOLD_DAYS + 2:
            continue
        fund_all  = get_fundamentals(code, days=600)
        chips_all = get_chips(code, days=600)
        own_raw   = get_ownership(code)
        ownership = {'foreign': own_raw['foreign_pct']} if own_raw else {'foreign': 52}

        score_by_date, vol_by_date = {}, {}
        # 2026-09-17 加：三個分項一併存。`full_score()` 本來就回傳
        # fund_score / tech_score / chip_score（權重 25%/40%/35%），
        # 舊版快取只留 total_score，導致「總分沒鑑別度，分項呢？」問不下去。
        parts_by_date = {}
        for i in range(MIN_HISTORY, len(prices) - 1):
            d = prices[i]['date']
            fund_slice  = [r for r in fund_all  if r['date'] <= d]
            chips_slice = [r for r in chips_all if r['date'] <= d][-65:]
            r = full_score(prices[:i+1], fund_slice, chips_slice, ownership)
            if r:
                score_by_date[d] = r['total_score']
                parts_by_date[d] = (r.get('tech_score'), r.get('chip_score'),
                                    r.get('fund_score'))
            v = _vol20([p['close'] for p in prices[max(0, i-20):i+1]])
            if v is not None:
                vol_by_date[d] = v
        # ⚠️ 只留模擬會用到的欄位。全市場 510 檔 × 527 列，
        #    整份 dict 存下來會讓 pickle 膨脹好幾倍且吃光記憶體。
        slim = [{'date': p['date'], 'open': p['open'], 'high': p['high'],
                 'low': p['low'], 'close': p['close']} for p in prices]
        stocks[code] = {
            'name': name, 'prices': slim,
            'idx': {p['date']: k for k, p in enumerate(slim)},
            'score': score_by_date, 'vol': vol_by_date,
            'parts': parts_by_date,        # {date: (tech, chip, fund)}
        }
        if n % 25 == 0 or n == len(wl):
            print(f'  [{n}/{len(wl)}] {code} {name}　{len(score_by_date)} 個評分點')

    with open(out_path, 'wb') as f:
        pickle.dump({'market_net': market_net, 'tpx_close': tpx_close,
                     'tpx_dates': tpx_dates, 'stocks': stocks,
                     'universe': universe}, f)
    print(f'\n✅ 快取已存 {out_path}（{len(stocks)} 檔）')


# ════════════════ 第二段：組合模擬 ════════════════
def simulate(cache, rank_key, max_positions, label, score_filter=None):
    """
    rank_key      : callable(code, date, stocks) -> 排序用的 tuple（小的先選）
    max_positions : None = 無上限（＝現行回測行為）
    score_filter  : None = 照階梯門檻（sc >= thr）；
                    給 callable(sc) -> bool 則**取代**門檻判斷，
                    用來測「進場評分落在某個區間」會怎樣（backtest_score_bands.py 用）。
                    ⚠️ `<45 停止進場` 那條規則**仍然生效**，只換掉個股門檻這一項。
    """
    stocks     = cache['stocks']
    market_net = cache['market_net']
    thr_fn     = make_ladder_fn(market_net)
    dates      = cache['tpx_dates']

    held, trades = {}, []

    for d in dates:
        # ── 1. 出場檢查（先做，才會空出當日可用的名額）──
        for code in list(held.keys()):
            st_ = stocks[code]
            i = st_['idx'].get(d)
            if i is None:            # 該股當日無資料，略過（不推進持有天數）
                continue
            p   = st_['prices'][i]
            pos = held[code]
            ep  = pos['entry_price']
            stop = ep * STOP_LOSS_RATIO

            if p['low'] <= stop:
                pos.update(exit_date=d, exit_price=stop, exit_reason='停損',
                           pnl=(stop - ep) / ep * 100)
                trades.append(pos); del held[code]; continue

            if i - pos['entry_idx'] >= HOLD_DAYS:
                sc = st_['score'].get(d, 0)
                if sc >= RENEW_THRESHOLD:        # 續抱（策略C）
                    pos['entry_idx'] = i
                    pos['renewed'] = pos.get('renewed', 0) + 1
                    continue
                pos.update(exit_date=d, exit_price=p['close'],
                           exit_reason=f'持滿{HOLD_DAYS}日', pnl=(p['close'] - ep) / ep * 100)
                trades.append(pos); del held[code]

        # ── 2. 進場 ──
        thr = thr_fn(d)
        if thr is None:
            continue
        free = (10**9) if max_positions is None else max_positions - len(held)
        if free <= 0:
            continue

        cands = []
        for code, st_ in stocks.items():
            if code in held:
                continue
            i = st_['idx'].get(d)
            if i is None or i + 1 >= len(st_['prices']):
                continue
            sc = st_['score'].get(d)
            if sc is None:
                continue
            if score_filter is None:
                if sc < thr:
                    continue
            elif not score_filter(sc):
                continue
            cands.append(code)

        cands.sort(key=lambda c: rank_key(c, d, stocks))
        for code in cands[:free]:
            st_ = stocks[code]
            i   = st_['idx'][d]
            eb  = st_['prices'][i + 1]
            held[code] = {
                'code': code, 'name': st_['name'], 'score': st_['score'][d],
                'vol': st_['vol'].get(d), 'signal_date': d,
                'entry_date': eb['date'], 'entry_price': eb['close'],
                'entry_idx': i + 1, 'renewed': 0,
            }

    # 收尾：回測結束時仍持有的部位以最後一根K平倉
    for code, pos in held.items():
        last = stocks[code]['prices'][-1]
        pos.update(exit_date=last['date'], exit_price=last['close'],
                   exit_reason='回測結束',
                   pnl=(last['close'] - pos['entry_price']) / pos['entry_price'] * 100)
        trades.append(pos)

    return label, trades


def stat(trades, tpx_close):
    if not trades:
        return None
    pnls = [t['pnl'] for t in trades]
    mkts = []
    for t in trades:
        a, b = tpx_close.get(t['entry_date']), tpx_close.get(t['exit_date'])
        mkts.append((b - a) / a * 100 if a and b else 0)
    n = len(trades)
    return {
        'n': n,
        'win': sum(1 for p in pnls if p > 0) / n * 100,
        'ret': sum(pnls) / n,
        'mkt': sum(mkts) / n,
        'alpha': sum(pnls) / n - sum(mkts) / n,
        'stop': sum(1 for t in trades if t['exit_reason'] == '停損') / n * 100,
        'vol': stt.mean([t['vol'] for t in trades if t.get('vol')]) if any(t.get('vol') for t in trades) else 0,
    }


def main(path=CACHE):
    if not os.path.exists(path):
        print(f'找不到快取，請先執行：python3 {os.path.basename(__file__)} cache')
        return
    with open(path, 'rb') as f:
        cache = pickle.load(f)
    S, tpx = cache['stocks'], cache['tpx_close']

    # 排序鍵：回傳 tuple，**小的先被選**，所以「高→低」要取負號
    keys = [
        ('A 基準：現行階梯，不限檔數',      lambda c, d, s: (c,),                              None),
        ('B 5檔・依評分高→低',             lambda c, d, s: (-s[c]['score'][d], c),            5),
        ('C 5檔・評分高→低，同分波動高→低', lambda c, d, s: (-s[c]['score'][d],
                                                          -(s[c]['vol'].get(d) or 0), c),    5),
        ('D 5檔・純依波動高→低',           lambda c, d, s: (-(s[c]['vol'].get(d) or 0), c),   5),
        ('E 5檔・純依波動低→高（反向）',    lambda c, d, s: ((s[c]['vol'].get(d) or 999), c),  5),
        ('★F 5檔・依代號（中性對照）',      lambda c, d, s: (c,),                              5),
    ]

    print('=' * 96)
    print('組合層級：「同時最多持 N 檔 + 排序鍵」對照表')
    print('=' * 96)
    print(f'{"規則":30}{"筆數":>6}{"勝率":>8}{"報酬":>9}{"同期大盤":>10}{"alpha":>9}{"停損率":>8}{"均波動":>8}')
    print('-' * 96)
    rows = []
    for label, fn, cap in keys:
        _, tr = simulate(cache, fn, cap, label)
        s = stat(tr, tpx)
        rows.append((label, s, tr))
        print(f'{label:30}{s["n"]:>6}{s["win"]:>7.1f}%{s["ret"]:>+8.2f}%'
              f'{s["mkt"]:>+9.2f}%{s["alpha"]:>+8.2f}%{s["stop"]:>7.1f}%{s["vol"]:>8.2f}')

    base = rows[0][1]
    neutral = rows[-1][1]
    print()
    print('※ 與中性對照 F（同樣限5檔、但用代號排序）的差距，才是「排序鍵」自己的貢獻：')
    for label, s, _ in rows[1:-1]:
        print(f'   {label:30} alpha {s["alpha"]:+.2f}%　vs F {neutral["alpha"]:+.2f}%'
              f'　→ 排序鍵貢獻 {s["alpha"] - neutral["alpha"]:+.2f}pp')
    print(f'\n※ 「5檔上限」本身的貢獻＝ F − A ＝ '
          f'{neutral["alpha"] - base["alpha"]:+.2f}pp（筆數 {neutral["n"]} vs {base["n"]}）')


if __name__ == '__main__':
    args = sys.argv[1:]
    mkt = 'market' in args
    if 'cache' in args:
        build_cache('market' if mkt else 'watchlist')
    else:
        main(CACHE_MARKET if mkt else CACHE)
