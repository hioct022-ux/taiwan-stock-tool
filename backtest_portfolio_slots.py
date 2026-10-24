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
import sys, os, pickle, random, statistics as stt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_stocks as bs
from database import (get_watchlist, get_prices, get_fundamentals,
                      get_chips, get_ownership)
from scorer import full_score

def cache_dir():
    """
    快取目錄。預設 `/tmp`（維持既有行為），但可用環境變數 `TWSTOOL_CACHE` 改掉。

    ★ 2026-10-21 加這個開關的原因：**/tmp 會被清掉。**
      10/16~10/18 的交叉驗證跑在本機的 `_pf_slots_cache_market.pkl` 上，
      10/21 要重用時整個不見了 ⇒ 一份 20~40 分鐘的快取白建。
      CLAUDE.md 早就把「所有快取都在 /tmp」標成已知的結構問題，這次它咬到了。

      放 /tmp 本身是對的（100MB+ 的 pickle 不該進 git），但**跨天重用的快取
      要放在不會被清的地方**。建議：
        export TWSTOOL_CACHE=~/台股分析工具/data/cache
      （`data/cache/` 已加進 .gitignore）

      ⚠️ 建快取與跑測試**必須用同一個值**，否則會「找不到快取」然後重建。
         所以所有讀寫快取的腳本都會把解析後的路徑印出來。
    """
    d = os.environ.get('TWSTOOL_CACHE', '/tmp')
    os.makedirs(d, exist_ok=True)
    return d


CACHE        = os.path.join(cache_dir(), '_pf_slots_cache.pkl')
CACHE_MARKET = os.path.join(cache_dir(), '_pf_slots_cache_market.pkl')

# ── 全市場宇宙的篩選條件（2026-09-23 新增，見下方 build_cache 的說明）──
UNI_MIN_TURNOVER = 5e7      # 近一年日均成交金額 ≥ 5,000 萬元
UNI_SINCE        = '2025-09-01'
UNI_MIN_DAYS     = 180

# ── 點時間宇宙（2026-10-21 新增，見 pit_universe 的說明）──
PIT_LOOKBACK = 130          # 回看幾個交易日算流動性（與 backtest_structure_bear 一致）
PIT_MIN_DAYS = 60           # 回看窗內至少要有幾天有成交
PIT_START    = '2018-01-01'


def listed_codes(conn):
    """
    上市普通股的集合——**判準是「有 chips」，不是查 stocks 表。**

    ★ 2026-10-21 新增。`stocks` 是**今天的掛牌清單**，所以
      「`mk.get(code)=='TWSE'`」這個寫法會把 2018 之後退場的股票
      整批判成非上市 ⇒ 它們從來沒有進過任何回測的宇宙。
      實測：`prices` 裡 2018 起的 4 碼普通股有 2,040 檔，
      其中 **73 檔在 `stocks` 查不到**（21 檔達流動性門檻、18 檔是歷史退場），
      含 **6452 康友-KY**（2020-08 財報造假下市，日均成交 2.89 億，完全達標）。

    `chips` 的來源是 TWSE T86，而 **T86 只收上市** ⇒ 「有 chips」是一個
    不依賴「今天的狀態」的乾淨判準。實測對照：
      18/18 已退場股都有 chips（2017-12 起）；
      上櫃 6488／3324／4979 的 chips 筆數 = 0 / 0 / 0。
    """
    return set(r[0] for r in conn.execute(
        "SELECT DISTINCT code FROM chips "
        "WHERE length(code)=4 AND code GLOB '[0-9][0-9][0-9][0-9]' "
        "AND code NOT LIKE '00%'"))


def pit_universe(conn, min_turnover=UNI_MIN_TURNOVER, start=PIT_START):
    """
    **點時間宇宙**：每月第一個交易日依「過去 PIT_LOOKBACK 日的流動性」重算。
    回傳 (months, union)：
      months = [(該月第一個交易日, tuple(codes)), ...]   ← 升序
      union  = sorted(所有月份的聯集)                    ← 快取要算的檔數

    ═══ 為什麼需要它（2026-10-21）═══
    `market_universe()` 用的是 `UNI_SINCE='2025-09-01'` 起的日均成交
    ⇒ **任何在那之前消失的股票，`n>=180` 必然不成立**，一律被排除。
    這不是流動性篩選，是「用今天的狀態定義過去的宇宙」——
    與 2026-09-24 那條「回測宇宙的組成時間必須早於回測期間的起點」
    是同一條通則，只是那次出現在**自選股**、這次出現在**股票母體**。

    ⚠️ 連帶更正：`backtest_structure_bear.py` 的 `uni_at` 雖然叫
    「point-in-time 宇宙」，但它的成員資格仍然是 `mk.get(code)=='TWSE'`
    ⇒ **10/07 與 10/08 那兩節也漏掉同一批股票**，只做對了「時間」那一半。

    ⚠️ 已知邊界：**全市場個股價格只回填到 2018-01-02**（TAIEX 有 2016-10，
    個股沒有）⇒ 2018 年前 60 個交易日湊不滿回看窗，2018 的月宇宙
    平均只有 192 檔（2019 起 265~496 檔）。那不是 bug，是價格涵蓋的邊界；
    **解讀 2018 的差異時要把這一項與 PIT 本身分開**。
    """
    listed = listed_codes(conn)
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' ORDER BY date")]
    i0 = next((i for i, d in enumerate(cal) if d >= start), 0)

    months, prev_m = [], None
    for i in range(i0, len(cal)):
        d = cal[i]
        if d[:7] == prev_m:
            continue
        prev_m = d[:7]
        lo = cal[max(0, i - PIT_LOOKBACK)]
        rows = conn.execute(
            "SELECT code, COUNT(*) k, AVG(value) av FROM prices "
            "WHERE date>=? AND date<? AND code!='TAIEX' "
            "GROUP BY code HAVING k>=? AND av>=?",
            (lo, d, PIT_MIN_DAYS, min_turnover)).fetchall()
        months.append((d, tuple(sorted(r[0] for r in rows if r[0] in listed))))

    union = sorted(set().union(*(set(m[1]) for m in months)) if months else set())
    return months, union


def pit_lookup(months):
    """把 months 轉成 lookup(date) -> frozenset；日期早於第一個月回空集合。"""
    from bisect import bisect_right
    keys = [m[0] for m in months]
    sets = [frozenset(m[1]) for m in months]
    empty = frozenset()

    def fn(d):
        k = bisect_right(keys, d) - 1
        return sets[k] if k >= 0 else empty
    return fn


def assert_pit_has_delisted(conn, union, min_n=10):
    """
    **阻斷式守衛**：點時間宇宙裡必須含有「今天的 `stocks` 表查不到」的股票。

    若為 0，代表上市判準又悄悄退回「查 current listing」——而那個錯誤
    **不會報錯、結果看起來完全正常**（陷阱41/42/45 的共同形狀）。
    所以這裡用 `sys.exit` 而不是印警告（陷阱51 那條「對帳要阻斷式」）。
    """
    cur = set(r[0] for r in conn.execute("SELECT code FROM stocks"))
    gone = sorted(c for c in union if c not in cur)
    print(f'  點時間宇宙 {len(union)} 檔，其中「今天已不在 stocks」的 {len(gone)} 檔'
          f'{"：" + " ".join(gone[:12]) if gone else ""}')
    if len(gone) < min_n:
        print(f'\n🚨 **只有 {len(gone)} 檔已退場股（門檻 {min_n}）** ⇒ 上市判準'
              f'可能退回查 stocks 表，宇宙又變成倖存者。中止。')
        sys.exit(1)
    return gone


def market_universe(conn, min_turnover=UNI_MIN_TURNOVER):
    """
    全市場回測用的標的宇宙：上市普通股 + 流動性門檻。

    🚨 **這支函式帶著倖存者偏誤，新的測試請改用 `pit_universe()`（2026-10-21）。**
       流動性是用 `UNI_SINCE='2025-09-01'` 起的日均成交算的 ⇒ 任何在那之前
       消失的股票 `n>=UNI_MIN_DAYS` 必然不成立，一律被排除；而 `market='TWSE'`
       又是查**今天的** `stocks` 表。兩個條件都擋，後者是決定性的。
       實測被漏掉的有 **18 檔歷史退場股**（含 6452 康友-KY，2020-08 財報造假
       下市、日均成交 2.89 億）。保留本函式**只為了與既有數字對帳**
       （★10%／現行階梯 應跑出 15,169~15,176 筆、alpha +0.31%）。

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
def build_cache(universe='watchlist', days=600, price_win=300):
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
    # ★ 2026-10-14：`days` 參數化。**原本五處全部寫死 600**，
    #   於是 2026-10-08 回填 2018 歷史之後，這支仍然只看 2024-05 起
    #   ——一個空頭年都沒有，而且不報錯。這是陷阱51 那條通則的
    #   **第三次出現**（前兩次：陷阱32 的 calc_all 餵 30 天、
    #   陷阱51 的 _build_market_signals 寫死 600）。
    #
    # ★ `price_win`：傳給 full_score 的價格視窗上限。
    #   原本是 `prices[:i+1]`（整段，對 2,133 筆資料是 O(n²)）。
    #   `calc_all()` 最長只需要 250 筆（pos_250／ma240），取 300 留餘裕。
    #   **2026-10-14 實測 2330：逐日逐欄 2042/2042 完全相同、快 1.4×。**
    #   ⚠️ 若日後新增週期 >300 的指標，這裡必須同步加大（陷阱32）。
    print(f'計算大盤訊號（S1–S8 逐日回溯，days={days}）...')
    market_net = bs._build_market_signals(days=days)
    tpx = get_prices('TAIEX', days=days)
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
        prices    = get_prices(code, days=days)
        if len(prices) < MIN_HISTORY + HOLD_DAYS + 2:
            continue
        fund_all  = get_fundamentals(code, days=days)
        chips_all = get_chips(code, days=days)
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
            r = full_score(prices[max(0, i - price_win + 1):i+1], fund_slice, chips_slice, ownership)
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
def simulate(cache, rank_key, max_positions, label, score_filter=None,
             entry_filter=None, threshold_fn=None, stop_ratio=None,
             pit_at=None, cand_probe=None, renew=None):
    """
    rank_key      : callable(code, date, stocks) -> 排序用的 tuple（小的先選）
    max_positions : None = 無上限（＝現行回測行為）
    score_filter  : None = 照階梯門檻（sc >= thr）；
                    給 callable(sc) -> bool 則**取代**門檻判斷，
                    用來測「進場評分落在某個區間」會怎樣（backtest_score_bands.py 用）。
                    ⚠️ `<45 停止進場` 那條規則**仍然生效**，只換掉個股門檻這一項。
    entry_filter  : None（預設）= 完全不改變行為；
                    給 callable(code, date) -> bool 則在**評分門檻通過之後**
                    再加一道篩選（AND，不取代任何既有條件）。
                    2026-10-14 新增，用來測「現有策略 ＋ 月營收 YoY 篩選」。
                    ★ 刻意設計成「附加」而非「取代」——filter=None 時這支函式
                      與改版前位元級相同，所以**不需要另寫一份 simulate 再對帳**
                      （10/07 那條「給對照組命名要逐條核對現行規則」的通則，
                      最可靠的落實方式就是根本不要有第二份實作）。
    threshold_fn  : None（預設）= 用 `make_ladder_fn()` 的現行 UI 階梯
                    ⇒ **與改版前位元級相同，不需對帳**。
                    給 callable(date) -> int | None 則取代整條大盤規則
                    （回 None = 該日停止進場）。
                    2026-10-15 新增，用來重跑「階梯 vs 固定門檻」的對照
                    ——那批數字原本是在「S4 幾乎是死的」狀態下跑的（陷阱51），
                    而且跑在含後見之明的自選股上（9/24）。
                    ★ 這是「按某變數動態調整參數，必須加測同等平均值的固定值
                      當對照」那條通則（停損校準那節立的）所需要的開關。
    stop_ratio    : None（預設）= 用模組常數 STOP_LOSS_RATIO（現行 0.90）
                    ⇒ **與改版前位元級相同，不需對帳**。
                    給 0.92／0.88… 則取代停損距離。
                    2026-10-16 新增，用來在**空頭樣本**上重驗停損 10%
                    ——8/27 那次校準是自選股（倖存者偏誤，9/24 確認）
                    ＋全多頭，而那節自己寫著「真的崩盤時 10% 會比 8%
                    每檔多賠 2pp，從未驗證」。
    pit_at        : None（預設）= 完全不改變行為 ⇒ **與改版前位元級相同**。
                    給 callable(date) -> set（用 `pit_lookup()` 產生）則
                    **只有當天在點時間宇宙裡的股票才可以進場**。
                    2026-10-21 新增，用來拆開「倖存者偏誤 × 持有長度」
                    ——10/18 標著最嚴重的那條限制。

                    ★ 刻意只擋**進場**、不強制出場：點時間宇宙回答的是
                      「那一天你買得到嗎」，不是「現在還該不該持有」。
                      已持有的部位照既有規則（停損／到期）走完。
    cand_probe    : None（預設）= 不做任何事 ⇒ **與改版前位元級相同**。
                    給 callable(date, n_cands, free) 則在候選算完、尚未依
                    `rank_key` 排序取前 `free` 名之前呼叫一次。
                    2026-10-22 新增，用來量 10/14 立的那個便宜判準
                    ——「**單日候選 ≥ 槽位數的天數比例**」。
                    它回答的是「篩選器是不是篩太兇、讓槽位填不滿」，
                    而那件事**只有在組合層級看得見**（per-trade 層級只統計
                    已經成交的交易，看不到閒置的槽位）。

                    ⚠️ `n_cands` 已排除「當天已持有」的股票，所以它是
                      「**還能再買幾檔可選**」，不是「達標幾檔」。
    renew         : None（預設）= 用模組常數 `RENEW_THRESHOLD`（現行 65）
                    ⇒ **與改版前位元級相同**。
                    給數字（60／55／50…）⇒ 取代續抱門檻。
                    給 `'profit'` ⇒ **到期時只要仍獲利就續抱**（不看評分），
                    與 `backtest_structure_bear.py` 的「續抱代理」同一條規則。
                    給 `('rand', p, salt)` ⇒ **★★ 中性對照**：到期時以固定機率
                    p 續抱、**完全不看任何資訊**，只為了把持有長度拉到與
                    被測規則相同。續抱決定由 `(salt, code, i)` 決定，
                    **與排序用的 seed 無關** ⇒ 100 條配對之間共用同一組
                    續抱決定，配對的差額只來自排序運氣，不會混進
                    「對照組自己也在隨機」這第二個噪音源。
                    2026-10-23 新增。
                    給 `('shuffle', thr, salt)` ⇒ **★★★ 決定性的中性對照**：
                    用**別人的評分**當續抱依據（每檔固定指派到另一檔）。
                    ⇒ 出場的**時機分布、自相關、橫斷面分布全部保留**，
                    但對這一檔完全沒有資訊。
                    2026-10-24 新增，起因見十五章「放寬續抱條件」那節：
                    `('rand', p)` 只對齊了「平均持有長度」，沒對齊
                    「出場時機的分布」——固定危險率會**隨機砍掉正在複利的
                    贏家**，而真規則的出場是罕見事件。那個沒對齊的維度
                    足以製造一個假的 ✅（實測 N30 vs R995 是 85/100、
                    p=0.000，但同一輪的排序顯示「評分用得越少優勢越大」
                    ⇒ 與「評分有資訊」直接矛盾）。

                    ═══ 為什麼要測這個 ═══
                    10/07 的結構測試量到**續抱是整個結構裡最強的一項**
                    （換手 1,102→57 次、Δ報酬 +169pp、20/20）；
                    10/18 的資金曲線又量到**一個完全沒有資訊的隨機數，
                    只要同樣拉長持有期，就能拿到大部分的效果**
                    （R50a vs A1 = +493pp、20/20）。
                    兩條獨立的路指向同一件事：**「抱更久」本身就是效果來源，
                    而那不需要月營收、也不必動 `scorer.py`。**

                    ⚠️ 解讀時必須用**資金曲線**，不是 per-trade alpha
                      ——放寬續抱會改變持有長度，而 per-trade alpha 沒有
                      除以持有天數 ⇒ 抱久一點 alpha 自然變大（10/18 的教訓）。
                    ⚠️ 中性對照必須在**持有長度**這一維對齊，而且要跑
                      **兩個隨機實現**（單一實現的噪音足以翻轉判定）。
    """
    stocks     = cache['stocks']
    market_net = cache['market_net']
    thr_fn     = threshold_fn if threshold_fn is not None else make_ladder_fn(market_net)
    dates      = cache['tpx_dates']

    _sr = STOP_LOSS_RATIO if stop_ratio is None else stop_ratio
    # renew=None ⇒ 與改版前完全相同的那一條路；其餘三種分支見 docstring
    _rn_profit = (renew == 'profit')
    _rn_rand   = isinstance(renew, tuple) and renew and renew[0] == 'rand'
    _rn_p, _rn_salt = (renew[1], renew[2]) if _rn_rand else (None, None)
    # ★★★ ('shuffle', thr, salt)：用**別人的評分**當續抱依據（2026-10-24）
    #   把每檔股票指派到另一檔（固定的隨機置換），續抱時查那一檔的評分。
    #   ⇒ 出場同樣是「罕見、成群出現」（分布／自相關／橫斷面都保留），
    #     但對**這一檔**完全沒有資訊。這是 ('rand', p) 配不上的那個維度。
    _rn_shuf = isinstance(renew, tuple) and renew and renew[0] == 'shuffle'
    _rn_map = None
    if _rn_shuf:
        _rn_thr_s = renew[1]
        _keys = sorted(stocks)                      # ⚠️ sorted（10/16 的 bug）
        _shuf = list(_keys)
        random.Random(f'shuffle|{renew[2]}').shuffle(_shuf)
        # 避免自我指派（那等於沒打亂）：與下一個互換
        for _i, _c in enumerate(_shuf):
            if _c == _keys[_i]:
                _j = (_i + 1) % len(_shuf)
                _shuf[_i], _shuf[_j] = _shuf[_j], _shuf[_i]
        _rn_map = dict(zip(_keys, _shuf))
    _rn_thr    = (RENEW_THRESHOLD if (renew is None or _rn_profit or _rn_rand
                                      or _rn_shuf)
                  else renew)
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
            stop = ep * _sr

            if p['low'] <= stop:
                pos.update(exit_date=d, exit_price=stop, exit_reason='停損',
                           pnl=(stop - ep) / ep * 100)
                trades.append(pos); del held[code]; continue

            if i - pos['entry_idx'] >= HOLD_DAYS:
                sc = st_['score'].get(d, 0)
                # ★ 續抱判斷。`'profit'` 那條**刻意用收盤價與最初進場價比**
                #   （不是與本輪起算價比）——與 `renew_position()` 的語意一致：
                #   續抱只重設計時起點，不動 `entry_price`（陷阱47）。
                if _rn_shuf:
                    # 查「別人的」評分；那一檔當日沒資料就視為不續抱（與
                    # `st_['score'].get(d, 0)` 的既有慣例一致）
                    _other = stocks[_rn_map[code]]['score'].get(d, 0)
                    _keep = _other >= _rn_thr_s
                elif _rn_rand:
                    # ★★ 中性對照：以固定機率 p 續抱，**完全不看任何資訊**。
                    #    決定值由 (salt, code, i) 決定 ⇒ 與 `pref` 的 seed 無關
                    #    ⇒ 100 條配對共用同一組續抱決定，配對只差在排序運氣。
                    _keep = random.Random(f'{_rn_salt}|{code}|{i}').random() < _rn_p
                elif _rn_profit:
                    _keep = p['close'] > ep
                else:
                    _keep = sc >= _rn_thr
                if _keep:                        # 續抱（策略C）
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

        pit_set = None if pit_at is None else pit_at(d)

        cands = []
        for code, st_ in stocks.items():
            if code in held:
                continue
            if pit_set is not None and code not in pit_set:
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
            if entry_filter is not None and not entry_filter(code, d):
                continue
            cands.append(code)

        if cand_probe is not None:
            cand_probe(d, len(cands), free)

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


def stat(trades, tpx_close, key='pnl'):
    """
    key='pnl'      ：未調整收盤價的報酬 ← **預設，與既有所有回測數字同基準**
    key='pnl_div'  ：除息調整後（需先跑 `exdiv.adjust_trades()`）

    🚨 `key='pnl_div'` 時回傳的 `alpha`／`ret`／`mkt` **不可拿去跟既有數字並列**：
       TAIEX 也是價格指數、同樣不含股利，只調整個股那一邊 ⇒ alpha 會憑空多出
       整個市場的殖利率（台股約 3~4%/年）。**它只能用在「兩組相減」**
       （兩組同基準 ⇒ 市場項精確消掉）。完整說明見 `exdiv.py` 的 docstring。
    """
    if not trades:
        return None
    pnls = [t.get(key, t['pnl']) for t in trades]
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


def _selftest_pit():
    """
    `pit_at` 的自我測試——**成對造情境**（照 2026-10-07 那條通則：
    只驗「有效果」那一邊，可能是方法把真訊號也殺掉了）。

      ① pit_at=None            ← 基準
      ② pit_at=「全部都在」      ← 必須與 ① **完全相同**（位元級）
      ③ pit_at=「排除某一檔」    ← 那一檔必須消失，其餘必須保留

    另外驗 `pit_lookup()` 的 bisect：日期早於第一個月 ⇒ 空集合（不可進場）。
    """
    import random
    print('=' * 60)
    print('pit_at 自我測試（合成資料）')
    print('=' * 60)

    rnd = random.Random(1234)
    dates = [f'2020-{m:02d}-{d:02d}' for m in range(1, 7) for d in range(1, 21)]
    codes = [f'{1000+k}' for k in range(8)]
    stocks = {}
    for k, c in enumerate(codes):
        px, cur = [], 100.0 + k
        for d in dates:
            cur *= 1 + rnd.uniform(-0.02, 0.025)
            px.append({'date': d, 'open': cur, 'high': cur * 1.01,
                       'low': cur * 0.995, 'close': cur})
        # ⚠️ 評分刻意浮動：若全給 80 分，續抱門檻 65 永遠成立 ⇒ 只會有
        #    最初那幾筆（實測 3 筆），identity 檢查幾乎沒有鑑別力。
        stocks[c] = {'name': c, 'prices': px,
                     'idx': {p['date']: i for i, p in enumerate(px)},
                     'score': {d: rnd.choice([40, 55, 68, 72, 85]) for d in dates},
                     'vol': {}, 'parts': {}}
    cache = {'stocks': stocks, 'market_net': {d: -5 for d in dates},
             'tpx_dates': dates,
             'tpx_close': {d: 10000.0 for d in dates}}
    rk = lambda c, d, s: c

    def sig(trades):
        return sorted((t['code'], t['entry_date'], round(t['pnl'], 9))
                      for t in trades)

    _, t1 = simulate(cache, rk, 3, 'base')
    allset = frozenset(codes)
    _, t2 = simulate(cache, rk, 3, 'all', pit_at=lambda d: allset)
    ok2 = sig(t1) == sig(t2)
    print(f'② 「全部都在」與基準相同：{"✅" if ok2 else "🚨 不同"}'
          f'（{len(t1)} vs {len(t2)} 筆）')

    drop = codes[0]
    sub = frozenset(c for c in codes if c != drop)
    _, t3 = simulate(cache, rk, 3, 'drop', pit_at=lambda d: sub)
    gone = all(t['code'] != drop for t in t3)
    had  = any(t['code'] == drop for t in t1)
    print(f'③ 排除 {drop}：基準有它={had}　排除後沒有它={gone}　'
          f'{"✅" if (had and gone) else "🚨"}')

    # ④ pit_lookup 的 bisect 邊界
    fn = pit_lookup([('2020-03-02', ('1001', '1002')),
                     ('2020-05-04', ('1003',))])
    b = [(fn('2020-01-15') == frozenset(), '早於第一個月 ⇒ 空集合'),
         (fn('2020-03-02') == frozenset({'1001', '1002'}), '當月第一天'),
         (fn('2020-04-30') == frozenset({'1001', '1002'}), '沿用上一個月'),
         (fn('2020-05-04') == frozenset({'1003'}), '換月'),
         (fn('2026-12-31') == frozenset({'1003'}), '最後一個月之後')]
    for okk, lab in b:
        print(f'④ pit_lookup {lab}：{"✅" if okk else "🚨"}')

    # ⑤ renew 參數（2026-10-23）——同樣成對驗，不只驗「有效果」那一邊
    _, t5a = simulate(cache, rk, 3, 'renew=None')
    _, t5b = simulate(cache, rk, 3, 'renew=65', renew=RENEW_THRESHOLD)
    ok5 = sig(t5a) == sig(t5b)
    print(f'⑤ renew=None 與 renew={RENEW_THRESHOLD} 相同：'
          f'{"✅" if ok5 else "🚨 不同"}（{len(t5a)} vs {len(t5b)} 筆）')

    def _renewals(tr):
        return sum(t.get('renewed', 0) for t in tr)

    _, t50 = simulate(cache, rk, 3, 'renew=50', renew=50)
    more = _renewals(t50) > _renewals(t5a)
    print(f'⑥ 放寬到 50 分 ⇒ 續抱次數變多：{_renewals(t5a)} → {_renewals(t50)}'
          f'　{"✅" if more else "🚨"}')

    # ⑦ 'profit' 的方向性：**成對造情境**（照 10/07 那條）
    #    世界A：到期時一定獲利 ⇒ 必須續抱（0 筆「持滿」出場）
    #    世界B：到期時一定虧損 ⇒ 必須不續抱
    def _world(up):
        dd = [f'2021-{m:02d}-{k:02d}' for m in range(1, 4) for k in range(1, 21)]
        px = []
        cur = 100.0
        for n, x in enumerate(dd):
            cur = cur * 1.01 if up else cur * 0.995   # 單調，且不觸發 -10% 停損
            px.append({'date': x, 'open': cur, 'high': cur * 1.001,
                       'low': cur * 0.999, 'close': cur})
        s = {'A': {'name': 'A', 'prices': px,
                   'idx': {p['date']: i for i, p in enumerate(px)},
                   # ⚠️ 評分要 ≥ 階梯門檻才進得場（否則連一筆交易都沒有，
                   #    ⑦ 會變成「兩邊都 0 次」而看起來像程式壞了）。
                   #    `renew='profit'` 的續抱判斷不看評分，所以設高不影響本測試。
                   'score': {x: 80 for x in dd},
                   'vol': {}, 'parts': {}}}
        return {'stocks': s, 'market_net': {x: -5 for x in dd}, 'tpx_dates': dd,
                'tpx_close': {x: 10000.0 for x in dd}}

    _, tu = simulate(_world(True), rk, 1, 'up', renew='profit')
    _, td = simulate(_world(False), rk, 1, 'down', renew='profit')
    up_renew = _renewals(tu) > 0 and all(t['exit_reason'] != f'持滿{HOLD_DAYS}日'
                                         for t in tu)
    dn_exit  = _renewals(td) == 0 and any(t['exit_reason'] == f'持滿{HOLD_DAYS}日'
                                          for t in td)
    print(f"⑦ renew='profit' 獲利時續抱：{'✅' if up_renew else '🚨'}"
          f"（續抱 {_renewals(tu)} 次）")
    print(f"⑦ renew='profit' 虧損時出場：{'✅' if dn_exit else '🚨'}"
          f"（續抱 {_renewals(td)} 次）")

    # ⑧ ('rand', p, salt) 中性對照的三個必要性質
    _, tr0 = simulate(cache, rk, 3, 'rand p=0', renew=('rand', 0.0, 's'))
    _, tr1 = simulate(cache, rk, 3, 'rand p=1', renew=('rand', 1.0, 's'))
    _, tr5 = simulate(cache, rk, 3, 'rand p=.5', renew=('rand', 0.5, 's'))
    _, tr5b = simulate(cache, rk, 3, 'rand p=.5', renew=('rand', 0.5, 's'))
    _, tr5c = simulate(cache, rk, 3, 'rand p=.5', renew=('rand', 0.5, 'other'))
    p0 = _renewals(tr0) == 0                      # p=0 ⇒ 從不續抱
    p1 = _renewals(tr1) > _renewals(tr5) > 0      # p 越大續抱越多
    det = sig(tr5) == sig(tr5b)                   # 同 salt ⇒ 確定性（配對前提）
    slt = sig(tr5) != sig(tr5c)                   # 換 salt ⇒ 真的是另一個實現
    print(f"⑧ ('rand',p) p=0 從不續抱：{'✅' if p0 else '🚨'}　"
          f"單調 {_renewals(tr0)}/{_renewals(tr5)}/{_renewals(tr1)}："
          f"{'✅' if p1 else '🚨'}")
    print(f"⑧ 同 salt 可重現：{'✅' if det else '🚨'}　"
          f"換 salt 是另一個實現：{'✅' if slt else '🚨'}")

    # ⑨ ('shuffle', thr, salt)：決定性的中性對照（2026-10-24）
    #   必須驗三件事，第三件最重要——**它真的在用別人的評分**。
    _, th1 = simulate(cache, rk, 3, 'shuf', renew=('shuffle', 65, 's'))
    _, th2 = simulate(cache, rk, 3, 'shuf', renew=('shuffle', 65, 's'))
    _, th3 = simulate(cache, rk, 3, 'shuf', renew=('shuffle', 65, 'other'))
    sh_det = sig(th1) == sig(th2)                 # 同 salt ⇒ 確定性
    sh_slt = sig(th1) != sig(th3)                 # 換 salt ⇒ 另一個置換
    sh_dif = sig(th1) != sig(t5b)                 # ★ 與「用自己的評分」不同
    print(f"⑨ ('shuffle') 同 salt 可重現：{'✅' if sh_det else '🚨'}　"
          f"換 salt 不同：{'✅' if sh_slt else '🚨'}")
    print(f"⑨ 與 renew=65（用自己的評分）**不同**："
          f"{'✅' if sh_dif else '🚨 一樣 ⇒ 置換沒生效，等於沒測到東西'}")
    # ★ 沒有任何股票被指派到自己——否則那幾檔等於沒打亂
    _k = sorted(cache['stocks'])
    _s = list(_k)
    random.Random('shuffle|s').shuffle(_s)
    for _i, _c in enumerate(_s):
        if _c == _k[_i]:
            _j = (_i + 1) % len(_s)
            _s[_i], _s[_j] = _s[_j], _s[_i]
    sh_self = all(a != b for a, b in zip(_k, _s))
    print(f"⑨ 無自我指派：{'✅' if sh_self else '🚨'}（{len(_k)} 檔）")

    allok = (ok2 and had and gone and all(x[0] for x in b)
             and ok5 and more and up_renew and dn_exit
             and p0 and p1 and det and slt
             and sh_det and sh_slt and sh_dif and sh_self)
    print()
    print('✅ 全部通過' if allok else '🚨 有項目失敗')
    return allok


if __name__ == '__main__':
    args = sys.argv[1:]
    mkt = 'market' in args
    if 'selftest' in args:
        sys.exit(0 if _selftest_pit() else 1)
    if 'pit' in args and 'cache' not in args:
        # 只印點時間宇宙的統計與守衛，不建快取（便宜，可先確認前提）
        from database import get_conn
        _c = get_conn()
        _m, _u = pit_universe(_c)
        _sz = [len(x[1]) for x in _m]
        print(f'點時間宇宙：{len(_m)} 個月，平均 {sum(_sz)/len(_sz):.0f} 檔'
              f'（{min(_sz)}~{max(_sz)}）')
        import collections as _co
        _by = _co.defaultdict(list)
        for d, cs in _m:
            _by[d[:4]].append(len(cs))
        for y in sorted(_by):
            print(f'  {y}  平均 {sum(_by[y])/len(_by[y]):>5.0f} 檔'
                  f'（{min(_by[y])}~{max(_by[y])}）')
        assert_pit_has_delisted(_c, _u)
        _c.close()
        sys.exit(0)
    if 'cache' in args:
        # ⚠️ `days` 必須可從 CLI 指定——這是陷阱51 那條通則的第四次。
        #    `build_cache()` 的預設是 600 天（＝2024-05 起），而 2018~2026 是
        #    2,130 個交易日。舊版 CLI 不傳 days ⇒ **跑 `cache market` 只會建出
        #    600 天的快取、一個空頭年都沒有，而且不報錯。**
        #    用法：python3 -u backtest_portfolio_slots.py cache market days=2600
        _days = 600
        for a in args:
            if a.startswith('days='):
                _days = int(a.split('=', 1)[1])
        print(f'[build_cache] universe={"market" if mkt else "watchlist"}　days={_days}')
        if _days <= 600:
            print('⚠️ days ≤ 600 ⇒ 只涵蓋約 2024-05 之後，**沒有任何空頭年**。'
                  '要測 2018~2026 請加 days=2600')
        build_cache('market' if mkt else 'watchlist', days=_days)
    else:
        main(CACHE_MARKET if mkt else CACHE)
