"""
一次性修復腳本：用 close 重算全表的 change / change_pct（2026-09-01）

═══ 背景 ═══
陷阱35（2026-08 記錄，當時只記現象未查根因）：prices 表約 4.7%（7,095/150,332 筆）
的 change_pct 被誤存為 0 或錯誤值。2026-09-01 追查到兩個根因並已修復 fetcher.py：

  1. `fetch_history_tpex()`（上櫃歷史回補）把 change / change_pct **直接寫死為 0**
     → 這是 1,496 檔股票大量歸零的主因
  2. `fetch_taiex()` 用迴圈內遞推的 prev_close 算漲跌幅，
     只要 yfinance 回傳的 hist 少了某個交易日，基準就會停在更早的日期，
     算出錯的值卻不報錯
     → 實測 TAIEX 400 筆中 3 筆中招（2026-08-04 / 08-18 / 08-31），
       每次隱含前收都剛好是「前兩個交易日」的收盤

**收盤價（close）本身經與 TWSE 官方 FMTQIK 逐日核對確認全部正確**，
因此可以安全地用 close 重建 change / change_pct。

═══ 這個腳本做什麼 ═══
  逐檔取出全部價格列（依日期升序），用相鄰兩日的 close 重算：
      change     = close - prev_close
      change_pct = change / prev_close * 100
  只在「重算值與現存值差異 > 0.01」時才 UPDATE，避免無謂寫入。
  每檔的第一筆（沒有前一日可比）保持原值不動。

═══ 使用方式 ═══
  cd 專案根目錄
  python3 repair_change_pct.py            # 先試跑，只報告不寫入
  python3 repair_change_pct.py --apply    # 確認後才實際寫入

  執行前建議先備份：cp data/stock.db data/stock.db.bak
"""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn

APPLY = '--apply' in sys.argv


def main():
    conn = get_conn()
    cur  = conn.cursor()

    codes = [r[0] for r in cur.execute(
        'SELECT DISTINCT code FROM prices ORDER BY code').fetchall()]
    print(f'共 {len(codes)} 檔股票（含 TAIEX）')
    print('模式：', '★ 實際寫入' if APPLY else '試跑（不寫入，加 --apply 才會寫）')
    print()

    total_rows = total_bad = 0
    affected_codes = []
    samples = []
    skipped_gap, skipped_wild = [], []

    for code in codes:
        rows = cur.execute(
            'SELECT date, close, change, change_pct FROM prices '
            'WHERE code=? ORDER BY date', (code,)).fetchall()
        total_rows += len(rows)
        if len(rows) < 2:
            continue

        fixes = []
        for i in range(1, len(rows)):
            d, close, chg_old, pct_old = rows[i]
            d_prev, prev = rows[i - 1][0], rows[i - 1][1]
            if not prev or not close:
                continue

            # ⚠️ 守衛一：日期斷層不計算（同陷阱26的教訓）
            # 資料若有缺口（該股當時沒抓、或中間停牌很久），相鄰兩「列」不等於
            # 相鄰兩「交易日」，跨斷層算出來的漲跌幅毫無意義。
            # 試跑時實際看到 0051 算出 +357%、0053 +544% 就是這個原因。
            # 7 天涵蓋正常週末與連假；超過就跳過，保持原值不動。
            try:
                gap = (datetime.strptime(d, '%Y-%m-%d')
                       - datetime.strptime(d_prev, '%Y-%m-%d')).days
            except Exception:
                continue
            if gap > 7:
                skipped_gap.append((code, d_prev, d, gap))
                continue

            chg_new = round(close - prev, 2)
            pct_new = round(chg_new / prev * 100, 2)

            # ⚠️ 守衛二：算出來仍然離譜就不動（台股有 10% 漲跌幅限制，
            # 但除權息/減資/新上市首日等會超過，放寬到 ±40% 當異常門檻）
            if abs(pct_new) > 40:
                skipped_wild.append((code, d, pct_old, pct_new))
                continue

            if (abs((pct_old or 0) - pct_new) > 0.01
                    or abs((chg_old or 0) - chg_new) > 0.01):
                fixes.append((chg_new, pct_new, code, d))
                if len(samples) < 20:
                    samples.append((code, d, pct_old, pct_new))

        if fixes:
            total_bad += len(fixes)
            affected_codes.append((code, len(fixes)))
            if APPLY:
                cur.executemany(
                    'UPDATE prices SET change=?, change_pct=? WHERE code=? AND date=?',
                    fixes)

    if APPLY:
        conn.commit()

    print(f'掃描 {total_rows:,} 筆，需修正 {total_bad:,} 筆 '
          f'（{total_bad / total_rows * 100:.2f}%），涉及 {len(affected_codes)} 檔')
    print()
    print('前 20 筆範例（代號 日期 舊值 → 新值）：')
    for c, d, o, n in samples:
        print(f'  {c:<8} {d}  {o if o is not None else "NULL":>8} → {n:+.2f}%')
    print()
    print('受影響最多的 15 檔：')
    for c, n in sorted(affected_codes, key=lambda x: -x[1])[:15]:
        print(f'  {c:<8} {n:>5} 筆')
    print()
    print(f'⚠️ 因日期斷層（>7天）跳過不計算：{len(skipped_gap):,} 筆')
    for c, a, b, g in skipped_gap[:5]:
        print(f'     {c:<8} {a} → {b}（相隔 {g} 天）')
    print(f'⚠️ 因算出值離譜（|%|>40）跳過：{len(skipped_wild):,} 筆')
    for c, d, o, n in skipped_wild[:5]:
        print(f'     {c:<8} {d}  {o} → {n:+.1f}%（不採用）')
    print('   以上兩類保持原值不動，需要時再個別查證。')

    conn.close()
    if not APPLY:
        print()
        print('※ 這是試跑。確認上面的數字合理後，執行：python3 repair_change_pct.py --apply')
        print('※ 寫入前建議先備份：cp data/stock.db data/stock.db.bak')


if __name__ == '__main__':
    main()
