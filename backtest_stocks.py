"""
個股評分回測腳本
策略 A（無大盤過濾）：個股 ≥ 65 分 → 隔日進場
策略 B（有大盤過濾）：個股 ≥ 65 分 + 大盤訊號非偏空 → 隔日進場
策略 C（策略 B + 到期續抱）：到期時重新評分，≥65 則再抱一輪
持有 10 個交易日出場，或跌破 8% 停損
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import (get_watchlist, get_prices, get_fundamentals, get_chips,
                      get_ownership, get_futures_institutional, get_market_margin,
                      get_conn, init_db)
from scorer import full_score
from indicators import calc_all

# ── 參數 ────────────────────────────────
SCORE_THRESHOLD  = 65      # 進場門檻
HOLD_DAYS        = 10      # 持有天數（交易日）
STOP_LOSS_RATIO  = 0.92    # 停損：進場價 × 0.92（跌 8%）
TRAILING_PCT     = None    # 移動停利：從波段高點回落幅度（None=不啟用）
MIN_HISTORY      = 90      # 最少需要幾筆歷史才開始評分

init_db()

# ── 大盤訊號預計算（與 backtest.py 邏輯相同）───────────
def _build_market_signals():
    """回傳 {date: net_score} 字典，net > 0 = 偏空，net < 0 = 偏多，0 = 中性"""
    taiex_all   = get_prices('TAIEX', days=600)
    futures_all = get_futures_institutional(days=600)
    margin_all  = get_market_margin(days=600)

    conn = get_conn()
    t86_rows = conn.execute('''
        SELECT date, SUM(foreign_net) AS fn, SUM(trust_net) AS tn
        FROM t86_ranking GROUP BY date ORDER BY date
    ''').fetchall()
    conn.close()

    t86_by_date = {r[0]: {'foreign_net_total': r[1], 'trust_net_total': r[2]} for r in t86_rows}
    fut_by_date = {r['date']: r for r in futures_all}
    mm_by_date  = {r['date']: r for r in margin_all}

    market_net = {}

    for i in range(1, len(taiex_all)):
        date_today = taiex_all[i]['date']
        date_prev  = taiex_all[i-1]['date']

        tpx_win = taiex_all[max(0, i-250):i]   # 250日：與 app.py 預判視窗一致（MA60 + 真正的250日位置）
        fut_win = [r for r in futures_all if r['date'] <= date_prev][-15:]
        mm_win  = [r for r in margin_all  if r['date'] <= date_prev][-15:]
        t86_prev = t86_by_date.get(date_prev)

        bear, bull = 0, 0

        # Signal 1：TAIEX 昨日漲跌
        if len(tpx_win) >= 2:
            c_now  = tpx_win[-1]['close']
            c_prev = tpx_win[-2]['close']
            chg    = (c_now - c_prev) / c_prev * 100 if c_prev else 0
            if   chg <= -2.0: bear += 3
            elif chg <= -1.0: bear += 2
            elif chg <= -0.3: bear += 1
            elif chg >=  2.0: bull += 3
            elif chg >=  1.0: bull += 2
            elif chg >=  0.3: bull += 1

        # Signal 2：融資5日趨勢
        if len(mm_win) >= 2:
            mb_now  = mm_win[-1]['margin_balance']
            mb_5ago = mm_win[-min(5, len(mm_win))]['margin_balance']
            mb_pct  = (mb_now - mb_5ago) / mb_5ago * 100 if mb_5ago else 0
            if   mb_pct >=  2.0: bear += 2
            elif mb_pct >=  0.5: bear += 1
            elif mb_pct <= -2.0: bull += 2
            elif mb_pct <= -0.5: bull += 1

        # Signal 3：外資期貨
        if len(fut_win) >= 2:
            f_now  = fut_win[-1]['foreign_net']
            f_prev = fut_win[-2]['foreign_net']
            f_5ago = fut_win[-min(5, len(fut_win))]['foreign_net']
            f_chg  = f_now - f_prev
            f_trend = f_now - f_5ago
            if   f_chg >=  3000: bull += 2
            elif f_chg >=  1000: bull += 1
            elif f_chg <= -3000: bear += 2
            elif f_chg <= -1000: bear += 1
            if   f_trend >= 2000: bull += 1
            elif f_trend <= -2000: bear += 1

        # Signal 4：T86 外資現貨
        if t86_prev:
            fg = t86_prev.get('foreign_net_total', 0) or 0
            tr = t86_prev.get('trust_net_total',   0) or 0
            if   fg >= 1050000: bull += 3
            elif fg >=  800000: bull += 2
            elif fg >=  650000: bull += 1
            elif fg <= -1050000: bear += 3
            elif fg <=  -800000: bear += 2
            elif fg <=  -650000: bear += 1
            if   tr >=  100000: bull += 1
            elif tr <= -100000: bear += 1

        # Signal 5-8：TAIEX 技術指標
        if len(tpx_win) >= 6:
            ind  = calc_all(tpx_win)
            b5   = ind.get('bias5')
            b20  = ind.get('bias20')
            p250 = ind.get('pos_250')
            mat  = ind.get('ma_trend')
            if b5 is not None:
                if   b5 >=  5: bear += 2
                elif b5 >=  2: bear += 1
                elif b5 <= -5: bull += 2
                elif b5 <= -2: bull += 1
            if b20 is not None:
                if   b20 >=  8: bear += 1
                elif b20 <= -8: bull += 1
            if p250 is not None:
                if   p250 >= 90: bear += 1
                elif p250 <= 10: bull += 2
                elif p250 <= 25: bull += 1
            if mat == 'bullish': bull += 1
            elif mat == 'bearish': bear += 1

        if len(tpx_win) >= 5:
            vols = [p['value'] for p in tpx_win[-5:] if p.get('value', 0) > 0]
            if len(vols) >= 3:
                avg3   = sum(vols[-3:]) / 3
                avgpre = sum(vols[:max(1, len(vols)-3)]) / max(1, len(vols)-3)
                vt = (avg3 - avgpre) / avgpre * 100 if avgpre else 0
                if   vt <= -15: bear += 1
                elif vt >=  20: bull += 1

        market_net[date_today] = bear - bull  # 正=偏空，負=偏多

    return market_net

# ── 回測核心（可選大盤過濾、到期續抱）─────
def _run_backtest(market_net=None, renew=False, trailing_pct=None, market_exit=False):
    """
    market_net   : dict {date: net_score} 或 None
    renew        : True = 到期時分數 ≥65 則續抱一輪（策略 C）
    trailing_pct : float 或 None = 從波段高點回落超過此比例則移動停利出場
    market_exit  : True = 持有期間大盤轉偏空（net≥2，評分≤40）提前出場
    """
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

            # ── 出場檢查 ──
            if open_trade:
                p           = prices[i]
                entry_price = open_trade['entry_price']
                stop_price  = entry_price * STOP_LOSS_RATIO

                # 更新波段高點
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

                # 大盤轉偏空提前出場（net≥2 = 大盤評分≤40）
                if market_exit and market_net is not None:
                    mnet = market_net.get(date_now, 0)
                    if mnet >= 2:
                        open_trade.update(exit_date=date_now, exit_price=p['close'],
                                          exit_reason=f'大盤轉偏空(net={mnet:+d})',
                                          pnl=(p['close'] - entry_price) / entry_price * 100)
                        all_trades.append(open_trade)
                        open_trade = None
                        continue

                # 移動停利：從波段高點回落超過 trailing_pct
                if trailing_pct is not None:
                    peak      = open_trade.get('peak_price', entry_price)
                    trail_price = peak * (1 - trailing_pct)
                    if p['close'] <= trail_price and peak > entry_price * 1.02:
                        # 需先有 2% 以上獲利才啟動，避免剛進場就被震出
                        open_trade.update(exit_date=date_now, exit_price=p['close'],
                                          exit_reason=f'移動停利(高{(peak/entry_price-1)*100:.1f}%回{trailing_pct*100:.0f}%)',
                                          pnl=(p['close'] - entry_price) / entry_price * 100)
                        all_trades.append(open_trade)
                        open_trade = None
                        continue

                # 持滿天數
                if i - open_trade['entry_idx'] >= HOLD_DAYS:
                    if renew:
                        # 重新評分：≥65 則續抱，重設計時起點
                        prices_slice = prices[:i+1]
                        fund_slice   = [r for r in fund_all  if r['date'] <= date_now]
                        chips_slice  = [r for r in chips_all if r['date'] <= date_now][-65:]
                        result = full_score(prices_slice, fund_slice, chips_slice, ownership)
                        renew_score = result['total_score'] if result else 0

                        if renew_score >= SCORE_THRESHOLD:
                            # 續抱：重設計時，不出場
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

            # ── 進場評估 ──
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


# ── 統計輸出 ─────────────────────────────
def _print_stats(trades, label):
    if not trades:
        print(f'\n【{label}】無交易記錄')
        return

    total     = len(trades)
    wins      = [t for t in trades if t['pnl'] > 0]
    losses    = [t for t in trades if t['pnl'] <= 0]
    stop_hits = [t for t in trades if t['exit_reason'] == '停損']
    win_rate  = len(wins) / total * 100
    avg_pnl   = sum(t['pnl'] for t in trades) / total
    avg_win   = sum(t['pnl'] for t in wins)   / max(1, len(wins))
    avg_loss  = sum(t['pnl'] for t in losses) / max(1, len(losses))
    ev        = win_rate/100 * avg_win + (1 - win_rate/100) * avg_loss

    print(f'\n【{label}】')
    print(f'  總交易次數：{total} 筆')
    print(f'  勝率：{len(wins)}/{total} = {win_rate:.1f}%')
    print(f'  平均報酬：{avg_pnl:+.2f}%')
    print(f'  平均獲利（贏）：{avg_win:+.2f}%')
    print(f'  平均虧損（輸）：{avg_loss:+.2f}%')
    print(f'  停損次數：{len(stop_hits)}（{len(stop_hits)/total*100:.1f}%）')
    print(f'  期望值：{ev:+.2f}%')

    print(f'\n  分數區段：')
    for lo, hi, lbl in [(65,75,'65–74'),(75,85,'75–84'),(85,101,'85+')]:
        band = [t for t in trades if lo <= t['score'] < hi]
        if band:
            wr = sum(1 for t in band if t['pnl'] > 0) / len(band) * 100
            ap = sum(t['pnl'] for t in band) / len(band)
            print(f'    {lbl}分：{len(band):3d}筆  勝率{wr:.0f}%  均{ap:+.2f}%')


# ── 主程式 ───────────────────────────────
def run():
    print('計算大盤訊號中...')
    market_net = _build_market_signals()

    print('執行策略 A（無大盤過濾）...')
    trades_a, skipped = _run_backtest(market_net=None)

    print('執行策略 B（有大盤過濾）...')
    trades_b, _       = _run_backtest(market_net=market_net)

    print('執行策略 C（大盤過濾 + 到期續抱）...')
    trades_c, _       = _run_backtest(market_net=market_net, renew=True)

    print('執行策略 D（大盤過濾 + 持有期間大盤轉空提前出場）...')
    trades_d, _       = _run_backtest(market_net=market_net, market_exit=True)

    print()
    print('=' * 60)
    print(f'  個股評分回測比較報告')
    print(f'  門檻：{SCORE_THRESHOLD}分 / 持有{HOLD_DAYS}日 / 停損{int((1-STOP_LOSS_RATIO)*100)}%')
    print('=' * 60)

    if skipped:
        print('\n【跳過（資料不足）】')
        for s in skipped:
            print(f'  {s}')

    _print_stats(trades_a, '策略 A：個股 ≥65分（無大盤過濾）')
    _print_stats(trades_b, '策略 B：個股 ≥65分 + 大盤非偏空')
    _print_stats(trades_c, '策略 C：策略 B + 到期分數 ≥65 則續抱')
    _print_stats(trades_d, '策略 D：策略 B + 持有期大盤轉空提前出場')

    # 策略 D 提前出場統計
    if trades_d:
        early = [t for t in trades_d if '大盤轉偏空' in t.get('exit_reason', '')]
        if early:
            ew = sum(1 for t in early if t['pnl'] > 0) / len(early) * 100
            ea = sum(t['pnl'] for t in early) / len(early)
            print(f'\n  策略 D 提前出場明細：')
            print(f'    觸發次數：{len(early)} 筆（佔 {len(early)/len(trades_d)*100:.1f}%）')
            print(f'    提前出場勝率：{ew:.1f}%  平均報酬：{ea:+.2f}%')

    # 策略 C 的續抱統計
    if trades_c:
        renewed = [t for t in trades_c if t.get('renewed', 0) > 0]
        total_renews = sum(t.get('renewed', 0) for t in trades_c)
        if renewed:
            rw = sum(1 for t in renewed if t['pnl'] > 0) / len(renewed) * 100
            ra = sum(t['pnl'] for t in renewed) / len(renewed)
            print(f'\n  策略 C 續抱明細：')
            print(f'    觸發續抱：{len(renewed)} 筆（共續 {total_renews} 次）')
            print(f'    續抱勝率：{rw:.1f}%  平均報酬：{ra:+.2f}%')

    # 最近 20 筆：策略 C
    if trades_c:
        recent = sorted(trades_c, key=lambda t: t['entry_date'])[-20:]
        print(f'\n【策略 C 最近 20 筆交易】')
        print(f'  {"進場日":12} {"代號":6} {"分":>4} {"進場":>8} {"出場":>8} {"報酬":>7} {"原因"}')
        print('  ' + '-' * 65)
        for t in recent:
            mark = '✅' if t['pnl'] > 0 else '❌'
            print(f'  {t["entry_date"]:12} {t["code"]:6} {t["score"]:3}  '
                  f'{t["entry_price"]:7.1f}  {t["exit_price"]:7.1f}  '
                  f'{t["pnl"]:+6.1f}%  {t["exit_reason"]} {mark}')

    # 各股明細（策略 C）
    if trades_c:
        print(f'\n【策略 C 各股明細】')
        print(f'  {"代號":6} {"名稱":10} {"筆數":>4} {"勝率":>6} {"均報酬":>8}')
        print('  ' + '-' * 40)
        for c in sorted(set(t['code'] for t in trades_c)):
            ts = [t for t in trades_c if t['code'] == c]
            wr = sum(1 for t in ts if t['pnl'] > 0) / len(ts) * 100
            ap = sum(t['pnl'] for t in ts) / len(ts)
            print(f'  {c:6} {ts[0]["name"][:5]:10} {len(ts):4d}  {wr:5.0f}%  {ap:+7.2f}%')


def scan_hold_days():
    """掃描不同持有天數，找出最佳參數（策略 B）"""
    global HOLD_DAYS

    print('計算大盤訊號中...')
    market_net = _build_market_signals()

    print()
    print('=' * 60)
    print('  持有天數參數掃描（策略 B：大盤非偏空）')
    print(f'  門檻：{SCORE_THRESHOLD}分 / 停損{int((1-STOP_LOSS_RATIO)*100)}%')
    print('=' * 60)
    print(f'  {"持有日":>6} {"筆數":>5} {"勝率":>7} {"平均報酬":>9} {"平均獲利":>9} {"平均虧損":>9} {"停損率":>7} {"期望值":>8}')
    print('  ' + '-' * 66)

    original = HOLD_DAYS
    rows     = []

    for days in [3, 5, 7, 10, 15, 20]:
        HOLD_DAYS = days
        trades, _ = _run_backtest(market_net=market_net)

        if not trades:
            rows.append({'days': days, 'empty': True})
            continue

        total    = len(trades)
        wins     = [t for t in trades if t['pnl'] > 0]
        losses   = [t for t in trades if t['pnl'] <= 0]
        stops    = [t for t in trades if t['exit_reason'] == '停損']
        win_rate = len(wins) / total * 100
        avg_pnl  = sum(t['pnl'] for t in trades) / total
        avg_win  = sum(t['pnl'] for t in wins)   / max(1, len(wins))
        avg_loss = sum(t['pnl'] for t in losses) / max(1, len(losses))
        ev       = win_rate/100 * avg_win + (1 - win_rate/100) * avg_loss
        stop_r   = len(stops) / total * 100

        rows.append({'days': days, 'total': total, 'win_rate': win_rate,
                     'avg_pnl': avg_pnl, 'avg_win': avg_win, 'avg_loss': avg_loss,
                     'stop_r': stop_r, 'ev': ev, 'empty': False})

    HOLD_DAYS = original  # 還原

    valid = [r for r in rows if not r['empty']]
    best_ev = max(r['ev'] for r in valid) if valid else None

    for r in rows:
        if r['empty']:
            print(f'  {r["days"]:5d}日   （無交易）')
        else:
            marker = ' ◀ 最佳' if r['ev'] == best_ev else ''
            print(f'  {r["days"]:5d}日  {r["total"]:5d}  {r["win_rate"]:6.1f}%  {r["avg_pnl"]:+8.2f}%  '
                  f'{r["avg_win"]:+8.2f}%  {r["avg_loss"]:+8.2f}%  {r["stop_r"]:6.1f}%  {r["ev"]:+7.2f}%{marker}')

    if valid:
        best = max(valid, key=lambda r: r['ev'])
        print(f'\n  最佳期望值：持有 {best["days"]} 日（EV {best["ev"]:+.2f}%，{best["total"]} 筆）')


def scan_trailing_stop():
    """掃描不同移動停利幅度（策略 B，10日持有）"""
    print('計算大盤訊號中...')
    market_net = _build_market_signals()

    print()
    print('=' * 65)
    print('  移動停利幅度掃描（策略 B，持有10日，停損8%）')
    print('  啟動條件：波段獲利 >2% 才開始追蹤高點回落')
    print('=' * 65)
    print(f'  {"設定":>8} {"筆數":>5} {"勝率":>7} {"平均報酬":>9} {"平均獲利":>9} {"停損率":>7} {"移動停利率":>10} {"期望值":>8}')
    print('  ' + '-' * 68)

    rows = []
    configs = [(None, '無停利'), (0.03, '3%'), (0.05, '5%'), (0.08, '8%')]

    for pct, label in configs:
        trades, _ = _run_backtest(market_net=market_net, trailing_pct=pct)
        if not trades:
            continue

        total    = len(trades)
        wins     = [t for t in trades if t['pnl'] > 0]
        losses   = [t for t in trades if t['pnl'] <= 0]
        stops    = [t for t in trades if t['exit_reason'] == '停損']
        trails   = [t for t in trades if '移動停利' in t.get('exit_reason', '')]
        win_rate = len(wins) / total * 100
        avg_pnl  = sum(t['pnl'] for t in trades) / total
        avg_win  = sum(t['pnl'] for t in wins)   / max(1, len(wins))
        avg_loss = sum(t['pnl'] for t in losses) / max(1, len(losses))
        ev       = win_rate/100 * avg_win + (1 - win_rate/100) * avg_loss
        stop_r   = len(stops)  / total * 100
        trail_r  = len(trails) / total * 100

        rows.append({'label': label, 'total': total, 'win_rate': win_rate,
                     'avg_pnl': avg_pnl, 'ev': ev})
        print(f'  {label:>8}  {total:5d}  {win_rate:6.1f}%  {avg_pnl:+8.2f}%  '
              f'{avg_win:+8.2f}%  {stop_r:6.1f}%  {trail_r:9.1f}%  {ev:+7.2f}%')

    if rows:
        best_ev = max(r['ev'] for r in rows)
        best    = next(r for r in rows if r['ev'] == best_ev)
        print(f'\n  最佳期望值：移動停利 {best["label"]}（EV {best["ev"]:+.2f}%，{best["total"]} 筆）')


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'scan':
        scan_hold_days()
    elif cmd == 'trail':
        scan_trailing_stop()
    else:
        run()
