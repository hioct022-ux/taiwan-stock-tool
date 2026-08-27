"""
進場型態驗證腳本：🎯 量縮整理 / 🔥 放量突破 對進場時點有沒有影響？
（2026-08-20 新增，實驗性質，未接入正式邏輯）

═══ 背景／要驗證的問題 ═══

大盤評分卡的操作建議寫著：
    「大盤偏多，個股門檻提高至 70 分；**買點挑回檔日（量縮、不破前低），不追漲**」

這句話**從未被驗證過**——它是寫進程式的一般交易原則，不是回測結論。
與「評分門檻65分」「停損8%」「持有10日」這些有 404 筆驗證的規則，證據等級完全不同。

2026-08-20 使用者看到投資策略頁「符合進場條件」清單的型態欄全是「—」，
順勢推論：「如果有出現量縮型態的會是首選，不挑放量型態的，對吧？」
推論本身與建議文字一致，但同樣缺乏證據。

本腳本要回答三件事：
  (a) 在 🎯（量縮整理）當天進場，後續報酬是否真的優於「不看型態、達標就進」？
  (b) 在 🔥（放量突破）當天進場是否真的較差？（＝驗證「不追漲」這句話對不對）
  (c) 加上型態條件會過濾掉多少交易？**過濾太多就沒機會進場**——
      會落入策略E confirm_days=4 那個陷阱（數字漂亮但規則實際上很少啟動）。

事前預期（先寫下來，避免事後合理化）：
  · 🎯 組的 EV 會略優於基準，但**筆數大幅減少**（條件嚴格：2026-08-20 當天
    86 檔自選股中 🎯 是 0 檔），可能少到失去統計意義。
  · 🔥 組**沒有把握**——「不追漲」是常見說法，但動量效應在實證上也常成立。
    這題事前真的不知道答案。

判準：
  全歷史EV、勝率、**筆數（過濾強度）**、空頭段表現。
  並且必須把交易成本納入考量——若筆數暴跌，每筆固定成本的影響會改變。
  ⚠️ 若某組筆數少於約 30 筆，直接視為樣本不足、不下結論（不要硬解讀）。

═══ 設計 ═══
  基準組（＝現行策略 C）：大盤淨值 ≤0 且個股評分 ≥65 → 隔日進場
  🎯 組：上述條件 + 訊號日當天 _check_consolidation_pattern() 為 True
  🔥 組：上述條件 + 訊號日當天 _check_volume_breakout() 為 True
  「—」組：上述條件 + 兩種型態皆不成立（對照用，看「沒有型態」是不是真的比較差）

  其餘規則（停損8%、持有10日、到期≥65續抱）三組完全相同，只差進場那一天的型態條件。

═══ 執行方式 ═══
  cd 專案根目錄（或先複製 *.py + data/stock.db 到暫存目錄，避免 FUSE 掛載緩慢）
  python3 backtest_entry_pattern.py
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

BEAR_START = '2026-07-14'
MIN_SAMPLE = 30      # 低於此筆數視為樣本不足，不下結論

init_db()


# ── 型態判斷（與 app.py 完全相同的邏輯，複製過來避免 import streamlit）──
def check_consolidation(prices):
    """🎯 站上月線 + 近3日量縮 + 低點不破底"""
    if len(prices) < 22:
        return False
    r = prices[-22:]
    ma20 = sum(x['close'] for x in r[-20:]) / 20
    if r[-1]['close'] <= ma20:
        return False
    vma = sum(x['volume'] for x in r[-20:]) / 20
    l3 = r[-3:]
    if not all(x['volume'] < vma for x in l3):
        return False
    lo = [x['low'] for x in l3]
    if lo[1] < lo[0] or lo[2] < lo[1]:
        return False
    return True


def check_breakout(prices):
    """🔥 站上月線 + 今日量 >1.5倍均量 + 前3日量縮 + 收盤不跌"""
    if len(prices) < 25:
        return False
    r = prices[-25:]
    ma20 = sum(x['close'] for x in r[-20:]) / 20
    if r[-1]['close'] <= ma20:
        return False
    vma = sum(x['volume'] for x in r[-20:]) / 20
    if r[-1]['volume'] <= vma * 1.5:
        return False
    if not all(x['volume'] < vma for x in r[-4:-1]):
        return False
    if r[-1]['close'] < r[-2]['close']:
        return False
    return True


def run(market_net, pattern=None, renew=True):
    """
    pattern: None='不看型態'（基準）, 'consol'=🎯, 'breakout'=🔥, 'none'=兩者皆非
    其餘規則與策略 C 完全相同。
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
                p = prices[i]
                entry_price = open_trade['entry_price']
                stop_price  = entry_price * STOP_LOSS_RATIO

                if p['low'] <= stop_price:
                    open_trade.update(exit_date=date_now, exit_price=stop_price,
                                      exit_reason='停損',
                                      pnl=(stop_price - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None
                    continue

                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    if renew:
                        fs = [r for r in fund_all  if r['date'] <= date_now]
                        cs = [r for r in chips_all if r['date'] <= date_now][-65:]
                        res = full_score(prices[:i+1], fs, cs, ownership)
                        if res and res['total_score'] >= SCORE_THRESHOLD:
                            open_trade['entry_idx'] = i
                            open_trade['renewed'] = open_trade.get('renewed', 0) + 1
                            continue
                    open_trade.update(
                        exit_date=date_now, exit_price=p['close'],
                        exit_reason=f'持滿{HOLD_DAYS}日',
                        pnl=(p['close'] - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None

            if open_trade is None:
                if market_net is not None and market_net.get(date_now, 0) > 0:
                    continue

                # 型態條件（在「訊號日」當天判斷，隔日才進場——與實際操作一致）
                if pattern is not None:
                    win = prices[max(0, i - 24):i + 1]
                    _c = check_consolidation(win)
                    _b = check_breakout(win)
                    if pattern == 'consol'   and not _c:            continue
                    if pattern == 'breakout' and not _b:            continue
                    if pattern == 'none'     and (_c or _b):        continue

                fs = [r for r in fund_all  if r['date'] <= date_now]
                cs = [r for r in chips_all if r['date'] <= date_now][-65:]
                res = full_score(prices[:i+1], fs, cs, ownership)
                if res is None:
                    continue
                if res['total_score'] >= SCORE_THRESHOLD:
                    eb = prices[i + 1]
                    open_trade = {
                        'code': code, 'name': name, 'score': res['total_score'],
                        'entry_date': eb['date'], 'entry_price': eb['close'],
                        'entry_idx': i + 1, 'renewed': 0,
                    }

        if open_trade:
            last = prices[-1]
            open_trade.update(exit_date=last['date'], exit_price=last['close'],
                              exit_reason='回測結束',
                              pnl=(last['close'] - open_trade['entry_price'])
                                  / open_trade['entry_price'] * 100)
            all_trades.append(open_trade)

    return all_trades


def stats(trades, bear_start=None):
    if bear_start:
        trades = [t for t in trades if t['entry_date'] >= bear_start]
    closed = [t for t in trades if t['exit_reason'] != '回測結束']
    if not closed:
        return None
    n = len(closed)
    wins = [t for t in closed if t['pnl'] > 0]
    stops = [t for t in closed if t['exit_reason'] == '停損']
    return dict(n=n, wr=len(wins) / n * 100,
                avg=sum(t['pnl'] for t in closed) / n,
                stoppct=len(stops) / n * 100)


if __name__ == '__main__':
    print('計算大盤訊號中...')
    net = bs._build_market_signals()

    rows = []
    for key, label in [(None, '基準（不看型態）'), ('consol', '🎯 量縮整理'),
                       ('breakout', '🔥 放量突破'), ('none', '— 兩者皆非')]:
        print(f'跑 {label} ...')
        rows.append((label, run(net, pattern=key)))

    print()
    print('=' * 96)
    print(f'{"進場條件":<18} {"全歷史EV":>9} {"全勝率":>7} {"筆數":>6} {"停損率":>7} | '
          f'{"空頭段均報酬":>11} {"段筆數":>6}')
    print('=' * 96)
    for label, tr in rows:
        a = stats(tr)
        b = stats(tr, BEAR_START)
        if a is None:
            print(f'{label:<18} 無交易')
            continue
        warn = '  ⚠️樣本不足' if a['n'] < MIN_SAMPLE else ''
        tail = f'{b["avg"]:+10.2f}% {b["n"]:6d}' if b else '        —      0'
        print(f'{label:<18} {a["avg"]:+8.2f}% {a["wr"]:6.1f}% {a["n"]:6d} '
              f'{a["stoppct"]:6.0f}% | {tail}{warn}')
    print()
    print(f'⚠️ 筆數 < {MIN_SAMPLE} 的組別視為樣本不足，不得據以下結論。')
    print('   過濾強度也要看：若某型態把交易數砍到只剩個位數，代表實務上幾乎沒機會用，')
    print('   即使EV漂亮也不具參考價值（同策略E confirm_days=4 的陷阱）。')
