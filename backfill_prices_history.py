"""
回填「全市場上市股」價格歷史 —— 2026-09-23 新增，一次性腳本

═══ 背景 / 要解決的問題 ═══
2026-09-23 量到兩件事：
  ① 大盤評分對隔日方向的準確率 52.7%，**低於「每天都猜漲」的基準 55.9%**
     （強訊號 47.8%，更差）。
  ② 個股評分的「5日變化」與**未來**報酬相關係數 ≈ 0，
     與**過去**報酬則是 +0.25（峰值在 -2 日）。評分是後照鏡，不是預警器。

兩個結論的共同限制是**看不見小效果**：現行回測 n=243，
雜訊帶 2.76pp——任何小於它的真實改善都無法與運氣區分。
在雜訊帶壓下來之前，任何「改良」都是盲改。

樣本數 = 時間 × 標的數。時間那一維走不通（實測每交易日只產生 0.47 筆，
要把雜訊帶壓到 1.5pp 還要 8.1 年）。**能立刻放大的是標的數。**

═══ 為什麼卡在價格 ═══
回測要三張表，現況（2026-09-23 實查）：

  chips         ✅ 309 天全市場（1,000~1,355 檔/天）← 2026-09-17 已補齊
  fundamentals  ⚠️ 只有 100 天（2026-05-23 起）← 補不回來，BWIBBU date 參數無效（陷阱44）
  prices        ❌ **全市場只有近 87 個交易日**；再往前只有 58 檔自選股

所以唯一擋住「擴大標的數」的就是價格。而它可以補：
`MI_INDEX?date=YYYYMMDD` 是「**一天一個請求拿全市場**」，
與 T86 同一個成本模型（陷阱41 已實測 date 參數真的有效）。

═══ 補到哪一天：為什麼是 2024-07 而不是 2025-07 ═══
評分要用到 `pos_250` / `ma240`，需要 **250 個交易日的暖身**。
若只補到 2025-07（＝chips 的起點），全市場新股只有 0 天暖身，
`calc_all()` 會**靜默地用較短區間計算**（陷阱32），
於是「全市場股票」與「自選股」的技術面分數基礎不同——
這正是 2026-09-17 踩過的坑：**同一個 65 分，在不同子樣本指的不是同一件事**。

所以預設從 2024-07-29（TAIEX 資料起點，約 250 個交易日前）開始補，
讓評分窗口 2025-07 起的每一檔都有完整暖身。

═══ 三個刻意的設計 ═══
1. **「缺」的定義是「該日全市場檔數 < 800」，不是「該日沒有任何資料」。**
   因為那 299 天其實有資料——只是只有 58 檔自選股。
   用「有沒有資料」判斷會全部跳過（這是陷阱45「水位線」的變形：
   不只要問「有沒有」，要問「該有的量有沒有到」）。
2. **不重寫解析邏輯，改用緩衝把 `save_prices` 換掉。**
   `_fetch_mi_index_prices_for_date()` 已含 MI_INDEX 的欄位對照與**日期驗證守衛**，
   重抄一份就是陷阱33 的病根（同一支 API 在兩處各自解析，改了一處漏另一處）。
   但它每檔呼叫一次 `save_prices()`，而那個函式**每次開關一次連線 + commit**——
   1,200 檔 × 438 天 = 52 萬次，會跑到天亮。
   解法：暫時把 `fetcher.save_prices` 換成只往記憶體塞的版本，
   每天結束再用一次 `executemany` 寫入。解析與守衛完全沿用原函式。
3. **可中斷續跑**——每次執行都重新算缺口。

═══ 已知限制（不是疏漏）═══
- **只有上市（TWSE）**。MI_INDEX 不含上櫃；上櫃要另外用 yfinance 逐檔抓（慢得多）。
- **基本面那 25% 權重仍是預設值 50**（2026-05 之前），永久無解。
  所以擴大後的回測，意義仍是「技術 40% + 籌碼 35% ＝ 75% 權重可驗證」。
- **樣本期間仍全在多頭**。標的數變多不會讓它變成跨環境樣本。

═══ 使用方式 ═══
  python3 backfill_prices_history.py --probe 20240801   # 先探路：確認該日期真的抓得到
  python3 backfill_prices_history.py                 # 試跑：只列出缺哪幾天
  python3 backfill_prices_history.py --apply         # 實際抓取並寫入
  python3 backfill_prices_history.py --apply --from 2025-07-01   # 只補評分窗口（不含暖身）

  執行前務必備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
  執行前請先關閉 App：pkill -f streamlit
  預估：約 440 天 × 2 秒 ≈ 15 分鐘；DB 會增加約 50~60 萬列（約 +80MB）
"""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn, init_db
import fetcher
from fetcher import _fetch_mi_index_prices_for_date

APPLY = '--apply' in sys.argv
FROM = '2024-07-29'          # 約 250 個交易日暖身，見上方說明
if '--from' in sys.argv:
    try:
        FROM = sys.argv[sys.argv.index('--from') + 1]
    except IndexError:
        print('--from 後面要接日期，例如 --from 2025-07-01')
        sys.exit(1)

SLEEP     = 2.0    # TWSE 速率限制，批次補抓用 2 秒（陷阱7）
MIN_FULL  = 800    # 該日 ≥ 這個檔數才算「全市場已有資料」


# ── 緩衝版 save_prices：解析仍用 fetcher 原本那支，只換掉寫入 ──
_BUF = []


def _buffered_save_prices(code, rows):
    for r in rows:
        _BUF.append((code, r['date'], r['open'], r['high'], r['low'],
                     r['close'], r['volume'], r['value'],
                     r['change'], r['change_pct']))


def _flush(conn):
    """一天一次 executemany，取代 1,200 次開關連線。"""
    global _BUF
    if not _BUF:
        return 0
    conn.executemany('''INSERT OR REPLACE INTO prices
        (code, date, open, high, low, close, volume, value, change, change_pct)
        VALUES (?,?,?,?,?,?,?,?,?,?)''', _BUF)
    conn.commit()
    n = len(_BUF)
    _BUF = []
    return n


def thin_trading_days(conn, since):
    """
    拿 TAIEX 的實際交易日當權威日曆，找出「全市場覆蓋不足」的日子。

    ⚠️ 判斷條件刻意是「檔數 < MIN_FULL」而不是「完全沒有資料」——
       那 299 天都有資料，只是只有自選股那 58 檔。
       只問「有沒有」會全部跳過（陷阱45 水位線思維的變形）。
    """
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? ORDER BY date", (since,))]
    have = dict(conn.execute(
        "SELECT date, COUNT(*) FROM prices WHERE code!='TAIEX' AND date>=? GROUP BY date",
        (since,)).fetchall())
    return cal, [d for d in cal if have.get(d, 0) < MIN_FULL]


def probe(ymd):
    """
    單日探路：只抓一天、不寫入，確認 MI_INDEX 對這個年份的歷史日期真的有回應。

    ⚠️ 存在的理由（專案通則）：TWSE 的 date 參數「看起來有效、其實被忽略」
       已經在同一份文件裡出現兩次（陷阱41 STOCK_DAY_ALL、陷阱44 BWIBBU_ALL）。
       花 3 秒先驗一天，勝過跑 15 分鐘後才發現整批是同一天的複製品。
    """
    _orig = fetcher.save_prices
    fetcher.save_prices = _buffered_save_prices
    try:
        cnt, actual = _fetch_mi_index_prices_for_date(ymd)
    finally:
        fetcher.save_prices = _orig
    want = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}'
    print(f'要求日期：{want}')
    print(f'回傳筆數：{cnt}　回傳日期：{actual}')
    _BUF.clear()
    if cnt == 0:
        print('結果：⚪ 查無資料——可能是假日，換一個交易日再試；'
              '若連續幾個交易日都查無資料，代表這個年份抓不到，要縮短 --from 範圍')
    elif actual != want:
        print('結果：❌ 日期不符——date 參數被忽略了，**不要執行 --apply**，先回報')
    else:
        print(f'結果：✅ 可以補。{cnt} 檔，日期正確')
    print('（探路不寫入任何資料）')


def main():
    if '--probe' in sys.argv:
        try:
            probe(sys.argv[sys.argv.index('--probe') + 1].replace('-', ''))
        except IndexError:
            print('--probe 後面要接日期，例如 --probe 20240801')
        return

    init_db()
    conn = get_conn()
    cal, thin = thin_trading_days(conn, FROM)

    if not cal:
        print(f'⚠️ {FROM} 之後沒有 TAIEX 交易日資料，無法建立日曆。先更新 TAIEX。')
        conn.close()
        return

    print(f'起點 {FROM}　TAIEX 交易日 {len(cal)} 天')
    print(f'其中全市場覆蓋足夠（≥{MIN_FULL} 檔）的有 {len(cal)-len(thin)} 天')
    print(f'需要補 **{len(thin)} 天**　預估耗時 {len(thin)*SLEEP/60:.0f} 分鐘（不含寫入）')
    print('模式：' + ('★ 實際抓取並寫入' if APPLY else '試跑（不抓不寫，加 --apply 才會執行）'))
    print('=' * 72)

    if not thin:
        print('✅ 沒有缺口，不需要補。')
        conn.close()
        return

    if not APPLY:
        print('覆蓋不足的交易日（前 40 天）：')
        for i in range(0, min(len(thin), 40), 8):
            print('  ' + '  '.join(thin[i:i + 8]))
        if len(thin) > 40:
            print(f'  …（其餘 {len(thin)-40} 天略）')
        print()
        print('※ 先備份再執行：')
        print('   cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)')
        print('   python3 backfill_prices_history.py --apply')
        conn.close()
        return

    # 換掉寫入路徑（解析與日期守衛仍是 fetcher 原本那支）
    _orig = fetcher.save_prices
    fetcher.save_prices = _buffered_save_prices

    ok = skipped = mismatch = failed = 0
    written = 0
    t0 = time.time()
    try:
        for i, d in enumerate(thin, 1):
            ymd = d.replace('-', '')
            try:
                cnt, actual = _fetch_mi_index_prices_for_date(ymd)
            except Exception as e:
                failed += 1
                _BUF.clear()
                print(f'  [{i}/{len(thin)}] {d}　❌ {type(e).__name__}: {e}')
                time.sleep(SLEEP)
                continue

            if cnt == 0:
                # 查無資料：假日、或 TWSE 該日沒有這份報表
                skipped += 1
                _BUF.clear()
                print(f'  [{i}/{len(thin)}] {d}　⚪ 查無資料，跳過')
            elif actual != d:
                # ⚠️ 陷阱41 的守衛。原函式內部已比對標題民國日期並擋下，
                #    這裡再確認一次並計數——不符就不寫入。
                mismatch += 1
                _BUF.clear()
                print(f'  [{i}/{len(thin)}] {d}　⚠️ 回傳日期是 {actual}，本日未補到')
            else:
                n = _flush(conn)
                written += n
                ok += 1
                if i % 10 == 0 or i == len(thin):
                    el = time.time() - t0
                    eta = el / i * (len(thin) - i) / 60
                    print(f'  [{i}/{len(thin)}] {d}　✅ {n} 筆　（累計 {written:,} 筆，剩約 {eta:.0f} 分）')
            time.sleep(SLEEP)
    finally:
        fetcher.save_prices = _orig

    print('=' * 72)
    print(f'補齊 {ok} 天　查無資料 {skipped} 天　日期不符 {mismatch} 天　失敗 {failed} 天')
    print(f'共寫入 {written:,} 列')

    # ── 結尾驗證 ──
    conn.close()
    conn = get_conn()
    _, thin2 = thin_trading_days(conn, FROM)
    print(f'重算後仍覆蓋不足 {len(thin2)} 天' +
          ('（多為假日或 TWSE 無該日報表）' if thin2 else ' ✅'))

    n_all = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    n_code = conn.execute(
        "SELECT COUNT(*) FROM (SELECT code FROM prices WHERE date>=? "
        "GROUP BY code HAVING COUNT(*)>=200)", (FROM,)).fetchone()[0]
    print(f'prices 總列數 {n_all:,}　其中 {FROM} 起有 ≥200 筆的股票：{n_code} 檔')
    print()
    print('※ 下一步：重建回測快取（全市場會慢很多，先估時間）')
    print('   python3 backtest_portfolio_slots.py cache')
    conn.close()


if __name__ == '__main__':
    main()
