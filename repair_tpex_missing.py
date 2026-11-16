"""
補上櫃（TPEx）缺漏的收盤日（2026-11-17 新增）

═══ 背景 ═══
上櫃收盤來自 TPEx OpenAPI，**只有當下快照、不能指定日期**（陷阱39 已知限制）。
所以某幾天沒按更新，上市那半會由 MI_INDEX 自動補回來，上櫃那半就永久缺。
而資料完整性檢查只看「那天有沒有任何一筆收盤」，上市補回來之後那天看起來就完整了
⇒ 2026-11-11、11-12 上櫃 970 檔整天消失，沒有任何警告。

═══ 做法 ═══
找出近 45 個交易日中「上櫃檔數 < 中位數一半」的日子，用 yfinance（{code}.TWO）
補回來（沿用 repair_tpex_dupes.repair_one，已用過、驗過）。
預設只補自選股裡的上櫃股（那些才進評分）；--all 補全部（很慢）。

═══ 使用方式 ═══
  cd ~/台股分析工具
  python3 repair_tpex_missing.py            # 試跑：列出缺漏日與要補的股票
  python3 repair_tpex_missing.py --apply    # 補自選股的上櫃股
"""
import sys, os, time, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn, get_watchlist
from repair_tpex_dupes import repair_one

APPLY = '--apply' in sys.argv
ALL = '--all' in sys.argv


def find_missing_days(lookback=45):
    conn = get_conn()
    tdays = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' ORDER BY date DESC LIMIT ?",
        (lookback,))][::-1]
    cnt = dict(conn.execute(
        "SELECT p.date, COUNT(*) FROM prices p JOIN stocks s ON s.code=p.code "
        "WHERE s.market='TPEx' AND p.date>=? GROUP BY p.date", (tdays[0],)).fetchall())
    conn.close()
    med = statistics.median([cnt.get(d, 0) for d in tdays])
    return [(d, cnt.get(d, 0), med) for d in tdays if cnt.get(d, 0) < med * 0.5]


def main():
    miss = find_missing_days()
    if not miss:
        print('✅ 近 45 個交易日的上櫃收盤都完整。')
        return
    print('上櫃收盤缺漏日：')
    for d, n, med in miss:
        print(f'  {d}　只有 {n} 檔（平常約 {med:.0f}）')
    dates = [d for d, _, _ in miss]

    conn = get_conn()
    if ALL:
        codes = [r[0] for r in conn.execute("SELECT code FROM stocks WHERE market='TPEx'")]
    else:
        tp = {r[0] for r in conn.execute("SELECT code FROM stocks WHERE market='TPEx'")}
        codes = sorted(w['code'] for w in get_watchlist() if w['code'] in tp)
    conn.close()
    print(f'\n要補的{"全部上櫃股" if ALL else "自選股上櫃股"}：{len(codes)} 檔')
    print('  ' + '、'.join(codes[:25]) + (' …' if len(codes) > 25 else ''))
    print('模式：', '★ 實際補齊' if APPLY else '試跑（加 --apply 才寫入）')
    if not APPLY:
        return

    total = fail = 0
    for i, code in enumerate(codes, 1):
        try:
            n = repair_one(code, dates)
            total += n
            mark = '' if n == len(dates) else f'　⚠️ 應補 {len(dates)} 天'
            print(f'  [{i}/{len(codes)}] {code}：補 {n} 天{mark}')
        except Exception as e:
            fail += 1
            print(f'  [{i}/{len(codes)}] {code} 失敗：{e}')
        time.sleep(0.3)
    print(f'\n完成：共補 {total} 筆，失敗 {fail} 檔。')
    print('※ 之後在 App 按一次「🚀 更新並同步到雲端」。')


if __name__ == '__main__':
    main()
