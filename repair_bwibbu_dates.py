"""
修正上市基本面（fundamentals）與大盤本益比（market_pe）的日期錯位（2026-11-17，陷阱57）

═══ 背景 ═══
陷阱44（2026-09-08）判定「BWIBBU_ALL 的 title 才是真報表日」，於是改用 title 存檔。
2026-11-17 用兩個月的資料重驗，結論相反：**title 比實際報表早一個日曆日**。

  相鄰兩份報表的隱含 EPS（close/pe）一致率（35,297 對）
    把 title 當報表日        12.6%
    把 title + 1 天當報表日   97.6%

後果：2026-09-08 起所有上市基本面與大盤本益比
  ① 日期早一天（還出現 2026-10-00、週六週日這種不可能的日期）
  ② eps_ttm 是用「錯的那一天」的收盤價反推的，也是錯的

═══ 做法 ═══
對 2026-09-08 起的上市股 fundamentals 與 market_pe：
  新日期 = 往回對齊到交易日（舊日期 + 1 天）     交易日以 TAIEX 為準
  eps_ttm 用新日期的收盤價重算
多個舊日期對到同一個新日期時（週末那次更新與週五那次是同一份報表），保留較晚的那筆。
上櫃基本面（yfinance 來源）不受影響、不動。

修正前先做一次**阻斷式驗證**：整體一致率要 ≥90% 才放行（避免判斷錯了還寫進去）。

═══ 使用方式 ═══
  cd ~/台股分析工具
  python3 repair_bwibbu_dates.py            # 試跑：只印對照表，不寫入
  python3 repair_bwibbu_dates.py --apply    # 實際修正
"""
import sys, os, sqlite3
from datetime import date as _date, timedelta as _td
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn

APPLY = '--apply' in sys.argv
SINCE = '2026-09-08'
MIN_OK = 0.90


def plus1(s):
    y, m, d = map(int, s.split('-'))
    return (_date(y, m, 1) + _td(days=d)).isoformat()   # 能處理 day=0


def _is_weekend(d):
    """只挪週六日（與不存在的日期）。平日不在 TAIEX 裡多半只是今天還沒更新，不動。"""
    try:
        return _date.fromisoformat(d).weekday() >= 5
    except ValueError:
        return True


def main():
    conn = get_conn()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' ORDER BY date")]

    def snap(d):
        i = bisect_right(cal, d)
        return cal[i - 1] if i else None

    # BWIBBU 是上市來源；stocks 表查不到市場別的（新上市、KY 等）也來自它。
    # 只排除上櫃（上櫃基本面另走 TPEx／yfinance，日期邏輯不同）。
    tpex = {r[0] for r in conn.execute("SELECT code FROM stocks WHERE market='TPEx'")}
    rows = [r for r in conn.execute(
        'SELECT code, date, eps_ttm, pe, pb, dividend_yield FROM fundamentals WHERE date>=?',
        (SINCE,)) if r[0] not in tpex]
    twse = {r[0] for r in rows}
    old_dates = sorted({r[1] for r in rows})
    mapping = {s: snap(plus1(s)) for s in old_dates}

    # ── 阻斷式驗證：相鄰報表的隱含 EPS 是否一致 ──
    px = {(c, d): cl for c, d, cl in conn.execute(
        'SELECT code, date, close FROM prices WHERE date>=?', (SINCE,))}
    by_date = {}
    for code, d, _, pe, _, _ in rows:
        if pe and pe > 0:
            by_date.setdefault(d, {})[code] = pe
    ok = tot = 0
    for a, b in zip(old_dates, old_dates[1:]):
        ra, rb = mapping[a], mapping[b]
        if ra == rb or a not in by_date or b not in by_date:
            continue
        for code, pa in by_date[a].items():
            pb_ = by_date[b].get(code)
            ca, cb = px.get((code, ra)), px.get((code, rb))
            if pb_ and ca and cb:
                tot += 1
                ea, eb = ca / pa, cb / pb_
                if abs(ea - eb) / ea < 0.003:
                    ok += 1
    rate = ok / tot if tot else 0
    print(f'驗證：修正後相鄰報表隱含 EPS 一致 {ok}/{tot} = {rate:.1%}（門檻 {MIN_OK:.0%}）')
    if rate < MIN_OK:
        print('🚨 一致率不足，判斷可能有誤，中止、不寫入任何資料。')
        sys.exit(1)

    # ── 對照表 ──
    print('\n舊日期 → 新日期')
    for s in old_dates:
        n = sum(1 for r in rows if r[1] == s)
        try:
            wd = _date.fromisoformat(s).strftime('%a')
        except ValueError:
            wd = '不存在'
        print(f'  {s}（{wd}）→ {mapping[s]}　{n} 檔')

    # 多對一：保留較晚的舊日期
    keep = {}
    for s in old_dates:
        keep[mapping[s]] = s
    dropped = [s for s in old_dates if keep[mapping[s]] != s]
    if dropped:
        print(f'\n同一份報表重複（保留較晚那筆、捨棄）：{dropped}')

    mpe = conn.execute('SELECT date, pe_ratio, pb_ratio, div_yield FROM market_pe WHERE date>=?',
                       (SINCE,)).fetchall()
    print(f'\nfundamentals 上市列 {len(rows)} 筆；market_pe {len(mpe)} 筆')
    print('模式：', '★ 實際修正' if APPLY else '試跑（加 --apply 才寫入）')
    if not APPLY:
        return

    cur = conn.cursor()
    new_rows = []
    for code, d, eps, pe, pb, dy in rows:
        if keep[mapping[d]] != d:
            continue
        nd = mapping[d]
        cl = px.get((code, nd))
        neps = round(cl / pe, 2) if pe and pe > 0 and cl else 0.0
        new_rows.append((code, nd, neps, pe, pb, dy))
    codes = sorted(twse)
    cur.executemany('DELETE FROM fundamentals WHERE code=? AND date>=?',
                    [(c, SINCE) for c in codes])
    cur.executemany('INSERT OR REPLACE INTO fundamentals (code, date, eps_ttm, pe, pb, dividend_yield) '
                    'VALUES (?,?,?,?,?,?)', new_rows)

    new_mpe = {}
    for d, pe, pb, dy in sorted(mpe):
        nd = snap(plus1(d))
        new_mpe[nd] = (nd, pe, pb, dy)          # 同一天保留較晚那筆
    cur.execute('DELETE FROM market_pe WHERE date>=?', (SINCE,))
    cur.executemany('INSERT INTO market_pe (date, pe_ratio, pb_ratio, div_yield) VALUES (?,?,?,?)',
                    list(new_mpe.values()))
    # 上櫃：週末更新時用了「今天」當日期 ⇒ 週六日的列往回挪到前一個交易日
    calset = set(cal)
    wk = [(c, d) for c, d in conn.execute(
        'SELECT code, date FROM fundamentals WHERE date>=?', (SINCE,))
        if c in tpex and d not in calset and _is_weekend(d)]
    moved = 0
    for c, d in wk:
        nd = snap(d)
        if nd and not conn.execute('SELECT 1 FROM fundamentals WHERE code=? AND date=?',
                                   (c, nd)).fetchone():
            cur.execute('UPDATE fundamentals SET date=? WHERE code=? AND date=?', (nd, c, d))
            moved += 1
        else:
            cur.execute('DELETE FROM fundamentals WHERE code=? AND date=?', (c, d))
    print(f'上櫃非交易日列：{len(wk)} 筆（挪到前一交易日 {moved}、與既有重複刪除 {len(wk)-moved}）')

    conn.commit()
    conn.close()
    print(f'完成：fundamentals 寫入 {len(new_rows)} 筆、market_pe 寫入 {len(new_mpe)} 筆。')
    print('※ 之後在 App 按一次「🚀 更新並同步到雲端」。')


if __name__ == '__main__':
    main()
