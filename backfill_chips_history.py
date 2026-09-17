"""
回填個股籌碼（chips）歷史 —— 2026-09-17 新增，一次性腳本

═══ 背景 / 要解決的問題（陷阱48 之後的延伸）═══
2026-09-17 發現：回測評分區間 292 個交易日裡，**chips 只有 140 天有資料**，
另外 152 天 `score_chips()` 因為 `if not chips_list: return 50` 而回傳預設值 50。

後果：那些日子的總分退化成
    總分 = 0.40×技術 + 0.35×50 + 0.25×50 = 0.40×技術 + 30
等於 **籌碼面（35% 權重）完全沒有參與**，整段回測測的其實是「技術面為主」的系統。

這支腳本把那 152 天補回來，讓籌碼面那 35% 權重變成可驗證。

═══ 為什麼便宜（動手前先確認過的事）═══
T86 是「**一天一個請求拿全市場**」，不是逐股抓。152 天 = 152 次呼叫，
每次間隔 2 秒 ≈ 5 分鐘。這與「逐股 × 逐日」的想像差了兩個數量級。

═══ 三個刻意的設計（都對應既有的陷阱教訓）═══
1. **用交易日日曆逐日比對，不用 `MAX(date)`**（陷阱45）——
   水位線模型看不到「中間的洞」，而本專案的缺口正是散在中間。
2. **驗證「回傳日期 == 要求日期」**（陷阱41）——
   TWSE 好幾支 API 會忽略 date 參數卻照樣回 200 + 合法資料。
   `_fetch_t86_chips_for_date()` 本身已用回傳日期存檔（正確防禦），
   這裡再比對一次並計數，不符的算失敗、不算補齊成功。
3. **可中斷續跑**——每次執行都重新算缺口，跑到一半斷掉直接再跑一次即可。

═══ 已知限制（不是疏漏）═══
- **上櫃股永遠補不到**：T86 只含上市股。自選股裡 17 檔上櫃（約 20%）
  的籌碼面會永遠停在預設值 50。
- **基本面（25% 權重）補不回來**：BWIBBU_ALL 的 date 參數無效（陷阱44 實測），
  只拿得到最新一份報表。那一項只能靠時間累積。

═══ 使用方式 ═══
  python3 backfill_chips_history.py              # 試跑：只列出缺哪幾天，不抓不寫
  python3 backfill_chips_history.py --apply      # 實際抓取並寫入
  python3 backfill_chips_history.py --apply --from 2025-01-01   # 自訂起點

  執行前建議備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
  執行前請先關閉 Streamlit（避免搶 SQLite 鎖）：pkill -f streamlit
"""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn, init_db, get_watchlist
from fetcher import _fetch_t86_chips_for_date

APPLY = '--apply' in sys.argv
FROM = '2025-07-01'
if '--from' in sys.argv:
    try:
        FROM = sys.argv[sys.argv.index('--from') + 1]
    except IndexError:
        print('--from 後面要接日期，例如 --from 2025-01-01')
        sys.exit(1)

SLEEP = 2.0          # TWSE 速率限制，批次補抓用 2 秒（見 CLAUDE.md 陷阱7）


def missing_trading_days(conn, since):
    """
    拿 TAIEX 的實際交易日當權威日曆，逐日比對 chips 表缺哪幾天。

    ⚠️ 刻意不用 `MAX(date)` 當水位線——陷阱45 的教訓：
       只要發生過一次「今天成功、昨天失敗」，水位線就會把那個洞永久跨過去。
    """
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? ORDER BY date", (since,))]
    have = {r[0] for r in conn.execute(
        'SELECT DISTINCT date FROM chips WHERE date>=?', (since,))}
    return cal, [d for d in cal if d not in have]


def main():
    init_db()
    conn = get_conn()
    cal, miss = missing_trading_days(conn, FROM)

    print(f'起點 {FROM}　交易日 {len(cal)} 天　chips 已有 {len(cal)-len(miss)} 天')
    print(f'需要補 **{len(miss)} 天**　預估耗時 {len(miss)*SLEEP/60:.1f} 分鐘')
    print('模式：' + ('★ 實際抓取並寫入' if APPLY else '試跑（不抓不寫，加 --apply 才會執行）'))
    print('=' * 72)

    if not miss:
        print('✅ 沒有缺口，不需要補。')
        conn.close()
        return

    if not APPLY:
        print('缺漏的交易日：')
        for i in range(0, len(miss), 8):
            print('  ' + '  '.join(miss[i:i+8]))
        print()
        print('※ 確認無誤後執行：python3 backfill_chips_history.py --apply')
        conn.close()
        return

    ok = skipped = mismatch = failed = 0
    for i, d in enumerate(miss, 1):
        ymd = d.replace('-', '')
        try:
            cnt, actual = _fetch_t86_chips_for_date(ymd)
        except Exception as e:
            failed += 1
            print(f'  [{i}/{len(miss)}] {d}　❌ {type(e).__name__}: {e}')
            time.sleep(SLEEP)
            continue

        if cnt == 0:
            # 查無資料：多半是該日 TWSE 沒有 T86（極少數情況），不是錯誤
            skipped += 1
            print(f'  [{i}/{len(miss)}] {d}　⚪ 查無資料，跳過')
        elif actual != d:
            # ⚠️ 陷阱41 的守衛：API 忽略 date 參數時會回「最新交易日」的資料。
            #    helper 已用回傳日期存檔（所以不會汙染），但這一天仍算沒補到。
            mismatch += 1
            print(f'  [{i}/{len(miss)}] {d}　⚠️ API 回傳的是 {actual}，本日未補到')
        else:
            ok += 1
            print(f'  [{i}/{len(miss)}] {d}　✅ {cnt} 筆')
        time.sleep(SLEEP)

    print('=' * 72)
    print(f'補齊 {ok} 天　查無資料 {skipped} 天　日期不符 {mismatch} 天　失敗 {failed} 天')

    # ── 結尾驗證：重算缺口 + 檢查自選股的涵蓋率 ──
    conn.close()
    conn = get_conn()
    _, miss2 = missing_trading_days(conn, FROM)
    print(f'重算後仍缺 {len(miss2)} 天' + ('（其中多為假日或 TWSE 無資料）' if miss2 else ' ✅'))

    wl = get_watchlist()
    twse = tpex = 0
    for s in wl:
        mk = conn.execute('SELECT market FROM stocks WHERE code=?', (s['code'],)).fetchone()
        n = conn.execute('SELECT COUNT(*) FROM chips WHERE code=? AND date>=?',
                         (s['code'], FROM)).fetchone()[0]
        if (mk[0] if mk else '') == 'TPEx':
            tpex += 1
        elif n > 0:
            twse += 1
    print(f'自選股籌碼涵蓋：上市 {twse} 檔有資料；上櫃 {tpex} 檔永遠沒有（T86 不含上櫃）')
    print()
    print('※ 下一步：重建回測快取才會用到新資料')
    print('   python3 backtest_portfolio_slots.py cache')
    conn.close()


if __name__ == '__main__':
    main()
