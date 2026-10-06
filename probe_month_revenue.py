#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_month_revenue.py — 月營收資料源實測（只讀不寫，不碰 DB）

════════════════════════════════════════════════════════════════════════
為什麼要先跑這支（10 分鐘，別跳過）
════════════════════════════════════════════════════════════════════════

本專案已經兩次因為「沒先實測 API 參數」而踩坑：
  陷阱41  STOCK_DAY_ALL 的 date 參數被忽略 → 補齊機制靜默失敗了好幾個月
  陷阱44  BWIBBU_ALL 的 date 參數無效、而且日期欄比報表日期晚一天

通則已經寫進文件：**任何「指定歷史日期」的功能，動手寫之前先花兩分鐘實測。**
這支就是在執行那條規矩。

════════════════════════════════════════════════════════════════════════
為什麼要做月營收（要驗證的問題）
════════════════════════════════════════════════════════════════════════

2026-09-23 量到：個股評分與**未來**報酬 corr = 0、與**過去** = +0.25 —— 它是後照鏡。
看組成就知道為什麼，而且比原本以為的更徹底：

  技術面 40%   = 價格的函數
  籌碼面 35%   = 昨天的成交結果
  基本面 25%   = PE/PB/殖利率 → **分母是價格、分子一季才動一次**
                 ⇒ 它的「日變動」幾乎也全部來自價格

**⇒ 三面加權裡，真正獨立於價格的成分幾乎是零。** 這不是調參能解決的。

月營收是第一個**真正正交**的候選輸入：
  • 每月 10 日前公布上月營收，是**營運事實**，分子自己會動
  • 有明確公布日 ⇒ 可做乾淨的事件研究，結構上不可能 look-ahead
  • 文獻上「盈餘/營收意外後的漂移」是少數反覆被重現的異常現象

**但這支腳本不測預測力**，只回答「這條路通不通」。

════════════════════════════════════════════════════════════════════════
這支要回答的四個問題（決定值不值得投入數小時）
════════════════════════════════════════════════════════════════════════

Q1  歷史拿得到多久？
    ⚠️ **這題決定一切。** 若只拿得到近 1 年，就會重演「基本面只有 2026-05 起」
       那個問題（十五章：回測期一半以上的日子評分只有技術面在跑）——
       測不出也無法歸因。**拿得到 3 年以上才值得做。**

Q2  是「一個請求拿全市場一個月」還是「逐股抓」？
    T86 那次的教訓：原本以為要「87 檔 × 數百天」，實際是「一天一個請求拿全市場」，
    159 個交易日只花 5 分鐘——**差兩個數量級**。這題決定抓取成本。

Q3  回傳的年月，就是要求的年月嗎？（陷阱41/44 的制式檢查）

Q4  拿得到**公布日**嗎，還是只有「營收月份」？
    ⚠️ 這題影響事件研究的乾淨程度。月營收是「上月營收、當月 1~10 日陸續公布」，
       各公司日期不同。若只有月份，保守做法是**假設次月 11 日才可用**
       （寧可少吃一點，也不要 look-ahead）。

用法：
    python3 probe_month_revenue.py
"""

import json
import re
import sys
from datetime import datetime

import requests

requests.packages.urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
TIMEOUT = 25

try:
    from config_local import FINMIND_TOKEN
except Exception:
    FINMIND_TOKEN = ''


def hr(title):
    print()
    print('=' * 78)
    print(title)
    print('=' * 78)


def get(url, **kw):
    kw.setdefault('headers', HEADERS)
    kw.setdefault('timeout', TIMEOUT)
    kw.setdefault('verify', False)
    return requests.get(url, **kw)


# ══════════════════════════════════════════════════════════════════
# 來源 A：FinMind TaiwanStockMonthRevenue
# ══════════════════════════════════════════════════════════════════
def probe_finmind():
    hr('【來源 A】FinMind  TaiwanStockMonthRevenue')
    if not FINMIND_TOKEN:
        print('  ⚠️ config_local.py 沒有 FINMIND_TOKEN，跳過')
        return None

    api = 'https://api.finmindtrade.com/api/v4/data'

    # A1：單股、要求很長的歷史 → 回答 Q1（歷史多久）
    print('\n--- A1  單股歷史長度（2330，要求 2015 起）---')
    rows = []
    try:
        r = get(api, params={
            'dataset': 'TaiwanStockMonthRevenue',
            'data_id': '2330',
            'start_date': '2015-01-01',
            'token': FINMIND_TOKEN,
        })
        j = r.json()
        print(f'  HTTP {r.status_code}　status={j.get("status")}　msg={j.get("msg")}')
        rows = j.get('data') or []
        print(f'  筆數 {len(rows)}')
        if rows:
            print(f'  欄位：{list(rows[0].keys())}')
            print(f'  最早：{rows[0]}')
            print(f'  最新：{rows[-1]}')
            yrs = sorted({str(x.get("revenue_year") or x.get("date", ""))[:4] for x in rows})
            print(f'  ★ Q1 涵蓋年度：{yrs[0]} ~ {yrs[-1]}（共 {len(yrs)} 年）')
    except Exception as e:
        print(f'  ❌ 失敗：{type(e).__name__}: {e}')

    # A2：不給 data_id → 回答 Q2（能不能一次拿全市場）
    print('\n--- A2  不指定 data_id，能不能一次拿全市場？---')
    try:
        r = get(api, params={
            'dataset': 'TaiwanStockMonthRevenue',
            'start_date': '2026-08-01',
            'end_date': '2026-08-31',
            'token': FINMIND_TOKEN,
        })
        j = r.json()
        d = j.get('data') or []
        print(f'  HTTP {r.status_code}　status={j.get("status")}　msg={j.get("msg")}')
        print(f'  筆數 {len(d)}　不同股票數 {len({x.get("stock_id") for x in d})}')
        if len(d) > 500:
            print('  ★ Q2 ✅ 一個請求可拿全市場 → 抓取成本極低')
        elif d:
            print('  ★ Q2 ⚠️ 有回資料但筆數偏少，可能被訂閱等級限制')
        else:
            print('  ★ Q2 ❌ 不給 data_id 拿不到 → 需逐股抓（1,000+ 檔，較慢）')
    except Exception as e:
        print(f'  ❌ 失敗：{type(e).__name__}: {e}')

    # A3：Q3 日期守衛 + Q4 公布日
    print('\n--- A3  Q3 年月是否相符 / Q4 有無公布日 ---')
    try:
        r = get(api, params={
            'dataset': 'TaiwanStockMonthRevenue',
            'data_id': '2330',
            'start_date': '2026-03-01',
            'end_date': '2026-05-31',
            'token': FINMIND_TOKEN,
        })
        d = (r.json().get('data') or [])
        for x in d:
            print(f'  {x}')
        if d:
            k = set(d[0].keys())
            has_pub = bool(k & {'publish_date', 'announce_date', 'release_date'})
            print(f'  ★ Q4 公布日欄位：{"✅ 有" if has_pub else "❌ 沒有（只有營收月份）"}')
            print(f'     ⇒ {"可用實際公布日" if has_pub else "保守假設次月 11 日才可用"}')
            # date 欄的語意
            print(f'  ★ `date` 欄語意判斷：{d[0].get("date")} '
                  f'(revenue_year={d[0].get("revenue_year")}, '
                  f'revenue_month={d[0].get("revenue_month")})')
    except Exception as e:
        print(f'  ❌ 失敗：{type(e).__name__}: {e}')

    return rows


# ══════════════════════════════════════════════════════════════════
# 來源 B：MOPS 公開資訊觀測站 月營收彙總表
# ══════════════════════════════════════════════════════════════════
def probe_mops():
    hr('【來源 B】MOPS 公開資訊觀測站（t21sc03，一個請求一個月全市場）')
    print('  ⚠️ MOPS 近年換過網域，所以多個候選一起試——照陷阱44「先實測不要假設」')

    # 民國年_月。測「近月」與「三年前同月」兩個時點 → 同時回答 Q1 與 Q2
    cases = [('近月', 115, 8), ('三年前', 112, 8), ('八年前', 107, 8)]
    hosts = ['https://mopsov.twse.com.tw', 'https://mops.twse.com.tw']

    ok_any = False
    for label, roc, mon in cases:
        print(f'\n--- {label}：民國 {roc} 年 {mon} 月（上市 sii）---')
        hit = False
        for host in hosts:
            url = f'{host}/nas/t21/sii/t21sc03_{roc}_{mon}_0.html'
            try:
                r = get(url)
                body = r.content.decode('utf-8', errors='ignore')
                if len(body) < 3000:
                    body = r.content.decode('big5', errors='ignore')
                # 粗略數一下表格列數與是否出現已知股票
                n_tr = body.count('<tr')
                has_2330 = '2330' in body
                # 抓標題裡的年月，驗證 Q3
                m = re.search(r'(\d{2,3})\s*年\s*(\d{1,2})\s*月', body)
                title_ym = f'{m.group(1)}年{m.group(2)}月' if m else '(抓不到)'
                print(f'  {host[:28]:<30} HTTP {r.status_code}　'
                      f'{len(body):>8,} bytes　<tr> {n_tr:>5}　2330 {"✅" if has_2330 else "❌"}')
                if r.status_code == 200 and n_tr > 100 and has_2330:
                    print(f'      ★ 可用！標題年月 = {title_ym}　'
                            f'（要求 {roc}年{mon}月 → {"相符 ✅" if m and int(m.group(1))==roc and int(m.group(2))==mon else "⚠️ 不符，需加守衛"}）')
                    hit = True
                    ok_any = True
                    break
            except Exception as e:
                print(f'  {host[:28]:<30} ❌ {type(e).__name__}')
        if not hit:
            print('      ❌ 這個時點拿不到')

    if ok_any:
        print('\n  ★ Q2 ✅ MOPS 是「一個請求一個月全市場」→ 15 年 ≈ 180 個請求，數分鐘')
    return ok_any


def main():
    print(f'月營收資料源實測　{datetime.now():%Y-%m-%d %H:%M}')
    print('（只讀，不寫入 DB、不改任何檔案）')

    fm = probe_finmind()
    mops = probe_mops()

    hr('【結論：這條路通不通】')
    print("""
  判斷標準（事前訂好，避免看到數字再找理由）：

    ✅ 值得投入   歷史 ≥ 3 年，且（全市場一次拿 或 逐股但可接受）
    ⚠️ 勉強       歷史 1~3 年 → 只能測近期，結論會很弱
    ❌ 擱置       歷史 < 1 年 → 會重演「基本面只有 2026-05 起」那個問題

  ⚠️ 不論結果如何，下一步都**不是**直接建表，而是先想清楚訊號定義：
     用「營收 YoY 的加速度」（本月 YoY vs 前三月 YoY 平均）還是「創新高」？
     以及公布日的保守處理（沒有公布日就假設次月 11 日才可用）。
    """.rstrip())
    print(f'\n  FinMind：{"有回資料" if fm else "無／失敗"}')
    print(f'  MOPS　 ：{"可用" if mops else "不可用／網址需再查"}')
    print('\n  把整段貼回對話，我依實際結果決定要不要做、怎麼做。')


if __name__ == '__main__':
    main()
