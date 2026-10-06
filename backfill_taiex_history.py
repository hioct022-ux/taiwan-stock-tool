"""
一次性回填 TAIEX 長歷史。

════════════════════════════════════════════════════════════════════════
為什麼要回填到 2018（2026-10-06 改版，原本只回填 2 年）
════════════════════════════════════════════════════════════════════════

原始版本（2026-07）只回填 24 個月，目的是讓 MA240 年線算得出來。
現在的理由完全不同、而且重要得多：

**`backfill_prices_history.py` 用 TAIEX 當交易日日曆**
（`thin_trading_days()` 讀 `WHERE code='TAIEX'`）。
⇒ **TAIEX 多長，就決定全市場個股價格能補多長。**
⇒ 而全市場價格的長度，決定整個專案有沒有空頭樣本。

目前的困境（2026-10-06 盤點）：

| | |
|---|---|
| TAIEX 現有 | 2024-07-29 起，**533 筆** |
| 全市場個股價格 | 同樣 2024-07-29 起 |
| 該期間指數 | **+124%，全多頭** |
| `monthly_revenue` 剛回填 | **105 個月（2018-01 起）** ← 但只有 26 個月算得出報酬 |

**專案裡每一個「⚠️ 限制：樣本全在多頭」的警語，根源都是這一條。** 包含：
  • 「回檔小」這個目前最站得住腳的優勢 —— 它的價值本來就該在空頭才顯現
  • 停損 8%→10% 的校準（明說「真的崩盤時 10% 會比 8% 每檔多賠 2pp」，沒驗過）
  • 大盤評分階梯的 `<45 停止進場`（價值該在空頭顯現）
  • 策略 D／E 的「空頭段」目前只有 2026-07 那兩週一個樣本

回填到 2018 就第一次有：**2020 COVID 崩盤（-30%）**、**2022 熊市（-28%）**。

執行：
    python3 backfill_taiex_history.py            # 預設 120 個月（10 年）
    python3 backfill_taiex_history.py 60         # 指定月數

⚠️ 舊資料的 `value`（成交金額）是 yfinance 原始值、不是億元（陷阱27）。
   均線只用 `close`，且成交量圖有 `0 < v < 50000` 過濾防護，不受影響。
   TAIEX 在這裡的用途是「交易日日曆 + 市場基準報酬」，兩者都只需要 close。

執行後**不要刪除此檔**（原版註解寫「可刪除」）——日後若要再往前延伸
（例如要 2008 金融海嘯），這是唯一的入口。
"""
import sys

from fetcher import fetch_taiex
from database import get_conn

MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 120

conn = get_conn()
before = conn.execute(
    "SELECT COUNT(*), MIN(date), MAX(date) FROM prices WHERE code='TAIEX'").fetchone()
conn.close()
print(f'回填前：{before[0]} 筆（{before[1]} ~ {before[2]}）')
print(f'要求月數：{MONTHS}（fetch_taiex 會映射成 yfinance period）')
print()

fetch_taiex(months=MONTHS, force=True)

conn = get_conn()
row = conn.execute(
    "SELECT COUNT(*), MIN(date), MAX(date) FROM prices WHERE code='TAIEX'").fetchone()
print(f'\n回填後：共 {row[0]} 個交易日（{row[1]} ~ {row[2]}）'
      f'　新增 {row[0] - before[0]} 筆')

# 逐年檢查，順便確認有涵蓋到空頭年份
print('\n逐年交易日數：')
for y in range(2016, 2028):
    n = conn.execute("SELECT COUNT(*) FROM prices WHERE code='TAIEX' AND date LIKE ?",
                     (f'{y}%',)).fetchone()[0]
    if n:
        tag = ''
        if y == 2020:
            tag = '  ← COVID 崩盤'
        elif y == 2022:
            tag = '  ← 熊市'
        print(f'  {y}　{n:>4} 筆{tag}')

# 空頭樣本確認：這才是這次回填的真正目的
print('\n★ 空頭樣本確認（年內最大回檔）：')
for y in (2020, 2022, 2024, 2025, 2026):
    rows = [r[0] for r in conn.execute(
        "SELECT close FROM prices WHERE code='TAIEX' AND date LIKE ? ORDER BY date",
        (f'{y}%',))]
    if len(rows) < 20:
        continue
    peak = dd = 0
    for v in rows:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    print(f'  {y}　最大回檔 {dd*100:>7.2f}%'
          + ('  ← 真正的空頭' if dd < -0.15 else ''))
conn.close()

print('\n下一步：')
print('  python3 backfill_prices_history.py --apply --from 2018-01-01')
print('  （用剛補好的 TAIEX 當日曆，補全市場個股價格）')
