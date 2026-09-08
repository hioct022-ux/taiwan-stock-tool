"""
補齊漏掉交易日的一次性腳本（2026-09-08 新增）

═══ 背景 ═══
使用者 9/7 沒做更新，9/8 更新時發現部分資料沒有一起補進來。診斷結果：

1. **個股收盤價（prices）9/7 缺**——根因已查明（陷阱41）：
   智慧補齊（陷阱39）用 `STOCK_DAY_ALL?date=YYYYMMDD` 補歷史，
   但**該端點的 date 參數其實無效**，永遠回傳最新交易日。
   實測要求 20260907 卻拿到 1150908（9/8）的資料 →
   解析器用 CSV 內的真實日期存檔（沒寫錯資料，是好的防禦），
   但回傳 count>0，於是印出「[補齊] 2026-09-07：2356 筆」看似成功，
   實際上只是把 9/8 的資料重寫一次。**靜默失敗。**
   已修正 `fetcher.py`：補歷史改用 `MI_INDEX`（date 參數實測有效），
   並加上「回傳日期 ≠ 要求日期就當失敗」的守衛。

2. **T86 排行（t86_ranking）9/2、9/7、9/8 缺**——API 實測正常
   （`selectType=ALL&date=20260907` 回傳 stat:OK、date:20260907），
   `fetch_t86()` 的補齊迴圈邏輯讀起來也正確，失敗原因不明（無執行日誌）。
   本腳本直接重抓指定日期，繞過該函式的守衛條件。

═══ 使用方式 ═══
  cd ~/台股分析工具
  python3 backfill_missing_days.py            # 試跑，只檢查缺哪些日期、不寫入
  python3 backfill_missing_days.py --apply    # 實際補抓

  可指定範圍（預設近 15 個日曆日）：
  python3 backfill_missing_days.py --apply --days 30

  執行前建議備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
"""
import sys, os, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn, get_prices
import fetcher

APPLY = '--apply' in sys.argv
DAYS = 15
if '--days' in sys.argv:
    try:
        DAYS = int(sys.argv[sys.argv.index('--days') + 1])
    except Exception:
        pass


def trading_days_from_taiex(days):
    """用 TAIEX 的實際交易日當基準——TAIEX 由 yfinance 抓整段，缺口最少。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    return [p['date'] for p in get_prices('TAIEX', days=400)
            if cutoff <= p['date'] <= today]


def existing_dates(table, where=''):
    conn = get_conn()
    rows = conn.execute(f'SELECT DISTINCT date FROM {table} {where}').fetchall()
    conn.close()
    return {r[0] for r in rows}


def main():
    tdays = trading_days_from_taiex(DAYS)
    if not tdays:
        print('取不到 TAIEX 交易日，請先確認資料庫有資料')
        return

    print(f'基準交易日（取自 TAIEX，近 {DAYS} 個日曆日）：{tdays[0]} ~ {tdays[-1]}，共 {len(tdays)} 天')
    print('模式：', '★ 實際補抓' if APPLY else '試跑（不寫入，加 --apply 才會抓）')
    print()

    have_prices = existing_dates('prices', "WHERE code != 'TAIEX'")
    have_t86    = existing_dates('t86_ranking')

    miss_prices = [d for d in tdays if d not in have_prices]
    miss_t86    = [d for d in tdays if d not in have_t86]

    print(f'個股收盤價（prices）缺 {len(miss_prices)} 天：{miss_prices or "無"}')
    print(f'T86 排行（t86_ranking）缺 {len(miss_t86)} 天：{miss_t86 or "無"}')
    print()

    if not APPLY:
        print('※ 這是試跑。確認上面清單合理後，執行：python3 backfill_missing_days.py --apply')
        return

    # ── 補個股收盤價（用 MI_INDEX，date 參數有效）──
    for d in miss_prices:
        try:
            c, ad = fetcher._fetch_mi_index_prices_for_date(d.replace('-', ''))
            print(f'[收盤價] {d}：{c} 筆' if c else f'[收盤價] {d}：無資料（可能非交易日）')
        except Exception as e:
            print(f'[收盤價] {d} 失敗：{e}')
        time.sleep(1)

    # ── 補 T86 排行 ──
    for d in miss_t86:
        try:
            n = backfill_t86_one_day(d)
            print(f'[T86] {d}：{n} 筆' if n else f'[T86] {d}：無資料')
        except Exception as e:
            print(f'[T86] {d} 失敗：{e}')
        time.sleep(1)

    print()
    print('補抓完成，重新檢查：')
    have_prices2 = existing_dates('prices', "WHERE code != 'TAIEX'")
    have_t862    = existing_dates('t86_ranking')
    print(f'  收盤價仍缺：{[d for d in tdays if d not in have_prices2] or "無"}')
    print(f'  T86 仍缺：{[d for d in tdays if d not in have_t862] or "無"}')
    print()
    print('※ 補完後請在 App 按一次「🚀 更新並同步到雲端」，讓雲端 JSON 也跟著更新。')


def backfill_t86_one_day(target_date):
    """重抓單一日期的 T86 排行（繞過 fetch_t86() 的守衛條件）。"""
    import requests
    from database import save_t86_ranking
    date_str = target_date.replace('-', '')
    url = (f'https://www.twse.com.tw/rwd/zh/fund/T86'
           f'?response=json&date={date_str}&selectType=ALL')
    data = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=fetcher.HEADERS, timeout=20, verify=False)
            data = r.json()
            break
        except Exception:
            if attempt < 2:
                time.sleep(5)
    if not data or data.get('stat') != 'OK':
        return 0

    # ⚠️ 日期驗證守衛（本次事件的核心教訓）：確認回傳的就是要求的那天
    if str(data.get('date', '')) != date_str:
        print(f'  ⚠️ T86 回傳日期 {data.get("date")} ≠ 要求 {date_str}，視為失敗')
        return 0

    def lots(v):
        return int(fetcher.clean_num(v) / 1000)

    rows = []
    for r in (data.get('data') or []):
        try:
            code = str(r[0]).strip()
            if not code or not code.isdigit() or len(r) < 12:
                continue
            fn, tn, dn = lots(r[4]), lots(r[10]), lots(r[11])
            rows.append({
                'code': code, 'name': str(r[1]).strip(),
                'foreign_buy': lots(r[2]), 'foreign_sell': lots(r[3]), 'foreign_net': fn,
                'trust_buy':   lots(r[8]), 'trust_sell':   lots(r[9]), 'trust_net':   tn,
                'dealer_net':  dn,
                'total_net':   lots(r[18]) if len(r) > 18 else (fn + tn + dn),
            })
        except Exception:
            continue
    if rows:
        save_t86_ranking(target_date, rows)
    return len(rows)


if __name__ == '__main__':
    main()
