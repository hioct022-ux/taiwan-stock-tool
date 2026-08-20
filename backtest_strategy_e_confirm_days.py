"""
策略 E 驗證腳本（2026-08 新增，實驗性質，不影響正式邏輯）

背景：
策略 C（大盤過濾＋到期續抱）在多頭段表現最好，但空頭段會硬扛到停損，
沒有防禦機制；策略 D（大盤過濾＋持有期間大盤轉空立即出場）相反，
空頭段防禦力強，但多頭段常被短暫回檔誤判、提早出場，全歷史表現墊底。

策略 E = 把 D 的「大盤轉空提前出場」規則，加進 C 的既有規則（到期續抱＋停損）裡，
並加入「連續 N 天 net≥2 才觸發出場」的確認機制（confirm_days），
避免大盤淨值單日雜訊就把部位巴出場。

2026-08-15 驗證結果（資料至 2026-08-14，空頭段窗口取 2026-07-14 起）：

  confirm_days | 全歷史EV  | 全歷史勝率 | 筆數 | 空頭段均報酬 | 空頭段停損率 | 空頭段觸發防禦次數
  1（=無確認）  | +1.98%   | 37.9%     | 707  | -0.11%      | 7%          | 40
  2            | +3.35%   | 49.1%     | 540  | -3.07%      | 48%         | 13
  3            | +3.63%   | 46.4%     | 496  | -4.19%      | 53%         | 7
  4            | +5.12%   | 48.4%     | 469  | -4.20%      | 53%         | 7
  5            | +5.12%   | 48.9%     | 454  | -7.43%（=純C）| 89%（=純C） | 0（=純C，防禦完全失效）

  對照組 純C：全歷史 EV +4.83%（445筆）；空頭段(7/14起)均報酬 -7.43%，停損率89%（9筆已平倉）
  對照組 純D：全歷史 EV +1.84%（734筆）；空頭段(7/14起)均報酬 -0.11%，停損率7%（43筆已平倉）

  重要陷阱：confirm_days≥4 時全歷史EV看起來最漂亮，但那是假象——這段空頭期間
  淨值很少連續4~5天都≥2（反覆巴動型走勢），確認門檻設太高導致防禦機制在真正
  需要它的時候幾乎沒觸發，退化成純C。不能只看全歷史EV選參數，一定要同時看
  空頭段的觸發次數和均報酬，否則會選到「防禦形同虛設」的參數。

  當時建議：confirm_days=2 是全歷史表現和空頭防禦力之間比較平衡的選擇，
  但這個結論只驗證過這一次（2026-07-14起）的空頭走勢型態（反覆巴動型），
  換一種空頭型態（例如緩跌盤跌型）結果可能不同，建議累積下一次空頭資料後
  重跑本腳本，比對新舊兩次的 confirm_days 曲線是否一致。

─────────────────────────────────────────────────────────────────
2026-08-20 第二次驗證（資料至 2026-08-20，補進 8/17~8/20 那週的震盪）

  要回答的問題：(a) confirm_days=2 的結論是否仍成立、(b) 新資料是讓策略E更站得住腳
  還是動搖了原結論。觸發原因：使用者實際操作已在跑策略D的邏輯（4筆持倉中3筆走
  「大盤轉空減碼」出場），與系統儀表板的比對基準（策略C）不一致。

  confirm_days | 全歷史EV  | 全歷史勝率 | 筆數 | 空頭段均報酬 | 空頭段停損率 | 空頭段觸發防禦次數
  1（=無確認）  | +1.89%   | 38.7%     | 688  | -1.35%      | 22%         | 40
  2            | +3.22%   | 50.3%     | 521  | -4.26%      | 61%         | 13
  3            | +3.50%   | 47.5%     | 478  | -5.52%      | 70%         | 7
  4            | +5.02%   | 49.7%     | 453  | -5.52%      | 70%         | 7
  5            | +4.89%   | 49.1%     | 438  | -6.51%（≒純C）| 78%        | 0（防禦失效）

  對照組 純C：全歷史 EV +4.67%（429筆）；空頭段(7/14起)均報酬 -6.51%，停損率78%
  對照組 純D：全歷史 EV +1.75%（715筆）；空頭段(7/14起)均報酬 -1.35%，停損率22%

  結論：**曲線形狀與 8/15 那次幾乎完全一致，confirm_days=2 仍是唯一平衡點。**
  cd=4 依舊是「EV最漂亮但防禦只觸發7次」的陷阱參數，重複驗證了不能只看EV的教訓。
  維持原決定：不接入正式邏輯。

  重要發現（與參數無關，價值高於上表）：
  **8/17~8/20 那一週根本不是「大盤轉空」。** 系統大盤淨值當週是 0/0/+1/0，從未觸及
  +2 警戒門檻（最後一次連續≥2 是 8/4~8/7）。把窗口改成「進場日 >= 2026-08-11」重跑，
  純C/純D/E(cd=1~5) **七種策略結果完全相同**：防禦觸發 0 次、停損率 100%、均報酬 -8.00%。
  → 沒有任何大盤層級規則救得了那一週，傷害是個股層級而非市場層級的。
  這也表示這次「新增的空頭樣本」其實不算數，CLAUDE.md 裡「待第二次空頭型態驗證」
  那個條件**仍然沒有被滿足**，下次真的出現市場級空頭時還是要再跑一次。

  附帶發現（單日進場集中度，見 CLAUDE.md 對應章節）：
  8/14 單日同時進場 15 檔（歷史最高；單日進場中位數僅 3 檔），15 檔中 12 檔虧損、
  6 檔在 3 個交易日內停損，整批平均 -4.28%。原因是 8/13 大盤淨值 -1 解除進場封鎖，
  一堆個股同時達標。現行策略對「進場時間集中度」完全沒有防禦（資金配置那三條規則
  管的是部位大小，管不到同一天開幾個新倉）。尚未設計對策。

─────────────────────────────────────────────────────────────────

使用方式：
  cd 專案根目錄（或先複製 *.py + data/stock.db 到暫存目錄，避免 FUSE 掛載緩慢）
  python3 backtest_strategy_e_confirm_days.py

  下次驗證時，如果已有新的空頭/震盪段資料，把下面的 BEAR_START 改成新的起始日期
  （看大盤淨值 history 或 render_market() 頁面找轉折點），再執行。
  若尚無新空頭資料，只看全歷史 EV 那組數字有沒有明顯變化即可，空頭段驗證部分延後。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import get_watchlist, get_prices, get_fundamentals, get_chips, get_ownership, init_db
from scorer import full_score
import backtest_stocks as bs

SCORE_THRESHOLD = bs.SCORE_THRESHOLD
HOLD_DAYS       = bs.HOLD_DAYS
STOP_LOSS_RATIO = bs.STOP_LOSS_RATIO
MIN_HISTORY     = bs.MIN_HISTORY

# ── 下次驗證時，若有新的空頭/震盪段，把這個日期改成新的起始日 ──
BEAR_START = '2026-07-14'

init_db()


def _build_confirmed_exit_dates(market_net, confirm_days):
    """回傳 set of dates，代表在該日期「net>=2 已連續 confirm_days 天」，可以觸發防禦出場。"""
    dates_sorted = sorted(market_net.keys())
    confirmed = set()
    streak = 0
    for d in dates_sorted:
        if market_net.get(d, 0) >= 2:
            streak += 1
        else:
            streak = 0
        if streak >= confirm_days:
            confirmed.add(d)
    return confirmed


def run_backtest_e(market_net, confirm_days=2, renew=True):
    """
    策略 E：C 的到期續抱規則 + D 的大盤轉空提前出場規則（需連續 confirm_days 天確認）。
    confirm_days=1 等同於沒有確認機制（跟原始 D 規則一樣，只是多了續抱）。
    """
    confirmed_exit_dates = _build_confirmed_exit_dates(market_net, confirm_days)

    watchlist = get_watchlist()
    all_trades = []
    skipped    = []

    for stock in watchlist:
        code = stock['code']
        name = stock['name']

        prices    = get_prices(code, days=600)
        fund_all  = get_fundamentals(code, days=600)
        chips_all = get_chips(code, days=600)

        ownership_raw = get_ownership(code)
        ownership = {'foreign': ownership_raw['foreign_pct']} if ownership_raw else {'foreign': 52}

        if len(prices) < MIN_HISTORY + HOLD_DAYS + 2:
            skipped.append(f'{code} {name}（資料不足 {len(prices)} 筆）')
            continue

        open_trade = None

        for i in range(MIN_HISTORY, len(prices) - 1):
            date_now = prices[i]['date']

            if open_trade:
                p           = prices[i]
                entry_price = open_trade['entry_price']
                stop_price  = entry_price * STOP_LOSS_RATIO

                if p['high'] > open_trade.get('peak_price', entry_price):
                    open_trade['peak_price'] = p['high']

                # 停損
                if p['low'] <= stop_price:
                    open_trade.update(exit_date=date_now, exit_price=stop_price,
                                      exit_reason='停損',
                                      pnl=(stop_price - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None
                    continue

                # 大盤轉偏空提前出場（需連續 confirm_days 天 net>=2）
                if date_now in confirmed_exit_dates:
                    mnet = market_net.get(date_now, 0)
                    open_trade.update(exit_date=date_now, exit_price=p['close'],
                                      exit_reason=f'大盤轉偏空確認{confirm_days}日(net={mnet:+d})',
                                      pnl=(p['close'] - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None
                    continue

                # 持滿天數
                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    if renew:
                        prices_slice = prices[:i+1]
                        fund_slice   = [r for r in fund_all  if r['date'] <= date_now]
                        chips_slice  = [r for r in chips_all if r['date'] <= date_now][-65:]
                        result = full_score(prices_slice, fund_slice, chips_slice, ownership)
                        renew_score = result['total_score'] if result else 0

                        if renew_score >= SCORE_THRESHOLD:
                            open_trade['entry_idx'] = i
                            open_trade['renewed']   = open_trade.get('renewed', 0) + 1
                            continue

                    open_trade.update(exit_date=date_now, exit_price=p['close'],
                                      exit_reason=f'持滿{HOLD_DAYS}日'
                                                  + (f'（續{open_trade.get("renewed",0)}次）'
                                                     if open_trade.get('renewed') else ''),
                                      pnl=(p['close'] - entry_price) / entry_price * 100)
                    all_trades.append(open_trade)
                    open_trade = None

            if open_trade is None:
                if market_net is not None:
                    if market_net.get(date_now, 0) > 0:
                        continue

                prices_slice = prices[:i+1]
                fund_slice   = [r for r in fund_all  if r['date'] <= date_now]
                chips_slice  = [r for r in chips_all if r['date'] <= date_now][-65:]

                result = full_score(prices_slice, fund_slice, chips_slice, ownership)
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
                        'peak_price':  entry_bar['close'],
                        'renewed':     0,
                    }

        if open_trade:
            last        = prices[-1]
            entry_price = open_trade['entry_price']
            open_trade.update(exit_date=last['date'], exit_price=last['close'],
                              exit_reason='回測結束',
                              pnl=(last['close'] - entry_price) / entry_price * 100)
            all_trades.append(open_trade)

    return all_trades, skipped


def _bear_window_stats(trades, label, bear_start=BEAR_START):
    """只看進場日 >= bear_start 的已平倉交易（排除回測結束時仍未平倉的部位）"""
    sub = [t for t in trades if t['entry_date'] >= bear_start]
    closed = [t for t in sub if t['exit_reason'] != '回測結束']
    openp  = [t for t in sub if t['exit_reason'] == '回測結束']
    if not closed:
        print(f'  {label}: 無已平倉交易（未平倉 {len(openp)} 筆，樣本不足，建議延後驗證）')
        return
    n = len(closed)
    wins = [t for t in closed if t['pnl'] > 0]
    avg = sum(t['pnl'] for t in closed) / n
    wr = len(wins) / n * 100
    stops = [t for t in closed if t['exit_reason'] == '停損']
    mkt_exit = [t for t in closed if '大盤轉偏空' in t['exit_reason']]
    print(f'  {label}: 已平倉={n} 未平倉={len(openp)} 勝率={wr:.1f}% '
          f'均報酬={avg:+.2f}% 停損={len(stops)}({len(stops)/n*100:.0f}%) '
          f'大盤提前出場觸發={len(mkt_exit)}')


if __name__ == '__main__':
    print('=' * 70)
    print('  策略 E（C續抱 + D提前出場，含confirm_days確認機制）驗證')
    print(f'  空頭段窗口：進場日 >= {BEAR_START}（如有新的空頭段，請修改此常數）')
    print('=' * 70)

    print('\n計算大盤訊號中...')
    market_net = bs._build_market_signals()

    print('\n【對照組：純 C / 純 D】')
    trades_c, _ = bs._run_backtest(market_net=market_net, renew=True)
    trades_d, _ = bs._run_backtest(market_net=market_net, market_exit=True)
    bs._print_stats(trades_c, '純 C')
    _bear_window_stats(trades_c, '純 C 空頭段')
    bs._print_stats(trades_d, '純 D')
    _bear_window_stats(trades_d, '純 D 空頭段')

    print('\n【策略 E：confirm_days 掃描】')
    for cd in [1, 2, 3, 4, 5]:
        trades_e, _ = run_backtest_e(market_net, confirm_days=cd, renew=True)
        bs._print_stats(trades_e, f'策略 E（confirm_days={cd}）')
        _bear_window_stats(trades_e, f'策略 E confirm_days={cd} 空頭段')

    print('\n注意：全歷史EV高不代表空頭段防禦力好（見腳本開頭陷阱說明），')
    print('      選參數務必同時對照空頭段的「觸發次數」和「均報酬」兩欄。')
