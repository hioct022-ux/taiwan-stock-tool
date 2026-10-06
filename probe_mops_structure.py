#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_mops_structure.py — 看清 MOPS 月營收表的實際結構（只讀，1 個請求）

背景：`probe_month_revenue.py` 已確認 MOPS t21sc03 可用（一個請求一個月全市場、
      民國107年都拿得到）。但**不能盲寫 parser**——那正是陷阱44 的錯誤
      （假設欄位結構／日期語意，而沒有先實測）。

這支要回答三件事：
  S1  編碼是什麼？（UTF-8 / Big5）
  S2  欄位順序與名稱？有幾個 table？產業分組標題列怎麼混在裡面？
  S3  能不能從頁面本身驗證「年月＝要求的年月」？（Q3 守衛要靠這個）
      ⚠️ 上一支的 regex 抓不到標題年月，這支要找出正確的字樣

只印結構與樣本列，不解析成資料、不寫入任何東西。
"""

import re
import sys

import requests

ROC, MON = 115, 8          # 民國115年8月，與上一支的「近月」同一份，方便對照
URL = f'https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{ROC}_{MON}_0.html'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}


def fetch(url):
    """
    ⚠️ 先用正常的 TLS 驗證；只有在憑證確實有問題時才退回 verify=False，
       而且**會印出來**——專案舊程式（fetcher.py 對 TWSE）一律 verify=False，
       那是沿用下來的習慣，新寫的不該默默照抄。
       這是公開政府網站的唯讀查詢，但「靜默關掉 TLS 驗證」本身就是壞習慣：
       日後若真遇到中間人，不會有任何跡象。
    """
    try:
        return requests.get(url, headers=HEADERS, timeout=25), True
    except requests.exceptions.SSLError as e:
        print(f'  ⚠️ TLS 驗證失敗（{type(e).__name__}），退回不驗證重試一次')
        print(f'     若正式接入要處理憑證，不要長期帶著 verify=False')
        requests.packages.urllib3.disable_warnings()
        return requests.get(url, headers=HEADERS, timeout=25, verify=False), False


def main():
    print(f'抓取：{URL}')
    r, tls_ok = fetch(URL)
    print(f'HTTP {r.status_code}　{len(r.content):,} bytes　'
          f'TLS 驗證 {"✅ 正常" if tls_ok else "⚠️ 已關閉"}')

    # ── S1 編碼 ──
    print('\n' + '=' * 76)
    print('【S1】編碼判斷')
    print('=' * 76)
    best, best_name = None, None
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            t = r.content.decode(enc, errors='strict')
            print(f'  {enc:<8} ✅ 可完整解碼')
            if best is None:
                best, best_name = t, enc
        except Exception as e:
            print(f'  {enc:<8} ❌ {type(e).__name__}')
    if best is None:
        best, best_name = r.content.decode('big5', errors='ignore'), 'big5(ignore)'
        print(f'  → 全部嚴格解碼失敗，退用 {best_name}')
    print(f'  ★ 採用：{best_name}')
    body = best

    # ── S3 年月字樣（先做，因為上一支在這裡失敗）──
    print('\n' + '=' * 76)
    print('【S3】頁面裡的年月字樣（Q3 守衛要用）')
    print('=' * 76)
    print(f'  要求的是：民國 {ROC} 年 {MON} 月')
    pats = [
        (r'\d{2,3}\s*年\s*\d{1,2}\s*月', 'N年N月'),
        (r'民國\s*\d{2,3}', '民國N'),
        (r'<title[^>]*>(.{0,120})', '<title>'),
        (r'(\d{3})/(\d{1,2})', 'NNN/N'),
    ]
    for pat, label in pats:
        ms = re.findall(pat, body)[:6]
        print(f'  {label:<10} → {ms if ms else "（找不到）"}')
    # 把開頭 1200 字（去標籤）印出來，人眼找標題最準
    head = re.sub(r'<[^>]+>', ' ', body[:4000])
    head = re.sub(r'\s+', ' ', head).strip()
    print(f'\n  去標籤後的開頭 500 字：\n  {head[:500]}')

    # ── S2 表格結構 ──
    print('\n' + '=' * 76)
    print('【S2】表格結構')
    print('=' * 76)
    tables = re.findall(r'<table.*?</table>', body, re.S | re.I)
    print(f'  <table> 數量：{len(tables)}')
    for i, tb in enumerate(tables):
        rows = re.findall(r'<tr.*?</tr>', tb, re.S | re.I)
        has_2330 = '2330' in tb
        print(f'    table[{i}]  <tr> {len(rows):>5}　2330 {"✅" if has_2330 else "—"}'
              f'　{len(tb):>8,} bytes')

    # 找含 2330 的那個 table，印表頭與樣本列
    target = next((tb for tb in tables if '2330' in tb), None)
    if target is None:
        print('\n  ❌ 找不到含 2330 的 table —— 結構與預期不同，把本段貼回對話')
        return

    rows = re.findall(r'<tr.*?</tr>', target, re.S | re.I)
    print(f'\n  ★ 目標 table：{len(rows)} 列')

    def cells(tr):
        cs = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)
        out = []
        for c in cs:
            c = re.sub(r'<[^>]+>', '', c)
            c = c.replace('&nbsp;', ' ').replace('&amp;', '&')
            out.append(c.strip())
        return out

    print('\n  --- 前 8 列（看表頭與產業分組列長什麼樣）---')
    for i, tr in enumerate(rows[:8]):
        cs = cells(tr)
        print(f'    [{i}] 共 {len(cs):>2} 欄  {cs}')

    print('\n  --- 2330 那一列（確認欄位對應）---')
    for tr in rows:
        cs = cells(tr)
        if cs and cs[0].strip() == '2330':
            print(f'    共 {len(cs)} 欄')
            for j, v in enumerate(cs):
                print(f'      [{j:>2}] {v}')
            break
    else:
        print('    ⚠️ 2330 不在第一欄，可能欄序不同——把上面前 8 列的輸出貼回對話')

    # 欄數分布：用來判斷「資料列 vs 分組標題列」怎麼區分
    print('\n  --- 欄數分布（判斷怎麼濾掉非資料列）---')
    from collections import Counter
    cnt = Counter(len(cells(tr)) for tr in rows)
    for k in sorted(cnt):
        print(f'    {k:>2} 欄 × {cnt[k]:>5} 列')

    print('\n' + '=' * 76)
    print('把整段貼回對話。我會依實際欄位寫 parser，不猜。')
    print('=' * 76)


if __name__ == '__main__':
    main()
