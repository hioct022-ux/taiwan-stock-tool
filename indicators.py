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
        result['stop_loss'] = round(ma20 * 0.99 * 0.92, 2)  # 停損價

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
