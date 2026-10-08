# ════════════════════════════════════════
# indicators.py　技術指標計算
# 負責計算所有技術指標
# ════════════════════════════════════════

import pandas as pd
import ta
from config import (MA_SHORT, MA_MID, MA_LONG, RSI_PERIOD,
                    KD_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
                    BBAND_PERIOD, BBAND_STD)

def calc_all(prices):
    # prices 是 list of dict，每筆含 date/open/high/low/close/volume
    if not prices or len(prices) < 5:
        return {}

    df = pd.DataFrame(prices)
    df['close']  = pd.to_numeric(df['close'],  errors='coerce')
    df['high']   = pd.to_numeric(df['high'],   errors='coerce')
    df['low']    = pd.to_numeric(df['low'],    errors='coerce')
    df['open']   = pd.to_numeric(df['open'],   errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df = df.dropna(subset=['close'])

    n = len(df)
    result = {}

    # ── 均線 ────────────────────────────
    result['ma5']  = round(df['close'].tail(MA_SHORT).mean(), 2) if n >= MA_SHORT  else None
    result['ma10'] = round(df['close'].tail(10).mean(), 2)       if n >= 10        else None
    result['ma20'] = round(df['close'].tail(MA_MID).mean(), 2)   if n >= MA_MID    else None
    result['ma60'] = round(df['close'].tail(MA_LONG).mean(), 2)  if n >= MA_LONG   else None
    result['ma120'] = round(df['close'].tail(120).mean(), 2)     if n >= 120       else None  # 半年線
    result['ma240'] = round(df['close'].tail(240).mean(), 2)     if n >= 240       else None  # 年線

    # ── RSI ─────────────────────────────
    if n >= RSI_PERIOD + 1:
        rsi = ta.momentum.RSIIndicator(df['close'], window=RSI_PERIOD)
        val = rsi.rsi().iloc[-1]
        result['rsi'] = round(val, 1) if not pd.isna(val) else None
    else:
        result['rsi'] = None

    # ── KD ──────────────────────────────
    if n >= KD_PERIOD:
        stoch = ta.momentum.StochasticOscillator(
            df['high'], df['low'], df['close'],
            window=KD_PERIOD, smooth_window=3
        )
        k = stoch.stoch().iloc[-1]
        d = stoch.stoch_signal().iloc[-1]
        result['k'] = round(k, 1) if not pd.isna(k) else None
        result['d'] = round(d, 1) if not pd.isna(d) else None
    else:
        result['k'] = None
        result['d'] = None

    # ── MACD ────────────────────────────
    if n >= MACD_SLOW + MACD_SIGNAL:
        macd_ind = ta.trend.MACD(
            df['close'],
            window_fast=MACD_FAST,
            window_slow=MACD_SLOW,
            window_sign=MACD_SIGNAL
        )
        dif = macd_ind.macd().iloc[-1]
        def_ = macd_ind.macd_signal().iloc[-1]
        hist = macd_ind.macd_diff().iloc[-1]
        result['macd_dif']  = round(dif,  2) if not pd.isna(dif)  else None
        result['macd_def']  = round(def_, 2) if not pd.isna(def_) else None
        result['macd_hist'] = round(hist, 2) if not pd.isna(hist) else None
    else:
        result['macd_dif']  = None
        result['macd_def']  = None
        result['macd_hist'] = None

    # ── 布林通道 ─────────────────────────
    if n >= BBAND_PERIOD:
        bb = ta.volatility.BollingerBands(
            df['close'],
            window=BBAND_PERIOD,
            window_dev=BBAND_STD
        )
        result['bb_upper'] = round(bb.bollinger_hband().iloc[-1], 2)
        result['bb_mid']   = round(bb.bollinger_mavg().iloc[-1],  2)
        result['bb_lower'] = round(bb.bollinger_lband().iloc[-1], 2)
        # 完整序列（供繪圖用）
        result['bb_upper_series'] = [round(v, 2) if not pd.isna(v) else None
                                     for v in bb.bollinger_hband().tolist()]
        result['bb_lower_series'] = [round(v, 2) if not pd.isna(v) else None
                                     for v in bb.bollinger_lband().tolist()]
    else:
        result['bb_upper'] = None
        result['bb_mid']   = None
        result['bb_lower'] = None
        result['bb_upper_series'] = []
        result['bb_lower_series'] = []

    # ── 量能 ────────────────────────────
    if n >= MA_MID:
        avg_vol = df['volume'].tail(MA_MID).mean()
        last_vol = df['volume'].iloc[-1]
        result['avg_vol_20']  = int(avg_vol)
        result['last_vol']    = int(last_vol)
        result['vol_ratio']   = round(last_vol / avg_vol, 2) if avg_vol > 0 else None
    else:
        result['avg_vol_20'] = None
        result['last_vol']   = None
        result['vol_ratio']  = None

    # ── 近期高低點 ───────────────────────
    close_now = df['close'].iloc[-1]

    # 20日（1個月）
    if n >= 20:
        result['high_20'] = round(df['high'].tail(20).max(), 2)
        result['low_20']  = round(df['low'].tail(20).min(),  2)
    else:
        result['high_20'] = round(df['high'].max(), 2)
        result['low_20']  = round(df['low'].min(),  2)

    # 65日（3個月）
    if n >= 65:
        result['high_65'] = round(df['high'].tail(65).max(), 2)
        result['low_65']  = round(df['low'].tail(65).min(),  2)
    else:
        result['high_65'] = round(df['high'].max(), 2)
        result['low_65']  = round(df['low'].min(),  2)

    # 250日（1年）
    if n >= 250:
        result['high_250'] = round(df['high'].tail(250).max(), 2)
        result['low_250']  = round(df['low'].tail(250).min(),  2)
    else:
        result['high_250'] = result['high_65']
        result['low_250']  = result['low_65']

    # ── 相對位置計算 ─────────────────────
    def _pos(c, h, l):
        return round((c - l) / (h - l) * 100, 1) if h and l and h != l else None

    result['pos_20']  = _pos(close_now, result['high_20'],  result['low_20'])
    result['pos_65']  = _pos(close_now, result['high_65'],  result['low_65'])
    result['pos_250'] = _pos(close_now, result['high_250'], result['low_250'])

    # ── 波動度（20日日報酬標準差，2026-08新增）──
    # 用收盤價逐日反推報酬率計算，不依賴資料庫 change_pct 欄位（該欄位有資料錯誤，見陷阱記錄）
    # 母體標準差（ddof=0），跟 backtest_stocks.py 的驗證分析算法一致，數字才能互相對照
    if n >= 21:
        daily_ret = df['close'].pct_change().dropna() * 100
        vol_val = daily_ret.tail(20).std(ddof=0)
        result['vol20'] = round(vol_val, 2) if not pd.isna(vol_val) else None
    else:
        result['vol20'] = None

    # ── 乖離率（BIAS）────────────────────
    ma5_val  = result.get('ma5')
    ma20_val = result.get('ma20')
    result['bias5']  = round((close_now - ma5_val)  / ma5_val  * 100, 2) if ma5_val  else None
    result['bias20'] = round((close_now - ma20_val) / ma20_val * 100, 2) if ma20_val else None

    # ── 均線排列判斷 ─────────────────────
    ma5  = result['ma5']
    ma20 = result['ma20']
    ma60 = result['ma60']
    if ma5 and ma20:
        if ma60:
            if ma5 > ma20 > ma60:
                result['ma_trend'] = 'bullish'
            elif ma5 < ma20 < ma60:
                result['ma_trend'] = 'bearish'
            else:
                result['ma_trend'] = 'sideways'
        else:
            # MA60 不足時，只用 MA5 和 MA20 判斷
            if ma5 > ma20:
                result['ma_trend'] = 'bullish'
            elif ma5 < ma20:
                result['ma_trend'] = 'bearish'
            else:
                result['ma_trend'] = 'sideways'
    else:
        result['ma_trend'] = None

    # ── 進出場價位計算 ───────────────────
    if ma20:
        result['buy_low']  = round(ma20 * 0.99, 2)   # 買進區間下緣
        result['buy_high'] = round(ma20 * 1.01, 2)   # 買進區間上緣
        result['stop_loss'] = round(ma20 * 0.99 * 0.90, 2)  # 停損價（10%，2026-08-27 由0.92改）

    if result['bb_upper']:
        # 目標價：近3個月前高 和 布林上軌 取較低者
        target_candidates = [c for c in [result['high_65'], result['bb_upper']] if c]
        result['target'] = round(min(target_candidates), 2) if target_candidates else None
    else:
        result['target'] = result['high_65']

    # ── 連續漲跌天數 ─────────────────────
    if n >= 2:
        consecutive = 0
        last_dir = None
        for i in range(n - 1, max(n - 11, -1), -1):
            chg = df['close'].iloc[i] - df['close'].iloc[i - 1]
            cur_dir = 'up' if chg > 0 else 'down'
            if last_dir is None:
                last_dir = cur_dir
                consecutive = 1
            elif cur_dir == last_dir:
                consecutive += 1
            else:
                break
        result['consecutive_days'] = consecutive
        result['consecutive_dir']  = last_dir
    else:
        result['consecutive_days'] = None
        result['consecutive_dir']  = None

    # ── 原始資料（供圖表使用）───────────
    result['dates']   = df['date'].tolist()
    result['closes']  = df['close'].tolist()
    result['opens']   = df['open'].tolist()
    result['highs']   = df['high'].tolist()
    result['lows']    = df['low'].tolist()
    result['volumes'] = df['volume'].tolist()

    # 計算每日均線序列（供圖表使用）
    result['ma5_series']  = df['close'].rolling(MA_SHORT).mean().round(2).tolist()
    result['ma20_series'] = df['close'].rolling(MA_MID).mean().round(2).tolist()
    result['ma60_series'] = df['close'].rolling(MA_LONG).mean().round(2).tolist()

    return result


# ══════════════════════════════════════════════════════════════════════
# 滾動百分位評分 —— Signal 4（法人現貨）與日後同類訊號的共用判準
#
# ★ 為什麼不用絕對門檻（2026-10-07，為了重測策略D 而挖出來的）
#
# 陷阱34（2026-07）把 S4 的門檻校準成絕對張數（1,050,000／800,000／650,000），
# 但那是用**近 51 個交易日**算的。拉到 258 天重看：
#
#   | | ±3分 | ±2分 | ±1分 |
#   |---|---|---|---|
#   | 現行絕對門檻的實際觸發率 | 1.6% | 5.0% | 7.8% |
#   | 陷阱34 自訂的校準目標   |  5%  | 15%  | 30%  |
#
# 更根本的問題是**量級會隨市場規模漂移**：外資淨額絕對值中位數
# 2025 是 134,810 張、2026 是 192,086 張（p95 由 366,841 → 544,660，差 48%）。
# ⇒ 任何絕對張數的門檻，套到 2018（市場規模小得多）必然幾乎不觸發，
#   S4 在空頭年會變成死訊號——而那正是最需要它的時候。
#
# 滾動百分位是**尺度無關**的，所以同一套規則在 2018 與 2026 都成立。
# 這與 Signal 11（選擇權 P/C）已經在用的做法完全相同，理由也一樣：
# 「台股 P/C 常態偏高是結構性因素，需以歷史百分位判斷相對位置」。
#
# ⚠️ 放在 indicators.py 是刻意的：app.py／backtest.py／backtest_stocks.py
#    三處都已經 import 這個模組。陷阱34 與陷阱43 都是「同一訊號三份實作、
#    改了其中一兩處」造成的，**唯一的根治方法是只留一份實作。**
# ══════════════════════════════════════════════════════════════════════

# ══════ 切點校準紀錄（★ 日後重新校準時先讀完這一整段）══════
#
# ★ 校準資料：2017-12-18 ~ 2026-10-07，**2,071 個可評分交易日**
#   （`chips` 共 2,130 天，前 59 天是百分位暖身期不計分）
#   校準日 2026-10-08　工具 `calibrate_signal4.py`
#   ⚠️ 這是**回填 2018 歷史之後**才有的樣本。在那之前只有 258 天，
#     trailing 300 視窗從來沒填滿過，量出來的觸發率不具代表性。
#
# 實測（舊切點 95/85/70、2,071 天）：
#
#   | | ±3分 | ≥±2分 | ≥±1分 |
#   |---|---|---|---|
#   | 外資 | 6.7% | 16.3% | 32.3% |
#   | 投信 | 7.6% | 19.9% | 35.8% |
#   | 設計目標 | 5% | 15% | 30% |
#
# ⇒ 已經很接近，**微調為 96/86/72**（外資驗算 5.1 / 15.2 / 30.1%）。
#   投信在 72 這一檔約 33.6%（+3.6pp）——它只給 ±1 分，
#   **刻意不另設一組切點**：「同一訊號兩套參數」正是陷阱34／43 反覆踩到的坑，
#   多 3.6pp 不值得換來那個風險。
#
# ──── 🚨 2026-10-07 那天寫的兩件事都要更正 ────
#
# (1) 當天在 258 天上量到 ±3分 **11.6%**；回填後在 2,071 天上重量是 **6.7%**。
#     ⇒ **11.6% 主要是「視窗從未填滿、一路從 60 膨脹到 258」造成的假象**，
#       不是方法本身的偏差。合成資料對照支持這點：量級固定、無自相關、
#       視窗填滿時 ±3分 = 5.6%（接近 5%）。
#
# (2) 當天把原因寫成「當期值放進自己的視窗 ＋ 視窗混著量級較小的舊值」。
#     合成資料四組對照（各 2,200 天、trailing 300、切點 95/85/70）：
#
#     | 合成序列 | ±3分 |
#     |---|---|
#     | ① 量級固定、無自相關 | 5.6% ← 方法本身沒偏差 |
#     | ② 量級 9 年成長 5 倍 | 8.7% ← +3.2pp |
#     | ③ 量級固定、強自相關 ar=.6 | 5.8% ← 只有 +0.2pp |
#     | ④ 兩者都有 | 8.6% |
#
#     ⇒ 量級漂移確實是機制之一（自相關幾乎沒影響），
#       但**在真實資料上它的量級遠小於當初以為的**（6.7% 而非 11.6%）。
#
# ──── ★ 逐年觸發率：怎麼判斷百分位有沒有真的消掉量級漂移 ────
#
#   年    ≥±1分    外資絕對值中位
#   2018  27.3%     77,432
#   2019  30.3%     86,554
#   2020  39.2%    128,441   ← COVID
#   2021  33.7%    155,381
#   2022  27.2%    116,068
#   2023  30.5%    101,336
#   2024  38.8%    144,785
#   2025  21.8%    126,970   ← 最平靜
#   2026  43.2%    194,073
#
#   全距 21.4pp（21.8% ~ 43.2%），量級中位差 2.5 倍。
#
# 🚨 **第一版在 `calibrate_signal4.py` 寫的判準「全距 <10pp 才算解決漂移」是錯的。**
#   純抽樣雜訊（p=30%、n≈240/年）標準誤就有 2.96pp ⇒ 9 年的期望全距約 **9.2pp**。
#   而且**真實的市場波動本來就會讓極端日的密度逐年不同**
#   （2020 COVID 與 2026 真的多極端日、2025 真的平靜）——那是訊號在做它該做的事。
#   **「全距小」本來就不該是期待。**
#
# ★ 正確的判準有兩個：
#   ① corr(逐年量級, 逐年觸發率)。實測 **+0.667**（n=9，p≈0.05）
#   ② **同量級年份的對照**（這一項才是決定性的）：
#        2020 量級 128,441 → 39.2%
#        2025 量級 126,970 → 21.8%
#      **量級幾乎相同、觸發率差 17.4pp ⇒ 量級不是決定因素。**
#
#   ⚠️ 不可過度延伸成「百分位完全消除了漂移」：r=+0.667 不算低，
#     而且**量級與波動度本身互相混淆**（波動大的年份絕對流量也大），
#     n=9 分不開這兩者。誠實的說法是
#     「**量級已不是主要驅動因素，但殘餘關聯在 n=9 下無法與真實波動度分離**」。
#
# ★ 什麼時候該重新校準：市場規模再出現明顯級別變化時
#   （例如外資絕對值中位數再變 2 倍以上）。直接跑 `calibrate_signal4.py`。
PCT_HI, PCT_MID, PCT_LO = 96, 86, 72     # ±3分／±2分／±1分 的百分位門檻
PCT_MIN_N = 60                           # 樣本不足就不計分（寧可 0 分，不要亂給）


def pct_rank_score(value, history, hi=PCT_HI, mid=PCT_MID, lo=PCT_LO,
                   min_n=PCT_MIN_N):
    """
    用「|value| 在 |history| 中的百分位」決定強度、用 value 的正負決定方向。

    參數
      value   : 當期值（例如外資現貨淨額，正=買超）
      history : 歷史值序列（**必須只含決策日及之前的資料**，否則就是偷看未來）

    回傳 (score, pct)
      score : -3 ~ +3 的整數，正 = 偏多；資料不足或 value 為 None 時回 0
      pct   : |value| 的百分位（0~100）；無法計算時回 None

    ⚠️ 用絕對值算百分位、方向另外取，是為了讓「大買」與「大賣」對稱
       ——若直接對帶正負號的序列算百分位，多頭期間的分布會整體右移，
       「大賣超」的百分位會被低估。
    """
    if value is None or not history:
        return 0, None
    hist = [abs(h) for h in history if h is not None]
    if len(hist) < min_n:
        return 0, None
    a = abs(value)
    pct = sum(1 for h in hist if h <= a) / len(hist) * 100
    if   pct >= hi:  mag = 3
    elif pct >= mid: mag = 2
    elif pct >= lo:  mag = 1
    else:            mag = 0
    if mag == 0:
        return 0, pct
    return (mag if value > 0 else -mag), pct


def _selftest_pct_rank_score():
    """離線單元測試——不碰 DB、不連網，`python3 indicators.py` 會跑到。"""
    h = list(range(1, 101))          # |history| = 1..100，百分位好算
    cases = [
        (100,  +3, '最大值 → p100 → +3'),
        (-100, -3, '最大負值 → 強度相同、方向相反'),
        (96,   +3, 'p96 ≥ 95'),
        (90,   +2, 'p90 落在 85~95'),
        (75,   +1, 'p75 落在 70~85'),
        (50,    0, 'p50 → 中性'),
        (-50,   0, '負的中性值也是 0，不會因為負號就給空方分'),
    ]
    for v, want, desc in cases:
        got, _ = pct_rank_score(v, h)
        assert got == want, f'FAIL {desc}: {v} → {got}，應為 {want}'
    # 對稱性：任何值的正負版本，強度必須相同
    for v in (5, 23, 71, 86, 99):
        assert pct_rank_score(v, h)[0] == -pct_rank_score(-v, h)[0], f'不對稱 @{v}'
    # 樣本不足 → 0 分（不是給個隨便的分數）
    assert pct_rank_score(999, list(range(10)))[0] == 0, '樣本不足應回 0'
    assert pct_rank_score(None, h)[0] == 0, 'None 應回 0'
    assert pct_rank_score(5, [])[0] == 0, '空歷史應回 0'
    # 尺度無關：整個序列乘 1000，結論不能變（這是改用百分位的全部理由）
    big = [x * 1000 for x in h]
    for v in (50, 75, 90, 96):
        assert pct_rank_score(v, h)[0] == pct_rank_score(v * 1000, big)[0], f'尺度不變性失敗 @{v}'
    print('pct_rank_score 單元測試全部通過（含對稱性與尺度不變性）')


if __name__ == '__main__':
    # 測試用假資料
    import random
    prices = []
    close = 100.0
    for i in range(100):
        close *= (1 + random.gauss(0, 0.01))
        prices.append({
            'date': f'2026-{i//30+1:02d}-{i%30+1:02d}',
            'open': round(close * 0.99, 2),
            'high': round(close * 1.01, 2),
            'low':  round(close * 0.98, 2),
            'close': round(close, 2),
            'volume': random.randint(10000, 100000)
        })
    result = calc_all(prices)
    for k, v in result.items():
        if not isinstance(v, list):
            print(f'{k}: {v}')
    print('indicators.py 測試完成')
    _selftest_pct_rank_score()
