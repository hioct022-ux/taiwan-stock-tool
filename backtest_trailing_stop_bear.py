"""
個股移動停損（從波段高點回落X%）驗證腳本（2026-08 補跑，含空頭段拆解）

背景：討論「進場成本固定停損」vs「從高點回落幅度停損」時，
使用者提出的疑慮：固定停損容易出現「本來有賺、後來吐回去變賠」的懊悔感，
是否該改成從高點回落幅度停損。

backtest_stocks.py 的 scan_trailing_stop() 只印全歷史數字，
這次比照 backtest_strategy_e_confirm_days.py 的做法，額外拆出
空頭段（BEAR_START起）的單獨統計，才能看出移動停損在真正下跌時表現如何。

使用方式：
  cd 專案根目錄（或先複製 *.py + data/stock.db 到暫存目錄，避免 FUSE 掛載緩慢）
  python3 backtest_trailing_stop_bear.py

下次驗證時，如果已有新的空頭/震盪段資料，把下面的 BEAR_START 改成新的起始日期。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import backtest_stocks as bs

BEAR_START = '2026-07-14'


def _bear_window_stats(trades, label, bear_start=BEAR_START):
    sub = [t for t in trades if t['entry_date'] >= bear_start]
    closed = [t for t in sub if t['exit_reason'] != '回測結束']
    openp  = [t for t in sub if t['exit_reason'] == '回測結束']
    if not closed:
        print(f'  {label}: 無已平倉交易（未平倉 {len(openp)} 筆，樣本不足）')
        return
    n = len(closed)
    wins = [t for t in closed if t['pnl'] > 0]
    avg = sum(t['pnl'] for t in closed) / n
    wr = len(wins) / n * 100
    stops = [t for t in closed if t['exit_reason'] == '停損']
    trails = [t for t in closed if '移動停利' in t.get('exit_reason', '')]
    print(f'  {label}: 已平倉={n} 未平倉={len(openp)} 勝率={wr:.1f}% '
          f'均報酬={avg:+.2f}% 停損={len(stops)}({len(stops)/n*100:.0f}%) '
          f'移動停利觸發={len(trails)}({len(trails)/n*100:.0f}%)')


if __name__ == '__main__':
    print('=' * 70)
    print('  個股移動停損（從高點回落幅度）驗證，含空頭段拆解')
    print(f'  空頭段窗口：進場日 >= {BEAR_START}')
    print('=' * 70)

    print('\n計算大盤訊號中...')
    market_net = bs._build_market_signals()

    configs = [(None, '無移動停損（現行）'), (0.03, '回落3%'), (0.05, '回落5%'), (0.08, '回落8%')]

    print('\n【全歷史 + 空頭段拆解】')
    for pct, label in configs:
        trades, _ = bs._run_backtest(market_net=market_net, trailing_pct=pct)
        bs._print_stats(trades, label)
        _bear_window_stats(trades, f'{label} 空頭段')
