"""
波動度調整停損驗證（2026-08-27 新增，實驗性質，未接入正式邏輯）

═══ 背景／要驗證的問題 ═══

2026-08-27 診斷「近一個月績效為何很差」的完整發現鏈：

  1. 策略C近一個月（進場 7/21~8/27）：20筆、平均 -6.66%、停損率高
  2. 拆解 beta / alpha 後發現：同期大盤僅 -1.33%，**alpha = -5.33%**
     → 不是市場害的，是策略主動摧毀價值
  3. 機制：16筆停損中 **14筆（88%）在停損後反彈**，停損後平均 +7.09%；
     若不停損抱到最後平均只有 -1.48%（實際認賠 -8.00%）
  4. 環境：自選股波動度中位數由 7/11 的 4.07 升至 4.63，高波動股（vol20>3.9）佔比 54%→62%
  → **8% 固定停損在高波動環境下「相對距離」變近，被雜訊反覆掃到**

  另外已排除的解方：
  · 趨勢強度過濾（ER / MA20斜率）→ 見 backtest_trend_filter.py，
    只在 2026 有效、2025 全面變差，且擋掉的訊號原本平均 +2.10%（擋掉的是好交易），
    判定為過度配適。且診斷顯示 ER 只是碰巧共伴，真正的變數是個股波動度。

假設：停損距離應隨**個股波動度**調整，而非全部一律 8%。
      停損價 = 進場價 × (1 − k × vol20 / 100)
      例：vol20=2.0（低波動）、k=2.5 → 停損 5%；vol20=4.6（高波動）→ 停損 11.5%
      ⚠️ 錨點仍是**進場成本**，與已否決的「移動停損」（錨點改成波段高點）本質不同。

═══ ⚠️ 最關鍵的方法論防護：必須有「單純放寬停損」的對照組 ═══

  同時測固定 10%、固定 12%。
  如果波動度調整的結果與「單純把停損放寬」差不多，
  代表 vol20 這個變數**沒有貢獻**，有效的只是「放寬」本身。
  沒有這組對照，極容易把功勞錯誤歸給波動度調整、白白引入一個沒必要的新變數。

═══ 要回答 ═══
  (a) 全歷史 EV 與 alpha 是否改善？
  (b) 停損觸發率降低多少？
  (c) **停損真的觸發時單筆虧損放大多少？**（放寬停損的代價，必須量化）
  (d) 分期間（2025 / 2026H1 / 近一個月）是否穩健，還是又只對近一個月有效？

═══ 事前預期（先寫下來，避免事後合理化）═══
  預期波動度調整會優於固定 8%，**但不會明顯優於固定 10~12%**。
  若成真，代表該做的只是「改一個數字」，而不是引入新變數。

═══ 執行 ═══
  python3 backtest_vol_stop.py
"""
import sys, os, statistics
sys.path.insert(0, os.path.dirname(__file__))

from database import (get_watchlist, get_prices, get_fundamentals, get_chips,
                      get_ownership, init_db)
from scorer import full_score
import backtest_stocks as bs

SCORE_THRESHOLD = bs.SCORE_THRESHOLD
HOLD_DAYS       = bs.HOLD_DAYS
MIN_HISTORY     = bs.MIN_HISTORY

# 波動度調整的上下限：避免極端值產生荒謬的停損距離
STOP_MIN_PCT = 0.04     # 最緊 4%
STOP_MAX_PCT = 0.16     # 最寬 16%

init_db()


def vol20_at(prices, i):
    """用 close 逐日反推日報酬算 20 日標準差（不用 change_pct，見陷阱35）。"""
    if i < 21:
        return None
    c = [x['close'] for x in prices[i - 20:i + 1]]
    r = [(c[j] - c[j - 1]) / c[j - 1] * 100 for j in range(1, len(c)) if c[j - 1]]
    if len(r) < 5:
        return None
    return statistics.pstdev(r)


def run(market_net, mode='fixed', param=0.08, renew=True):
    """
    mode='fixed'  → 停損 = 進場價 × (1 − param)          param 為固定比例
    mode='vol'    → 停損 = 進場價 × (1 − k×vol20/100)     param 為 k，受上下限夾擠
    """
    all_trades = []

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
                p  = prices[i]
                ep = open_trade['entry_price']
                sp = open_trade['stop_price']
                if p['low'] <= sp:
                    open_trade.update(exit_date=date_now, exit_price=sp,
                                      exit_reason='停損', pnl=(sp - ep) / ep * 100)
                    all_trades.append(open_trade); open_trade = None; continue
                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    fs = [r for r in fund_all  if r['date'] <= date_now]
                    cs = [r for r in chips_all if r['date'] <= date_now][-65:]
                    res = full_score(prices[:i+1], fs, cs, ownership)
                    if renew and res and res['total_score'] >= SCORE_THRESHOLD:
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

                v = vol20_at(prices, i)
                if mode == 'vol':
                    if v is None:
                        continue
                    pct = max(STOP_MIN_PCT, min(STOP_MAX_PCT, param * v / 100))
                else:
                    pct = param

                eb = prices[i + 1]
                open_trade = {
                    'code': code, 'name': name, 'score': res['total_score'],
                    'entry_date': eb['date'], 'entry_price': eb['close'],
                    'entry_idx': i + 1, 'renewed': 0,
                    'stop_price': eb['close'] * (1 - pct),
                    'stop_pct': pct * 100, 'vol20': v,
                }

        if open_trade:
            last = prices[-1]
            open_trade.update(exit_date=last['date'], exit_price=last['close'],
                              exit_reason='回測結束',
                              pnl=(last['close'] - open_trade['entry_price'])
                                  / open_trade['entry_price'] * 100)
            all_trades.append(open_trade)

    return all_trades


def build_market_lookup():
    tpx = {x['date']: x['close'] for x in get_prices('TAIEX', days=900)}
    ds = sorted(tpx)
    def mkt(a, b):
        A = [d for d in ds if d >= a]; B = [d for d in ds if d <= b]
        return (tpx[B[-1]] - tpx[A[0]]) / tpx[A[0]] * 100 if A and B else None
    return mkt


def stat(trades, mkt, a=None, b=None):
    if a: trades = [t for t in trades if t['entry_date'] >= a]
    if b: trades = [t for t in trades if t['entry_date'] <= b]
    cl = [t for t in trades if t['exit_reason'] != '回測結束']
    if not cl:
        return None
    n = len(cl)
    stops = [t for t in cl if t['exit_reason'] == '停損']
    alphas = []
    for t in cl:
        m = mkt(t['entry_date'], t['exit_date'])
        if m is not None:
            alphas.append(t['pnl'] - m)
    return dict(n=n,
                wr=len([t for t in cl if t['pnl'] > 0]) / n * 100,
                avg=sum(t['pnl'] for t in cl) / n,
                alpha=statistics.mean(alphas) if alphas else 0.0,
                stoppct=len(stops) / n * 100,
                stoploss=statistics.mean([t['pnl'] for t in stops]) if stops else 0.0,
                avgstop=statistics.mean([t['stop_pct'] for t in cl if 'stop_pct' in t]))


PERIODS = [('全期間', None, None),
           ('2025全年', '2025-01-01', '2025-12-31'),
           ('2026H1', '2026-01-01', '2026-07-13'),
           ('近一個月', '2026-07-21', '2026-08-27')]


if __name__ == '__main__':
    print('計算大盤訊號中...')
    net = bs._build_market_signals()
    mkt = build_market_lookup()

    configs = [('fixed', 0.08, '固定 8%（現行）'),
               ('fixed', 0.10, '固定 10%（對照）'),
               ('fixed', 0.12, '固定 12%（對照）'),
               ('vol',   2.0,  'vol×2.0'),
               ('vol',   2.5,  'vol×2.5'),
               ('vol',   3.0,  'vol×3.0')]

    for mode, param, label in configs:
        tr = run(net, mode, param)
        print()
        print('=' * 92)
        print(f'【{label}】')
        for plab, a, b in PERIODS:
            s = stat(tr, mkt, a, b)
            if not s:
                print(f'  {plab:<10} 無已平倉樣本'); continue
            print(f'  {plab:<10} n={s["n"]:>4} 勝率={s["wr"]:>5.1f}% 報酬={s["avg"]:>+6.2f}% '
                  f'alpha={s["alpha"]:>+6.2f}% 停損率={s["stoppct"]:>3.0f}% '
                  f'停損時虧={s["stoploss"]:>+6.2f}% 平均停損距離={s["avgstop"]:>4.1f}%')
    print()
    print('判準：先比「vol×k」與「固定10%/12%」——若差異不大，')
    print('      代表有效的只是放寬停損，vol20 這個變數沒有貢獻，不必引入。')
