"""
趨勢強度進場過濾驗證（2026-08-21 新增，實驗性質，未接入正式邏輯）

═══ 背景／要驗證的問題 ═══

2026-08-21 診斷「近一個月績效為何很差」時發現：
  · 策略C近一個月（進場日 7/21~8/20）：19筆、勝率 5.3%、平均 -6.59%、停損率 79%
    （全期間為 437筆、47.1%、+4.56%、34%）
  · 但**不是選股問題**：同期加權指數 +1.58%、87檔自選股中位數 +0.78%（46漲41跌）
  · 16筆停損交易中，**14筆（88%）在停損後反彈**，停損後平均 +7.09%；
    若不停損抱到今天平均只有 -1.48%（實際停損認賠 -8.00%）
  → 典型的高波動＋無趨勢「洗盤」：8%停損被反覆掃到，反彈時已不在車上
  · 自選股中位波動度由 7/11 的 4.07 升至 8/20 的 4.63（高波動股佔比 54%→62%）
  · 大盤 2026 上半年 124 個交易日漲 54.62%（每日 +0.44%），近一個月 23 日僅 +1.58%
    （每日 +0.069%）——回測 +10.20% 的期望值裡，相當比例其實來自市場順風

假設：現行大盤評分只判斷「多空方向」（偏多／偏空／中性），
      無法區分「有方向的中性」與「沒方向的來回震盪」。
      加一個**趨勢強度過濾**：進場前先檢查大盤是否有明確方向，無趨勢期暫停進場。

本腳本要回答：
  (a) 全歷史加了這個過濾後，期望值變好還是變差？
  (b) **被過濾掉的交易原本會賺還是會賠？**（若原本會賺，這過濾就是在破壞價值）
  (c) 會過濾掉多少交易？（同策略E confirm_days 陷阱：砍太多＝實務上沒機會進場）
  (d) 分期間看，是普遍有效還是只對近一個月有效？

⚠️ 最大風險：**事後諸葛（過度配適）**。
   本腳本是在「已知近一個月很糟」之後才去找能避開它的指標，
   天生有 data snooping 的危險。**判準必須以全歷史與各子期間為主，
   近一個月的改善只能當佐證，絕不能當採用的理由。**
   若某個門檻只在近一個月有效、在 2025 或 2026H1 反而變差 → 直接判定為過度配適，不採用。

═══ 指標 ═══
  Kaufman 效率比（Efficiency Ratio, ER）——衡量「震盪 vs 趨勢」的標準做法：
      ER = |close[t] − close[t−n]| ÷ Σ|close[i] − close[i−1]|   (i = t−n+1 … t)
      接近 1 = 單邊趨勢（走直線）；接近 0 = 來回洗盤（走很多路但沒到哪裡）
  對照指標：MA20 斜率（近10日 MA20 變化率）

  兩者都只用「訊號日當天及之前」的 TAIEX 資料，無未來資訊。

═══ 執行 ═══
  python3 backtest_trend_filter.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import (get_watchlist, get_prices, get_fundamentals, get_chips,
                      get_ownership, init_db)
from scorer import full_score
import backtest_stocks as bs

SCORE_THRESHOLD = bs.SCORE_THRESHOLD
HOLD_DAYS       = bs.HOLD_DAYS
STOP_LOSS_RATIO = bs.STOP_LOSS_RATIO
MIN_HISTORY     = bs.MIN_HISTORY

ER_WINDOW = 20

init_db()


def build_trend_metrics():
    """回傳 {date: {'er': float, 'ma20_slope': float}}，只用當日及之前的 TAIEX 資料。"""
    tpx = get_prices('TAIEX', days=900)
    out = {}
    closes = [x['close'] for x in tpx]
    dates  = [x['date'] for x in tpx]
    for i in range(len(tpx)):
        d = dates[i]
        rec = {}
        # Kaufman 效率比
        if i >= ER_WINDOW:
            net = abs(closes[i] - closes[i - ER_WINDOW])
            path = sum(abs(closes[j] - closes[j - 1])
                       for j in range(i - ER_WINDOW + 1, i + 1))
            rec['er'] = (net / path) if path > 0 else 0.0
        else:
            rec['er'] = None
        # MA20 斜率（近10日變化率 %）
        if i >= 29:
            ma_now  = sum(closes[i - 19:i + 1]) / 20
            ma_prev = sum(closes[i - 29:i - 9]) / 20
            rec['ma20_slope'] = (ma_now - ma_prev) / ma_prev * 100 if ma_prev else 0.0
        else:
            rec['ma20_slope'] = None
        out[d] = rec
    return out


def run(market_net, trend, metric=None, threshold=None):
    """
    metric=None → 基準（策略C）
    metric='er'         → 需 ER >= threshold 才進場
    metric='ma20_slope' → 需 MA20 斜率 >= threshold 才進場
    被過濾掉的訊號會記錄在 filtered，供檢查「原本會賺還是會賠」。
    """
    all_trades, filtered = [], []

    for stock in get_watchlist():
        code, name = stock['code'], stock['name']
        prices    = get_prices(code, days=600)
        fund_all  = get_fundamentals(code, days=600)
        chips_all = get_chips(code, days=600)
        own_raw   = get_ownership(code)
        ownership = {'foreign': own_raw['foreign_pct']} if own_raw else {'foreign': 52}
        if len(prices) < MIN_HISTORY + HOLD_DAYS + 2:
            continue

        open_trade = None
        for i in range(MIN_HISTORY, len(prices) - 1):
            date_now = prices[i]['date']

            if open_trade:
                p = prices[i]
                ep = open_trade['entry_price']
                sp = ep * STOP_LOSS_RATIO
                if p['low'] <= sp:
                    open_trade.update(exit_date=date_now, exit_price=sp, exit_reason='停損',
                                      pnl=(sp - ep) / ep * 100)
                    all_trades.append(open_trade); open_trade = None; continue
                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    fs = [r for r in fund_all  if r['date'] <= date_now]
                    cs = [r for r in chips_all if r['date'] <= date_now][-65:]
                    res = full_score(prices[:i+1], fs, cs, ownership)
                    if res and res['total_score'] >= SCORE_THRESHOLD:
                        open_trade['entry_idx'] = i
                        open_trade['renewed'] = open_trade.get('renewed', 0) + 1
                        continue
                    open_trade.update(exit_date=date_now, exit_price=p['close'],
                                      exit_reason=f'持滿{HOLD_DAYS}日',
                                      pnl=(p['close'] - ep) / ep * 100)
                    all_trades.append(open_trade); open_trade = None

            if open_trade is None:
                if market_net is not None and market_net.get(date_now, 0) > 0:
                    continue
                fs = [r for r in fund_all  if r['date'] <= date_now]
                cs = [r for r in chips_all if r['date'] <= date_now][-65:]
                res = full_score(prices[:i+1], fs, cs, ownership)
                if res is None or res['total_score'] < SCORE_THRESHOLD:
                    continue

                # 趨勢強度過濾
                passed = True
                if metric is not None:
                    v = (trend.get(date_now) or {}).get(metric)
                    passed = (v is not None and v >= threshold)

                eb = prices[i + 1]
                rec = {'code': code, 'name': name, 'score': res['total_score'],
                       'entry_date': eb['date'], 'entry_price': eb['close'],
                       'entry_idx': i + 1, 'renewed': 0}
                if passed:
                    open_trade = rec
                else:
                    # 記錄被擋掉的訊號，用「持有10日或觸及停損」模擬它原本的結果
                    filtered.append(_simulate(prices, i + 1, rec))

        if open_trade:
            last = prices[-1]
            open_trade.update(exit_date=last['date'], exit_price=last['close'],
                              exit_reason='回測結束',
                              pnl=(last['close'] - open_trade['entry_price'])
                                  / open_trade['entry_price'] * 100)
            all_trades.append(open_trade)

    return all_trades, filtered


def _simulate(prices, idx, rec):
    """簡化模擬被擋掉的訊號：持有10日或先觸停損（不含續抱），供估算機會成本。"""
    ep = rec['entry_price']
    sp = ep * STOP_LOSS_RATIO
    for j in range(idx, min(idx + HOLD_DAYS + 1, len(prices))):
        if prices[j]['low'] <= sp:
            rec.update(exit_date=prices[j]['date'], exit_price=sp,
                       exit_reason='停損', pnl=(sp - ep) / ep * 100)
            return rec
    j = min(idx + HOLD_DAYS, len(prices) - 1)
    rec.update(exit_date=prices[j]['date'], exit_price=prices[j]['close'],
               exit_reason=f'持滿{HOLD_DAYS}日',
               pnl=(prices[j]['close'] - ep) / ep * 100)
    return rec


def stat(trades, a=None, b=None):
    if a: trades = [t for t in trades if t['entry_date'] >= a]
    if b: trades = [t for t in trades if t['entry_date'] <= b]
    cl = [t for t in trades if t['exit_reason'] != '回測結束']
    if not cl:
        return None
    n = len(cl)
    return dict(n=n,
                wr=len([t for t in cl if t['pnl'] > 0]) / n * 100,
                avg=sum(t['pnl'] for t in cl) / n,
                stop=len([t for t in cl if t['exit_reason'] == '停損']) / n * 100)


PERIODS = [('全期間', None, None),
           ('2025全年', '2025-01-01', '2025-12-31'),
           ('2026H1(大多頭)', '2026-01-01', '2026-07-13'),
           ('近一個月', '2026-07-21', '2026-08-20')]


if __name__ == '__main__':
    print('計算大盤訊號與趨勢指標中...')
    net = bs._build_market_signals()
    trend = build_trend_metrics()

    configs = [(None, None, '基準（策略C，無過濾）')]
    for th in (0.20, 0.30, 0.40):
        configs.append(('er', th, f'ER ≥ {th:.2f}'))
    for th in (0.0, 1.0):
        configs.append(('ma20_slope', th, f'MA20斜率 ≥ {th:.1f}%'))

    for metric, th, label in configs:
        tr, fl = run(net, trend, metric, th)
        print()
        print('=' * 88)
        print(f'【{label}】')
        for plab, a, b in PERIODS:
            s = stat(tr, a, b)
            line = (f'  {plab:<16} 筆數={s["n"]:>4} 勝率={s["wr"]:>5.1f}% '
                    f'平均={s["avg"]:>+6.2f}% 停損率={s["stop"]:>3.0f}%') if s else \
                   f'  {plab:<16} 無已平倉樣本'
            print(line)
        if fl:
            fs = stat(fl)
            print(f'  ── 被過濾掉 {fs["n"]} 筆，那些訊號原本的平均損益 = {fs["avg"]:+.2f}%'
                  f'（勝率 {fs["wr"]:.1f}%）')
            print('     ⚠️ 若這個數字是正的，代表過濾擋掉的是好交易，該設定不宜採用')
    print()
    print('判準提醒：以全歷史與 2025／2026H1 為主。若某門檻只在「近一個月」有效、')
    print('          在其他期間反而變差，直接視為過度配適，不採用。')
