#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_futures_history.py — 台指期三大法人未平倉的歷史到底拿不拿得到？

════════════════════════════════════════════════════════════════════════
背景（2026-10-07）
════════════════════════════════════════════════════════════════════════

要重測策略D 必須有大盤淨值（S1–S8）。S4（法人現貨）與 S2（融資融券）
已實測可回填到 2018，但 **S3 台指期卡住了**：

    TAIFEX futContractsDateDown?queryStartDate=2026/09/01&queryEndDate=2026/09/04
      → ✅ 回傳的就是那四天（參數有效）
    同一端點要求 2018/01/02~01/05  → ❌ **回應是空的**
    同一端點要求 2022/01/03        → ❌ **回應是空的**

⇒ 不是參數無效，是**下載端點的歷史範圍有限**。

🚨 順帶記錄一個我自己犯的錯（與陷阱41 同一類，值得留著）：
   先前用 `futContractsDate`（HTML 頁）要求 2018/01/02，頁面回了一張
   有數字的表格，我就認定「TAIFEX 有 2018 資料」。
   但那一頁自己標著「**日期2026/10/07**」——**它忽略了日期參數、回傳最新資料**。
   我看到表格裡有數字就下結論，**沒有核對頁面自己標的日期**。
   這正是陷阱41 的通則：「必須驗證回傳的日期就是要求的日期」，
   而我在套用這條規矩去驗別人的程式時，自己違反了它。

════════════════════════════════════════════════════════════════════════
這支腳本要回答兩個問題
════════════════════════════════════════════════════════════════════════

  Q1  TAIFEX 下載端點的歷史邊界在哪？（二分搜尋）
  Q2  FinMind 有沒有更長的歷史？（專案已有 FINMIND_TOKEN）

**每一次都核對回傳的日期**，不只看「有沒有東西」。

用法：
    python3 probe_futures_history.py
"""
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from fetcher import HEADERS, _parse_futures_csv

TAIFEX_URL = 'https://www.taifex.com.tw/cht/3/futContractsDateDown'


def taifex_has(d):
    """
    要求單一日期，回傳 (有沒有資料, 實際拿到的日期集合)。
    ⚠️ 必須回傳實際日期——只看「非空」會重演上面那個錯誤。
    """
    try:
        r = requests.get(TAIFEX_URL, params={
            'down_type': '1', 'commodity_id': 'TXF',
            'queryStartDate': d.strftime('%Y/%m/%d'),
            'queryEndDate':   d.strftime('%Y/%m/%d'),
        }, headers=HEADERS, timeout=30)
        if not r.content or not r.content.strip():
            return False, set()
        parsed = _parse_futures_csv(r.content) or {}
        return bool(parsed), set(parsed)
    except Exception as e:
        print(f'    {d} 例外：{e}')
        return False, set()


def q1_taifex_boundary():
    print('=' * 70)
    print('【Q1】TAIFEX 下載端點的歷史邊界')
    print('=' * 70)

    # 先逐年粗測（每年抓一個一定是交易日的日子）
    probes = [date(y, 6, 15) for y in range(2018, 2027)]
    results = {}
    print('\n  逐年粗測（每年 6/15 附近）：')
    for d in probes:
        # 6/15 可能是週末，往後找到平日
        dd = d
        while dd.weekday() >= 5:
            dd += timedelta(days=1)
        ok, got = taifex_has(dd)
        results[dd.year] = ok
        tag = '✅ 有' if ok else '❌ 空'
        extra = f'　回傳日期 {sorted(got)}' if got else ''
        print(f'    {dd}  {tag}{extra}')
        time.sleep(1.5)

    have = [y for y, v in results.items() if v]
    if not have:
        print('\n  ⇒ 連今年都抓不到 —— 可能是 headers / 網路問題，先確認每日更新還正常')
        return None
    earliest_ok_year = min(have)
    print(f'\n  有資料的年份：{sorted(have)}')

    if earliest_ok_year == 2018:
        print('  ⇒ 2018 就有，不需要二分搜尋')
        return date(2018, 1, 1)

    # 二分搜尋邊界（在「最早有資料的年份」與它前一年之間）
    lo = date(earliest_ok_year - 1, 6, 15)
    hi = date(earliest_ok_year, 6, 15)
    print(f'\n  二分搜尋邊界（{lo} ~ {hi}）：')
    while (hi - lo).days > 20:
        mid = lo + (hi - lo) / 2
        while mid.weekday() >= 5:
            mid += timedelta(days=1)
        ok, got = taifex_has(mid)
        print(f'    {mid}  {"✅ 有" if ok else "❌ 空"}')
        if ok:
            hi = mid
        else:
            lo = mid
        time.sleep(1.5)
    print(f'\n  ★ 邊界約在 {lo} ~ {hi} 之間（誤差 ≤20 天）')
    return hi


def q2_finmind():
    print('\n' + '=' * 70)
    print('【Q2】FinMind 有沒有更長的台指期三大法人歷史')
    print('=' * 70)
    try:
        from config import FINMIND_TOKEN as TOK
    except Exception:
        TOK = ''
    if not TOK:
        print('  ⚠️ config_local.py 沒有 FINMIND_TOKEN，跳過')
        return

    # 專案已用過的 dataset 命名慣例：TaiwanFuturesDaily（app.py:5471）
    # 三大法人的可能名稱逐一試，並**核對回傳的 date 欄**
    candidates = [
        'TaiwanFuturesInstitutionalInvestors',
        'TaiwanFutOptInstitutionalInvestors',
        'TaiwanOptionInstitutionalInvestors',
    ]
    for ds in candidates:
        for probe_start, label in (('2018-01-01', '2018'), ('2022-01-01', '2022')):
            try:
                r = requests.get('https://api.finmindtrade.com/api/v4/data',
                                 params={'dataset': ds, 'data_id': 'TX',
                                         'start_date': probe_start,
                                         'end_date': probe_start[:4] + '-01-15',
                                         'token': TOK}, timeout=30)
                js = r.json()
                st = js.get('status')
                rows = js.get('data') or []
                dates = sorted({x.get('date') for x in rows if x.get('date')})
                if st == 200 and rows:
                    print(f'  ✅ {ds:<40}{label}：{len(rows)} 列　'
                          f'日期 {dates[0]} ~ {dates[-1]}')
                    print(f'     欄位：{sorted(rows[0].keys())}')
                else:
                    print(f'  ❌ {ds:<40}{label}：status={st} '
                          f'msg={str(js.get("msg"))[:60]} 列數={len(rows)}')
            except Exception as e:
                print(f'  ❌ {ds:<40}{label}：例外 {e}')
            time.sleep(1.0)


def main():
    print('台指期三大法人歷史可得性探測\n')
    b = q1_taifex_boundary()
    q2_finmind()

    print('\n' + '=' * 70)
    print('【怎麼讀這份結果】')
    print('=' * 70)
    print("""
  • 若 TAIFEX 邊界晚於 2022 且 FinMind 也拿不到
    ⇒ **任何空頭年都算不出完整的大盤淨值**。
      退路是「S1+S2+S4+S5~S8 的 7 項淨值」（只缺 S3，±3 分），
      比原本缺 S2+S3+S4（±8 分）小得多，但**必須在結論裡標明缺 S3**。

  • 若 FinMind 拿得到 ⇒ 寫一支 FinMind 版的 S3 回填，淨值就完整了。
    ⚠️ 兩個來源的「口數」定義要先對帳：拿 2026 的重疊期間
      逐日比對 FinMind 與 TAIFEX 的 foreign_net，相符才能混用
      —— 否則就是陷阱42「跨來源借資料」的翻版。""")


if __name__ == '__main__':
    main()
