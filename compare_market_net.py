#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_market_net.py — 回填＋校準之後，大盤淨值長什麼樣？新舊差多少？

════════════════════════════════════════════════════════════════════════
要回答三個問題（2026-10-08，陷阱51 待辦第 4 步）
════════════════════════════════════════════════════════════════════════

  Q1  新舊 S4 在**兩邊都算得出來的期間**差多少？
      （舊 S4 = t86_ranking 加總 + 絕對門檻；只有 2026-05-26 起有資料）

  Q2  ★ 策略D 的兩個觸發門檻，在三個空頭年到底會不會啟動？
      這題**直接決定 D 重測有不有意義**——若 `net≥4` 在 2022 一次都沒觸發，
      那 UI 上那個紅框在最嚴重的空頭年根本不會亮，這本身就是結論。

  Q3  淨值的逐年分布（看 S4 修正後整體有沒有被系統性推偏）

⚠️ 跑之前必須先完成回填 ＋ 校準：
    python3 backfill_futures_finmind.py --apply
    python3 backfill_market_signals.py --apply
    python3 calibrate_signal4.py        （並把切點寫進 indicators.py）

用法：
    python3 compare_market_net.py
"""
import os
import sys
import statistics as st
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn
from backtest_stocks import _build_market_signals
from indicators import PCT_HI, PCT_MID, PCT_LO

# 策略D 的兩個門檻（app.py 的減碼警報框用的就是這兩個）
D_WARN, D_ALERT = 2, 4


def main():
    print('大盤淨值（S1–S8）：回填＋校準後的樣貌')
    print(f'Signal 4 切點：{PCT_HI}/{PCT_MID}/{PCT_LO}（滾動百分位）\n')

    # ⚠️ 必須明確加大視窗——預設 600 天只會看到 2024-05 起，一個空頭年都沒有
    net = _build_market_signals(days=2600)
    if not net:
        print('❌ 算不出淨值')
        return
    ds = sorted(net)
    print(f'涵蓋 {len(ds)} 個交易日　{ds[0]} ~ {ds[-1]}')
    if ds[0] > '2019-01-01':
        print(f'''
🚨 **只涵蓋到 {ds[0]}，沒有 2018 ⇒ 回填可能還沒完成，或視窗仍不足。**
   先確認：
     sqlite3 data/stock.db "SELECT COUNT(DISTINCT date) FROM chips;"      （應約 2130）
     sqlite3 data/stock.db "SELECT COUNT(*) FROM market_margin;"          （應約 2130）
     sqlite3 data/stock.db "SELECT COUNT(*) FROM futures_institutional;"  （應約 2110）''')
        return

    # ── Q3：逐年分布 ──
    by_year = defaultdict(list)
    for d in ds:
        by_year[d[:4]].append(net[d])
    BEAR = {'2018', '2020', '2022'}

    print('\n' + '=' * 78)
    print('【Q3】淨值逐年分布（正 = 偏空）')
    print('=' * 78)
    print(f'  {"年":<8}{"天數":>6}{"中位":>7}{"最小":>7}{"最大":>7}'
          f'{"偏空天數":>10}{"偏多天數":>10}')
    print('  ' + '-' * 72)
    for y in sorted(by_year):
        v = by_year[y]
        if len(v) < 30:
            continue
        tag = ' ★空頭' if y in BEAR else ''
        print(f'  {y + tag:<8}{len(v):>6}{st.median(v):>7.0f}{min(v):>7}{max(v):>7}'
              f'{sum(1 for x in v if x > 0):>9}{sum(1 for x in v if x < 0):>10}')

    # ── Q2：D 的觸發門檻在空頭年會不會啟動（本腳本的重點）──
    print('\n' + '=' * 78)
    print(f'【★ Q2】策略D 的兩個門檻會不會啟動（net≥{D_WARN} 橘框／net≥{D_ALERT} 紅框）')
    print('=' * 78)
    print(f'  {"年":<8}{"天數":>6}{"net≥2":>9}{"佔比":>8}{"net≥4":>9}{"佔比":>8}'
          f'{"最長連續≥2":>12}')
    print('  ' + '-' * 72)
    for y in sorted(by_year):
        v = by_year[y]
        if len(v) < 30:
            continue
        w = sum(1 for x in v if x >= D_WARN)
        a = sum(1 for x in v if x >= D_ALERT)
        run = best = 0
        for x in v:
            run = run + 1 if x >= D_WARN else 0
            best = max(best, run)
        tag = ' ★空頭' if y in BEAR else ''
        flag = '  🚨' if (y in BEAR and a == 0) else ''
        print(f'  {y + tag:<8}{len(v):>6}{w:>9}{w/len(v)*100:>7.1f}%'
              f'{a:>9}{a/len(v)*100:>7.1f}%{best:>12}{flag}')
    print(f'''
  ⇒ 怎麼讀：
     • **🚨 標記 = 那個空頭年 `net≥4`（紅框「全面減碼或出場」）一次都沒觸發。**
       若三個空頭年都是這樣，那 UI 上那個紅框在最該亮的時候不會亮
       ⇒ **這本身就是結論，不需要再跑 D 的回測。**
     • 「最長連續≥2」對照策略E 的 `confirm_days`
       （2026-08 測過 cd=2 是唯一平衡點，但當時只有一個空頭樣本）''')

    # ── Q1：新舊 S4 在重疊期間的差異 ──
    print('\n' + '=' * 78)
    print('【Q1】新舊 S4 的差異（只能在 t86_ranking 有資料的期間比）')
    print('=' * 78)
    conn = get_conn()
    t86 = {r[0]: (r[1] or 0, r[2] or 0) for r in conn.execute(
        'SELECT date,SUM(foreign_net),SUM(trust_net) FROM t86_ranking GROUP BY date')}
    conn.close()
    if not t86:
        print('  t86_ranking 無資料，略過')
        return

    def old_s4(fg, tr):
        """舊版：t86_ranking 加總 + 陷阱34 的絕對門檻。回傳對 net 的貢獻（正=偏空）"""
        bull = bear = 0
        if   fg >= 1050000: bull += 3
        elif fg >=  800000: bull += 2
        elif fg >=  650000: bull += 1
        elif fg <= -1050000: bear += 3
        elif fg <=  -800000: bear += 2
        elif fg <=  -650000: bear += 1
        if   tr >=  100000: bull += 1
        elif tr <= -100000: bear += 1
        return bear - bull

    both = sorted(set(t86) & set(ds))
    print(f'  重疊 {len(both)} 天（{both[0]} ~ {both[-1]}）')
    o = [old_s4(*t86[d]) for d in both]
    print(f'\n  舊 S4 對 net 的貢獻：非零 {sum(1 for x in o if x)} / {len(o)} 天'
          f'　絕對值平均 {st.mean([abs(x) for x in o]):.2f}'
          f'　最大 {max(abs(x) for x in o)}')
    print('''
  ⚠️ **不能直接拿「新舊淨值」相減**：舊版的 S4 來源（t86_ranking）只有 85 天，
     而新版用 chips（2,130 天）。兩者的可比期間太短、且那 85 天全在多頭，
     差異讀不出統計意義。這張表的用途只是確認
     「舊 S4 在它唯一能跑的期間確實幾乎不說話」。''')


if __name__ == '__main__':
    main()
