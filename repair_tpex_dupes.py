"""
修復上櫃（TPEx）重複日期資料（2026-09-08 新增，一次性腳本）

═══ 背景（陷阱42）═══
`fetch_today_prices()` 的上櫃區段舊版**強制沿用 TWSE 的日期**、完全不看 TPEx
自己回傳的日期欄位。TPEx 這支 API 只回傳「當下快照」，於是在
「TPEx 已更新到今日、但 TWSE 尚未發布今日資料」的時間點按更新，
就會把**今日的上櫃快照寫成昨日的資料**，造成兩天完全相同。

實測（近一個月，相鄰交易日「開高低收四欄全等」的檔數）：

  日期配對        上市相同   上櫃相同 / 上櫃總數
  08-03→08-04        2      970 / 971   ★
  08-13→08-14        2      978 / 979   ★
  08-19→08-20        0      979 / 980   ★
  09-07→09-08        2      975 / 976   ★
  （其他日期上櫃相同數僅 1~23，屬正常平盤股）

★ 這四天整個上櫃市場被寫入重複資料。上市同期只有 0~6 檔，證明不是市場現象。

**這比「缺資料」更嚴重**——缺資料看得出來，錯資料看起來完全正常，
會直接汙染評分、均線、波動度、回測。

fetcher.py 已修正（優先用 TPEx 自身日期；取不到就只在「TWSE日期==今天」時才存）。
本腳本負責回填既有的錯誤資料。

═══ 做法 ═══
用 yfinance（`{code}.TWO`）重抓上櫃股票的真實歷史日線——yfinance 有正確的
逐日歷史，不像 TPEx OpenAPI 只有當下快照。

**預設只修自選股中的上櫃股**（那些才會進評分與回測；全市場 900+ 檔
逐一呼叫 yfinance 太慢且非必要）。加 `--all` 可修全部受影響的上櫃股。

═══ 使用方式 ═══
  cd ~/台股分析工具
  python3 repair_tpex_dupes.py              # 試跑：找出重複日並列出受影響股票
  python3 repair_tpex_dupes.py --apply      # 修自選股中的上櫃股
  python3 repair_tpex_dupes.py --apply --all  # 修全部（很慢，數百次 yfinance 呼叫）

  執行前建議備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
"""
import sys, os, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn, get_prices, save_prices, get_watchlist

APPLY = '--apply' in sys.argv
ALL   = '--all' in sys.argv
DUPE_RATIO = 0.8      # 上櫃「四欄全等」比例超過此值，視為該日整批重複


def find_dupe_days():
    """回傳 [(前一交易日, 重複日, 重複檔數, 上櫃總數), ...]"""
    conn = get_conn()
    tdays = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' ORDER BY date").fetchall()]
    out = []
    for i in range(1, len(tdays)):
        a, b = tdays[i - 1], tdays[i]
        row = conn.execute('''
            SELECT SUM(CASE WHEN p1.open=p2.open AND p1.close=p2.close
                             AND p1.high=p2.high AND p1.low=p2.low THEN 1 ELSE 0 END),
                   COUNT(*)
            FROM prices p1 JOIN prices p2 ON p1.code=p2.code
            JOIN stocks s ON p1.code=s.code
            WHERE p1.date=? AND p2.date=? AND s.market='TPEx' ''', (a, b)).fetchone()
        same, tot = (row[0] or 0), (row[1] or 0)
        if tot >= 100 and same / tot >= DUPE_RATIO:
            out.append((a, b, same, tot))
    conn.close()
    return out


def affected_codes(dupe_days, watchlist_only=True):
    conn = get_conn()
    wl = {w['code'] for w in get_watchlist()} if watchlist_only else None
    codes = set()
    for a, b, _, _ in dupe_days:
        rows = conn.execute('''
            SELECT p1.code FROM prices p1 JOIN prices p2 ON p1.code=p2.code
            JOIN stocks s ON p1.code=s.code
            WHERE p1.date=? AND p2.date=? AND s.market='TPEx'
              AND p1.open=p2.open AND p1.close=p2.close
              AND p1.high=p2.high AND p1.low=p2.low''', (a, b)).fetchall()
        for r in rows:
            if wl is None or r[0] in wl:
                codes.add(r[0])
    conn.close()
    return sorted(codes)


def repair_one(code, target_dates):
    """用 yfinance 重抓該股，覆寫指定日期。回傳修好的天數。"""
    import yfinance as yf
    hist = yf.Ticker(f'{code}.TWO').history(period='6mo', auto_adjust=False)
    if hist.empty:
        return 0
    by_date = {}
    for ts, row in hist.iterrows():
        by_date[ts.strftime('%Y-%m-%d')] = row

    fixed = 0
    prev_closes = {d: c for d, c in
                   [(x['date'], x['close']) for x in get_prices(code, days=400)]}
    for d in target_dates:
        row = by_date.get(d)
        if row is None:
            continue
        close = round(float(row['Close']), 2)
        if close <= 0:
            continue
        # 前一交易日收盤（yfinance 自身序列），用來算 change/change_pct
        ds = sorted(by_date)
        i = ds.index(d)
        prev = round(float(by_date[ds[i - 1]]['Close']), 2) if i > 0 else None
        chg = round(close - prev, 2) if prev else 0
        save_prices(code, [{
            'date': d,
            'open':  round(float(row['Open']), 2),
            'high':  round(float(row['High']), 2),
            'low':   round(float(row['Low']), 2),
            'close': close,
            'volume': int(row['Volume']) if row['Volume'] else 0,
            'value': 0,
            'change': chg,
            'change_pct': round(chg / prev * 100, 2) if prev else 0,
        }])
        fixed += 1
    return fixed


def main():
    dupes = find_dupe_days()
    print(f'偵測到 {len(dupes)} 個「整批重複」的上櫃日期：')
    for a, b, same, tot in dupes:
        print(f'  {b}（與前一交易日 {a} 相同：{same}/{tot} 檔，{same/tot*100:.0f}%）')
    if not dupes:
        print('沒有發現重複日，不需修復。')
        return

    bad_dates = [b for _, b, _, _ in dupes]
    codes = affected_codes(dupes, watchlist_only=not ALL)
    scope = '全部上櫃股' if ALL else '自選股中的上櫃股'
    print()
    print(f'受影響的{scope}：{len(codes)} 檔')
    print('  ' + '、'.join(codes[:20]) + (' …' if len(codes) > 20 else ''))
    print()
    print('模式：', '★ 實際修復' if APPLY else '試跑（不寫入，加 --apply 才修）')

    if not APPLY:
        print()
        print('※ 確認後執行：python3 repair_tpex_dupes.py --apply')
        print('※ 若要連非自選股一起修（很慢）：加 --all')
        return

    total = 0
    for i, code in enumerate(codes, 1):
        try:
            n = repair_one(code, bad_dates)
            total += n
            print(f'  [{i}/{len(codes)}] {code}：修復 {n} 天')
        except Exception as e:
            print(f'  [{i}/{len(codes)}] {code} 失敗：{e}')
        time.sleep(0.3)

    print()
    print(f'完成，共修復 {total} 筆。重新檢查：')
    for a, b, same, tot in find_dupe_days():
        print(f'  ⚠️ {b} 仍有 {same}/{tot} 檔重複（未修的多半是非自選股）')
    print()
    print('※ 修復後請在 App 按一次「🚀 更新並同步到雲端」。')


if __name__ == '__main__':
    main()
