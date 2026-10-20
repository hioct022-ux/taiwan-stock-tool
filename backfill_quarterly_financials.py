"""
背景 / 要驗證的問題（2026-10-20）
────────────────────────────────────────────────────────────
使用者問「為什麼個股華新科看不到資料？其它個股也會這樣嗎」。

查證結果：華新科（2492）的 prices／chips／fundamentals／monthly_revenue
全部完整到當天，**唯一空的是「季度 EPS 趨勢」那張圖**
（`stock_quarterly_financials` 表）。而且不只它——

    全市場只有 66 檔有季報；103 檔自選股裡 39 檔完全沒有，
    連 2330 台積電、2454 聯發科、2881 富邦金都缺。

而本機實測 yfinance **有**資料（2492 (45,5)、2330 (54,6)、
2454 (45,6)、1101 (47,6)）⇒ 不是資料源的問題。

根因是 `app.py` 季度 EPS 區塊那段懶加載（陷阱19 留下的）：

    st.session_state[f'_qf_fetched_{code}'] = True   # ← 抓之前就鎖住
    try:    _n = _fetch_qf(code, years=4)
    except Exception:  pass                          # ← 失敗沒有任何痕跡

只要那一次抓取失敗（FinMind 逾時、yfinance 連線慢），鎖會留著、
錯誤被吞掉、畫面只是空白——而 Streamlit App 常開著數天不重啟。
這是陷阱51「零結果會被印成什麼？」的同一族：
**失敗必須長得跟成功不一樣。**

本腳本做的事
────────────────────────────────────────────────────────────
把自選股（或指定代號）缺季報的檔一次補齊，並且**逐檔印出結果**，
失敗的明確列出，不靜默。

用法
────────────────────────────────────────────────────────────
    python3 -u backfill_quarterly_financials.py              # 試跑：只列出缺哪些，不抓
    python3 -u backfill_quarterly_financials.py --apply      # 補自選股缺的那些
    python3 -u backfill_quarterly_financials.py --apply --all        # 自選股全部重抓
    python3 -u backfill_quarterly_financials.py --apply 2492 2330    # 只補指定代號

⚠️ 必須在本機執行（沙盒的 proxy 會擋 yfinance 與 FinMind）。
⚠️ `save_quarterly_financials()` 走 INSERT OR REPLACE ⇒ 重抓是幂等的，
   但陷阱18 記著 yfinance 的 NaN 曾把正確資料覆蓋成 0；
   `fetch_quarterly_financials()` 已有 isnan 守衛，所以重抓是安全的。
"""
import sys
import time

from database import (get_watchlist, get_quarterly_financials,
                      get_quarterly_financials_last_period)
from fetcher import fetch_quarterly_financials

SLEEP = 1.2        # 每檔間隔（yfinance 與 FinMind 都有速率限制）


def _why_zero(code: str, name: str) -> str:
    """
    零結果的分類。2026-10-20 首次執行時 39 檔有 4 檔零結果，
    而那 4 檔**全部是結構性的、不是 bug**：

      2881 富邦金／2882 國泰金／2891 中信金  ← 金融保險業（industry='17'）
      9103 美德醫療-DR                        ← 存託憑證

    金融業的損益表**沒有「毛利」這個科目**（銀行與保險的收入結構是
    利息淨收益／保費收入，不走「營收 − 銷貨成本」），而
    `fetch_quarterly_financials()` 兩條路都有 `if rev and gp` 的守衛
    ⇒ 必然被擋掉。DR 是在台掛牌的存託憑證，本身沒有獨立財報。

    ⇒ 這兩類**永遠補不回來**，不該算進「待處理」。
       與十九章「監控清單要區分可修復與已知無解」同一條通則：
       把無解的照樣算進警告數字，使用者兩週後就會學會忽略整個警告。
    """
    try:
        from database import get_conn
        conn = get_conn()
        row = conn.execute('SELECT industry FROM stocks WHERE code=?', (code,)).fetchone()
        conn.close()
        ind = row[0] if row else None
    except Exception:
        ind = None

    if ind == '17':
        return '⚪ 金融保險業，損益表沒有毛利科目 ⇒ 結構性，永遠補不回來'
    if '-DR' in (name or '') or (name or '').endswith('DR'):
        return '⚪ 存託憑證（DR），沒有獨立財報 ⇒ 結構性'
    return '🚨 兩個來源都沒有資料，原因未知 ⇒ 要查'


def main() -> None:
    args  = [a for a in sys.argv[1:]]
    apply = '--apply' in args
    force = '--all' in args
    codes = [a for a in args if not a.startswith('--')]

    wl = {w['code']: w.get('name', '') for w in get_watchlist()}

    if codes:
        targets = [(c, wl.get(c, '')) for c in codes]
        scope   = f'指定 {len(targets)} 檔'
    else:
        targets = [(c, n) for c, n in wl.items()]
        scope   = f'自選股 {len(targets)} 檔'

    # 盤點現況
    missing, has = [], []
    for c, n in targets:
        if get_quarterly_financials_last_period(c) is None:
            missing.append((c, n))
        else:
            has.append((c, n))

    print('=' * 72)
    print(f'季度財報補抓　{scope}')
    print(f'  已有資料 {len(has)} 檔　缺資料 {len(missing)} 檔')
    print('=' * 72)

    todo = targets if force else missing
    if not todo:
        print('\n✅ 沒有要補的（全部已有資料）。若要強制重抓請加 --all')
        return

    print(f'\n要處理 {len(todo)} 檔' + ('（--all 強制重抓）' if force else '（只補缺的）'))
    for c, n in todo:
        print(f'  {c} {n}')

    if not apply:
        print('\n⚠️ 試跑模式，沒有實際抓取。加 --apply 才會寫入。')
        return

    print('\n' + '-' * 72)
    ok, zero, err = [], [], []
    for i, (c, n) in enumerate(todo, 1):
        label = f'[{i}/{len(todo)}] {c} {n}'
        try:
            saved = fetch_quarterly_financials(c, years=4)
        except Exception as e:
            # ★ 刻意不吞：失敗要長得跟成功不一樣（這正是本腳本存在的理由）
            err.append((c, n, repr(e)[:120]))
            print(f'{label}　🚨 例外：{repr(e)[:80]}')
            time.sleep(SLEEP)
            continue

        if saved > 0:
            # ⚠️ 2026-10-20 修：原本用 get_quarterly_financials(...)[0]['period']
            #    當「最新」——但那支函式的 docstring 明寫**升序**，[0] 是最舊的，
            #    而且 quarters=12 會把 15 季截掉前 3 季
            #    ⇒ 35 檔全部印出同一個「2023Q3」，看起來像資料落後三年。
            #    資料其實完全正確（2022Q4~2026Q2）。
            #    這是「用索引假設排序」在本專案的第 N 次（陷阱43 同一族），
            #    而且是在「報告層」而非計算層——數字對、讀出來的結論錯。
            #    正解：用專門回答這件事的那支函式，它也不受 quarters 截斷影響。
            latest = get_quarterly_financials_last_period(c) or '?'
            ok.append((c, n, saved, latest))
            print(f'{label}　✅ 存入 {saved} 季　最新 {latest}')
        else:
            zero.append((c, n))
            print(f'{label}　⚪ 回傳 0 季（{_why_zero(c, n)}）')
        time.sleep(SLEEP)

    print('\n' + '=' * 72)
    print(f'成功 {len(ok)} 檔　零結果 {len(zero)} 檔　例外 {len(err)} 檔')
    print('=' * 72)

    if zero:
        _struct = [(c, n) for c, n in zero if _why_zero(c, n).startswith('⚪')]
        _unknown = [(c, n) for c, n in zero if not _why_zero(c, n).startswith('⚪')]
        if _struct:
            print(f'\n⚪ 結構性、永遠補不回來（{len(_struct)} 檔，不必再處理）：')
            for c, n in _struct:
                print(f'  {c} {n}　{_why_zero(c, n)}')
        if _unknown:
            print(f'\n🚨 原因未知，要查（{len(_unknown)} 檔）：')
            for c, n in _unknown:
                print(f'  {c} {n}')
    if err:
        print('\n🚨 例外（這些要看訊息決定怎麼處理）：')
        for c, n, e in err:
            print(f'  {c} {n}　{e}')

    # 補完後重新盤點，確認真的補上了
    # ★ 結構性缺漏（金融股／DR）不列入「待處理」——十九章那條通則：
    #   把無解的照樣算進警告數字，使用者就會學會忽略整個警告
    still = [(c, n) for c, n in todo
             if get_quarterly_financials_last_period(c) is None]
    _still_fix = [(c, n) for c, n in still if not _why_zero(c, n).startswith('⚪')]
    print(f'\n重算後仍缺 {len(still)} 檔　'
          f'其中結構性無解 {len(still) - len(_still_fix)} 檔、'
          f'待處理 {len(_still_fix)} 檔'
          + ('　✅' if not _still_fix else ''))
    for c, n in _still_fix:
        print(f'  🚨 {c} {n}')

    if ok:
        print('\n最新季度分布（看資料來源落後多少）：')
        dist: dict[str, int] = {}
        for _, _, _, latest in ok:
            dist[latest] = dist.get(latest, 0) + 1
        for p in sorted(dist, reverse=True):
            print(f'  {p}　{dist[p]} 檔')
        print('\n存入季數分布（FinMind 通常給 15 季，yfinance 只有 5~6 季）：')
        sdist: dict[int, int] = {}
        for _, _, s, _ in ok:
            sdist[s] = sdist.get(s, 0) + 1
        for s in sorted(sdist, reverse=True):
            print(f'  {s} 季　{sdist[s]} 檔')


if __name__ == '__main__':
    main()
