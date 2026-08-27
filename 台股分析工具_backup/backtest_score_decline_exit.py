"""
策略 F 驗證腳本：評分自峰值衰退即出場（2026-08-20 新增，實驗性質，未接入正式邏輯）

═══ 背景／要驗證的問題 ═══

2026-08-20 把「買入訊號衰退警告」（原本只在個股頁「⭐綜合評分」分頁）搬到側邊欄
持倉觀察與投資策略頁持倉管理後，使用者提出一個直覺：

  「看到評分衰退就自行決定出場，而不用呆板地等 C 或 D 出現訊號，
    這樣應該更能保全獲益表現。」

這個直覺目前只有 4 檔、1 天的觀察支撐（2026-08-18 那天四檔持倉中三檔亮燈，
唯一沒亮燈的南亞科正好是唯一撐過來的那檔），**完全不足以當統計證據**。

而且方向上要警惕：這在本質上就是一條「更敏感的出場規則」，只是執行者從程式換成人。
「更敏感的出場」這個家族本專案已經驗證過三次，三次都是同樣的形狀——
空頭段少賠、但常態下大量原本能撐過短期回檔的交易被提早巴出場：
  · 移動停損（從高點回落3%）：全歷史EV +3.54% → +0.91%，勝率 50.8% → 33.9%
  · 策略E confirm_days=1（大盤淨值一轉就出）：全歷史EV 僅 +1.89%
  · 策略D 本身：全歷史EV +1.75%，遠低於純C 的 +4.67%

本腳本要回答的具體問題：
  把這個直覺寫成明確規則——「持有期間，若評分自近期峰值（峰值需 ≥65）回落 ≥N 分
  就出場」——它的實際績效落在哪裡？值不值得從「純資訊提示」升級成「正式規則」？

對照組：純C（不提前出場）、純D（大盤轉空提前出場）
掃描參數：N = 5 / 8 / 12（5 是目前 UI 警告框的觸發門檻）

事前預期（先寫下來，避免事後合理化）：
  F 會落在 C 和 D 之間；空頭段比 C 好、全歷史比 C 差；
  但**可能比 D 好**，因為它看的是個股體質而非市場雜訊，誤殺理論上較少。

判準（沿用策略E那次的教訓）：
  全歷史EV、全歷史勝率、空頭段均報酬、空頭段停損率，
  **以及防禦觸發次數**——觸發次數掉到個位數就代表規則形同虛設，EV再漂亮也不算數。

═══ 2026-08-20 執行結果 ═══

  策略              | 全歷史EV | 全勝率 | 筆數 | 空頭段(7/14起)均報酬 | 段停損率 | 段防禦觸發
  純C（現行）        | +4.67%  | 47.6% | 429  | -6.51%             | 78%     | 0
  純D               | +1.75%  | 39.9% | 715  | -1.35%             | 22%     | 40
  F 衰退5分         | +0.17%  | 26.6% | 851  | -1.93%             | 15%     | 60
  F 衰退8分         | +0.62%  | 33.1% | 723  | -2.53%             | 25%     | 41
  F 衰退12分        | +1.61%  | 37.7% | 616  | -3.23%             | 39%     | 25

  **事前預期完全錯誤。** 原本預測 F 會落在 C 和 D 之間、甚至可能優於 D
  （理由是「看個股體質而非市場雜訊，誤殺應該較少」）。實際上 F 全面差於 D，
  而且越敏感越差——衰退門檻從 12 分收緊到 5 分，EV 從 +1.61% 一路掉到 +0.17%。

  **致命點：F 衰退5分（＝目前 UI 警告框的觸發門檻）扣掉交易成本後是虧錢的。**
  交易次數從 429 筆暴增到 851 筆，每筆都在付來回成本
  （FEE_RATE 0.001425 × FEE_DISCOUNT 0.6 × 2 + TAX_RATE 0.003 ≈ 0.47%）：
      純C：      +4.67% − 0.47% = +4.20%  淨賺
      F 衰退5分： +0.17% − 0.47% = −0.30%  淨賠
  勝率 26.6% 代表四筆裡三筆賠錢。

  **但同時發現了使用者直覺的來源（重要）：**
  把窗口改成「進場日 >= 2026-08-11」（＝使用者實際經歷的那一週）重跑：
      純C：       -8.00%，停損率 100%，防禦觸發 0
      純D：       -8.00%，停損率 100%，防禦觸發 0
      F 衰退5分：  -1.99%，停損率  9%，防禦觸發 29
  **那一週 F 是唯一有效的規則。** 因為當週大盤淨值全程 0~+1，市場層級訊號從未啟動，
  傷害純粹發生在個股層級，而 F 是唯一「看個股體質」的規則。
  → 使用者的直覺在他剛好經歷的情境下完全正確，問題是該情境罕見，
    為了防它要付的常態成本高到讓整套策略由賺轉賠。

  **結論：不採用。** 評分衰退提示維持「純資訊揭露」定位，不升級成正式出場規則。
  定位應該是「這檔要特別盯著」，而不是「立刻出場」。

═══ 執行方式 ═══
  cd 專案根目錄（或先複製 *.py + data/stock.db 到暫存目錄，避免 FUSE 掛載緩慢）
  python3 backtest_score_decline_exit.py

  全程約 3–6 分鐘（每個持有中的交易日都要重算評分，比其他回測腳本慢很多）。
  若環境有單次執行時間上限，用 --only N 只跑單一設定，結果 pickle 存檔後再彙整。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import (get_watchlist, get_prices, get_fundamentals, get_chips,
                      get_ownership, init_db)
from scorer import full_score
import backtest_stocks as bs

SCORE_THRESHOLD = bs.SCORE_THRESHOLD    # 65
HOLD_DAYS       = bs.HOLD_DAYS          # 10
STOP_LOSS_RATIO = bs.STOP_LOSS_RATIO    # 0.92
MIN_HISTORY     = bs.MIN_HISTORY        # 90

# 空頭段窗口（與策略E腳本同一個日期，方便兩份結果互相對照）
BEAR_START = '2026-07-14'

# 評分峰值需達此值，衰退才算數（與 UI 警告框、個股頁邏輯一致）
PEAK_MIN = 65

init_db()


def run_backtest_f(market_net, decline_n=5, renew=True):
    """
    策略 F = 策略 C（大盤過濾進場 + 停損 + 到期續抱）
             + 「持有期間評分自峰值回落 ≥ decline_n 分即出場」

    峰值定義：進場後每個交易日重算評分，記錄期間出現過的最高分（含進場當日評分）。
    只有當峰值 >= PEAK_MIN 時，回落才觸發出場——與 UI 警告框的條件一致
    （避免一檔評分始終在低檔徘徊的股票，因為小幅波動就被判定「衰退」）。
    """
    watchlist  = get_watchlist()
    all_trades = []

    for stock in watchlist:
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
                p           = prices[i]
                entry_price = open_trade['entry_price']
                stop_price  = entry_price * STOP_LOSS_RATIO

                # 1. 停損（最高優先，與正式規則一致）
                if p['low'] <= stop_price:
                    open_trade.update(exit_date=date_now, exit_price=stop_price,
                                      exit_reason='停損',
                                      pnl=(stop_price - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None
                    continue

                # 2. 評分衰退出場（本策略新增的規則）
                #    持有期間每日重算評分並更新峰值
                fund_slice  = [r for r in fund_all  if r['date'] <= date_now]
                chips_slice = [r for r in chips_all if r['date'] <= date_now][-65:]
                res_now = full_score(prices[:i+1], fund_slice, chips_slice, ownership)
                score_now = res_now['total_score'] if res_now else None

                if score_now is not None:
                    if score_now > open_trade.get('peak_score', 0):
                        open_trade['peak_score'] = score_now
                    _peak = open_trade.get('peak_score', 0)
                    if _peak >= PEAK_MIN and (score_now - _peak) <= -decline_n:
                        open_trade.update(
                            exit_date=date_now, exit_price=p['close'],
                            exit_reason=f'評分衰退{decline_n}分'
                                        f'(峰值{_peak}→{score_now})',
                            pnl=(p['close'] - entry_price) / entry_price * 100)
                        all_trades.append(open_trade)
                        open_trade = None
                        continue

                # 3. 持滿天數（到期續抱邏輯，與策略C相同）
                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    if renew and score_now is not None and score_now >= SCORE_THRESHOLD:
                        open_trade['entry_idx']  = i
                        open_trade['renewed']    = open_trade.get('renewed', 0) + 1
                        # 續抱後峰值重新起算，否則舊高點會讓下一輪一進場就觸發衰退
                        open_trade['peak_score'] = score_now
                        continue

                    open_trade.update(
                        exit_date=date_now, exit_price=p['close'],
                        exit_reason=f'持滿{HOLD_DAYS}日'
                                    + (f'（續{open_trade.get("renewed",0)}次）'
                                       if open_trade.get('renewed') else ''),
                        pnl=(p['close'] - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None

            if open_trade is None:
                # 大盤過濾：淨值 > 0（偏空）不進場
                if market_net is not None and market_net.get(date_now, 0) > 0:
                    continue

                fund_slice  = [r for r in fund_all  if r['date'] <= date_now]
                chips_slice = [r for r in chips_all if r['date'] <= date_now][-65:]
                result = full_score(prices[:i+1], fund_slice, chips_slice, ownership)
                if result is None:
                    continue

                score = result['total_score']
                if score >= SCORE_THRESHOLD:
                    entry_bar = prices[i + 1]
                    open_trade = {
                        'code': code, 'name': name, 'score': score,
                        'entry_date':  entry_bar['date'],
                        'entry_price': entry_bar['close'],
                        'entry_idx':   i + 1,
                        'peak_score':  score,   # 峰值從進場當下的評分起算
                        'renewed':     0,
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
    n     = len(closed)
    wins  = [t for t in closed if t['pnl'] > 0]
    stops = [t for t in closed if t['exit_reason'] == '停損']
    defs_ = [t for t in closed if ('評分衰退' in t['exit_reason']
                                   or '大盤' in t['exit_reason'])]
    return dict(n=n, wr=len(wins) / n * 100,
                avg=sum(t['pnl'] for t in closed) / n,
                stoppct=len(stops) / n * 100, defense=len(defs_))


def print_table(rows, bear_start):
    print('=' * 100)
    print(f'空頭段窗口 = 進場日 >= {bear_start}')
    print('=' * 100)
    print(f'{"策略":<20} {"全歷史EV":>9} {"全勝率":>7} {"全筆數":>6} | '
          f'{"段均報酬":>9} {"段勝率":>7} {"段筆數":>6} {"段停損率":>8} {"段防禦觸發":>10}')
    for label, tr in rows:
        a = stats(tr)
        b = stats(tr, bear_start)
        tail = (f'{b["avg"]:+8.2f}% {b["wr"]:6.1f}% {b["n"]:6d} '
                f'{b["stoppct"]:7.0f}% {b["defense"]:10d}') if b else '  （無已平倉樣本）'
        print(f'{label:<20} {a["avg"]:+8.2f}% {a["wr"]:6.1f}% {a["n"]:6d} | {tail}')
    print()


if __name__ == '__main__':
    print('計算大盤訊號中...')
    market_net = bs._build_market_signals()

    rows = []
    print('跑對照組 純C ...')
    rows.append(('純C（現行）', bs._run_backtest(market_net=market_net, renew=True)[0]))
    print('跑對照組 純D ...')
    rows.append(('純D（大盤轉空出場）', bs._run_backtest(market_net=market_net,
                                                market_exit=True)[0]))

    for n in (5, 8, 12):
        print(f'跑策略 F（評分衰退 {n} 分出場）...')
        rows.append((f'F 評分衰退{n}分', run_backtest_f(market_net, decline_n=n)))

    print()
    print_table(rows, BEAR_START)
    print_table(rows, '2026-08-11')
    print('提醒：不要只看全歷史EV。防禦觸發次數掉到個位數＝規則形同虛設，')
    print('      再漂亮的EV都是「防禦沒在運作」換來的假象（見策略E那次的教訓）。')
