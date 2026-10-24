# CLAUDE.md — AI 維護交接文件

> 這份文件給接手維護這個台股分析工具的 AI 看。包含所有函式簽名、資料結構、API 細節、已知陷阱，以及常見修改模式。不需要先讀源碼，讀這份文件就能直接開始工作。

---

## 一、專案概覽

**用途：** 台股每日盤後資料收集 + 分析 + 雲端同步的工具。本機執行 Streamlit，雲端只讀。

**技術棧：**
- Python 3.11+（Streamlit 1.58+, Plotly, SQLite, yfinance, APScheduler）
- 本機：SQLite → 每日抓資料 → 匯出 JSON → git push → GitHub
- 雲端（Streamlit Cloud）：從 GitHub raw URL 讀取 JSON → 匯入暫時 SQLite → 唯讀瀏覽

**所有者的 GitHub repo：** `hioct022-ux/taiwan-stock-tool`（`config.py` 中 `GITHUB_REPO`）

---

## 二、檔案職責一覽

| 檔案 | 職責 | 改功能時通常需要動到 |
|------|------|------|
| `app.py` | 所有頁面 UI 和渲染邏輯 | 顯示邏輯、訊號閾值、圖表 |
| `database.py` | SQLite 讀寫封裝 | 新增資料表或欄位 |
| `fetcher.py` | TWSE/yfinance/TAIFEX 資料抓取 | 新增資料來源 |
| `github_sync.py` | JSON 匯出/匯入、git push | 新增需要同步到雲端的資料 |
| `indicators.py` | 技術指標計算（MA/RSI/KD/MACD/布林） | 新增指標公式 |
| `scorer.py` | 個股評分引擎 | 調整個股評分邏輯 |
| `backtest.py` | 開盤前預判訊號回測（本機執行） | 回測邏輯 |
| `backtest_stocks.py` | 個股評分策略回測（A/B/C/D + 掃描） | 策略參數調整 |
| `config.py` | 所有可調參數（閾值、係數、路徑） | 調整指標參數 |
| `config_local.py` | **本機專屬、不上傳 Git**（Token、IS_LOCAL） | — |
| `scheduler.py` | APScheduler 每日排程（16:30 自動抓資料） | 排程時間 |

---

## 三、IS_LOCAL 模式切換邏輯

```python
# config.py
try:
    from config_local import IS_LOCAL as _IS_LOCAL
    IS_LOCAL = _IS_LOCAL   # 本機：True
except ImportError:
    IS_LOCAL = False        # 雲端：False（config_local.py 不存在）
```

IS_LOCAL 影響的功能：

| 功能 | 本機（True） | 雲端（False） |
|------|------------|-------------|
| 資料抓取 | ✅ 可用 | ❌ 停用 |
| 三大法人現貨圖資料來源 | `get_chips_market_aggregate()` | 直接讀 `chips_market_agg.json` |
| 開盤前預判資料來源 | DB（`get_market_margin` 等） | 直接讀各 JSON 檔 |
| 自選股評分資料來源 | DB（`get_prices` 等） | 直接讀 `{code}.json` via `_read_stock_json()` |
| Signal 4（法人現貨）資料來源 | `get_chips_market_aggregate()` 轉換格式 | 同左（讀 `chips_market_agg.json`） |
| 「🚀 同步到雲端」按鈕 | ✅ 顯示 | ❌ 隱藏 |
| 個股自動補抓 | ✅ 自動執行 | ❌ 停用 |

---

## 四、database.py — 所有函式簽名

### 連線

```python
get_conn() -> sqlite3.Connection
# 回傳 WAL 模式的 SQLite 連線，DB_PATH = data/stock.db
```

### 初始化

```python
init_db() -> None
# 建立所有資料表（IF NOT EXISTS），執行 migration（ALTER TABLE 補欄位）
# 新增資料表必須在這裡加 CREATE TABLE IF NOT EXISTS
```

### 價格資料

```python
save_prices(code: str, rows: list[dict]) -> None
# rows 每項：{'date','open','high','low','close','volume','value','change','change_pct'}
# UNIQUE(code, date)，使用 INSERT OR REPLACE

get_prices(code: str, days: int = 400) -> list[dict]
# 依日期升序，最多 days 筆
# 回傳 key：date, open, high, low, close, volume, value, change, change_pct

get_latest_price_date(code: str) -> str | None
# 回傳最新有資料的日期字串，例如 '2026-06-06'
```

### 基本面

```python
save_fundamental(code, date, eps, pe, pb, div) -> None

get_fundamentals(code: str, days: int = 400) -> list[dict]
# key：date, eps_ttm, pe, pb, dividend_yield
```

### 籌碼（個股）

```python
save_chips(code: str, date: str, data: dict) -> None
# data key：foreign_buy/sell/net, trust_buy/sell/net, dealer_buy/sell/net,
#            margin_balance, short_balance（均為整數，單位：張）

get_chips(code: str, days: int = 65) -> list[dict]
# 注意：內部有 WHERE date >= date('now', '-{days*2} days') 的日期範圍過濾
# key：date, foreign_buy, foreign_sell, foreign_net,
#      trust_buy, trust_sell, trust_net,
#      dealer_buy, dealer_sell, dealer_net,
#      margin_balance, short_balance
```

### 三大法人市場彙總（雲端用）

```python
save_chips_market_agg(rows: list[dict]) -> None
# rows 每項：{'date', 'foreign_net', 'trust_net', 'dealer_net'}

get_chips_market_agg_from_table(days: int = 30) -> list[dict]
# 從 chips_market_agg 表讀取（雲端使用），升序
# key：date, foreign_net, trust_net, dealer_net（單位：張）

get_chips_market_aggregate(days=60, min_stocks=500, stocks_only=True) -> list[dict]
# 本機使用：從 chips 表彙整全市場，HAVING COUNT(*) >= min_stocks 過濾不完整日期
# 必須加 WHERE date >= date('now', '-{days*2} days') 否則會撈出 2017 年老資料
# key：date, stock_count, foreign_net, trust_net, dealer_net
#
# ⚠️ stocks_only=True 是 2026-10-07 新增且**設為預設**（陷阱51）：
#    只算 4 碼純數字、非 00 開頭的普通股，**排除 ETF／權證**。
#    主動型 ETF 的「外資買賣超」是初級市場申購買回量，不是外資在買股票；
#    實測 ETF 占外資絕對值中位 41%、**11% 的日子把方向整個翻轉**。
#    預設設 True 是刻意的——Signal 4、市場壓力監控、三大法人現貨圖三處
#    都走這個函式，讓它們各自決定會重演「同一個數字在不同地方不一樣」。

get_chips_market_series(since=None, min_stocks=500, stocks_only=True) -> list[dict]
# 2026-10-07 新增。全期間（或 since 之後）全市場三大法人每日淨額，**升序**。
# 與 get_chips_market_aggregate() 的差別：**不受 date('now', -N days) 限制**，
# 供回測與歷史回溯使用（那些情境要整段歷史，不是「近 N 天」）。
# ⚠️ 新增理由：回測的 S4 原本讀 t86_ranking、app.py 讀 chips 彙總——**兩邊不同源**，
#    而門檻是依 chips 校準的，套在 t86_ranking 上實測 ±3分觸發率 0.0%
#    ⇒ 回測裡的 S4 幾乎是死的。這個函式讓兩邊讀同一份資料。見陷阱51。
```

### 滾動百分位評分（`indicators.py`，2026-10-07 新增）

```python
pct_rank_score(value, history, hi=95, mid=85, lo=70, min_n=60) -> (score, pct)
# 用 |value| 在 |history| 的百分位決定強度（±3/±2/±1/0）、用 value 正負決定方向。
# history **必須只含決策日及之前的資料**，否則就是偷看未來。
# 樣本 < min_n 或 value 為 None → 回 (0, None)，寧可不計分也不亂給。
#
# ★ 為什麼用百分位而不是絕對門檻：量級會隨市場規模漂移
#   （外資淨額 p95：2025 是 366,841、2026 是 544,660，差 48%）
#   ⇒ 絕對張數的門檻套到 2018 必然幾乎不觸發，S4 在空頭年會是死訊號。
#   百分位是尺度無關的，同一套規則在 2018 與 2026 都成立。
#   與 Signal 11（P/C 比率）已經在用的做法相同。
# ⚠️ 切點 95/85/70 尚未校準完成（實際觸發率 11.6/21.6/38.7% vs 目標 5/15/30%），
#   原因與待辦見陷阱51。PCT_HI/PCT_MID/PCT_LO 已抽成模組常數。
#
# 三處（app.py / backtest.py / backtest_stocks.py）共用這一份實作——
# 陷阱34／43 都是「同一訊號三份實作、只改一兩處」造成的。
```

### 月營收（`monthly_revenue`，2026-10-14 新增存取函式）

```python
get_monthly_revenue(code, limit=24, as_of=None) -> list[dict]
# 依「營收月份」降序（最新在前）。key：rev_year, rev_month, avail_date,
#   revenue, yoy_pct, mom_pct, cum_yoy_pct, revenue_last_y
# ⚠️ revenue 單位是 **仟元**（MOPS 原始單位）。1 億元 = 100,000 仟元，
#    換算放在顯示層（`app.py` 用 `/100000`）。
#
# ★ 內建 `avail_date <= as_of`（預設今天）的過濾，**不可以拿掉**。
#   理由見十五章月營收那節：沒有來源提供逐股公布日，而 2026-10-06 實查
#   9 月營收當天只有 176/993 檔已公布 ⇒ 用「次月1日」拿到的是
#   「只有 18% 公司、且偏向先公布者（業績通常較好）」，
#   那比單純偷看 10 天**更惡性**。
#
# 回填腳本 `backfill_monthly_revenue.py` 原本直接寫 DB、沒有存取函式，
# 這支是 2026-10-14 為了個股頁顯示才補的。
#
# ★ 2026-10-17 另加**完整度守衛**（`incomplete_revenue_months()`）：
#   某營收月筆數 < 全市場中位 ×0.6 ⇒ **整月不回傳**。
#   理由：一次性回填把「執行當天只公布了 18%」的 2026-09 凍結進 DB，
#   而那個子集的 YoY 中位比完整月高 **8.5pp**（純選擇偏誤）。見陷阱53。
#   守衛放在這裡而非 UI ⇒ `github_sync` 的雲端匯出自動受保護。
#   ⚠️ 回測端直接查表，**不受這道守衛保護**。
```

### T86 三大法人排行

```python
save_t86_ranking(date: str, rows: list[dict]) -> None
# 先 DELETE WHERE date=date，再批次 INSERT
# rows 每項：{code, name, foreign_buy, foreign_sell, foreign_net,
#             trust_buy, trust_sell, trust_net, dealer_net, total_net}

get_t86_ranking(date=None, sort_by='trust_net', top=15) -> (list[dict], str)
# date=None 自動取最新日期；sort_by 可為 trust_net/foreign_net/total_net/dealer_net
# 回傳 (rows, date)

get_t86_ranking_bottom(date=None, sort_by='trust_net', top=15) -> (list[dict], str)
# 同上，但 ORDER BY ASC（賣超排行）

get_t86_last_date() -> str | None
# T86 最新日期

get_t86_market_aggregate(days: int = 10) -> list[dict]
# 從 t86_ranking 彙整每日市場合計（外資/投信/合計），升序
# key：date, foreign_net_total, trust_net_total, total_net_total
```

### 大盤融資融券

```python
save_market_margin(date: str, data: dict) -> None
# data key：margin_balance, margin_buy, margin_sell,
#            short_balance, short_buy, short_sell（均為億元整數）

get_market_margin(days: int = 120) -> list[dict]
# 升序，key 同上加 date

get_market_margin_last_date() -> str | None
```

### 台指期三大法人未平倉

```python
save_futures_institutional(date: str, data: dict) -> None
# data key：foreign_long, foreign_short, foreign_net,
#            trust_long, trust_short, trust_net,
#            dealer_long, dealer_short, dealer_net（口數，正=多）

get_futures_institutional(days: int = 90) -> list[dict]
# 升序，key 同上加 date
```

### 選擇權 P/C 比率（2026-06 新增）

```python
save_options_pc(date: str, call_oi: int, put_oi: int, pc_ratio: float) -> None
# 資料來源：TAIFEX pcRatioDown，Big5 CSV

get_options_pc(days: int = 60) -> list[dict]
# 升序，key：date, call_oi, put_oi, pc_ratio
# ⚠️ 必須用 dict(zip(cols, r))，get_conn() 無 row_factory，dict(r) 無效

get_options_pc_last_date() -> str | None
# ⚠️ 必須用 row[0]，不能用 row['date']
```

**TAIFEX pcRatioDown CSV 格式陷阱：**
```python
# 日期格式：'2026/06/12'（斜線分隔，非民國年）
date = raw_date.replace('/', '-')  # → '2026-06-12'

# 欄位順序（put 在 call 之前）：
# cols[0]=日期, cols[1]=賣權成交量, cols[2]=買權成交量, cols[3]=成交量比率%,
# cols[4]=賣權未平倉量, cols[5]=買權未平倉量, cols[6]=未平倉比率%
put_oi  = int(cols[4].replace(',', ''))
call_oi = int(cols[5].replace(',', ''))
pc_ratio = round(float(cols[6].replace(',', '')) / 100, 4)  # 168.35 → 1.6835
```

### 大盤本益比

```python
save_market_pe(date, pe_ratio, pb_ratio=None, div_yield=None) -> None

get_market_pe(days: int = 250) -> list[dict]
# key：date, pe_ratio, pb_ratio, div_yield

get_market_pe_last_date() -> str | None
```

### 除權息

```python
save_exdividend(rows: list[dict]) -> None
# is_confirmed=1（TWT49U 正式）→ INSERT OR REPLACE
# is_confirmed=0（TWT48U 早期預告）→ INSERT OR IGNORE（正式資料已存在則跳過）

get_exdividend(days=30) -> list[dict]              # 近 days 天（含過去）
get_exdividend_upcoming(days=30) -> list[dict]      # 今天起未來 days 天
get_exdividend_by_code(code) -> list[dict]          # 個股近一年
```

### 自選股與標籤

```python
get_watchlist() -> list[dict]
# key：code, name, tags(list), added_at

add_watchlist(code: str, name: str, tags=None) -> None
# tags 可為 list 或 str

remove_watchlist(code: str) -> None

update_watchlist_tags(code: str, tags: list) -> None
update_watchlist_tag(code: str, tag: str) -> None  # 向下相容舊版

get_tags() -> list[str]     # 依 sort_order 排序
add_tag(name: str) -> bool
rename_tag(old: str, new: str) -> bool  # 同步更新所有自選股的標籤
delete_tag(name: str) -> bool           # 同步從所有自選股移除
```

### 其他

```python
save_stock_info(code, name, market, industry) -> None
# market = 'TWSE' | 'TPEx'

search_stock(keyword: str) -> list[dict]
# 對 code 和 name 做 LIKE 查詢，最多 20 筆

save_note(code, auto_note, user_note='') -> None
get_notes(code, limit=10) -> list[dict]
delete_note(note_id: int) -> None
update_user_note(code, date, user_note) -> None

save_etf_holdings(etf_code, etf_name, constituents) -> None
# 先 DELETE 再寫入
get_etf_holders(stock_code) -> list[dict]  # 持有此股的所有 ETF
get_etf_last_update() -> str | None

save_ownership(code, foreign_pct, date) -> None
get_ownership(code) -> dict | None  # {'foreign_pct', 'date'}

log_update(status, message) -> None
get_last_update() -> dict | None  # {'date', 'status', 'message', 'updated_at'}
```

---

## 五、資料庫 Schema 完整版

```sql
stocks (code PK, name, market, industry, updated_at)
prices (code+date UNIQUE, open, high, low, close, volume, value, change, change_pct)
fundamentals (code+date UNIQUE, eps_ttm, pe, pb, dividend_yield)
chips (code+date UNIQUE, foreign_buy/sell/net, trust_buy/sell/net, dealer_buy/sell/net, margin_balance, short_balance)
chips_market_agg (date PK, foreign_net, trust_net, dealer_net)  ← 雲端用彙整表
watchlist (code UNIQUE, name, tag TEXT, added_at)  ← tag 欄位存逗號分隔字串
watchlist_tags (name PK, sort_order)
notes (id PK, code, date, auto_note, user_note, created_at)
etf_holdings (etf_code+stock_code UNIQUE, etf_name, weight, shares, updated_at)
update_log (id PK, date, status, message, updated_at)
ownership (code PK, foreign_pct, date, updated_at)
exdividend (ex_date+code UNIQUE, name, prev_close, ref_price, div_value, div_type, is_confirmed)
t86_ranking (date+code UNIQUE, name, foreign_buy/sell/net, trust_buy/sell/net, dealer_net, total_net)
market_margin (date PK, margin_balance/buy/sell, short_balance/buy/sell)
futures_institutional (date PK, foreign/trust/dealer × long/short/net)
market_pe (date PK, pe_ratio, pb_ratio, div_yield)
options_pc_ratio (date PK, call_oi, put_oi, pc_ratio)  ← 2026-06 新增，TAIFEX 選擇權P/C
monthly_revenue (code+rev_year+rev_month UNIQUE, avail_date, name, revenue,
           revenue_prev_m, revenue_last_y, mom_pct, yoy_pct,
           cum_revenue, cum_last_y, cum_yoy_pct, market, note, updated_at)
           ← 2026-10-07 新增。來源 MOPS t21sc03（一請求一月全市場、cp950 編碼）
           105 個月 / 2018-01~ / 993 檔 / 97,701 列
           ★ avail_date = 營收月的**次月 11 日** = 最早可用日，防 look-ahead
             （法規 10 日前公布完；FinMind 的 date 欄是次月1日 ⇒ 用它會偷看 10 天）
             存成實體欄位是刻意的：任何查詢都不可能忘記加這個限制。**不要「優化」掉**
           yoy_pct 是 MOPS 直接給的，與用 revenue/revenue_last_y 反算 100.000% 相符
positions (id PK, code, name, entry_date, entry_price, shares, stop_price,
           renew_count, status, entry_score, entry_ms, exit_reason,
           exit_date, exit_price, pnl_pct, note, created_at)
           ← 2026-07 新增，持倉追蹤（本機專屬，不匯出 JSON）
           entry_score/entry_ms = 進場時的個股/大盤評分，供策略驗證分組
```

---

## 六、github_sync.py — 關鍵函式

### export_to_json(code=None)
匯出所有資料到 `data/json/`。匯出的 JSON 檔列表：

| 檔案 | 內容 |
|------|------|
| `stocks.json` | 全市場股票清單（list） |
| `watchlist.json` | 自選股清單（list），空清單不覆蓋 |
| `watchlist_tags.json` | 自訂標籤（list of str） |
| `meta.json` | 最後更新時間、`exported_at`（觸發雲端重新載入的 key） |
| `TAIEX.json` | `{'prices': [...], 'exported_at': ...}` |
| `market_margin.json` | `{'rows': [...], 'exported_at': ...}` |
| `futures_institutional.json` | `{'rows': [...], 'exported_at': ...}` |
| `market_pe.json` | `{'rows': [...], 'exported_at': ...}` |
| `exdividend.json` | `{'rows': [...], 'exported_at': ...}` |
| `t86.json` | `{'date', trust_top/bot, foreign_top/bot, total_top/bot, 'exported_at'}` |
| `chips_market_agg.json` | `{'rows': [...], 'exported_at': ...}` |
| `options_pc.json` | `{'rows': [...], 'exported_at': ...}` |
| `{stock_code}.json` | `{'code', prices, fundamentals, chips, ownership, monthly_revenue, 'exported_at'}` ← `monthly_revenue` 2026-10-14 新增 |

### sync_via_git(code=None)
呼叫 `export_to_json()` 後執行 `git add data/json/ → git commit → git push`。使用本機 git 認證（SSH key 或 macOS Keychain），不需要 Token。

### init_cloud_data()
雲端版啟動時呼叫（被 `st.cache_resource` 包裹）。從本機 JSON 路徑讀取（Streamlit Cloud 部署時 JSON 已在 repo 內）。

**重要：** 個股 JSON 迴圈的 skip 名單：
```python
if code in ('stocks', 'watchlist', 'meta', 't86', 'exdividend', 'TAIEX',
            'market_margin', 'futures_institutional', 'market_pe', 'chips_market_agg',
            'watchlist_tags', 'options_pc', 'positions'):
    continue
```
**每新增一個大盤層級的 JSON 檔，都必須加到這個 skip 名單**，否則會被誤當成股票代號解析。（`positions.json` 2026-08新增，內容是加密過的持倉資料，見十八章「雲端唯讀同步與密碼／加密保護」）

---

## 七、config.py — 可調參數

```python
# 路徑
DB_PATH  = data/stock.db
JSON_DIR = data/json/

# GitHub
GITHUB_REPO   = 'hioct022-ux/taiwan-stock-tool'
GITHUB_BRANCH = 'main'
GITHUB_TOKEN  = 從 config_local.py 讀取（雲端沒有此檔案，則為空字串）

# 排程
AUTO_FETCH_HOUR   = 16
AUTO_FETCH_MINUTE = 30

# 技術指標
MA_SHORT = 5, MA_MID = 20, MA_LONG = 60
# indicators.py 另計算 ma120（半年線）/ ma240（年線），無對應 config 常數
RSI_PERIOD = 14, KD_PERIOD = 9
MACD_FAST = 12, MACD_SLOW = 26, MACD_SIGNAL = 9
BBAND_PERIOD = 20, BBAND_STD = 2

# 評分權重（2026-06 調整：強化短線預判）
WEIGHT_FUNDAMENTAL = 0.25   # 基本面 25%（原 40%）
WEIGHT_TECHNICAL   = 0.40   # 技術面 40%（原 35%）
WEIGHT_CHIPS       = 0.35   # 籌碼面 35%（原 25%）

# 大盤市值校準（每 6~12 個月更新一次）
TWSE_CAP_COEF       = 16.70   # 億元 / 指數點
TWSE_CAP_CALIBRATED = '2026-05-30'
TWSE_CAP_WARN_DAYS  = 365

# 融資警戒比例（佔市值）
MARGIN_RATIO_WARNING = 1.0    # %
MARGIN_RATIO_DANGER  = 1.2    # %

# 個股評分等級閾值
GRADE = {80:'強力買進', 65:'偏多操作', 50:'中性觀望', 35:'偏空謹慎', 0:'風險偏高'}
```

---

## 八、外部 API 來源與注意事項

### TWSE（台灣證券交易所）

| 資料 | API 端點 | 格式 | 速率限制 |
|------|----------|------|---------|
| 全市場收盤（帶日期，首選） | `STOCK_DAY_ALL?date=YYYYMMDD` | **CSV**（民國7碼日期） | 每日一次 |
| 全市場收盤（無日期，備援） | `STOCK_DAY_ALL?response=json` | JSON | 偶爾回傳舊資料 |
| 個股日線價格（上市） | `STOCK_DAY` | JSON | 每月一次，間隔 ≥ 0.4s |
| 上市股票清單 | `BWIBBU_ALL` | JSON | 日更新 |
| 個股三大法人（T86） | `T86` | JSON | 每日一次 |
| 大盤融資融券 | `MI_MARGN` | JSON | 日更新，標籤要完全比對 |
| 除權息（預告）| `TWT48U` | JSON | is_confirmed=0 |
| 除權息（正式）| `TWT49U` | JSON | is_confirmed=1 |

**日期格式陷阱（最常見 Bug）：**
```python
# TWSE 混用兩種格式：
# 民國年 7 碼：1150528 → 2026-05-28
# 西元年 8 碼：20260528 → 2026-05-28
def parse_date(s):
    if len(s) == 7 and s[0] == '1':
        return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
    elif len(s) == 8 and s[0] == '2':
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
```

**融資融券標籤完全比對（不能用 in）：**
```python
# 正確
if label == '融資(交易單位)': ...
if label == '融資金額(仟元)': ...
if label == '融券(交易單位)': ...
# 錯誤：'融資' in label 會讓「融資金額」覆蓋「融資張數」
```

### TPEx（上櫃）
- 個股日線、基本面：用 `yfinance`，suffix = `.TWO`
- 三大法人：不支援（TWSE T86 只有上市股）

### TAIFEX（台灣期貨交易所）
- API 回傳 Big5 編碼 CSV：`r.content.decode('big5', errors='ignore')`
- 單次查詢最多 30 天；歷史補抓需逐月分批
- 外資期貨絕對口數（常態 -5 ~ -8 萬口）是結構性避險部位，**不代表方向**；開盤前預判用「日變化量」
- **Signal 3 閾值（2026-07 依實際資料校準）**：日變化中位數約 1,800 口、平均約 2,500 口
  - 強訊號（±2分）：日變化 **≥±5,000 口**（約 9% 天數）
  - 弱訊號（±1分）：日變化 **≥±3,000 口**（約 30% 天數）
  - 中性：日變化 < ±3,000 口（約 70% 天數）
  - 5日趨勢（±1分）：累積變化 **≥±8,000 口**（約 13% 天數）

### yfinance（即時外部市場）
- 函式：`_fetch_global_markets()`，`@st.cache_data(ttl=900)`（15 分鐘快取）
- Tickers：

| 名稱 | Ticker | 類型 |
|------|--------|------|
| S&P 500 | `^GSPC` | 指數（計入評分） |
| Nasdaq | `^IXIC` | 指數（計入評分） |
| 費半 SOX | `^SOX` | 指數（計入評分） |
| TSM ADR | `TSM` | 股票（計入評分） |
| VIX | `^VIX` | 指數（計入評分） |
| WTI 原油 | `CL=F` | 期貨（不計入評分，僅顯示） |
| 黃金 | `GC=F` | 期貨（不計入評分，僅顯示） |
| 美元指數 | `DX-Y.NYB` | 指數（不計入評分，僅顯示） |
| USD/TWD | `TWD=X` | 匯率（不計入評分，僅顯示；值愈高 = 台幣愈弱） |

---

## 九、app.py — 頁面路由與主要函式

### 頁面架構

```python
# st.session_state['page'] 控制路由
# 可能值：'market' | 'watchlist' | 'stock_detail' | 't86' | 'exdividend'
#         | 'notes' | 'market_tracker' | 'strategy'

def render_market()          # 大盤分析（含開盤前預判 Signal 1–11、評分歷史圖）
def render_watchlist()       # 自選股（含 🎯/🔥 型態篩選）
def render_stock(code)       # 個股查詢（7 個分頁：技術/基本/估值/籌碼/評分/備註/匯出）
def render_t86()             # 法人排行（T86 買超/賣超榜）
def render_exdividend()      # 除權息（預告 + 正式，TWT48U / TWT49U）
def render_notes()           # 個股筆記
def render_market_tracker()  # 市場追蹤（DDR4/上銀/鴻海/台達電/鴻勁 5 個監控分頁）
def render_strategy()        # 投資策略（依大盤評分決定個股進場門檻）
```

### 側邊欄自選股清單顯示（2026-06 新增）

每支自選股按鈕下方會顯示一行價格摘要，直接從 DB 讀取（`get_prices(code, days=1)`）：

```
⚪ 2330 台積電 72分
06-24  2,390  ▼ -100 (-4.02%)
```

- 日期格式：`MM-DD`（省略年份節省空間）
- 收盤價：白色加粗
- 漲跌顏色：**台灣慣例，紅色=漲、綠色=跌**（`'#ef4444' if chg >= 0 else '#22c55e'`）；符號 ▲=漲 ▼=跌
- 使用 `:+.0f` 格式，**不要另外加 `+` 前綴否則會出現 `++100`**
- 本機與雲端版均顯示（不受 IS_LOCAL 影響）
- 每次頁面渲染都直接讀 DB，不走快取（N 支股票 N 次 SQLite 查詢，速度足夠）

### 個股頁籤結構（render_stock 內）

```python
tabs = st.tabs(['📊 技術面', '💰 基本面', '📈 估值分析',
                '🏦 籌碼面', '⭐ 綜合評分', '📝 備註欄', '📤 匯出分析'])
# tabs[0] render_technical(result, name)
# tabs[1] render_fundamental(result, code, name)
# tabs[2] render_valuation(result, code, name, fund_data)   ← 2026-06 新增
# tabs[3] render_chips(result, code, name, chips_list, market, ownership_override=_own)
# tabs[4] render_score(result, code, name)
# tabs[5] render_notes(result, code, name)
# tabs[6] render_export(result, code, name, chips_list)
```

**`fund_data` 來源（render_stock 內）：**
- 本機：`get_fundamentals(code, days=400)`
- 雲端：`_read_stock_json(code)` 回傳的第二個元素

### render_valuation(result, code, name, fund_data) — 估值分析頁籤

**Section 1：歷史估值百分位**
- 用 `fund_data` 過濾有效 PE（0 < pe < 500）、PB（0 < pb < 100）
- 計算各分位值（25%/50%/75%）與現值百分位排名
- 顏色：≥85% 紅（偏貴）、≥60% 橘、≥40% 黃、≥20% 淡綠、<20% 綠（便宜）
- PE 歷史走勢圖：橘線 + 三條虛線（25%/50%/75%）+ 紫色現值線 + 藍色合理區間帶

**Section 2：合理價格區間（三情境 PE 估值）**
- 預設 PE 假設：歷史 25%（悲觀）/ 50%（合理）/ 75%（樂觀）分位
- 預設 EPS 預估：eps_now × 0.9 / 1.0 / 1.2
- 用 `st.number_input` 讓使用者自行調整各情境 PE 與 EPS
- 計算 `val = pe × eps` 並顯示現價相對估值的漲跌幅
- 長條圖 + 紫色虛線（現價）對比三情境
- EPS ≤ 0 時不顯示估值區間（PE 法不適用）

**注意：** widget key 為 `f'pe_bear_{code}'` 等，帶入股票代號避免多股同時渲染衝突。

### 個股頁月營收 YoY 顯示（2026-10-14 新增，**純資訊、不計分**）

**起因：** 使用者問「個股的評分機制似乎失去合理性，如南亞，它近期漲勢和它的評分
相去遠，是不是應該檢討評分機制的加權？」

**先查資料，結果與推測相反——評分在漲之前確實給了訊號：**

| 日期 | 收盤 | 總分 | 技術 | 基本 | 籌碼 | 之後 60 日 |
|---|---|---|---|---|---|---|
| 2026-04-29 | 91.6 | **71** | 75 | 50 | 81 | **+90.0%** |
| 2026-06-11 | 96.9 | **70** | 87 | 43 | 69 | **+137.9%** |
| 2026-09-30 | 255.5 | **78** | 96 | 38 | 85 | — |
| **2026-10-14** | **349.0** | **51** | 52 | **23** | 70 | — |

4/29 與 6/11 都跨過 65 門檻（股價 91.6／96.9，10/14 是 349）。**系統講過了。**
今天 51 分是因為過熱：RSI 80.6、BIAS5 +9.4%、近1年位置 100%、PE 56.3、殖利率 0.23%。
**分數低正是因為它漲了 310%。**

**⇒ 「調加權讓漲多的股票分數更高」這個方向已經量測過是錯的**（2026-09-24，n=44,521）：
評分越高 → 報酬越高（+1.04%→+1.87%）但**勝率越低（45.6%→41.8%，4.1 個標準誤）**，
而 alpha 完全不動。調加權去追價格 = 把評分推得更像後照鏡（corr(評分變化, 未來報酬)=0）。

**但使用者指出了一個真缺口：基本面 25% 全是評價類指標（PE/PB/殖利率），完全不看成長。**
南亞月營收 YoY 連四月加速（+19.4→+31.4→+31.8→+44.5→**+46.7%**），
而基本面給它 23 分、判為「昂貴」。trailing PE 對盈餘反轉中的公司本來就沒有意義。

**處置：採「只顯示、不動規則」**（使用者選的方案 C）。位置在個股「💰 基本面」頁籤、
季度 EPS 趨勢**之前**。兩個 metric 列（最新月營收／YoY／MoM）＋ 雙子圖
（上：YoY 長條，紅=成長、綠=衰退，陷阱25 的台灣慣例；下：月營收億元）。

**⚠️ 定位（caption 必須保留那串字）：純資訊參考、不計入評分、不影響進場門檻、
不可當作進出場理由。** 與 🎯🔥 型態、量能水位、類股資金流向**完全相同的定位**，
這是第五次套用同一條通則。即使它是專案唯一通過檢定的訊號，仍有兩個硬限制：

| 限制 | 數字 |
|---|---|
| 優勢太小、被配置的運氣吃掉 | 約 **0.5pp/月**，而持 5 檔的資金曲線帶寬是 **±8pp/月** ⇒ 完全看不見 |
| 動能交互作用 | **動能最弱那組 YoY 幾乎沒用**（+0.61%，t=+1.42 不顯著）|

⇒ 要當規則必須先回測「**現有策略 ＋ YoY 篩選**」——那是十五章月營收那節
標著「尚未做」的兩項之一（另一項「當第四個分項 vs 當篩選門檻」已於 2026-10-18 做完，
**結果是第四個分項顯著更好**，見十五章該節）。

#### 實作上的三個刻意選擇

| | 做法 | 理由 |
|---|---|---|
| 雲端支援 | 塞進**個股 JSON**（`{code}.json` 加 `monthly_revenue` 欄位，24 個月） | 若另開大盤層級 JSON 就得改 `init_cloud_data()` 的 skip 名單（第六章規定），而月營收本來就是 per-stock 資料 |
| 讀取 | 新增 `_monthly_revenue_for(code)`，**不動 `_read_stock_json()`** | 後者現在回 4-tuple、多處呼叫；改成 5-tuple 等於要同步改每個 call site，漏一處就是 ValueError |
| 防 look-ahead | 過濾寫在 `get_monthly_revenue()` 裡，匯出時就已套用 | 雲端讀到的 JSON 本身就不含未公布月份，**兩條路徑不會不一致** |

#### ✅ 已接進每日更新 ＋ 完整度守衛（2026-10-17，原本的「已知缺口」已處理）

原本這裡寫著「`monthly_revenue` 是一次性回填、`fetch_all()` 完全沒碰它，
**它會隨時間變舊而且不會有任何警告**」。2026-10-17 處理完，而且**查的時候發現
真正的問題比「變舊」嚴重得多**——完整記錄見陷阱53，摘要：

| | |
|---|---|
| 🚨 不是變舊，是**變偏** | DB 裡的 2026-09 只有 **176/993 檔（18%）**，那是 10/06 回填當天的快照。而 9 月的 `avail_date` 是 10-11，**已經過了** ⇒ 個股頁那時正在供應那份 18% 子集 |
| 偏誤已量到 | 同看 **2026-08（完整月）**，那 176 檔「早公布者」YoY 中位 **+21.8%** vs 其餘 817 檔 **+13.3%** ⇒ **差 8.5pp**。同一個月、唯一分組依據是「9月有沒有早公布」 |

**兩道防線（刻意做兩層，因為它們擋的是不同的失敗）：**

| | 做法 | 擋什麼 |
|---|---|---|
| ① `fetcher.fetch_monthly_revenue()` | 每日重抓「**當月＋前兩個月**」，`INSERT OR REPLACE` 蓋掉不完整的那份。**不用水位線**（陷阱45 的病根） | 資料變舊／停在不完整快照 |
| ② `database.incomplete_revenue_months()` | 某營收月筆數 < 全市場中位 ×0.6 ⇒ **整月不供應** | **①沒跑成功時的保險**。「只有 176 檔」與「這個月真的只有 176 家公司」在數字上長得一樣 |

**★ 守衛放在存取函式（`get_monthly_revenue()`）裡，不是放在 `app.py`**
⇒ `github_sync.export_to_json()` 走同一支 ⇒ **雲端匯出自動受保護**，不必改第二處。

⚠️ **回測端不受這道守衛保護**：`backtest_revenue_filter.py` /
`backtest_revenue_signal.py` 直接查表（`SELECT ... FROM monthly_revenue`）。
目前影響極小（只有最後一個月、且 10/14 那次測試的資料截止在那之前），
但**日後若要用「含最新月份」的資料重跑，要自己過濾**。

#### 順帶驗證的兩件事

- **KY 股確實沒有月營收**（實測 1256／1337／1338／1340／1341／1589／1590／1591 全部 0 筆）
  ⇒ 十五章那句「KY 股 30 檔沒有月營收（MOPS 列在另一區段）」**正確**。
  ⚠️ 第一次測試我挑了 8422 當「KY 股」，它回 24 筆——**那是我選錯股票**（8422 不是 KY），
  不是資料有問題。**驗證既有結論時，先確認樣本真的屬於那個類別。**
- **單位**：`revenue` 是仟元。南亞 2026-08 的 30,601,161 仟元 = **306.0 億元**，合理。
  （跨欄位/跨單位運算前先拿真實數字手算一次——陷阱28 的通則。）

---

### _check_consolidation_pattern(prices) — 量縮整理型態掃描（2026-07 新增）

定義在模組頂層（`_CHART_CONFIG` 上方）。自選股側邊欄每支股票渲染時呼叫，符合條件者在按鈕標籤前顯示 🎯。

**三個條件同時成立才回傳 True：**
1. 今日收盤 > MA20（月線之上）
2. 近 3 日成交量均低於 20 日均量（量縮）
3. 近 3 日低點不破底（`low[1] >= low[0]` 且 `low[2] >= low[1]`）

**資料來源：** `get_prices(code, days=25)`（側邊欄渲染時已取 25 天，共用同一份資料）

**篩選入口：** 自選股清單篩選列「🎯 整理」選項，點選後只顯示符合的股票。

**注意：** 第四個條件（主力券商買超）刻意不實作，因資料來源（券商分點）不在現有系統內。

### _scan_watchlist_patterns() — 把買點型態接到會被看到的地方（2026-08 新增）

**問題：** 大盤評分的操作建議會寫「買點挑回檔日（**量縮、不破前低**），不追漲」，但使用者看完不知道**哪幾檔**符合，得自己一檔一檔翻。而 `_check_consolidation_pattern()` 的三個條件（站上月線＋近3日量縮＋低點不破底）**就是那句建議的具體化**——功能早就存在（2026-07 就做了），只是只接在側邊欄旗標與篩選列，沒接到「使用者讀到那句建議的當下」。這是本專案第三次出現同一類問題（前兩次：評分衰退警告只在個股頁、軋空旗標只在自選股清單），處理原則見十八章「評分衰退提示搬到持倉列表」的通則。

**函式：** 定義在 `_check_volume_breakout()` 正上方。掃描全部自選股，回傳 `{'consol': [(code,name),...], 'breakout': [...]}`。判斷順序與側邊欄旗標一致（兩者互斥、🔥 優先）。快取於 `st.session_state`，key 為 `_wl_patterns_{TAIEX最新日期}`（雲端用 `_get_meta_version()`），86 檔只掃一次。本機走 `get_prices(code, days=25)`、雲端走 `_read_stock_json()`。

**接入兩處：**

| 位置 | 顯示 |
|------|------|
| 大盤評分卡下方（`_ms >= 45` 才顯示） | 藍框「📍 目前符合上述買點型態的自選股」，列出 🎯/🔥 各幾檔與前 4 檔股名；**都沒有時顯示灰框「不必勉強找標的，等型態出現再說」** |
| 投資策略頁「符合進場條件」清單 | 新增「型態」欄（6欄→7欄：`[2.0,0.7,0.9,0.9,1.3,0.9,0.6]`），顯示 🎯 綠／🔥 橘／— 灰 |

大盤偏空（評分 <45）時不顯示買點掃描框——那時本來就該暫停進場，顯示買點反而矛盾。

**「都沒有」也要顯示，是刻意的設計：** 空清單本身就是答案（「今天沒有符合回檔條件的標的」），比什麼都不顯示更有用，可以直接阻止「想買點什麼」的衝動。

**⚠️ 定位（UI caption 必須保留這句）：型態純供挑進場時點，不是進場理由，也不影響評分或門檻。** 回測從來沒有驗證過 🎯/🔥 型態本身有沒有預測力，它只是把「大盤建議說的回檔日」翻譯成具體標的。**不可把型態當成第二道篩選條件**（例如「只買有 🎯 的」），那等於新增一條未經驗證的規則——若日後真想這樣做，必須先照十五章的流程回測。

### 量能水位顯示 ＋ `<45` 暫停進場提示（2026-09-15 新增，兩者皆純顯示層）

**起因：** 使用者問「近日成交量一直減少代表什麼」，接著提出「這種盤不容易有利得，系統是不是該有警戒訊號、不要勉強出手」。

**先查有沒有測過——有，而且已經否決。** `backtest_trend_filter.py`（2026-08-27，見十五章「停損距離校準」同批）用 Kaufman 效率比 ER 測過「趨勢不明確時別進場」：ER≥0.20/0.30/0.40 在 2026 有效但 **2025 全面變差**，且**被擋掉的訊號原本平均 +2.10%～+2.82%（是好交易）**。更關鍵的是按 ER 四等分的檢視：**最震盪那組 alpha 仍有 +1.21%、停損率與其他組相當**——**震盪期表現差主要是 beta 低（市場漲得少），不是 alpha 壞掉**。

**使用者這版的差別是用「量能」而非「趨勢強度」，那沒測過，所以實測了一次（253 個交易日，TAIEX 層級）：**

| 5日量 vs 20日量 | 天數 | 未來10日均漲 | 勝率 | vs 基準 |
|---|---|---|---|---|
| ★ 無條件基準 | 223 | **+2.63%** | **66.8%** | — |
| **≤-15%（量縮）** | **15** | **-0.46%** | 46.7% | **-3.09pp** |
| -15~-5% | 53 | +2.57% | 60.4% | -0.06pp |
| -5~+5% | 72 | +2.60% | 65.3% | -0.02pp |
| +5~+15% | 50 | +3.02% | 74.0% | +0.39pp |
| ≥+15% | 33 | +3.59% | 78.8% | +0.96pp |

**單調遞增、量越縮未來越差，看起來是個漂亮的訊號。但拆開樣本就現形：**

| 段 | 期間 | 天數 | 未來10日均漲 |
|---|---|---|---|
| 1 | 2025-12-04~09 | 4 | -0.57% |
| 2 | 2026-03-27 | 1 | **+9.61%** |
| 3 | **2026-07-08~28** | 8 | **-2.69%** |
| 4 | 2026-08-25~26 | 2 | **+3.62%** |

**那 15 天只是 4 段連續期間，2 勝 2 負**；-3.09pp 幾乎全由第 3 段撐起來——**那正好就是 7/14 那波已知空頭**。一個事件被「連續日期 + 重疊前瞻視窗」膨脹成 15 個樣本。

**結論：不做成擋進場的規則。** 三個理由疊加：(a) 最接近的版本（ER）測過並否決；(b) 本次資料拆開後不構成證據；(c) 系統**已經有**「市場不好就少進場」的機制（大盤評分階梯 65→70→75→停止），再加量能是在同一件事上疊第二層篩子。

**⚠️ 方法論（本則主要價值）：看到分組統計呈現漂亮的單調關係時，第一件事是問「這些樣本彼此獨立嗎」。** 時間序列的分組幾乎必然違反獨立假設——同一個市場狀態會連續出現好幾天，而前瞻視窗又彼此重疊。**正確做法是把命中的日期印出來看它們聚成幾段**，段數才是有效樣本數。本例 n=15 實際上 n≈4。這與「單日進場集中度」是同一個病根（多筆觀察在時間上高度相關），只是那則出現在交易層、這則出現在統計層。

**實際做的兩件事（都在 `render_market()`，型態掃描框附近）：**

1. **量能水位 caption**（型態框正上方）：顯示 `近5日均量 X 億（對比20日均量 Y 億，±Z%／標籤）`，五段標籤為 量縮(≤-15%)／量能偏低(≤-5%)／量能持平／量能回升(≥+5%)／量能放大(≥+15%)。**caption 內必須保留「不計入評分、不影響進場門檻、關聯未經驗證、請勿當作進出場理由」這串字**——定位與 🎯🔥 型態完全相同，少了這句日後必被當訊號用。用 `try/except` 包住，資料不足或欄位異常就整段不顯示。
2. **`_ms < 45` 時補上暫停提示**：原本型態框寫成 `if _ms >= 45:` 且**沒有 else**，理由是「偏空時不需要顯示型態現況」——那個推論只對了一半。型態確實不必顯示，但**「規則現在要你暫停」這件事反而最該講，因為那正是最容易勉強出手的時候**。新增橘框明講「大盤評分 N 分（＜45）——規則：暫停進場」，並補一句「這不是找不到標的，是策略本來就要你這時候不出手」＋「手上部位照既有規則管理，不需要額外動作」。

**通則（本專案第四次套用同一條）：** 「系統是不是該加個警戒」這類提案，**先查那個東西是不是已經做好了、只是被某個條件擋住沒顯示**。本例使用者想要的「別勉強出手」提示，其實 2026-08 就隨型態掃描框的空清單設計做好了（原始註解寫著「空清單本身就是答案，可以直接阻止想買點什麼的衝動」），只是被 `_ms >= 45` 這個條件擋在門外——而偏空正是最需要它的時候。**零成本的顯示層修補要優先於動規則。**

### _check_volume_breakout(prices) — 量縮後放量突破掃描（2026-07 新增）

定義在模組頂層（`_check_consolidation_pattern` 正下方）。與 🎯 互斥，🔥 優先顯示。

**四個條件同時成立才回傳 True：**
1. 今日收盤 > MA20（月線之上）
2. 今日成交量 > 20 日均量 × 1.5（量明顯放大）
3. 前 3 日成交量均低於 20 日均量（之前有量縮，確保從 🎯 狀態轉換而來）
4. 今日收盤 ≥ 昨日收盤（價格不破底）

**顯示邏輯：**
```python
if _check_volume_breakout(_latest_prices):
    _pattern_flag = '🔥 '
elif _check_consolidation_pattern(_latest_prices):
    _pattern_flag = '🎯 '
else:
    _pattern_flag = ''
```

兩者互斥的原因：🎯 要求近 3 日（含今日）量縮，🔥 要求今日量放大，不可能同時成立。

**篩選入口：** 自選股清單篩選列「🔥 放量」選項，點選後只顯示今日量縮後放量的股票。

**解讀：** 🎯 = 整理蓄勢中，🔥 = 量能啟動（可能是整理結束的訊號，需搭配其他條件判斷）。

### _check_short_squeeze(prices, chips_list) — 個股軋空偵測（2026-07 新增）

定義在模組頂層（`_check_volume_breakout` 正下方）。同時用於側邊欄標旗與籌碼頁警示框。

**回傳值：**
- `'squeezing'`：軋空進行中（高空單 + 大漲 + 融券實際回補）
- `'at_risk'`：軋空風險（高空單 + 股價啟動，或超高券資比）
- `None`：正常

**三階段判斷條件：**

| 回傳 | 券資比 | 5日漲幅 | 融券5日趨勢 |
|------|--------|---------|------------|
| `squeezing` | ≥20% | ≥5% | ≤-5%（回補中） |
| `at_risk` | ≥20% | ≥3% | 任意 |
| `at_risk` | ≥30% | 任意 | 任意 |
| `None` | ＜15% | — | — |

**資料需求：** `prices` 需 ≥6 筆，`chips_list` 需 ≥2 筆；`margin_balance` 或 `short_balance` 為 0 時直接回傳 `None`。

**側邊欄標旗優先順序：**
```python
if _sq_result == 'squeezing':
    _pattern_flag = '🌀 '   # 最高優先
elif _check_volume_breakout(_latest_prices):
    _pattern_flag = '🔥 '
elif _sq_result == 'at_risk':
    _pattern_flag = '⚡ '
elif _check_consolidation_pattern(_latest_prices):
    _pattern_flag = '🎯 '
else:
    _pattern_flag = ''
```

側邊欄 chips 資料來源：`get_chips(code, days=10)`（IS_LOCAL）；雲端不做標旗（`_sq_chips = []`）。

**篩選入口：** 自選股清單篩選列「🌀 軋空」選項（僅本機有效）。

**籌碼頁警示框：** 觸發時在融資融券圖下方顯示帶色框（🌀 綠色 / ⚡ 橘色），含三個數字：
- 券資比（%）
- 5日漲幅（%）
- 融券5日趨勢（%，負值 = 回補中）

**`render_chips()` 函式簽名更新：** 新增 `prices=None` 參數，呼叫時傳入：
```python
render_chips(result, code, name, chips_list, market=_mkt_tab,
             ownership_override=_own, prices=prices)
```

### 圖表統一函式（必須用這個，不能直接 st.plotly_chart）

```python
_CHART_CONFIG = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}

def show_chart(fig, key=None):
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CONFIG, key=key)
```

### K 線圖均線規格

```python
# MA5=橘色, MA20=紫色, MA60=綠色，固定不變
ma_colors = {'MA5': '#f97316', 'MA20': '#a855f7', 'MA60': '#22c55e'}
# 同時顯示大盤圖和個股圖，顯示最近 20 天
# 圖例 orientation='h' 水平排列
```

### 均線位置指標卡（render_market 頂部指標列，2026-07 改版）

原本固定顯示「MA20 站上/跌破月線」，跌破季線時資訊失真（顯示「跌破月線」但實際更嚴重），回升時也看不出已收復哪些均線。

**改為對稱設計**：列出所有可用均線（5日/月/季/半年/年線），依股價分成「已站上」與「未站上」兩組：

| 狀態 | 顯示 |
|------|------|
| 全數站上 | 「站上所有均線 ✅」+ 各線數值 |
| 部分站上 | 「{站上的最長週期線}之上」+ 最近反壓線與價位 + caption 顯示最近支撐與距離點數 |
| 全數跌破 | 「跌破 {實際涵蓋的線名}」+ 最近反壓線與距離 |

**注意：** delta 文字不可寫死「跌破所有均線」——實際涵蓋哪幾條線取決於 DB 資料量（年線需 240+ 交易日），必須動態組出線名清單，否則資料不足時會誤導。

**半年線/年線（2026-07 新增）：** `indicators.py` 新增 `ma120` / `ma240`，資料不足回傳 `None`（指標卡會自動略過該線）。TAIEX 原本只抓 6 個月（約 100 筆）不足以算年線，`fetch_taiex()` 新增 `force` 參數（回填時不跳過既有日期）與 2y/5y period 支援，搭配一次性腳本 `backfill_taiex_history.py` 回填 2 年歷史。回填的舊資料 `value` 欄是 yfinance 原始值（非億元），但均線只用 `close`，且成交量圖有 `<50000` 過濾防護（陷阱 27），不受影響。

### render_market_tracker() — 市場追蹤頁（2026-06 新增，2026-07 擴充）

路由值：`'market_tracker'`，側邊欄按鈕「🌐 市場追蹤」觸發。雲端本機均可使用。

**分頁結構（5 tabs）：**

| 分頁 | 函式 | 股票 | 指標 |
|------|------|------|------|
| 💾 DDR4（南亞科） | DDR4 現貨走勢（TrendForce 手動輸入） | — | DRAM 現貨價 |
| 🤖 機器人（上銀 2049） | `_render_hiwin_monitor()` | 2049 | 法人連買週數、毛利率 |
| 🦊 AI Server（鴻海 2317） | `_render_foxconn_monitor()` | 2317 | AI Server 占比、毛利率 |
| ⚡ AI 電源（台達電 2308） | `_render_delta_monitor()` | 2308 | AI/Server 占比、毛利率、籌碼 |
| 🎯 AI 精密（鴻勁 7769） | `_render_hongjing_monitor()` | 7769 | AI/HPC占比、毛利率、EPS、產能利用率、法說展望 |

**`_render_hongjing_monitor()` 重點（2026-07 新增）：**
- 毛利率門檻：50/55/58%（鴻勁實際水位 49–59%，與台達電 32/35/38% 不同）
- EPS 資料來源：`quarterly_financials.net_income`（季度 EPS），非手動輸入
- `net_income` 欄位在 yfinance 台股中直接存儲 EPS（非實際淨利金額）
- 手動輸入欄：AI/HPC 占比、市場預期 EPS（consensus）、產能利用率、法說展望（上修/維持/下修 → 1.0/0.0/-1.0）
- 段落資料存入 `stock_segment_revenue`：segment key = `'ai_hpc'`、`'quarterly_eps'`、`'capacity_util'`、`'guidance_update'`

**quarterly_financials 的 net_income 欄注意事項：**
yfinance 台股季報的 `Net Income` 欄有時回傳每股 EPS（小數），有時回傳實際淨利（數十億）。目前已知：
- 7769（鴻勁）：net_income = EPS（~15–25 元）✓
- 2317（鴻海）：net_income = EPS（~3–4 元）✓  
- 2049（上銀）：net_income = EPS（~1–2 元）✓
- 2308（台達電）：2023Q2 後 net_income 遭 NaN 污染歸零，需重新補抓

**⚠️ 金融保險業與 DR 永遠沒有這張表的資料（2026-10-20 確認，陷阱54）：**
`fetch_quarterly_financials()` 兩條路（FinMind／yfinance）都有 `if rev and gp` 守衛，
而**金融業的損益表沒有「毛利」科目**（收入是利息淨收益／保費收入，不走
「營收 − 銷貨成本」）⇒ 2881 富邦金／2882 國泰金／2891 中信金實測全部 0 筆。
DR（如 9103 美德醫療-DR）沒有獨立財報，同理。
**這是結構性的，不是漏抓**，所以腳本與 UI 都標成「⚪ 結構性」而不列入待處理。

### render_strategy() — 投資策略頁（2026-06 新增）

路由值：`'strategy'`，側邊欄按鈕「💡 投資策略」觸發。

**功能：**
- 從 `st.session_state` 讀取 `_market_ms`、`_market_net`（需先進過大盤分析頁）
- 依大盤評分決定個股建議門檻（≥70→65分、55–69→70分、45–54→75分、<45→停止進場）
- 重用 `_wl_scores` 快取（自選股評分），列出符合門檻的個股
- 退場警示：持有中個股若評分 <45 顯示紅色警告、45–54 顯示橘色注意
- 靜態策略說明：進場條件、持有管理（10日 + 到期續抱）、資金配置

**股票列表版面（2026-07 改）：** 進場符合、退場警示、觀察中三個區塊均改為 `st.columns` + `st.button`，點選股票直接跳轉個股分析頁。button key 分別為 `strat_q_{code}`、`strat_d_{code}`、`strat_ob_{code}`（避免同一頁面 key 衝突）。

**參考停損價欄位（2026-07 新增，空頭回測後補強）：** 進場符合清單改為 4 欄 `[3,1,1.6,1.4]`（股票/評分/參考停損價/標籤）。停損價 = 最新收盤 ×0.90（2026-08-27 由0.92校準），紅色顯示，旁附現價。內部函式 `_latest_close_for(code)`：IS_LOCAL 走 `get_prices(code, days=1)`，雲端走 `_read_stock_json()`。caption 明確指示「買進當日立即在券商 App 預掛停損單」——因為工具是盤後資料 + 隔日才能動作，評分類退場警訊天生延遲 2–3 天，唯有價格觸發的預掛停損單能即時出場。

**大盤轉空全面減碼警報（2026-07 新增，策略 D 邏輯）：** 大盤評分卡下方，依 `_market_net` 顯示兩級警報：
- `net >= 4`：紅色警報「全面減碼或出場」，引用空頭回測資料（D 平均 -1.84% vs C -4.52%）
- `net >= 2`：橘色警報「開始減碼」，提醒確認停損單已掛
設計依據：系統性下跌時個股齊跌，個股評分警訊必然落後；大盤層級訊號比個股評分早 1–2 天，且策略 D 的空頭回測驗證了「大盤轉空即出場」的優勢。此警報不改變評分/回測邏輯，純顯示層。

**雲端可行：** 是。資料來源均為 session_state 快取，無需 IS_LOCAL 分支（停損價欄位除外，該欄位兩種模式均支援）。

**注意：** `_wl_scores` 在大盤分析或自選股頁計算後會存入 session_state；若直接進投資策略頁，此快取可能不存在，需提示使用者先進自選股頁。

---

### render_score() 簽名（2026-06 擴充）

```python
def render_score(result, code, name, prices=None, fund_data=None, chips_all=None, ownership=None):
```

新增參數用於計算評分歷史走勢圖（總分正下方）。

**評分歷史走勢圖（雙線圖）：**
- 個股評分：回溯 90 日，每 3 日一點（~30 點），結果快取於 `st.session_state[f'_score_hist_{code}']`
- 大盤評分：從 `st.session_state['_market_score_history']` 取對應日期（需先訪問大盤分析頁）
- 兩條線同圖：個股（綠線）+ 大盤（藍虛線）
- 參考線：橘色 65（個股進場門檻）、綠色 70（大盤偏多）、紅色 45（大盤偏空）
- 可選顯示分項走勢（技術面紫、基本面藍、籌碼面橘）
- Caption：「近90日走勢，每3日計算一次；最後一點為今日即時評分。綠點 ≥65分，紅點 ＜65分。」

**波動度標示（2026-08 新增，純資訊顯示）：**

等級框（grade-box）正下方新增一行 caption：

```python
_vol20 = ind.get('vol20')
if _vol20 is not None:
    _vlabel, _ = _vol20_label(_vol20)
    st.caption(f'📊 近20日波動度：{_vol20:.1f}（{_vlabel}）（20日日報酬標準差，越大代表平常漲跌幅越劇烈；'
               f'純資訊參考，不計入評分，高分不代表短期漲幅一定大，低分也不代表不會大幅波動。'
               f'低/中/高分級依 {VOL20_LOW_CUT}／{VOL20_HIGH_CUT} 門檻，取自404筆歷史交易驗證，日後重新驗證會更新）')
```

**緣起：** 使用者觀察到國泰金（2882）評分持續偏高，但進場後 10 天股價幾乎不動，質疑「評分系統沒有討論到波動性」。**先驗證再動手**：用 `backtest_stocks.py` 策略 C 的 404 筆實際交易，逐筆用進場前 20 日收盤價算波動度（`statistics.pstdev`），與交易損益、進場評分做相關性分析。

**驗證結果（404 筆交易）：**
- corr(波動度, 損益) = 0.053、corr(評分, 波動度) = 0.036 —— 兩者幾乎無關，評分高低本來就不代表波動大小，這是預期之內、非系統缺陷
- 波動度三分位（低/中/高）平均報酬相近（+4.52% / +5.41% / +4.93%），但勝率差異明顯（50.4% / 53.3% / 44.0%），高波動組呈現「大賺大賠」分佈更分散
- **結論：** 波動度影響的是離散度/風險，不影響期望報酬，不構成「評分系統有缺陷」；但使用者確實需要這個資訊來判斷「這檔股票平常是穩健盤還是劇烈震盪」，尤其在決定願不願意持有到 10 天到期。因此只做**資訊顯示**，不改評分邏輯、不做篩選或排序，避免用一個與損益無關的指標去干擾已驗證有效的評分系統。

**中途發現的資料問題（未修復，僅繞開）：** 驗證過程中發現 DB 的 `change_pct` 欄位在約 4.7%（7,095/150,332）的價格列上被誤存為 `0.0`，即使當日 `close` 實際上與前一日不同。範圍橫跨 1,496 檔股票、2025-03 至 2026-08 全時間段（非單次批次匯入造成），根本原因未查。因此波動度計算刻意不依賴 `change_pct`，改由 `close` 價格逐日反推報酬率（見下方 `indicators.py` 說明），此問題已記錄於「已知陷阱」第 35 則，尚待日後追查 `fetcher.py` 寫入路徑。

**`_vol20_for(code)` — 投資策略頁「進場符合」清單同步顯示：**

```python
def _vol20_for(code):
    if IS_LOCAL:
        _vp = get_prices(code, days=30)
    else:
        _vp, _, _, _ = _read_stock_json(code)
        _vp = _vp[-30:] if _vp else _vp
    if not _vp:
        return None
    return calc_all(_vp).get('vol20')
```

清單欄位由 4 欄 `[3,1,1.6,1.4]` 改為 6 欄 `[2.2,0.8,0.9,1.4,1.0,0.7]`（股票/評分/波動度/參考停損價/標籤/登錄），波動度欄用中性灰色顯示（刻意不用紅綠色階，因驗證顯示波動度沒有「好/壞」之分，避免使用者誤讀為風險警示或加分項）。清單下方附 caption：「波動度＝近20日日報酬標準差，數字越大代表平常漲跌幅越劇烈。純資訊參考，不影響評分或進場門檻。」

**低/中/高文字標籤（2026-08 補強）：** 使用者反映純數字（如 2.2、7.5）沒有量尺感，不容易一眼判斷高低。新增 `_vol20_label(vol20)` 共用函式（定義在 `_check_short_squeeze()` 正下方，`VOL20_LOW_CUT`/`VOL20_HIGH_CUT` 兩個模組層級常數旁邊），回傳「低波動／中波動／高波動」文字：

```python
VOL20_LOW_CUT  = 2.4
VOL20_HIGH_CUT = 3.9

def _vol20_label(vol20):
    if vol20 is None:
        return None, None
    if vol20 < VOL20_LOW_CUT:
        return '低波動', '#64748b'
    elif vol20 < VOL20_HIGH_CUT:
        return '中波動', '#64748b'
    else:
        return '高波動', '#64748b'
```

門檻 **2.4／3.9** 直接取自本節「驗證結果」用的那 404 筆策略 C 交易，逐筆算進場前 20 日波動度後切三等分的實際分界點，不是憑感覺定的數字。三個等級刻意用同一個中性灰色（`#64748b`），不因為「高波動」就標紅——維持「波動度沒有好壞，只是特性」的一貫立場，避免使用者把文字標籤誤讀成風險警示。個股頁 caption 與投資策略頁清單 caption 都附註「門檻依404筆歷史交易驗證，日後重新驗證會更新」，提醒這兩個數字不是永久常數。**日後若重新驗證波動度與績效的關係**（例如樣本數累積更多、或策略邏輯改變後），要記得同步更新 `VOL20_LOW_CUT`／`VOL20_HIGH_CUT` 這兩個常數，而不是留著舊門檻。

**評分走勢圖今日即時補點（2026-07 新增）：**
歷史快取（`_hist`）最後一點是前幾天；每次渲染時動態計算今日 `full_score()` 並補入 `_hist_display`（不存快取），確保圖表最右端永遠是今日即時評分。

```python
_hist_display = list(_hist)
_today_price_date = prices[-1]['date'] if prices else None
if _today_price_date and (not _hist_display or _today_price_date > _hist_display[-1]['date']):
    _r_today = full_score(prices, fund_data, _chips_for_today, ownership)
    if _r_today:
        _hist_display.append({'date': _today_price_date, 'total': ..., ...})
```

**趨勢標籤（趨強/趨弱/持穩）與近7日動能（2026-07 新增）：**

評分等級框（grade-box）先用 `st.empty()` 佔位，`_hist_display` 建立後再更新，加入趨勢標籤（掛在等級文字旁的小標籤）：

| 今日 vs 前一計算點 | 標籤 | 顏色 |
|---|---|---|
| +3 分以上 | 趨強 | 綠色 #22c55e |
| -3 分以下 | 趨弱 | 紅色 #ef4444 |
| 其他 | 持穩 | 灰色 #94a3b8 |

**設計原則：** 刻意不用方向箭頭（↑/↓），避免「偏空 + ↑」被誤讀為多方訊號。趨強/趨弱/持穩明確表達「評分的方向性」，不會與市場漲跌混淆。

圖表下方附一行「近7日評分變化：+X分 ｜ 評分小幅趨強/評分持續趨弱…」文字列（加入「評分」二字作為主語，避免歧義）。

**大盤評分卡趨勢標籤（2026-07 新增）：**

`render_market()` 的大盤評分卡（`_market_score_placeholder`）同樣顯示趨強/趨弱/持穩標籤，顯示在等級名稱右側。資料來源：session_state 中前一次載入的 `_market_score_history`（取倒數第二點）與今日評分作比較。首次進入頁面（無歷史快取）不顯示標籤。

**買入訊號衰退警告（2026-07 新增）：**

走勢圖下方、分項評分上方，偵測評分從買入區間開始下滑的模式：

```
觸發條件（同時成立）：
  1. 最近 5 個計算點（約 15 日）中的峰值（不含今日）≥ 65
  2. 今日評分比那個峰值低了 ≥ 5 分
警告等級：
  🟡 今日仍 ≥65（仍在買入區間但動能轉弱）→ 橘色方塊
  🔴 今日已 ＜65（已跌破買入門檻）→ 紅色方塊
```

顯示格式：帶色邊框的 div（橘 #f59e0b / 紅 #ef4444），說明近期高點、當前分數、下滑幅度與操作建議。

低點回升預警**刻意不實作**：低分區雜訊多、觸發條件難定義，且側邊欄 🎯/🔥 型態已承擔部分早期偵測功能，暫以評分走勢圖人工觀察為主。
（2026-07 後續補充：個股轉折觀察清單的「底部觀察」版本已部分承接此功能，見下節。）

**個股轉折觀察清單（2026-07 新增）：**

位置：評分歷史走勢圖 / 買入訊號衰退警告之後、分項評分之前。與大盤版轉折清單同一設計語言（✅/❌ + 數值 + 白話說明 + X/6 標題），但閾值針對個股波動特性放寬。中間地帶（總分 50–64）不顯示，避免資訊過載。

`total < 50` 顯示「🧭 底部轉折觀察清單」：

| 項目 | 條件 |
|------|------|
| 量縮整理 | 近3日量均 < 20日均量 |
| 低點不再創新低 | min(近5日低) > min(前20日低) |
| 法人停止連續賣超 | 外資+投信連賣 ≤1 天 |
| 融資餘額明顯下降 | 近20日 ≤-5% |
| 站回月線之上 | close ≥ MA20 |
| 評分止跌回升 | `_hist_display` 末3點遞增 |

`total >= 65` 顯示「🧭 過熱衰竭觀察清單」：

| 項目 | 條件 |
|------|------|
| 短線乖離過大 | BIAS5 ≥ +8%（個股閾值比大盤 +5% 寬） |
| 漲時量縮 | 5日價漲 + 近3日量縮 |
| 法人由買轉賣 | 最新日外資+投信合計 < 0 |
| 融資急增 | 近5日 ≥+10% |
| RSI 超買 | RSI ≥ 80 |
| 評分從峰值下滑 | 與買入訊號衰退警告同邏輯（峰值≥65 且回落≥5分） |

**與側邊欄旗標的關係：** 🎯🔥🌀⚡ 旗標與篩選功能**照舊保留**（掃描視角，跨股票發現訊號）；清單是深入視角（單一股票的完整狀態儀表板），量縮等核心偵測邏輯與旗標對齊，避免兩邊判斷矛盾。

**附註設計：** 底部清單註明「個股受消息面影響大，條件再完整也可能單日反轉」；過熱清單註明「過熱不等於馬上跌，用途是調高警覺而非立即賣出訊號」。

**call site（main() 中）：**
```python
chips_all = get_chips(code, days=200)   # 本機
chips_all = _c_json                      # 雲端（完整 JSON chips）
chips_list = chips_all[-65:] if len(chips_all) > 65 else chips_all

with tabs[4]:
    render_score(result, code, name,
                 prices=prices, fund_data=fund_data,
                 chips_all=chips_all, ownership=ownership)
```

---

### 大盤評分歷史走勢圖（render_market() 內，2026-06 新增）

**位置：** 大盤評分卡（`_market_score_placeholder`）正下方，用 `st.container()` 佔位符。

**計算：** Signal 1–8 對每個歷史日期回溯評分（不含 Signal 9 yfinance 即時資料）。  
180 日視窗，快取於 `st.session_state['_market_score_history']`，格式：`[{'date', 'ms', 'net', 'close'}, ...]`。

**同時存入 session_state：**
```python
st.session_state['_market_ms']   = _ms    # 今日大盤評分
st.session_state['_market_net']  = _net   # 今日 net（bear-bull）
st.session_state['_market_bear'] = _bear_score
st.session_state['_market_bull'] = _bull_score
```

**圖表結構：** 雙子圖（上=大盤評分折線 + 70/45 參考線，下=加權指數收盤價）。

---

### 開盤前預判訊號（Signal 1–11）

Signal 1–8 使用昨日資料（本機 DB / 雲端 JSON），Signal 9 使用即時 yfinance，Signal 10 使用 `_mm`（market_margin），Signal 11 使用 P/C 比率。

**資料變數（`render_market()` 開頭載入）：**
- `_mm`：大盤融資融券（`market_margin.json` 或 DB）
- `_fut`：台指期三大法人（`futures_institutional.json` 或 DB）
- `_tpx`：TAIEX 價格（`TAIEX.json` 或 DB）
- `_t86`：三大法人現貨彙總，**本機和雲端均從 `chips_market_agg` 來源轉換**，key 為 `foreign_net_total / trust_net_total / total_net_total`

**評分變數：** `_bear_score`（空方分）、`_bull_score`（多方分），`net = bear - bull`

**訊號邏輯位置：** `render_market()` 中，搜尋 `Signal 1` 到 `Signal 11`

### 大盤評分（2026-06 新增）

顯示在 `render_market()` 頁面頂部，使用 `st.empty()` 佔位符，在 `_net` 計算完成後填入。

```python
_ms = max(0, min(100, 50 - _net * 5))   # 乘數 ×5，net=-10→100，net=+10→0
```

| 分數 | 等級 | 個股建議門檻 |
|------|------|------------|
| ≥85 | 強烈偏多 | ≥65 分可積極進場 |
| 70–84 | 偏多 | ≥65 分可積極進場 |
| 55–69 | 中性偏多 | 建議提高至 70 分 |
| 45–54 | 中性 | 建議提高至 75 分 |
| 35–44 | 中性偏空 | 建議提高至 75 分 |
| <35 | 偏空/強烈偏空 | 建議暫停進場 |

> **⚠️ 這張門檻表的「刻度」缺乏資料支持（2026-09-10 首次驗證，詳見十五章末）。**
>
> **❌ 原本這裡寫「評分的方向驗過（有方向 51.4%、強訊號 59.5%）」——那句話 2026-09-23 被推翻。**
> 那兩個數字**從來沒有跟無條件基準並列過**。同一批資料裡，隔日上漲的無條件機率是 **55.9%**，
> 也就是「每天都猜漲」就有 55.9%。實測全期 524 天：全部訊號 **52.7%（-3.2pp）**、
> 強訊號 **47.8%（-8.2pp，更差）**。**方向這一項同樣沒有被驗證有效。** 詳見十五章末。
>
> 至於**乘數 ×5、級距切點、四段門檻本身**則從未校準。2026-09-10 實測後：
> - 階梯整體優於回測在驗的策略C（alpha +2.33% vs +1.69%），**但**
> - 「完全不看大盤、一律 70 分」就有 alpha +2.07%——**階梯只多 0.26pp，卻少 26% 的進場機會**
> - `≥70`（唯一說「可積極進場」的那檔）516 天只出現 **15 天**，實質上不存在
>
> **結論是「維持現狀、不動規則」**（樣本全多頭、差距在雜訊範圍），但**不要把這張表當成已驗證的東西去延伸**。

**乘數調整原則：** 若太容易到達 100/0，調小乘數；目前 ×5 在 net=±10 時才觸及上下限。

**閾值判斷：**
```python
if   net >= 6:  verdict = '🔴 強烈偏空'
elif net >= 3:  verdict = '🔴 偏空'
elif net >= 1:  verdict = '🔴 小幅偏空'
elif net <= -6: verdict = '🟢 強烈偏多'
elif net <= -3: verdict = '🟢 偏多'
elif net <= -1: verdict = '🟢 小幅偏多'
else:           verdict = '⚪ 中性'
```

**操作建議原理說明（2026-07 新增）：** 偏空/強烈偏空的操作建議附「逢反彈減碼」原理（方向由趨勢決定、時點由價格決定；空頭反彈=出貨機會，特徵：量縮、過不了前高；與停損單互補）。偏多/強烈偏多附對稱的「逢回檔佈局」原理（多頭不追高；健康回檔特徵：量縮、不破前低、不破月線）。

**轉折觀察清單（2026-07 新增）：**

位置：綜合判斷框 + 評估基準日 caption 之後。設計原則：**不做時間預測**（空頭走多久取決於下跌原因，盤後資料無法預估），改用條件判斷回答「趨勢接近尾聲了嗎」。每項顯示 ✅/❌ + 當前數值 + 白話說明，標題顯示 X/6 項出現。

`net >= 1` 顯示「🧭 空頭轉折觀察清單」（出現越多越接近底部）：

| 項目 | 條件 | 資料來源 |
|------|------|---------|
| 融資餘額止穩 | 近2日變化均 > -0.5% | `_mm` margin_balance |
| 量縮下跌（賣壓衰竭） | `_pv_diverge == 'accumulation'` | Signal 8 |
| 外資停止連續賣超 | 連賣天數 ≤1 | `_t86_raw` |
| 恐慌情緒達極端 | P/C 百分位 ≥90% | Signal 11 `_pc_rank` |
| 大盤評分連續回升 | `_ms_hist_display` 末3點遞增 | 評分歷史 |
| 站回月線之上 | close ≥ MA20 | `_ind_tpx` |

`net <= -1` 顯示「🧭 多頭衰竭觀察清單」（出現越多越接近高點）：

| 項目 | 條件 |
|------|------|
| 融資餘額急增 | 近5日增幅 ≥+3% |
| 漲時量縮（分配跡象） | `_pv_diverge == 'distribution'` |
| 外資由買轉賣 | 最新一日 foreign_net < 0 |
| 市場過度樂觀 | P/C 百分位 ≤25% |
| 大盤評分連續下滑 | 末3點遞減 |
| 短線乖離過大 | BIAS5 ≥ +5% |

**實作注意：** Signal 11 的 try 區塊前必須有 `_pc_rank = None` 初始化（資料缺漏時清單才不會 NameError）。中性（net=0）不顯示清單。

**Signal 10：斷頭 / 多殺多風險評估**

資料來源：`_mm`（`get_market_margin(days=15)`），需 `len(_mm) >= 3`。  
僅在大跌情境下觸發，平常不影響評分。

| 條件 | 門檻 | 加分 |
|------|------|------|
| 多殺多啟動 | 跌 ≥3% 且融資賣出比例 ≥5% | Bear +3 |
| 多殺多跡象 | 跌 ≥3% 且融資賣出比例 ≥3.5% | Bear +2 |
| 斷頭風險 | 跌 ≥2% 且融資賣出比例 ≥3.5% | Bear +2 |
| 斷頭警示 | 跌 ≥2% 且融資賣出比例 ≥2.5% | Bear +1 |
| 斷頭加速（連續 2 日） | 融資餘額連跌 ≥1.5%/日 | Bear +2 |
| 斷頭加速（單日） | 融資餘額單日萎縮 ≥1.5% | Bear +1 |
| 融券回補反彈 | 跌 ≥2% 且融券回補比例 ≥3% | Bull +1 |

**融資賣出比例**（正常值參考）：正常日 1.5–2.5%，異常 ≥3.5%，多殺多 ≥5%  
**融資餘額萎縮**：單日 ≥1.5% 代表非主動賣出，而是被動斷頭

A/B 條件（多殺多/斷頭風險）互斥取最嚴重；C（斷頭加速）與 D（融券回補）獨立疊加。

**多殺多 / 斷頭獨立警告框（2026-07 新增）：**

Signal 10 計算時同步記錄 `_s10_alert_level`（0=無、1=輕度、2=警告、3=嚴重）與 `_s10_alert_info`（詳細資訊 dict）。在大盤評分卡下方顯示獨立警告框：

| 等級 | 觸發條件 | 顯示 | 顏色 |
|---|---|---|---|
| 3 / 2 | 多殺多啟動/跡象、斷頭風險、斷頭加速（連2日） | 🚨 紅色警告框 | #ef4444 |
| 1 | 斷頭警示、斷頭加速（單日） | ⚠️ 橘色提示框 | #f59e0b |
| 0 | 未觸發 | 不顯示 | — |

框內顯示：標題、昨日跌幅、融資賣出比例、融資餘額萎縮幅度（依實際觸發條件顯示），以及操作建議。與信號清單獨立，讓使用者一眼看到而不需要翻閱全部訊號。

**市場壓力監控區塊（2026-07 新增，方案B統一顯示框）**

Signal 11 後、訊號清單前**計算**四項市場應力指標並顯示統一警告框。只要有任一指標觸發（level ≥ 1）就顯示；沒有觸發不佔版面。

**顯示位置（2026-07 調整）：** 多殺多框與壓力監控框均透過 `_market_alert_placeholder`（st.container 佔位符）填入**頁面頂部**，視覺順序：大盤評分卡 → 緊急警告（多殺多框 + 壓力監控框）→ 轉折觀察清單 → 評分歷史走勢圖 → 外部市場。設計理由：這兩個框代表「正在發生的緊急狀況」，應在第一眼位置，與下方「開盤前預判」（明天的推論）區隔。

**四項指標（`_stress_alerts` 清單）：**

| 指標 | 資料來源 | 輕度（level 1）| 嚴重（level 2）|
|------|----------|--------------|--------------|
| 台幣走弱/急貶 | Signal 9 `global_data['USD/TWD']` | 日貶 ≥0.5% Bear+1 | 日貶 ≥1.0% Bear+2 |
| 三大法人同步賣超 | `_t86_raw[-1]`（foreign/trust/dealer 全負） | 合計賣超 ＞3萬張 Bear+1 | 合計 ＞15萬且外資 ＞8萬 Bear+2 |
| 外資連續賣超天數 | `_t86_raw`（reversed 遍歷計連續） | 5–9 天 Bear+1 | ≥10 天 Bear+2 |
| 量價背離 | Signal 8 `_pv_diverge` 變數 | 'distribution'（漲時量縮）Bear+1（已在S8計分） | — |
| （正面）量縮下跌 | Signal 8 `_pv_diverge='accumulation'` | Bull+1（S8已計分），level 0 顯示綠色 | — |

**資料載入異動：** `_t86_raw` 由 `days=5` 改為 `days=15`（JSON 也由 `[-5:]` 改 `[-15:]`），以提供足夠天數計算連續賣超。Signal 4 不受影響（只用 `_t86[-1]`）。

**變數初始化位置：** 在 `_bear_score = 0` 同處新增：
```python
_stress_alerts = []   # 市場壓力監控（統一顯示框用）
_pv_diverge    = None  # 量價背離：'distribution' | 'accumulation' | None
_vol_trend     = 0   # Signal 8 成交量趨勢 %
```

**顯示規則：**
- 無任何 level ≥ 1 且無 level 0：不顯示框
- 有 level 0 但無 level ≥ 1：只顯示正面訊息（綠框）
- 最高 level = 1：橘色框（#1a1505 / #f59e0b）
- 最高 level ≥ 2：紅色框（#2d0a0a / #ef4444）
- 框標題顯示異常數量；level 0 項目附在下方顯示為綠色

**Signal 9 台幣計分補充：**  
USD/TWD 原本只顯示不計分（台幣貶值）。現在加入評分：升值 ＞0.5% Bull+1，貶值 ≥0.5% Bear+1，貶值 ≥1.0% Bear+2。

**Signal 8 量價背離邏輯修改：**  
原本量縮統一給 Bear+1。現改為：
- 漲時量縮 `_tpx_chg ≥ 0.5% AND _vol_trend ≤ -15%`：Bear+1（分配跡象），`_pv_diverge='distribution'`
- 跌時量縮 `_tpx_chg ≤ -0.5% AND _vol_trend ≤ -15%`：Bull+1（跌勢趨緩），`_pv_diverge='accumulation'`
- 量縮但無明顯方向：Bear+1（市場觀望，維持原邏輯）

**Signal 11：選擇權 P/C 比率（2026-06 新增）**

資料來源：`get_options_pc(days=60)`（本機）或 `options_pc.json`（雲端）。需 `len >= 5`。

| P/C 歷史百分位 | 意義 | 訊號 |
|------|------|------|
| >90% | 市場極度恐慌 → 反向底部 | Bull +1 |
| >75% | 避險需求偏高 | Bear +1 |
| <25% | 市場過度樂觀 | Bear +1 |
| <15% | 過熱（僅提示，不加分） | — |

P/C 值解讀：>1.3 偏空（紅色）、0.7–1.3 中性（藍色）、<0.7 偏多（綠色）。  
台股 P/C 常態偏高（1.3–1.7），結構性因素，需以**歷史百分位**判斷相對位置。

圖表：柱狀圖（顏色依值）+ 20日MA虛線 + 三個 metric（今日P/C / 20日均值 / 歷史百分位）。

### 三大法人現貨圖（大盤）

```python
# IS_LOCAL 控制資料來源（雲端直接讀 JSON，不經 DB，確保資料最新）
if IS_LOCAL:
    _chips_agg = get_chips_market_aggregate(days=20)
else:
    # 直接讀 JSON，跳過 init_cloud_data() 的 DB 匯入
    with open('data/json/chips_market_agg.json') as f:
        _chips_agg = json.load(f).get('rows', [])[-20:]

# 固定顏色
INST_COLORS = {'外資': '#f97316', '投信': '#3b82f6', '自營商': '#a855f7'}
# 兩個子圖：上=各自柱狀圖，下=合計柱狀圖 + 7日MA線
```

**注意：** Signal 4 的 `_t86` 變數與此圖使用**相同資料來源**，確保頁面上下數字一致。`_t86` 是將 `_chips_agg` 格式轉換為 `{foreign_net_total, trust_net_total, total_net_total}`。

### 雲端初始化（模組頂層）

```python
@st.cache_resource          # 必須在模組頂層定義，不能在 if 區塊內
def _init_cloud_cache(version: str):
    from github_sync import init_cloud_data
    init_cloud_data()
    return version

if not IS_LOCAL:
    _init_cloud_cache(_get_meta_version())   # key 是 meta.json 的 exported_at
```

**雲端的直接 JSON 讀取模式（2026-06 架構調整）：**  
大盤分析、開盤前預判、自選股評分等關鍵資料，雲端版**不依賴 `init_cloud_data()` 的 DB 匯入**，改為直接從 JSON 檔讀取。這樣確保 sync 後資料即時反映，不受 `@st.cache_resource` 快取影響。

| 資料 | 雲端讀取位置 |
|------|------------|
| 三大法人現貨 | `data/json/chips_market_agg.json` |
| Signal 4（法人現貨訊號） | 同上，轉換 key 格式 |
| 大盤融資融券 | `data/json/market_margin.json` |
| 台指期三大法人 | `data/json/futures_institutional.json` |
| TAIEX 價格 | `data/json/TAIEX.json` |
| 個股評分（prices/fundamentals/chips/ownership） | `data/json/{code}.json` via `_read_stock_json()` |
| Signal 11（P/C 比率） | `data/json/options_pc.json` |

### _read_stock_json(code) — 雲端專用

```python
def _read_stock_json(code) -> (prices, fundamentals, chips, ownership):
    # 直接從 data/json/{code}.json 讀取，回傳 4-tuple
    # ownership 是 {'foreign_pct': float, 'date': str} 或 None
    # 例外時回傳 ([], [], [], None)
```

**重要：** 個股 JSON 的 `ownership` 欄位是 2026-06 加入的。同步後才有此欄位；舊版 JSON 沒有，`_read_stock_json()` 會回傳 `None`，評分時自動 fallback 到 52%。

---

## 十、已知陷阱與 Bug 記錄

### 1. git push 失敗（index.lock 或 HEAD.lock）
```bash
rm -f ~/台股分析工具/.git/index.lock
rm -f ~/台股分析工具/.git/HEAD.lock
git -C ~/台股分析工具 push
```

### 2. 三大法人現貨圖顯示幾年前資料
`chips` 表有 2017 年起的歷史資料，若不加日期範圍過濾，`HAVING stock_count >= 500` 無效（舊日期只有少數股票）。  
**修正：** `get_chips_market_aggregate()` 需加 `WHERE date >= date('now', '-{days*2} days')`

### 3. 雲端 chips_market_agg 無資料
現象：雲端三大法人現貨圖空白。  
原因：`chips_market_agg` 是新資料表，需要確認：
1. `github_sync.py` 的 `export_to_json()` 有匯出 `chips_market_agg.json`
2. `init_cloud_data()` 有匯入此檔案
3. 個股迴圈的 skip 名單有加 `'chips_market_agg'`
4. 本機已 `git push` 最新 `.py` 檔，且 JSON 已推送

### 4. 雲端 ImportError
本機改了函式名稱但 push 的 `.py` 不完整（例如只 push 了 `app.py` 但 `database.py` 沒更新）。  
**修正：** 每次改函式時，確認所有涉及的 `.py` 都一起 push。

### 5. Streamlit 1.58+ 的 st.html 警告
舊版 `import streamlit.components.v1 as _components; _components.html(...)` 已棄用。  
**修正：** 改用 `st.html(..., unsafe_allow_javascript=True)`

### 6. 外資期貨口數誤判方向
外資台指期淨多單常態為 -5 ~ -7 萬口（結構性避險，非方向性訊號）。  
開盤前預判使用**日變化量**（`f_now - f_prev`），不用絕對口數。

### 7. TWSE API 速率限制
批次補抓歷史資料時每筆需 `time.sleep(0.4)`；大量補抓改用 2 秒。

### 8. TAIFEX Big5 亂碼
```python
r.content.decode('big5', errors='ignore')  # 不是 r.text
```

### 9. st.cache_resource 必須在模組頂層
若 `@st.cache_resource` 定義在 `if not IS_LOCAL:` 區塊內，雲端每次重整都會重新執行 `init_cloud_data()`（快取失效）。必須在頂層定義函式，只有呼叫放在 if 區塊內。

### 10. 雲端法人張數「上下不一致」
現象：大盤分析頁面，三大法人現貨圖的數字與開盤前預判 Signal 4 的外資現貨數字不同。  
原因：Signal 4 用 `get_t86_market_aggregate()`，雲端 `t86_ranking` 只有前15名股票，加總遠小於真實市場總計；圖表用 `chips_market_agg`（全市場）。  
**修正（2026-06）：** Signal 4 的 `_t86` 變數改成由 `chips_market_agg` 資料轉換，兩邊來源統一。

### 11. 雲端自選股評分與本機不同
現象：雲端評分明顯偏高或偏低，無法對齊本機結果。  
原因：個股 JSON 缺少 `ownership`（外資持股比例），雲端固定用預設 52%，而本機讀 DB 取真實值（各股差異顯著）。  
**修正（2026-06）：** `export_to_json()` 的個股 JSON 加入 `ownership` 欄位；`_read_stock_json()` 回傳 4-tuple 含 ownership；評分路徑雲端/本機均使用各自的 ownership 資料。

**操作提醒：** 修正後須重新按「🚀 更新並同步到雲端」，讓新版 JSON（含 ownership）推到 GitHub，雲端評分才會正確。

### 12. get_options_pc() 回傳空 list
現象：P/C 比率圖顯示「尚無資料」，但 SQLite 內有資料。
原因：`get_conn()` 無 `row_factory = sqlite3.Row`，`fetchall()` 回傳 tuple，`dict(r)` 對 tuple 無效。
**修正（2026-06）：** 改為 `cols = ['date', 'call_oi', 'put_oi', 'pc_ratio']; return [dict(zip(cols, r)) for r in reversed(rows)]`。`get_options_pc_last_date()` 同理，用 `row[0]` 不用 `row['date']`。
**通則：** database.py 所有 read 函式都必須手動 zip 欄名，不能依賴 row_factory。

### 13. 本機與雲端大盤評分差 ±5 分
現象：大盤評分本機和雲端不一致，但差距在 5 分以內。
原因：Signal 9（外部市場即時）使用 yfinance，快取 TTL=900 秒（15分鐘）。本機和雲端各自發請求，抓取時間點不同，美股指數/VIX/TSM ADR 即時值略有差異。
**結論：** ±5 分以內屬正常，無法消除。差距 ≥15 分才需檢查 JSON 資料是否同步。

### 14. TWSE STOCK_DAY_ALL 無日期版本回傳舊資料（2026-06 發現）
現象：手動更新顯示「全部更新成功」，但個股資料仍停在前一交易日。  
原因：`STOCK_DAY_ALL?response=json`（不帶日期）有時回傳一個月前的舊資料（TWSE 伺服器端 bug），程式只要收到 `stat=OK` 就算成功。  
**修正（2026-06）：**
1. 新增 `_parse_twse_csv_all()` 解析帶日期版本的 CSV 格式
2. `fetch_today_prices()` 改為**優先使用帶日期 CSV 端點**，無日期 JSON 版本降為備援
3. `fetch_today_prices()` 回傳實際抓到的資料日期（`twse_actual_date`）
4. `fetch_all()` 比對回傳日期與今天：不符則記錄 `PENDING` 狀態，不再誤報「全部更新成功」
5. 手動更新按鈕完成後重新讀取資料狀態，顯示 `⏳ TWSE 尚未發布今日資料` 而非 `✅`

**兩種端點差異：**

| 端點 | 格式 | 狀況 |
|---|---|---|
| `STOCK_DAY_ALL?response=json` | JSON，date 在頂層 | 偶爾回傳舊日期 |
| `STOCK_DAY_ALL?date=20260624` | CSV（`response=json` 無效），date 在每列第一欄，民國 7 碼 `1150624` | 可靠，永遠是指定日期 |

**CSV 欄位順序：** 日期, 證券代號, 證券名稱, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數

```python
# 日期解析（twse_date_to_std 已支援）
"1150624" → "2026-06-24"   # 7碼民國年，d[0]=='1'
```

### 15. APScheduler 排程在 Streamlit 重啟時失效（2026-06 發現）
現象：程式每天 16:30 應自動抓資料，但 update_log 只有手動更新紀錄，沒有自動執行的記錄。  
原因：APScheduler 跑在 Streamlit Python 程序內部，每次 Streamlit 重新載入（存檔、刷新）就會重置排程，若重啟時間點正好跨過 16:30 則整天都不會觸發。  
**建議：** 改用 macOS cron 獨立執行 `run_daily_fetch.sh`（已在專案根目錄），完全不依賴 Streamlit 存活。  
**目前做法：** 使用者每日手動按「🔄 手動更新資料」，TWSE 通常在 15:00~16:30 更新，建議 17:00 後再按。

### 16. GitHub Token 被自動撤銷（2026-07 發現）
現象：`git push` 報 `Invalid username or token`，即使 Token 設定為無限期。  
原因：GitHub Secret Scanning 偵測到 Token 出現在曾 commit 的檔案中（如 `config_local.py` 意外推送），會自動撤銷，無視有效期限設定。  
**修正（2026-07）：** 移除 remote URL 中的 Token，改用 macOS Keychain 儲存：
```bash
git remote set-url origin https://github.com/hioct022-ux/taiwan-stock-tool.git
git config --global credential.helper osxkeychain
git push origin main  # 首次輸入帳號 + Token，之後自動記住
```
**通則：** Token 不應放在 remote URL 或任何可能被 commit 的檔案。`config_local.py` 中的 `GITHUB_TOKEN` 欄位可留空，push 靠 Keychain 認證。

### 17. 雲端新增分頁後仍顯示舊版（2026-07 發現）
現象：本機 push 後 Streamlit Cloud Reboot，仍只看到舊的分頁數量。  
原因：git push 實際上失敗（Token 已撤銷），remote 停在舊 commit，Reboot 只是重啟同一份舊程式碼。  
**診斷：** `git ls-remote origin HEAD` 的 commit hash 必須和 `git log --oneline -1` 相同，不同代表 push 沒成功。  
**修正：** 先修復 Token（見陷阱 16），再重新 push，Streamlit Cloud 才會自動重新部署。

### 18. quarterly_financials EPS 欄位遭 NaN 污染歸零（2026-07 發現）
現象：台達電（2308）季度 EPS 圖只顯示到 2023Q1，之後全部為 0。  
原因：yfinance 對未來/未釋出季度回傳 NaN，`float('nan')` 在 Python 是 truthy → 通過 `if rev and gp` 檢查 → 寫入 SQLite 變 NULL（net_income=0.0）→ 覆蓋原本正確資料。  
**已修正（fetcher.py）：** 加入 `math.isnan()` 守衛 + `rev > 0 and gp > 0` 條件，NaN 不再寫入。  
**但既有 0 值不會自動修復**，需手動重新抓取：
```bash
python3 -c "from fetcher import fetch_quarterly_financials; print(fetch_quarterly_financials('2308', years=4))"
```

### 19. 季度 EPS 圖資料永遠停在 114年（2026-07 發現）
現象：自選股個股頁「季度 EPS 趨勢」圖，最新資料停在 2025 年底（114年Q4）。  
原因：圖表直接即時呼叫 yfinance `quarterly_income_stmt`，yfinance 台股季報更新比實際公告慢 1–2 個月，Q1 2026 結果要到 5–6 月才會進 yfinance。  
**修正（2026-07）：** 改為優先讀取 `quarterly_financials` DB（`net_income` 欄即季度 EPS），DB 無資料才 fallback 到 yfinance。懶加載：IS_LOCAL 下首次讀取無資料的股票自動補抓並存入 DB。  
**呼叫位置：** `render_fundamental()` 內，`#### 📊 季度 EPS 趨勢` 區塊。

### 20. EPS TTM 顯示 0（虧損股或新上市股）（2026-07 發現）
現象：部分自選股的「EPS（近四季TTM）」顯示 0 元。  
原因：EPS TTM 由 `close ÷ PE` 反推，虧損股或新上市股的 PE 欄位為 0 或 None，導致 eps=0。  
**修正（2026-07）：** 加入三層 fallback：
1. TWSE `close ÷ PE`（正常）
2. `quarterly_financials` 最近 4 季 `net_income` 加總（虧損股備援）
3. yfinance `trailingEps`（快取 24 小時，最後手段）

數字旁附來源小字標注（TWSE 不顯示，其他來源顯示 `(quarterly_financials)` 或 `(yfinance)`）。

### 21. T86 更新按鈕後仍顯示舊日期（2026-07 發現）
現象：按「🚀 更新並同步到雲端」後，T86 排行顯示日期仍是前一交易日。  
原因：TWSE T86 API 在特定時間點回傳空 body（HTTP 200 但無 JSON），`resp.json()` 拋出 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`，錯誤被靜默吞掉，T86 資料未更新。同時 `fetch_all()` 的 T86 區塊只 catch exception、不檢查回傳值，導致 `✅ 全部更新成功` 誤報。  
**修正（2026-07）：**
1. `fetch_t86()` 的請求改為最多 3 次重試（間隔 5 秒）
2. 全部重試失敗時 `return False`
3. `fetch_all()` 改為 `if fetch_t86() is False: errors.append(...)`，失敗會反映在 UI 上
4. 手動補救：`python3 -c "from fetcher import fetch_t86; fetch_t86()"`

### 22. Safari InvalidCharacterError：訊號訊息中的 < > 字元（2026-07 發現）
現象：大盤分析頁在 Safari 瀏覽器出現 `InvalidCharacterError: The string contains invalid characters`，Chrome 正常。  
原因：Signal 7（均線排列）訊息含 `MA5<MA20<MA60`，Signal 10（斷頭/多殺多）含 `<2.5%`、`>3.5%`，個股籌碼面券資比含 `< 2.5%`。這些字串被放入 `<div>` HTML 後，Safari 的 DOM parser 將 `<MA20` 誤判為 HTML 標籤，最終 `document.createTextNode()` 收到破損字串而拋錯。Chrome 有更寬鬆的 error recovery，故不受影響。  
**修正（2026-07）：** 將訊息字串中的 `<` / `>` 全部改為全形 `＜` / `＞`：
- Signal 7 bear：`MA5＜MA20＜MA60`
- Signal 7 bull：`MA5＞MA20＞MA60`
- Signal 10 多殺多：`（正常 ＜2.5%）`
- Signal 10 斷頭風險：`（＞3.5% 警戒）`
- Signal 10 融券回補：`（＞3% 偏高）`
- 個股籌碼 sig3_label：`（＜ 2.5%）`

**通則：** 凡是動態字串被放入 `st.markdown(..., unsafe_allow_html=True)` 的 HTML div，若含有 `<` 或 `>` 必須使用 `＜` `＞`（全形）或 `&lt;` `&gt;`（HTML 實體）代替。純比較符號用全形即可，不影響閱讀。

**觸發時機：** 此 Bug 只在特定訊號第一次觸發時才被察覺。Signal 7 平時在多頭市場不觸發（MA5>MA20>MA60），只有在均線轉空頭排列後才第一次執行到那行程式碼。Signal 10 同理（需大跌才觸發）。

---

### 23. 台指期夜盤雲端版不顯示（2026-07 確認）
現象：雲端版大盤分析頁台指期夜盤區塊消失。  
原因：`_fetch_taiex_futures()` 需要 `FINMIND_TOKEN`，該 Token 存於 `config_local.py`（不上傳 Git），雲端無法取得，函式直接 `return {}`。  
**目前做法（2026-07）：** 接受本機專屬，雲端版顯示說明文字：「🇹🇼 台指期夜盤資料需 FinMind Token，僅本機版可用」。  
**如欲解決：** 到 Streamlit Cloud → Settings → Secrets 加入 `FINMIND_TOKEN = "your_token"`，並在 `_fetch_taiex_futures()` 加 fallback：
```python
if not _fmt:
    try:
        _fmt = st.secrets.get('FINMIND_TOKEN', '')
    except Exception:
        _fmt = ''
```

---

### 24. 大盤評分歷史圖最後一點只到昨日（2026-07 修正）
現象：大盤評分走勢圖最右端停在昨日，今日即時評分未反映。  
原因：歷史圖從 TAIEX DB/JSON 回溯計算（S1–S8），DB 最新資料是昨日；即時評分（S1–S11）算完後存在 session_state 但沒有被加進圖裡。  
**修正（2026-07）：** 顯示圖表前動態補入今日即時評分：
```python
_ms_hist_display = list(_ms_hist)
if _ms_hist_display and _tpx_date > _ms_hist_display[-1]['date']:
    _ms_hist_display.append({'date': _tpx_date, 'ms': _ms, 'net': _net, 'close': _tpx_now})
elif _ms_hist_display and _tpx_date == _ms_hist_display[-1]['date']:
    # 同一天：用即時評分（含S9–S11）覆蓋回溯評分（僅S1–S8）
    _ms_hist_display[-1] = {'date': _tpx_date, 'ms': _ms, 'net': _net, 'close': _tpx_now}
```
Caption 改為：「近180日大盤評分走勢。歷史點僅含S1–S8；最後一點為今日即時評分（含S9–S11）。」

**⚠️ 這個修正只處理了「隔一天」的情況，隔兩天以上會漏點——見陷阱 40。**

---

### 40. 評分歷史快取 key 沒帶資料版本，隔兩個交易日會漏掉中間那天（2026-09-02 修正）

**現象：** 使用者反映「為什麼 9 月 1 日的大盤分數不見了？」大盤評分走勢圖上 9/1 那個點整個消失，但 DB 裡 9/1 的資料完好（S1–S8 實算 net=+1、評分 45）。

**根本原因（兩個設計缺陷疊加）：**

1. **快取 key 寫死、沒有資料版本**：`_ms_hist_key = '_market_score_history_v3'` 是固定字串，`if _ms_hist_key not in st.session_state` 代表**一個 session 只算一次**，之後即使按了「🔄 手動更新資料」也不會重算。
2. **動態補點只補一個**：陷阱 24 加的「補入今日即時評分」邏輯只 append `_tpx_date` 這**一天**。

兩者疊加後：快取建立時資料到 8/31 → 使用者更新到 9/1（App 未重開，快取仍是 8/31）→ 隔天再更新到 9/2 → 動態補點只補 9/2，**9/1 直接被跳過**：

```
圖表日期： 8/27 → 8/28 → 8/31 → 9/02      ← 9/1 消失
```

**修正：** key 改為帶資料最新日期，資料一更新 key 就變、快取自動失效並重算整段：

```python
_ms_hist_key = f'_market_score_history_v3_{_tpx_date}'
```

**連帶修正的三處（改 key 時很容易漏）：**

| 位置 | 問題 |
|---|---|
| `render_score()` 個股評分走勢圖 | `_score_hist_{code}` 同樣沒帶日期，同一 session 更新資料後個股走勢圖也停在舊資料 → 改為 `_score_hist_{code}_{prices[-1]["date"]}` |
| 大盤評分卡的趨勢標籤（趨強/趨弱/持穩） | 原本讀舊的固定 key，改版後會永遠讀不到而**silently 消失** |
| 個股頁疊加的大盤評分線 | 同上 |

後兩者的解法：掃描 `st.session_state` 中所有 `_market_score_history_v3_*` 開頭的 key，取日期最新的一份——因為它們跑在歷史計算之前，當日 key 可能還不存在，而它們只需要「前一個評分點」，用稍舊的那份仍然正確。

**⚠️ 修正後本機 App 需重啟一次**（`pkill -f streamlit` 再重跑），舊 session_state 裡的舊 key 才會清掉。

**通則（重要，本專案已多次踩到）：** 任何「一個 session 只算一次」的 `st.session_state` 快取，**key 必須帶資料版本**（本機用最新價格日期、雲端用 `_get_meta_version()`）。專案內已用對這個模式的有 `_pos_trend_{code}_{date}`、`_wl_patterns_{date}`；用錯的就是本則的兩個。判斷方法很簡單：**問「使用者在同一個 session 內按了更新資料之後，這份快取會不會自動失效？」如果不會，就是 bug。** 另外，「動態補最新一點」這種補救寫法只能處理「差一天」，不能取代正確的快取失效——**兩者要一起做對**。

---

### 25. 股價漲跌顏色使用西方慣例（綠漲紅跌）（2026-07 修正）
台灣習慣：**紅色=漲、綠色=跌**（與西方相反）。  
**修正範圍（2026-07）：** 以下所有股價/籌碼方向相關的顏色已改為台灣慣例：
- 側邊欄價格摘要（`_color`）
- K 線量柱（`colors`）
- 連續漲跌方向文字（`dir_color`）
- 個股頁最新價漲跌（`chg_color`）
- 外資/投信/自營商近5日 net（`color`）
- 週籌碼柱狀圖（`_w_colors`、`_ch_colors`）
- 季度 EPS 柱狀圖（`_ecolors`）
- DRAM 現貨漲跌幅（`_colors`）
- 台指期日夜盤（`_tcolor`、`_d_color`）
- 三大法人大盤彙總（`_cc()`、`_ca_total`）
- 個股三大法人彙總（`net_color()`）
- 個股近5日收盤（`color`）
- 外部市場卡片（`_market_card` else 分支，涵蓋 S&P/Nasdaq/SOX/TSM/原油/黃金/台幣）

**沒改的**（非股價方向，保持紅=警戒/綠=安全的通用邏輯）：
- RSI 超買/超賣色、PE 高低估色、大盤評分歷史色
- VIX、美元指數、美債10年（各有特殊邏輯）
- 多方/空方訊號燈（🔴/🟢 emoji 對應色）

### 26. DDR4 漲跌幅柱狀圖只顯示 1–2 根（2026-07 修正）
現象：市場追蹤頁 DDR4 分頁的漲跌幅柱狀圖只顯示極少根柱子。  
**根本原因一（只有 1 根）：** `spot_chg_pct` 欄位只在自動抓取當下即時計算存入，歷史資料以 `0.0` 儲存，顯示邏輯原本用 `is not None` 過濾，導致全部 `0.0` 的日期都被納入但值都是零（肉眼看似空白），只有 1 根有實際值的柱子可見。  
**根本原因二（修正後只有 2 根）：** 改為從價格序列動態計算後，`dram_prices` 表中同時存有**季度資料**（2025-03-31、2025-07-31、2025-11-30，每季一筆）和**每日資料**（2026-06 起每日）。連續計算時把季度跳空（如 3.26→10.4→25.52）當成日漲跌，產生 +218%、+145%、+180% 的巨大假漲幅，撐爆 Y 軸，使真正的每日小幅漲跌肉眼不可見，看起來只有 2 根巨柱。  
**修正（2026-07）：** 計算漲跌幅時加入日期間距過濾，只計算相鄰 ≤7 天的資料：
```python
if (_curr_d - _prev_d).days > 7:   # 跨週以上的缺口不計算
    continue
```
這樣季度資料之間的跳空被跳過，只有真正的每日連續資料才會產生漲跌幅柱子。

---

### 27. 大盤分析成交量圖單位錯誤 + 歷史資料單位混雜（2026-07 修正）

**現象一（單位錯誤）：** 大盤分析頁「加權指數」走勢圖，成交量子圖 Y 軸標示「成交金額（億元）」，但顯示的數字（~100–180）跟 Signal 8、K 線解讀、caption 顯示的成交金額（~8,000–13,000 億元）對不上。
**原因：** 圖表資料來源用了 `ind.get('volumes', [])`（來自 `prices['volume']` 欄位，成交股數/億股），而其他地方都用 `prices['value']`（成交金額/億元），兩者單位不同、來源不同。
**修正：** 圖表改為直接從 `prices` 用 `p['value']` 建立 `volumes`，與 Signal 8、K 線解讀對齊：
```python
_tpx_val_dict = {p['date']: p.get('value', 0) for p in prices}
volumes = [_tpx_val_dict.get(d, 0) for d in dates]
```

**現象二（改完後 Y 軸被撐到 8M）：** 上面的修正做完後，圖表 Y 軸出現到 `8M` 的天文數字，遠超合理的成交金額範圍。
**原因：** `fetch_market_volume()`（FMTQIK 補正函式）原本只呼叫**不帶 `date` 參數**的 FMTQIK API，該端點只回傳「當月」資料。因此只有最近一個月的 `prices.value` 是正確的億元值（如 `8663`），而 3–6 月等較舊資料仍停留在 **yfinance 原始值**（未經補正，數量級是 `4,000,000–8,000,000`，非億元）。同一個 `value` 欄位裡混雜了兩種單位，圖表把兩者連在一起畫，Y 軸被舊資料的量級撐爆，近期真正的資料反而看不出波動。

**修正（fetcher.py `fetch_market_volume()`）：** 重構為逐月呼叫 FMTQIK（`?date=YYYYMM01`），預設補全近 12 個月：
```python
def fetch_market_volume(months=12):
    ...
    for i in range(months - 1, -1, -1):
        target = now - timedelta(days=30 * i)
        date_str = target.strftime('%Y%m01')
        _fmtqik_fetch_month(date_str, conn)   # 該月份逐日補正 value/volume
        time.sleep(0.3)
```

**app.py 防禦性修正：** 圖表資料加上單位合理性過濾（成交金額不可能 ≥ 50,000 億元/日），避免未來又有未補正資料混入時再次撐爆 Y 軸：
```python
volumes = [v if 0 < v < 50000 else 0
           for v in [_tpx_val_dict.get(d, 0) for d in dates]]
_has_missing_vol = any(v == 0 for v in volumes[-60:])
```
若近 60 日仍有缺值，圖表下方顯示提示：「部分歷史成交金額尚未補正，請按手動更新資料」。

**操作提醒：** 修正後需在本機按一次「🔄 手動更新資料」，讓 `fetch_market_volume(months=12)` 跑過一輪，把 3–6 月的 `value` 欄位補正為正確億元值。之後每日更新只需補正當月，不會重跑全部 12 個月的舊資料（`UPDATE ... WHERE date=?`，已補正的資料再次執行是幂等的，只是稍微浪費 API 呼叫）。

**通則：** 任何「歷史資料 + 新資料」用不同來源/方法產生的欄位（本例：yfinance 原始值 vs FMTQIK 補正值），如果只在「新增當下」用新方法補正，舊資料會永久停留在舊格式，形成同一欄位混雜多種單位的陷阱。修正時必須考慮**回填歷史**，不能只改「未來新資料」的產生邏輯。

---

### 28. Signal 10 融資賣出比例爆出 5000%+ 離譜數字（2026-07 修正）

**現象：** 大盤分析頁跳出「斷頭風險」警告，但顯示「融資賣出比例 5418.1%」，明顯不合理（正常值 1.5–2.5%，異常也頂多 3–5%）。

**根本原因：** `market_margin` 表裡的欄位單位不一致：
- `margin_balance`：**億元**（`fetch_market_margin()` 內用「融資金額(仟元)」÷ 100000 換算而來）
- `margin_sell` / `margin_buy`：**張**（「融資(交易單位)」欄位，未經任何換算）

Signal 10 原始計算：
```python
_ms_ratio = _ms_now / _mb_s10 * 100   # margin_sell(張) / margin_balance(億元)
```
分子是「張」、分母是「億元」，兩者量級差了約 10 萬倍（1 億元對應的張數遠大於「1」），導致比例失真到 5000%+ 這種荒謬數字。融券那邊的 `_ss_ratio = short_buy(張) / short_balance(張)` 因為兩者都是「張」，單位一致，沒有這個問題——這也是為什麼只有融資賣出比例出包。

**追根究底：** `fetch_market_margin()` 內部其實已經算出「融資餘額（張）」這個值（變數 `margin_lots`），但只拿它當 `margin_balance` 抓不到「融資金額(仟元)」時的**備援**，從沒有單獨存進 DB。所以 Signal 10 想找一個「張」單位的融資餘額當分母時，DB 裡根本沒有這個欄位可用，才會誤用單位不同的 `margin_balance`。

**修正：**
1. `database.py`：`market_margin` 表新增 `margin_lots` 欄位（張，融資餘額），並在 `init_db()` migrations 加 `ALTER TABLE market_margin ADD COLUMN margin_lots INTEGER DEFAULT 0`；`save_market_margin()` / `get_market_margin()` 同步支援這個欄位。
2. `fetcher.py`：`_parse_market_margin_response()`（歷史補抓用）與 `fetch_market_margin()`（每日抓取用）都把原本就算出來的 `margin_lots` 一併存入 DB。
3. `app.py` Signal 10：
   ```python
   _mb_lots_s10 = _mm[-1].get('margin_lots', 0) or 0   # 融資餘額（張）
   _ms_ratio = _ms_now / _mb_lots_s10 * 100 if _mb_lots_s10 > 0 else 0
   ```
   分子分母都改成「張」，單位一致。

**歷史資料回填：** 既有 `market_margin` 資料的 `margin_lots` 一律是 0（欄位新增前沒有值），修正當下 Signal 10 會暫時失效（分母為 0 直接回傳 0%，不會誤報但也不會正確觸發）。提供 `backfill_margin_lots.py`（一次性腳本，執行後可刪除）重新呼叫 TWSE MI_MARGN 補近 20 個交易日的 `margin_lots`。之後每日「🔄 手動更新資料」會自動帶入新資料，不需要再手動補。

**通則：** 同一張表裡不同欄位如果分別代表「原始單位」與「換算後單位」（本例 `margin_buy/sell` 是張、`margin_balance` 是換算過的億元），寫比例公式前務必先確認兩個欄位的實際單位是否一致，不能只看欄位語意接近就直接相除。跨欄位運算前，最快的驗證方法是拿 DB 裡的真實數字手算一次，數量級對不上就是單位錯誤的訊號。

---

### 29. 台指期夜盤資料偶爾「消失」——FinMind ReadTimeout（2026-07 修正）

**現象：** 大盤分析頁的台指期日盤/夜盤區塊有時突然不顯示，但 token 沒過期、`config_local.py` 也沒被改動。

**原因：** `_fetch_taiex_futures()` 內層用 `except Exception: return {}` 把任何錯誤都吞掉直接回傳空字典，包含單純的連線逾時（`ReadTimeout`）。原本 `timeout=12` 秒偏緊，FinMind API 偶爾回應較慢，一旦單次請求超過 12 秒就直接判定失敗，畫面上完全看不出「是額度用完、token失效、還是單純網路慢」，只會看到整個區塊消失。

**診斷方式：** 寫了一次性腳本 `debug_taiex_futures.py`（可重複使用，不用每次都刪），會印出 HTTP 狀態碼、FinMind 回傳的 `status`/`msg`、資料筆數，直接執行：
```bash
python3 debug_taiex_futures.py
```
這次實際測試結果是 `ReadTimeout`（15秒都沒回應完），確認是網路/伺服器回應速度問題，不是 token 或程式邏輯錯誤。

**修正（app.py `_fetch_taiex_futures()`）：**
1. `timeout` 從 12 秒拉長到 20 秒
2. 加最多 3 次重試（間隔 3 秒），只針對連線層級例外（`requests.exceptions.RequestException`）：
```python
data = None
for _attempt in range(3):
    try:
        r = _req.get(..., timeout=20)
        data = r.json()
        break
    except _req.exceptions.RequestException:
        if _attempt < 2:
            _time.sleep(3)
            continue
        return {}
if data is None or data.get('status') != 200:
    return {}
```

**通則：** 外部 API 呼叫如果用 `except Exception: return {}` 這種寬鬆的錯誤處理，會讓「額度用完」「token失效」「單純網路慢」在畫面上呈現一模一樣的「資料不見了」，難以追查。建議搭配一個診斷腳本（印出原始 HTTP 狀態碼與錯誤訊息）放在專案裡備用，遇到類似「怎麼突然不見了」的回報時可以直接請使用者執行、貼結果回來，不用臆測。

---

### 30. 多殺多/斷頭警告框日期硬編碼「昨日」（2026-07 修正）

**現象：** 大盤分析頁的多殺多/斷頭警告框，文字寫死「昨日大盤跌幅 X%」。使用者反映：今天看是「昨日」，那明天再看該不會還顯示同一個「昨日」吧？——這正是問題所在：日期用字是寫死的字串，沒有跟著資料實際日期走。

**根本原因：** 陷阱 4（2026-06）已經把訊號清單裡的文字訊息（`_bear_msgs`）從「昨日」改成套用 `_tpx_date`（資料實際日期）。但「多殺多/斷頭獨立警告框」是**在陷阱 4 之後才新增的功能**（2026-07），這個警告框的文字是另外寫的一段程式碼，沒有沿用同樣的修正，殘留了舊的硬編碼寫法，導致同一頁面出現「訊號清單用對日期、警告框用死日期」的不一致。

**修正（app.py）：**
1. `_s10_alert_info` 這個 dict 在 4 處直接指派 + 2 處 `setdefault` 都補上 `'date': _tpx_date`
2. 警告框顯示文字改為：
```python
_al_date_label = _s10_alert_info.get('date', '')
_al_lines.append(f'{_al_date_label} 大盤跌幅 <b>{_s10_alert_info["chg"]:.2f}%</b>')
```
取代原本寫死的 `f'昨日大盤跌幅 ...'`。

**效果：** 修正後不管哪一天開啟工具查看，警告框都會顯示事件實際發生的日期（例如「2026-07-28 大盤跌幅 2.67%」），不會因為查看的時間點不同而產生語意錯亂。

**通則：** 修正「相對日期用字」（昨日/今日/近日）這類問題時，要注意程式裡可能有**多處**用類似邏輯產生訊息文字（例如本例的「訊號清單文字」與「警告框文字」是分別維護的兩段程式碼），只改其中一處容易漏掉另一處。搜尋關鍵字（如「昨日」）確認全檔案沒有殘留，是比較保險的做法。

---

### 31. 轉折觀察清單在中性（net=0）時整個消失（2026-07 修正）

**現象：** 大盤分析頁的轉折觀察清單某天突然不見了，程式碼沒動過。

**原因：** 顯示條件寫成 `if _net >= 1 or _net <= -1:`，`net` 恰為 0（多空訊號互相抵銷）時兩個分支都不成立，清單完全不渲染。而多空抵銷正是最需要觀察轉折條件的時候，這個設計反而在關鍵時刻失效。

**修正：** 改為先決定 `_chk_mode` 再一律渲染：
```python
if   _net >= 1: _chk_mode = 'bear'
elif _net <= -1: _chk_mode = 'bull'
else:  # 中性：依股價相對月線決定顯示哪一份
    _chk_mode = 'bear' if (_ind_ma20_mode and _tpx_now < _ind_ma20_mode) else 'bull'
```
中性時在副標註明「目前多空訊號互相抵銷，依股價在月線之下/上顯示此清單」，避免使用者困惑。

**通則：** 用 `if X >= 1 or X <= -1` 這種寫法排除「中間值」時，要先確認中間值是否真的不需要處理。特別是評分/淨值類的變數，0 往往不是「無意義」而是「勢均力敵」，反而更需要顯示資訊。

---

### 32. calc_all() 傳入的資料視窗太短，長週期指標永遠算不出來（2026-07 修正）

**現象：** 大盤預判的 S7（均線排列）判斷結果與看盤軟體不符；`pos_250`（近250日位置）顯示 6.2%，但實際上大盤還在相對高檔。

**根本原因：** `render_market()` 的開盤前預判區塊只取 30 日資料：
```python
_tpx = get_prices('TAIEX', days=30)   # ← 只有 30 筆
_ind_tpx = calc_all(_tpx)
```
而 `calc_all()` 內部所有指標都是 `if n >= 週期 else None`，於是：
- `ma60` 永遠是 `None`（需 60 筆）→ `ma_trend` 退化成只用 MA5/MA20 兩線判斷
- `pos_250` 的 `tail(250)` 在只有 30 筆時就變成「近 30 日位置」，**名稱與實際計算不符**

**實測差異（2026-07-30 同一天資料）：**

| 指標 | 30 日視窗 | 250 日視窗（正確） |
|---|---|---|
| MA60 | None | 44,056 |
| ma_trend | bearish（兩線誤判） | sideways |
| pos_250 | **6.2%** | **67.2%** |

`pos_250` 的失真最嚴重：6.2% 會被判定為「接近歷史低檔」給 2 分偏多（超跌反彈），但真實位置 67.2% 屬相對高檔，根本不該給這個分數。等於大盤評分被系統性地往偏多拉。

**修正：**
1. `_tpx` 取 250 日（本機 `get_prices` 與雲端 JSON `[-250:]` 同步改）
2. 評分歷史回溯視窗 `_htpx` 同步改 250 日；資料改取 430 日（顯示末 180 日 + 前面 250 日供視窗用），迴圈起點 `_hi_start = max(1, len(_h_tpx) - 180)`
3. `backtest.py` / `backtest_stocks.py` 的 `tpx_win` 同步改 250，確保回測與線上邏輯一致
4. session_state key 升版為 `_market_score_history_v3` 強制重算舊快取（30 日視窗算出的歷史點與新的即時點基礎不同，混用會產生斷層）

**回測驗證（2024-07~2026-07，452 交易日）：**

| 視窗 | 有方向準確率 | 強訊號準確率 |
|---|---|---|
| 30 日 | 52.6% | 60.0% |
| 90 日 | 51.6% | 58.1% |
| 250 日 | 51.4% | 59.5% |

差異均在雜訊範圍（380 樣本誤差約 ±5pp），**準確率無顯著變化**。此修正的目的是恢復指標語意正確，不是提升準確率——記錄下來避免未來有人看到回測數字略降而想改回去。

**通則：** 任何呼叫 `calc_all()`（或類似的指標計算函式）的地方，都要確認傳入的資料筆數 ≥ 最長週期指標的需求。特別注意 `pos_250`、`ma240` 這類名稱帶週期數字的欄位——資料不足時它們不會報錯，而是**靜默地用較短區間計算**，產生看似合理但完全失真的數值。新增長週期指標時，務必回頭檢查所有 call site 的視窗長度。

---

## 十一、新增功能的標準流程

### A. 新增一個大盤指標（從 API 抓資料到顯示）

1. **`database.py`**：
   - `init_db()` 加 `CREATE TABLE IF NOT EXISTS new_table (...)`
   - 加 `save_new(date, data)` 和 `get_new(days)` 函式

2. **`fetcher.py`**：
   - 加 `fetch_new()` 函式
   - 在 `fetch_all()` 末端加呼叫

3. **`github_sync.py`**：
   - `export_to_json()` 加 JSON 匯出
   - `init_cloud_data()` 加 JSON 匯入
   - **個股迴圈 skip 名單加入新的 JSON 檔名**（重要！）

4. **`app.py`**：
   - import 新函式
   - `render_market()` 加顯示邏輯

### B. 修改開盤前預判訊號閾值

`app.py` → `render_market()` → 搜尋 `Signal 1` 到 `Signal 10`，直接改數字。

### C. 新增外部市場指標

`app.py` → `_fetch_global_markets()` → 在 `equity_symbols` 或 `macro_symbols` dict 加入新 ticker。  
評分邏輯在 Signal 9 區塊（`# ══ Signal 9`）。

### D. 新增個股籌碼判斷欄位

`app.py` → `render_chips()` → 圖表下方的判斷文字區塊。

### E. 新增頁面

```python
# 側邊欄加按鈕
if st.sidebar.button('新頁面', use_container_width=True):
    st.session_state['page'] = 'new_page'

# render 函式
def render_new_page():
    ...

# main() 路由
elif page == 'new_page':
    render_new_page()
```

---

## 十二、部署與維護操作

### 日常推送（只改資料，不改程式碼）
在 App 按「🚀 更新並同步到雲端」即可（本機執行）。

### 推送程式碼更新到雲端

```bash
cd ~/台股分析工具
git add app.py database.py github_sync.py fetcher.py config.py
git commit -m "說明修改內容"
git push
# Streamlit Cloud 會在 1~2 分鐘內自動重新部署
```

### 補抓歷史資料

```bash
cd ~/台股分析工具

# 大盤融資融券（月數）
python3 -c "from fetcher import fetch_market_margin_history; fetch_market_margin_history(months=4)"

# 台指期未平倉（逐月分批，TAIFEX 限 30 天/次）
python3 -c "from fetcher import fetch_futures_institutional_history; fetch_futures_institutional_history(months=3)"

# 單股歷史價格
python3 -c "from fetcher import fetch_history; fetch_history('2330', months=6)"

# 今日全部抓一次
python3 -c "from fetcher import fetch_all; fetch_all()"

# 初始化 DB（新增資料表後必須執行）
python3 -c "from database import init_db; init_db()"

# 執行回測
python3 backtest.py
```

### 校準大盤市值係數

1. 查 [TWSE 市場資訊](https://www.twse.com.tw/zh/statistics/statisticsReport/marketInformation.html) 最新上市總市值
2. `TWSE_CAP_COEF = 最新市值(億) / 當日指數收盤`
3. 更新 `config.py` 的 `TWSE_CAP_COEF` 和 `TWSE_CAP_CALIBRATED`

### 查詢 DB 內容

```bash
# 直接 SQLite
sqlite3 ~/台股分析工具/data/stock.db ".tables"
sqlite3 ~/台股分析工具/data/stock.db "SELECT * FROM chips_market_agg ORDER BY date DESC LIMIT 10;"

# Python
python3 -c "from database import get_market_pe; [print(r) for r in get_market_pe(5)]"
```

---

## 十三、config_local.py 範本

```python
# config_local.py — 此檔不上傳 Git（已在 .gitignore）
IS_LOCAL         = True
GITHUB_TOKEN     = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'  # GitHub Personal Access Token
FINMIND_TOKEN    = 'your_finmind_token'  # FinMind API，用於 ETF 成分股
POSITIONS_ENC_KEY = 'random_long_string'  # 2026-08新增，持倉資料加密金鑰，
                                           # 需與 Streamlit Cloud Secrets 的同名值完全一致
```

---

## 十四、開盤前預判回測說明（backtest.py）

回測使用 Signal 1–8（S9 即時資料無法回測），逐日模擬評分。

**已知偏差：** 在單邊多頭市場，偏空訊號（BIAS 過高、位置偏高）系統性失準（約 42%），這是趨勢性市場的必然現象，訊號設計本身沒有問題。資料累積 6 個月以上、跨越不同市場環境後，統計意義才會提高。

**使用方式：** `python3 backtest.py`，輸出整體準確率、強訊號準確率（|net|≥3）、逐日明細。

> **🚨 這支腳本印出來的準確率，本身沒有基準可比——直接讀會得到錯誤結論（2026-09-23 補做）。**
> 「有方向 51.4%、強訊號 59.5%」看起來像五成到六成命中，但**同期隔日上漲的無條件機率是 55.9%**。
> 也就是說「什麼都不看、每天猜漲」就有 55.9%。**引用本章任何準確率時，必須把基準一起寫出來。**
> 完整結果見十五章末「大盤評分加上無條件基準之後是輸的」。

### 空頭段驗證（2026-07-28 執行，市場 7/14 起轉空）

2026-07 中旬台股自 45,600 高點反轉（7/17 -6.47%、7/24 -2.67%、7/28 -4.65%），首次有真實空頭資料可驗證：

| 指標 | 全期間（3/3–7/28） | 空頭段（7/14–7/28） |
|---|---|---|
| 有方向預判準確率 | 53.7% | 62%（5/8） |
| 預判偏空準確率 | 50.0% | **75%**（3/4） |
| 預判偏多準確率 | 57.9% | 50%（2/4） |

**驗證結論：** 偏空訊號在空頭環境如預期變準（多頭時的失準是環境因素，非設計缺陷）。

**結構性限制（重要）：** 兩根最大跌棒（7/24 -2.67%、7/28 -4.65%）前一晚的預判都是「偏多」，全數漏接。原因：兩天前面都有大反彈（7/21 +4.2%、7/22 +1.3%），動能類訊號（S1、均線）被反彈帶成偏多。**急殺型下跌本質上無法靠前日盤後資料預警**（與斷頭機制同理：維持率是跌到位才觸發，不會提前反映）。Signal 10（斷頭偵測）的作用正是在事後第一時間補上這個缺口。

---

## 十五、個股量化回測（backtest_stocks.py）（2026-06 新增）

**用途：** 回測自選股的買賣訊號策略，驗證評分系統的實際績效。

### 核心函式

```python
_run_backtest(stocks, hold_days=10, score_threshold=65, stop_loss=0.08,
              renew=False, market_exit=False, trailing_pct=None) -> dict
```

- `renew=True`：策略 C，到期時評分 ≥ threshold 則重置持有期（續抱）
- `market_exit=True`：策略 D，持有期間大盤 net ≥ 2 提前出場
- `trailing_pct`：移動停利比例（None=不啟用）

### 四種策略與回測結果（2026-06 定版）

| 策略 | 筆數 | 勝率 | 期望值 | 說明 |
|------|------|------|--------|------|
| A（無大盤過濾） | 176 | 58.0% | +7.27% | 基準 |
| B（大盤過濾） | 157 | 63.7% | +8.11% | 大盤偏空不進場 |
| **C（B + 到期續抱）** | **127** | **60.6%** | **+10.20%** | **採用** |
| D（B + 大盤轉空提前出場） | 184 | 51.1% | +5.51% | 不採用 |

**策略 C 續抱統計：** 再持子集 83.3% 勝率，均報酬 +27.2%

> **⚠️ 這張表是 176 筆時代 + 8% 停損跑的，兩個結論都已不成立（2026-09-10 重驗）：**
> 1. **A→B 的「大盤過濾有效」在 541 筆上翻轉**——現在無過濾 alpha +2.09%、有過濾 +1.69%，過濾是負貢獻。
> 2. **這裡的「策略 B/C」跑的是「`net>0` 不進場 + 一律 65 分」，不是 UI 教使用者的四段門檻階梯。** 兩者是不同的規則、筆數差一倍。
>
> 引用任何「回測依據」數字前，先讀本章末的「大盤評分門檻階梯的第一次驗證」，確認自己引的是哪一套規則。

> **🚨 更根本的問題（2026-09-24 發現）：本章所有在「自選股」上量出來的 alpha 都含後見之明。**
> 87 檔自選股**全部**是 2026-05 之後才加入的，而回測期從 2024-07 開始——
> 等於拿今天的清單回頭考兩年前的試。同一套規則改用全市場 510 檔重測，
> alpha 從 **+2.44% 變成 -0.32%**。詳見本章末「全市場擴充」那節。
> **本章的數字仍可用來比較「規則之間的相對優劣」，但不可當成「這套策略能賺錢」的證據。**

### 掃描功能

```bash
python3 backtest_stocks.py        # A/B/C/D 四策略比較
python3 backtest_stocks.py scan   # 持有天數掃描（3/5/7/10/15/20 日）
python3 backtest_stocks.py trail  # 移動停利掃描（None/3%/5%/8%）
```

**持有天數掃描結論：** 10 日有最佳勝率；20 日 EV 最高但多頭偏差大。採用 10 日。  
**移動停利掃描結論：** 多頭市場中移動停利均劣於無停利。不採用。（2026-08 補跑含空頭段資料重新驗證，結論不變，見下方「移動停損空頭段驗證」小節）

### 空頭段驗證（2026-07-28 執行，僅統計 7/14 後進場的交易）

| 策略 | 進場筆數 | 平均損益 | 停損筆數 | 備註 |
|------|---------|---------|---------|------|
| A（無過濾） | 25 | -4.91% | 9 | |
| B（大盤過濾） | 16 | -4.38% | 3 | 擋掉 18 筆（被擋交易平均虧 -4.21%），過濾有效 |
| C（現行採用） | 13 | -4.52% | 2 | |
| **D（大盤轉空提前出場）** | **25** | **-1.84%** | 5 | 20 筆靠大盤訊號提前出場（net≥+4）|

**核心發現：** 策略 D 在多頭回測墊底（51.1% 勝率，被 C 淘汰），但在空頭段大幅勝出——「大盤轉空提前出場」在多頭是錯殺、在空頭是保命。這是環境依賴的典型案例。

**待決策（樣本不足暫緩）：** 混合策略構想——多頭用 C（續抱吃波段）、大盤評分轉弱時切換 D 的提前出場邏輯。目前空頭樣本僅 2 週 / 25 筆，不足以定案。**待空頭資料累積 1–2 個月後重跑本節回測，若 D 優勢持續再實作。**

### 策略 E：大盤轉空提前出場的確認天數（2026-08-15 驗證，實驗性質）

延續上面「待決策」的混合策略構想，把 D 的「大盤轉空提前出場」規則加進 C（到期續抱＋停損），並加入「連續 N 天 net≥2 才觸發出場」的確認機制（`confirm_days`），避免大盤淨值單日雜訊就把部位巴出場。腳本：`backtest_strategy_e_confirm_days.py`（實驗性質，未接入正式邏輯，未進版控）。

| confirm_days | 全歷史EV | 全歷史勝率 | 空頭段均報酬 | 空頭段停損率 | 空頭段防禦觸發次數 |
|---|---|---|---|---|---|
| 1（=無確認） | +1.98% | 37.9% | -0.11% | 7% | 40 |
| 2 | +3.35% | 49.1% | -3.07% | 48% | 13 |
| 3 | +3.63% | 46.4% | -4.19% | 53% | 7 |
| 4 | +5.12% | 48.4% | -4.20% | 53% | 7 |
| 5 | +5.12%（=純C） | 48.9% | -7.43%（=純C） | 89%（=純C） | 0（防禦失效） |

對照組：純 C 全歷史 EV +4.83%（445筆），空頭段均報酬 -7.43%、停損率89%；純 D 全歷史 EV +1.84%（734筆），空頭段均報酬 -0.11%、停損率7%。

**結論：** `confirm_days=2` 是全歷史表現與空頭防禦力之間唯一站得住腳的平衡點——從 1 跳到 2 全歷史數字有實質改善（不是雜訊），且防禦仍確實在運作（停損率48%、13次觸發）；再往上到 4、5，全歷史數字繼續墊高，但防禦觸發次數持續下滑到 7 次、最終 0 次，是「防禦形同虛設」換來的假象好看數字，**選參數不能只看全歷史EV，一定要同時看空頭段觸發次數**。**限制：** 只驗證過一次空頭型態（7/14起，反覆巴動型），換一種空頭型態（例如緩跌盤跌型）結論可能不同，建議累積下一次空頭資料後重跑比對，一致才真正採用。目前**不接入正式邏輯**。

### 策略 E 第二次驗證（2026-08-20 重跑，資料補進 8/17~8/20 那週）

**要回答的問題：** (a) `confirm_days=2` 的結論是否仍成立、(b) 新資料是讓策略E更站得住腳還是動搖原結論。**觸發原因：** 檢視使用者四檔實際持倉（微星、南亞科、緯創、國泰金）發現，四筆中三筆的出場原因都記「大盤轉空減碼」——**實際操作跑的是策略D的邏輯，但系統的策略驗證儀表板是拿策略C的基準（60.6%勝率、+10.20%）在比對**，等於拿蘋果比橘子，累積下去會誤判「策略失效」。

| confirm_days | 全歷史EV | 全歷史勝率 | 筆數 | 空頭段均報酬 | 空頭段停損率 | 空頭段防禦觸發次數 |
|---|---|---|---|---|---|---|
| 1（=無確認） | +1.89% | 38.7% | 688 | -1.35% | 22% | 40 |
| **2** | **+3.22%** | **50.3%** | 521 | **-4.26%** | 61% | **13** |
| 3 | +3.50% | 47.5% | 478 | -5.52% | 70% | 7 |
| 4 | +5.02% | 49.7% | 453 | -5.52% | 70% | 7 |
| 5 | +4.89% | 49.1% | 438 | -6.51%（≒純C） | 78% | 0（防禦失效） |

對照組：純 C 全歷史 EV +4.67%（429筆），空頭段均報酬 -6.51%、停損率78%；純 D 全歷史 EV +1.75%（715筆），空頭段均報酬 -1.35%、停損率22%。

**結論一（參數）：** 曲線形狀與 8/15 那次幾乎完全一致，`confirm_days=2` 仍是唯一平衡點；cd=4 依舊是「EV最漂亮但防禦只觸發7次」的陷阱參數，**重複驗證了不能只看EV的教訓**。維持原決定，**不接入正式邏輯**。

**結論二（更重要）：這一週根本不是「大盤轉空」，所以不算新的空頭樣本。** 系統大盤淨值 8/17~8/20 是 0/0/+1/0，從未觸及 +2 警戒門檻（最後一次連續≥2 是 8/4~8/7）。把窗口改成「進場日 >= 2026-08-11」重跑，**純C／純D／E(cd=1~5) 七種策略結果完全相同**：防禦觸發 0 次、停損率 100%、均報酬 -8.00%。沒有任何大盤層級規則救得了那一週——傷害是**個股層級**而非市場層級的。因此上一節「待第二次空頭型態驗證」那個條件**仍然沒有被滿足**，下次真的出現市場級空頭時還是要再跑一次。

**附帶觀察：** 使用者 8/19 那三筆「大盤轉空減碼」出場，當天系統淨值只有 +1，兩個警報門檻（+2／+4）都沒觸發——那是使用者自己的判斷，不是系統訊號。這也提醒：`exit_reason` 選「大盤轉空減碼」時未必真有系統訊號，做策略驗證分組統計時要留意這個欄位是人工填的。

> **❌ 本節原本寫「事後看方向正確（微星少賠3.8pp、國泰金少賠0.7pp、緯創少賺1.2pp，整體划算）」——那個結論在 2026-09-12 被推翻，見十八章末「評估出場決策的窗口長度」。**
> 那句話是 8/20 寫的，**只看了一個交易日**。拉到 15 個交易日（＝策略的持有期尺度），三筆全部變成賣飛（緯創 +6.2%、微星 +7.6%、國泰金 +12.3%）。**同一個決定，窗口長度不同，結論完全相反。**

### 單日進場集中度：現行策略完全沒有防禦的風險（2026-08-20 發現，尚未設計對策）

**發現經過：** 跑策略E第二次驗證時，順手看了「單日同時進場筆數」的分佈，發現 **2026-08-14 單日同時進場 15 檔**，是全歷史最高（單日進場**中位數僅 3 檔**、平均 3.2 檔）。這 15 檔的結果：**12 檔虧損、6 檔在 3 個交易日內停損，整批平均 -4.28%**。

**成因：** 進場條件是「大盤淨值 ≤0 解除封鎖 + 個股評分達標」，兩者都滿足時**所有達標個股會在同一天一起進場**。8/13 大盤淨值 -1 剛好解除封鎖，累積了數日的達標個股同時湧入。等於在同一個時間點把子彈全部打出去，之後市場一震盪就是整批一起受傷。

**現行機制為何擋不住：** 資金配置的三條規則（單檔上限20%、同時持股5檔、大盤偏空縮減）管的是**部位大小**與**總持股檔數**，管不到**進場時間的集中度**。而且「同時持股5檔」這條目前也只是警示、不阻擋登錄。

**尚未處理（刻意不急著改）：** 加一條「單日最多開 N 倉」需要另外設計並回測（N 該取多少、超額的個股是延後進場還是直接放棄、延後會不會反而錯過最佳點），且會牽動現有已驗證的進場邏輯。先記錄，不動正式規則。

**通則：** 回測統計平常只看勝率／EV／停損率這些「每筆交易」層級的指標，會完全看不見「多筆交易在時間上高度相關」這種組合層級的風險。**每次做策略驗證時，順手看一下進場日期的分佈（單日筆數的中位數 vs 最大值），成本很低但能抓到這類單看平均值抓不到的結構性問題。**

### 大盤日K盤中結構（「先殺後拉」）對隔日的預測力（2026-09-01 驗證，結論：不採用）

**背景：** 2026-09-01 台股 +1.78%，但**開盤只跳空 +0.11%**，漲幅幾乎全在盤中走出來（+1.67%，收當日最高）；前一日 8/31 也是先跌到 -1.9% 再拉回。使用者觀察連兩天「先殺後拉」，推測代表低檔有承接力道。值得測的理由：現行 Signal 1–11 **全部只用收盤價**，完全沒用到 open/high/low 的盤中結構，這是既有資料裡尚未被使用的面向。腳本：`backtest_intraday_reversal.py`。

| 型態 | 樣本 | 隔日勝率（vs基準） | 隔日均漲（vs基準） |
|---|---|---|---|
| **基準（無條件）** | 508 | **55.9%** | **+0.161%** |
| A 先殺後拉（收高檔+破前收） | 60 | 50.0%（**-5.9pp**） | -0.079%（-0.241pp） |
| B 強力反轉（A+反彈≥1.5%） | 16 | 56.2%（+0.3pp） | +0.075%（樣本不足） |
| C 長下影線 ≥0.4 | 111 | 55.0%（-1.0pp） | +0.021%（-0.140pp） |
| D 收在最高 ≥0.9 | 86 | 57.0%（+1.1pp） | +0.057%（-0.104pp） |
| E 連兩日先殺後拉 | 10 | 50.0%（-5.9pp） | -0.026%（樣本不足） |
| **X 收在最低 ≤0.1**（反向對照） | 100 | **58.0%（+2.1pp）** | **+0.385%（+0.224pp）** |
| **Y 長上影線 ≥0.4**（反向對照） | 74 | **58.1%（+2.2pp）** | +0.325%（+0.163pp） |

**結果：方向是反的。** 「先殺後拉」不但沒有預測力，隔日表現還比什麼都不看**更差**；反而「收在最低」「長上影線」這些看起來弱的型態隔日略優於基準（符合短線均值回歸：收得越弱越容易反彈，而先殺後拉是當日已把反彈走完）。

**不建議反過來用**：超額僅 +2.1pp 勝率／+0.22pp 報酬，500 筆樣本下接近雜訊；且樣本全在大多頭，均值回歸在多頭市特別容易成立，換環境可能翻轉。**不加入 Signal。**

**⚠️ 本次最重要的方法論收穫：驗證任何「訊號出現後會怎樣」的問題，一定要設「無條件基準」對照組。** 若沒有基準線，看到「先殺後拉隔日勝率 50%」可能會覺得「五五波、也許有點用」；一對照才知道基準是 **55.9%**，實際上是明顯更差。**大多頭樣本會把所有訊號的絕對數字都墊高**（本樣本 501 個交易日指數 +102%），不設基準線會全部誤判為有效。這與「停損距離校準」那次「必須看 alpha 而非原始報酬」是同一個道理——**都是在扣掉市場本身的貢獻之後才看得出訊號的真實價值**。

**累計：這是第五次驗證出「看起來合理的型態／規則訊號實測無效」**（前四次：🎯🔥進場型態、移動停損、confirm_days=1、策略F）。日後再有型態類提案，可先引用這五次的紀錄說明先驗機率很低，但仍應實測——本次「方向是反的」就不在事前預期內。

### 策略 F：評分自峰值衰退即出場（2026-08-20 驗證，結論：不採用）

**要驗證的問題：** 把「評分衰退提示」搬到持倉列表後（見十八章對應小節），使用者提出直覺——「看到評分衰退就自行決定出場，不用呆板等 C 或 D 的訊號，應該更能保全獲益」。把這個直覺寫成明確規則後實測：「持有期間評分自近期峰值（峰值需 ≥65）回落 ≥N 分即出場」，其餘規則與策略 C 相同。腳本：`backtest_score_decline_exit.py`。

| 策略 | 全歷史EV | 全勝率 | 筆數 | 空頭段(7/14起)均報酬 | 段停損率 | 段防禦觸發 |
|---|---|---|---|---|---|---|
| 純C（現行） | **+4.67%** | **47.6%** | 429 | -6.51% | 78% | 0 |
| 純D | +1.75% | 39.9% | 715 | **-1.35%** | 22% | 40 |
| **F 衰退5分** | **+0.17%** | **26.6%** | 851 | -1.93% | 15% | 60 |
| F 衰退8分 | +0.62% | 33.1% | 723 | -2.53% | 25% | 41 |
| F 衰退12分 | +1.61% | 37.7% | 616 | -3.23% | 39% | 25 |

**事前預期完全錯誤（記錄下來供校準）：** 原本預測 F 會落在 C 和 D 之間、甚至可能優於 D，理由是「看個股體質而非市場雜訊，誤殺應該較少」。實際上 F 全面差於 D，且**越敏感越差**（門檻由12分收緊到5分，EV 從 +1.61% 一路掉到 +0.17%）。這個「更敏感 → 更差」的形狀與移動停損、confirm_days=1 完全一致，是第四次驗證出同樣結論。

**致命點：F 衰退5分（＝目前 UI 警告框的觸發門檻）扣掉交易成本後是虧錢的。** 交易次數由 429 筆暴增到 851 筆，每筆都付來回成本（`FEE_RATE×FEE_DISCOUNT×2 + TAX_RATE ≈ 0.47%`）：

- 純C：+4.67% − 0.47% = **+4.20% 淨賺**
- F 衰退5分：+0.17% − 0.47% = **−0.30% 淨賠**

勝率 26.6% 代表四筆裡三筆賠錢。**這也是第一次在本專案的回測中，交易成本本身成為決定性因素**——過去比較 C/D/E 時各策略交易次數同數量級，成本可先忽略；F 讓次數翻倍，就不能忽略了。日後任何會顯著增加交易次數的規則，**都必須把 0.47% 的來回成本納入比較**，不能只看毛EV。

**但同時找到了使用者直覺的來源（本次最有價值的發現）：** 把窗口改成「進場日 >= 2026-08-11」（＝使用者實際經歷的那一週）重跑：

| 策略 | 段均報酬 | 段停損率 | 段防禦觸發 |
|---|---|---|---|
| 純C | -8.00% | 100% | 0 |
| 純D | -8.00% | 100% | 0 |
| **F 衰退5分** | **-1.99%** | 9% | **29** |

**那一週 F 是唯一有效的規則。** 因為當週大盤淨值全程 0~+1，市場層級訊號從未啟動（見上一節），傷害純粹發生在**個股層級**，而 F 是本專案唯一測過的「看個股體質」的出場規則。

**結論：不採用。** 評分衰退提示維持「純資訊揭露」定位，不升級成正式出場規則。UI 上的定位應是「這檔要特別盯著」，而不是「立刻出場」。

**通則（重要，適用於所有來自使用者直覺的規則提案）：** 使用者的直覺往往形成於**某一個特定情境**，而在那個情境下直覺通常是正確的——這正是它感覺如此強烈的原因。但把它推廣成通則後，要付的是**每一筆交易都在付的常態成本**。驗證這類提案時，除了跑全歷史，一定要**另外拆出「使用者當初形成這個直覺的那段期間」單獨統計**——如果只跑全歷史，會得到「這規則很爛」的結論卻無法解釋為何使用者感受如此強烈，說服力不足；兩者並列，才能同時說明「你的觀察是對的」和「但不能這樣推廣」。

### 停損距離校準：8% → 10%（2026-08-27 驗證，**已採用，正式規則變更**）

**這是本專案第一次因回測而變更正式規則的參數**（前幾次驗證的結論都是「維持現狀」）。

> **🚨 本節的核心結論「alpha 在 10% 見頂」2026-10-16 被推翻——那個峰值是樣本造成的。**
> 全市場 512 檔 ＋ 2018~2026（含三個空頭年）＋ 配對設計重測：
> **六個停損距離的 alpha 全距只有 0.10pp，而雜訊帶是 0.28pp ⇒ 分不出來**；
> 5 檔配對五個對照**全部 ⚪**，其中「**10% vs 8%」是 50/100、p=1.000 的完美 null**
> ——也就是說本節那個「+1.68% → +2.06%」的改善，在沒有倖存者偏誤、
> 又含空頭年的樣本上**完全不存在**。
>
> **而本節自己標著「從未驗證」的那句（崩盤時 10% 比 8% 每檔多賠 2pp）方向是對的：**
> 2018 空頭年逐年看是 **8% +0.39% → 幾乎不停損 +0.18%（單調遞減，越緊越好）**，
> 而 2026 大多頭是 **8% +0.22% → 15% +0.77%（單調遞增，越寬越好）**。
> ⇒ **本節的樣本全在多頭，所以必然指向「放寬」。方向是樣本決定的，不是停損本身。**
>
> **規則維持 10% 不變**（理由見本章末「停損距離在空頭樣本上的重驗」那節），
> 但**不可再引用本節當成「10% 經過驗證」的依據**。

**起因：** 使用者反映「近一個月績效不好」。診斷（`backtest_stocks.py` 分期間統計）：

| 期間 | 筆數 | 勝率 | 平均損益 | 停損率 |
|---|---|---|---|---|
| 全期間 | 437 | 47.1% | +4.56% | 34% |
| 2025全年 | 189 | 54.5% | +5.06% | 21% |
| 2026H1 | 225 | 45.3% | +5.30% | 40% |
| **近一個月** | **20** | **5.0%** | **-6.66%** | **80%** |

**關鍵診斷步驟：把報酬拆成 beta（市場）與 alpha（超額）。** 這是本專案第一次做這件事，也是後續所有判斷的基礎：

| 期間 | 個股報酬 | 同期大盤 | alpha |
|---|---|---|---|
| 全期間 | +4.56% | **+2.88%** | +1.68% |
| 2025全年 | +5.06% | +2.83% | +2.24% |
| 2026H1 | +5.30% | +3.32% | +1.97% |
| 近一個月 | -6.66% | **-1.33%** | **-5.33%** |

兩個發現：(1) **策略報酬有 63% 來自 beta**——若市場長期橫盤，期望值會從 +4.56% 掉到約 +1.7%，這個數字才該是心理預期基準；(2) 近一個月**大盤只跌 1.33%，但交易賠 6.66%**，是策略主動摧毀價值，不是市場害的。

**機制（決定性證據）：** 近一個月 16 筆停損中 **14 筆（88%）在停損後反彈**，停損後平均 +7.09%；若不停損抱到最後平均僅 -1.48%（實際認賠 -8.00%）。同期自選股波動度中位數由 7/11 的 4.07 升至 4.63、高波動股佔比 54%→62%——**8% 的相對距離在高波動期變近，被雜訊反覆掃到**。

**停損距離掃描（`backtest_vol_stop.py`，全期間 437 筆）：**

| 停損 | 報酬 | **alpha** | 停損率 | 最大單筆虧損 |
|---|---|---|---|---|
| 8%（舊） | +4.56% | +1.68% | 34% | -8.0% |
| **10%（採用）** | +5.22% | **+2.06%** ← 見頂 | 24% | -10.0% |
| 12% | +5.31% | +2.01% | 17% | -12.0% |
| 15% | +5.36% | +1.99% | 10% | -15.0% |
| 25% | +5.51% | +1.98% | 2% | -25.0% |
| 幾乎不停損 | +5.41% | +1.83% | 0% | **-67.6%** |

**⚠️ 最重要的方法論教訓：必須看 alpha，不能看原始報酬。** 原始報酬一路上升到 25%，若照它選會得到「停損越寬越好」的錯誤結論——但那多出來的部分是大多頭的 beta（停損越寬、持有越久、吃到越多市場漲幅），不是策略貢獻。扣掉同期大盤後，alpha 在 **10% 見頂**、之後持續下滑。四個子期間結論一致（全期間／2025／2026H1／近一個月全部改善），不是只對近期有效。「幾乎不停損」的 **-67.6% 最大單筆虧損**說明停損不能拿掉。

**同批否決：依個股波動度調整停損距離**（`停損 = 進場價 × (1 − k×vol20)`）。對齊平均距離後與固定值幾乎完全相同：

| 設定 | 平均停損距離 | 報酬 | alpha |
|---|---|---|---|
| vol×2.5 | 8.0% | +4.68% | +1.71% |
| 固定 8% | 8.0% | +4.56% | +1.68% |
| vol×3.0 | 9.4% | +5.21% | +2.00% |
| 固定 10% | 10.0% | +5.22% | +2.06% |

**vol20 這個變數無貢獻，不引入。** 這組「單純放寬」的對照是**必要的方法論防護**——若只測 vol×3.0 看到 +5.21%，會誤以為波動度調整有效。**日後任何「按某變數動態調整既有參數」的提案，都必須加測「把該參數直接改成同等平均值的固定值」當對照。**

**同批否決：趨勢強度過濾**（`backtest_trend_filter.py`，Kaufman 效率比 ER／MA20 斜率）。ER≥0.20/0.30/0.40 在 2026 有效但 **2025 全面變差**（+5.06%→+4.63/+4.89/+3.85），且被擋掉的訊號原本平均 **+2.10%～+2.82%（是好交易）**，判定為過度配適。另按 ER 四等分檢視 437 筆：最震盪組 alpha 仍有 +1.21%、停損率 35%（與其他組相當），代表震盪期表現差主要是**市場漲得少**，不是策略特別失靈——近一個月的 alpha -5.33% 在歷史上是異常值，不是震盪期的常態。

**已同步修改的位置（改參數時務必全部檢查）：**

| 檔案 | 位置 |
|---|---|
| `config.py` | `STOP_LOSS_RATIO = 0.90`（`database.add_position()` 的預設停損來源） |
| `backtest_stocks.py` | 另一份獨立的 `STOP_LOSS_RATIO = 0.90` + docstring；所有 `backtest_*.py` 都 import 這一份 |
| `indicators.py` | `result['stop_loss'] = ma20 × 0.99 × 0.90`（個股技術面「停損參考價」） |
| `app.py` | 進場清單參考停損價、進場登錄表單預設值、手動登錄表單預設值、caption 的「×0.90」字樣、策略規則區塊「跌 10%」、程式說明第七章、版本紀錄 v3.5 |
| `投資策略.md` | 二節停損規則、四節回測條件註記、新增五節「停損距離驗證」 |

**⚠️ 既有持倉的 `stop_price` 不會自動更新**（那是已經在券商掛出去的價格，屬既成事實）。若要改用新距離，需在持倉列用 ✏️ 手動修改，並同步改券商的預掛單。

**⚠️ 上表「四、回測依據」的 A/B/C/D 數字（60.6%／+10.20% 等）是 8% 停損時期跑的**，與現行 10% 不同源。日後重跑時要一併更新，或至少標明基準不同。

**限制：** 樣本仍是 2024–2026（大盤 +102%），沒有經歷真正的長期空頭。真的崩盤時 10% 會比 8% 每檔多賠 2 個百分點。

### 移動停損空頭段驗證（2026-08-18 補跑，回應「進場成本停損 vs 從高點回落停損」的討論）

背景：使用者提出「固定停損容易有『本來有賺、後來吐回去變賠』的懊悔感，該不該改成從高點回落幅度停損」的疑慮。上面的移動停利掃描結論是用早期偏多頭資料測的，這次用含空頭段的完整資料重新驗證，並額外拆出空頭段單獨統計（原本 `scan_trailing_stop()` 只印全歷史數字）。腳本：`backtest_trailing_stop_bear.py`（實驗性質，未接入正式邏輯，未進版控）。

| 設定 | 全歷史EV | 全歷史勝率 | 空頭段均報酬 | 空頭段勝率 | 空頭段停損率 | 空頭段移動停利觸發率 |
|---|---|---|---|---|---|---|
| 無移動停損（現行） | +3.54% | 50.8% | -3.04% | 21.7% | 52% | 0% |
| 回落3% | +0.91% | 33.9% | -1.42% | 8.9% | 11% | 80% |
| 回落5% | +1.83% | 39.1% | -1.72% | 21.9% | 19% | 59% |
| 回落8% | +2.90% | 47.1% | -2.73% | 23.1% | 38% | 23% |

**結論：** 全歷史結論不變——移動停損幅度越緊，EV 掉得越多（+3.54%→+0.91%/+1.83%/+2.90%），確認不是舊資料不足造成的假象。但空頭段拆解出一個新發現：移動停損確實會讓**每筆虧損的平均幅度變小**（回落3%時空頭段均報酬只有-1.42%，遠優於現行的-3.04%），代價是**勝率大幅下滑**（8.9% vs 21.7%）——大量「本來會撐過短期回檔、最終打平或小賺」的交易被提早巴出場變成小賠。**維持現狀，不採用移動停損**：全歷史的代價是每筆交易都在付的常態成本，「不用看著獲利吐回去」的心理舒適感只在空頭那幾週才有感，用經常性大成本換偶爾的心理安慰不划算；且現行策略的「滿10日重新評分續抱」機制，本來就已經用「體質有沒有轉弱」取代「價格有沒有回落」在做類似的事，不需要再疊加一層價格層面的移動停損。

**通則（給下一次做回測驗證時參考）：** 做任何回測驗證前，先講清楚**這次要驗證什麼問題、想回答哪個具體疑慮**（例如這次是「使用者質疑固定停損的心理不適感，該不該改用高點回落停損」），再動手寫腳本、跑資料。原因：這類實驗性回測腳本通常不進版控（跟正式的 `backtest.py`／`backtest_stocks.py` 不同），時間一久很容易忘記當初為什麼要跑這個、要驗證的具體問題是什麼，事後只留下一堆數字表格但脫離了原本的問題脈絡。每個腳本的 docstring 開頭都應該先寫「背景/要驗證的問題」，再放程式碼。

**回測執行注意（sandbox 環境）：** 直接對掛載目錄跑回測極慢（FUSE + SQLite），需先把 `*.py` + `data/stock.db` 複製到本地暫存目錄再跑。`backtest_stocks.py` 全程約 60–80 秒，若環境有單次執行時間上限，可用 wrapper 腳本逐一執行策略（`_build_market_signals()` + `_run_backtest(...)` 各策略獨立呼叫，結果 pickle 存檔後彙整）。

### 大盤評分門檻階梯的第一次驗證（2026-09-10，**發現實作落差，結論：不動規則**）

**起因：** 使用者問「大盤評分的機制好像沒有做過回測？」查證後確認**只測過一半**，而且沒測到的正好是每天實際在用的那一半。腳本：`backtest_market_score.py`（已進版控）。

| | 狀態 |
|---|---|
| S1–S8 的 net 對隔日方向的準確率 | ~~✅ 測過~~ → **❌ 測過但沒設基準，2026-09-23 補做後發現低於基準**（52.7% vs 55.9%） |
| 「`net > 0` 不進場」二元開關 | ✅ 測過（策略 A vs B） |
| **UI 的四段門檻階梯** | ❌ **從沒測過** |
| 乘數 ×5、45/55/70/85 級距切點 | ❌ 從沒校準過（對照 S3/S4 的門檻是抓實際分布算百分位校準的，陷阱34） |

**⚠️ 最重要的發現不是數字，是實作落差：回測驗的規則跟 UI 教的規則根本是兩套。**

| | UI 教使用者的（`render_strategy()`） | 回測一直在驗的（`_run_backtest`） |
|---|---|---|
| 大盤 | 四段門檻階梯 + `<45` 停止進場 | `if market_net.get(date) > 0: continue` |
| 個股門檻 | 65／70／75 隨大盤變 | 一律 65 |
| 交易筆數 | 242 | 470 |

**所有標著「回測依據」的數字描述的都是右邊那欄。照 UI 操作的人，實際進場機會比回測基準少了一半。**

#### Q1：固定門檻 65 分，依「決策日大盤評分」分組（541 筆）

決策日 = 評分所依據的那根K，**不是進場日**（用進場日等於偷看未來）。為此在 `backtest_stocks.py` 的 trade dict 新增 `signal_date` 欄位——事後用進場日回推會對錯，因為個股若有缺資料，它的「下一根K」未必等於 TAIEX 的下一個交易日。

大盤評分的歷史分布（516 個決策日）：`≥70` 僅 **15 天（2.9%）**、`55–69` 197 天、`45–54` 217 天、`<45` 87 天。

| 決策日大盤評分 | 筆數 | 勝率 | 報酬 | 同期大盤 | **alpha** | 停損率 |
|---|---|---|---|---|---|---|
| ★ 基準（全部） | 541 | 51.0% | +5.39% | +3.31% | **+2.09%** | 22.0% |
| ≥70 | **8** | 75.0% | +29.31% | +7.27% | +22.03% | 0.0% |
| 55–69 | 195 | 46.7% | +2.68% | +2.70% | **-0.01%** | 25.1% |
| 45–54 | 225 | 52.4% | +6.17% | +3.51% | +2.66% | 20.4% |
| <45 | 113 | 54.0% | +6.82% | +3.66% | **+3.16%** | 21.2% |

分期間 alpha（2025／2026H1）確認排序一致：55–69 是 +0.94%／-0.27%，45–54 是 +3.28%／+4.19%，<45 是 +3.44%／+5.19%。**不是被單一時段帶走的。**

**`≥70` 這一檔（唯一說「可積極進場」的）實質上不存在**——516 天只出現 15 天、8 筆交易，那個 +22% alpha 不可當證據。

#### Q1-c：順帶重驗大盤過濾本身（舊基準已不成立）

| | 筆數 | 勝率 | 報酬 | alpha | 停損率 |
|---|---|---|---|---|---|
| 無大盤過濾 | 541 | 51.0% | +5.39% | +2.09% | 22.0% |
| 有大盤過濾（策略C） | 470 | 51.1% | +4.72% | **+1.69%** | **24.3%** |

**⚠️ 本章開頭「四種策略」表的 A→B（58.0%→63.7%、+7.27%→+8.11%）是 176 筆時代跑的，在 541 筆上不成立。** 現在的資料上，過濾擋掉 71 筆換來 alpha 少 0.40pp、停損率反而升高 2.3pp。

#### Q2：各組內把門檻提高到 70／75 有沒有用（alpha／筆數／停損率）

| 大盤評分組 | 門檻 65 | 門檻 70 | 門檻 75 |
|---|---|---|---|
| 55–69（現行 70） | -0.01%／195／25.1% | **+2.33%／115／18.3%** ←現行 | -2.98%／22／22.7% |
| 45–54（現行 75） | +2.66%／225／20.4% | +1.58%／149／15.4% | **+4.10%／36／11.1%** ←現行 |
| <45（現行 停止） | **+3.16%／113／21.2%** | -0.51%／83／19.3% | +2.48%／32／15.6% |

`55–69` 那格是階梯裡**唯一有紮實證據**的一格（n=115，alpha 由 -0.01% 拉到 +2.33%，停損率同步改善）。`45–54` 的現行值看起來最好但 n=36 且非單調（70 反而比 65 差），`<45` 也非單調——兩者都比較像雜訊。

#### Q3：把階梯真的實作進回測（第一次）

為此在 `_run_backtest()` 新增 `threshold_fn(date) -> int | None` 參數（回傳 None = 該日停止進場）。續抱門檻固定 65，與策略C 的續抱規則一致；只有進場門檻走階梯。

| 規則 | 筆數 | 勝率 | 報酬 | 同期大盤 | **alpha** | 停損率 |
|---|---|---|---|---|---|---|
| 基準：不看大盤，一律 65 | 541 | 51.0% | +5.39% | +3.31% | +2.09% | 22.0% |
| 策略C（回測長期在驗的） | 470 | 51.1% | +4.72% | +3.03% | +1.69% | 24.3% |
| **現行 UI 階梯** | 242 | 54.5% | +5.54% | +3.21% | **+2.33%** | **16.5%** |
| 階梯但 `<45` 不封鎖 | 383 | 53.5% | +5.64% | +3.63% | +2.01% | 19.1% |
| **對照：不看大盤，一律 70 分** | 329 | 53.8% | +5.90% | +3.83% | **+2.07%** | 17.6% |

**三個結論：**

1. **階梯確實優於回測長期在驗的策略C**（alpha +2.33% vs +1.69%、停損率 16.5% vs 24.3%）。所以它不是壞設計。
2. **但它的好處幾乎全部來自「門檻整體拉高到 70 左右」，不是來自「隨大盤調整」。** 對照組「**完全不看大盤**、一律 70 分」alpha +2.07%——只差 **0.26pp**，而且多了 26% 的進場機會（329 vs 242 筆）。大盤評分這個面向的邊際貢獻在 242 筆樣本下是雜訊等級。

   > **❌ 這一條的後半在 2026-10-15 被推翻。** 修好 S4（陷阱51）＋ 改用全市場 512 檔
   > ＋ 2018~2026 含三個空頭年 ＋ 配對設計之後重測：「門檻由 65 拉到 70」
   > **「階梯 ≈ 一律70」是完美 null（10/20、p=1.000，兩份快取都一致）**
   > ⇒ 本條當成「階梯唯一真實好處」的那一維，**不存在**。
   > **而且更進一步：階梯整體顯著差於「不看大盤、一律 65 分」**
   > （-0.25pp、4/20、p=0.012；另一份快取 3/20、p=0.003）。
   > ⚠️ 但「拉高到 70」單獨拆出來是 6/20、7/20，**方向同、沒跨過顯著**。
   > 「階梯 ≈ 一律70」這前半仍然成立（這次是 10/20、p=1.000 的完美 null）。
   > 完整記錄見本章「階梯的第二次驗證」那節。
3. `<45 停止進場` 在同一個 run 內貢獻 +0.32pp alpha（2.33% vs 2.01%），代價是少 141 筆交易。

**結論：不動規則。** 與停損校準那次不同（那次 alpha 有明確峰值、四個子期間一致），這次差距在雜訊範圍；且樣本期指數 +102%、沒經歷長期空頭，而 `<45 停止進場` 的價值本來就該在空頭才顯現（2026-07 空頭段實測 B 擋掉 18 筆平均 -4.21%）。錯的方向不對稱：多頭少賺 vs 空頭大賠。

**⚠️ 引用本節數字時的三個限制：**
- **跨 run 的數字不能直接相減**——有狀態依賴（一檔已被持有就無法在別的日子進場），只有同一個 run 內的對照才嚴謹。例如 Q2 的 `<45`／65分 alpha +3.16%，在 Q3 的 `階梯但<45不封鎖` 裡實際只貢獻約 +1.46%。
- 樣本全在大多頭，任何「減少市場曝險」的規則必然扣分——這是結構性偏誤，不等於規則無效。
- `≥70` 組全部格子 n<20，整組無法判斷。

**方法論收穫（兩點，都是既有通則的再次應驗）：**

1. **「按某變數動態調整參數」必須加測「把該參數改成同等平均值的固定值」當對照**——停損校準那節立的規矩，這次直接派上用場。階梯的平均門檻落在 70 附近，對照一跑，「大盤評分」這個面向就現出原形。**沒有這個對照，看到階梯 alpha 較高會直接誤判為「大盤評分有效」。**
2. **分組比較時，要確認分組用的門檻與現行規則一致。** 本次第一版（Q1）拿「所有組都用 65 分」在比，得到「階梯方向是反的」這個結論——但現行規則本來就對不同組用不同門檻，那張表其實是「拿掉階梯會怎樣」，不是「現行系統的表現」。**Q1 單獨看會導向錯誤結論，是 Q3 把階梯真的跑起來才修正回來。分組統計永遠要問一句：這個分組方式，跟系統實際在做的事一樣嗎？**

### 🚨 階梯的第二次驗證：「隨大盤調整」貢獻為零，而「門檻拉高」的方向偏負但不可靠（2026-10-15/16）

**⚠️ 這一節推翻了 2026-09-10 的主要解讀。** 那次的結論是
「階梯的好處幾乎全部來自**門檻整體拉高到 70**，不是來自隨大盤調整」
——而這次量到**「階梯 ≈ 一律70」是完美 null**，所以「拉高」不是好處。
**而真正顯著的那一對是「階梯 vs 一律65」**（-0.25pp、4/20、p=0.012，兩份快取一致）。
⚠️ **我第一版把「一律70 vs 一律65（2/20、p=0.000）」當成頭條，那是 `sorted()` bug
的產物**，詳見下方「我第一版的頭條是 bug 的產物」。

腳本：`backtest_market_ladder.py`（已進版控）。

#### 為什麼要重跑：9/10 那次的三個問題，全部是之後才發現的

| | 問題 | 何時發現 |
|---|---|---|
| ① | **S4 法人現貨幾乎是死的**——回測 ±3分觸發率 **0.0%** ⇒ net 分布天生偏窄 | 陷阱51（10/07）|
| ② | 跑在**自選股 74 檔**上，而 87/87 檔都是回測期之後才加入 ⇒ **含後見之明** | 10/09~24 |
| ③ | n=242、雜訊帶 2.76pp ⇒ 結論只能是「差距在雜訊範圍」 | 同上 |

本次三者全修：S4 已修並校準、全市場 **512 檔**、**2018-01-02 ~ 2026-10-14（2,132 日）**
含三個空頭年、配對設計消掉抽樣運氣。

**★ 第一個變化：`≥70` 那一檔不再「實質上不存在」。**
9/10 那次它只有 **15 天（2.9%）**，當時明寫「實質上不存在、那個 +22% alpha 不可當證據」。
S4 修好後是 **193 天（9.1%）**——因為 S4 原本幾乎不出分，net 被壓在中間。

| 大盤評分分段 | 9/10（516 日、S4 死） | **10/15（2,132 日、S4 已修）** |
|---|---|---|
| ≥70 | 15 天（2.9%）| **193 天（9.1%）** |
| 55–69 | 197 | 634（29.7%）|
| 45–54 | 217 | 661（31.0%）|
| <45 | 87 | 644（30.2%）|

#### ★ 事前預期（先寫下再跑）—— 主預期錯，但我自己標的「反方向」對了

> 「階梯與『固定 70 分』仍然分不出來，但 **`<45 停止進場` 可能第一次測得出效果**
> ——9/10 那次 `<45` 只有 87 天且全在多頭，現在有三個空頭年。
> **反方向的可能（而且我認為機率更高）：** 10/08 已量到大盤淨值
> 在 2022 觸發率九年最低、2026 大多頭最高——它是**過熱偵測器不是空頭偵測器**。」

| 預期 | 結果 |
|---|---|
| 階梯 ≈ 固定 70 | ✅ **對**（10/20、p=1.000，完美 null）|
| `<45` 在空頭年測得出效果 | ❌ **錯**。空頭年 +0.03pp、其他年 -0.06pp，整體 8/20 p=0.503 |
| 「反方向」：淨值是過熱偵測器 | ✅ **對，而且在交易層看得更清楚**（見下）|

#### ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）

| 規則 | 筆數 | alpha | **扣 0.47% 成本** | 勝率 |
|---|---|---|---|---|
| A 不看大盤・一律 65（基準） | 28,613 | +0.19% | -0.28% | 43.8% |
| B 策略C（net>0 不進場・一律65） | 23,948 | +0.19% | -0.28% | 43.7% |
| **C ★現行 UI 階梯** | 15,176 | **+0.31%** | **-0.16%** | 42.9% |
| D 階梯但 `<45` 不封鎖 | 15,666 | +0.34% | -0.13% | 42.9% |
| **★E 不看大盤・一律 70（關鍵對照）** | 17,885 | **+0.14%** | -0.33% | 42.5% |
| F 不看大盤・一律 75 | 7,596 | +0.15% | -0.32% | 41.7% |

```
各組 alpha 全距 0.20pp　vs 最寬雜訊帶 0.36pp
⇒ ⚪ per-trade 層級**六組全在雜訊帶內，不可解讀**
```

**★ 順手的對帳點：** `C 現行 UI 階梯` 跑出 **15,176 筆、alpha +0.31%**，
與 10/14 那次的 `A0 現行策略` **完全相同** ⇒ 新加的 `threshold_fn` 參數
確實位元級一致，不需要另外對帳（這正是「不要有第二份實作」那條通則的用處）。

> **⚠️ 2026-10-22 更正（陷阱56）：這個對帳點只在「同一份快取內」有效。**
> 10/21 用新建的快取重跑同一組設定得到 **15,221 筆、alpha +0.24%**
> ——因為 FMTQIK 每日 UPDATE 近 12 個月的 `prices.value`、而 S8 讀它
> ⇒ **大盤淨值會回溯改變**。而**不碰淨值**的對照組（一律 65 分）
> 則幾乎完全對上（28,444／+0.18% vs 28,613／+0.19%），分解很乾淨。

**⚠️ 而且扣掉 0.47% 來回成本後，六組全部是負的（-0.13% ~ -0.33%）。**
這張表比的是「哪一組虧得少一點」，不是「哪一組會賺」。

#### ★★ ② 5 檔配置・配對比較（20 條，同一 seed 同一組真隨機排序）

#### 🚨 我第一版的頭條是 bug 的產物，正確答案是另一組（2026-10-16）

**發現經過：** 使用者在本機跑同一支腳本、同一組 seed，六個配對有**兩個與我沙盒不一致**。
根因是我自己的 bug：

```python
pref = {c: rnd.random() for c in cache['stocks']}      # ← 舊版，少了 sorted()
```

`cache['stocks']` 是 dict ⇒ 順序＝**插入順序**。而兩份快取的建構路徑不同：

| 快取 | 建法 | 實測是否 sorted |
|---|---|---|
| `_pf_slots_cache_market.pkl`（使用者本機） | `build_cache()` 循序建，而 `market_universe()` **回傳 `sorted(...)`** | **✅ 是** |
| `_rev_filter_cache.pkl`（我沙盒） | 分塊後 `stocks.update()` 合併 | **❌ 不是** |

⇒ **我那一份的隨機偏好配錯了股票**，而使用者那一份一直是對的。
**換句話說：不是「兩次都合法但不一致」，是我那次有 bug。**

#### ✅ 修正後兩份快取**六個判定全部一致**（這才是正確答案）

| 配對 | 沙盒（修正後） | **本機** | 判定 |
|---|---|---|---|
| **★★ 階梯 vs 一律70** | -0.08pp　10/20　**1.000** | -0.01pp　10/20　**1.000** | ⚪ **完美 null** |
| **🚨 階梯 vs 一律65** | -0.23pp　**3/20　0.003** | -0.25pp　**4/20　0.012** | **❌ 唯一顯著，兩份一致** |
| 階梯 vs 策略C | -0.17pp　6/20　0.115 | -0.14pp　6/20　0.115 | ⚪ |
| ★ `<45` 封鎖的貢獻 | -0.13pp　6/20　0.115 | -0.12pp　7/20　0.263 | ⚪ 測不出來 |
| 一律70 vs 一律65 | -0.19pp　6/20　0.115 | -0.15pp　7/20　0.263 | ⚪ **方向同但沒跨** |
| 一律75 vs 一律70 | -0.01pp　10/20　1.000 | -0.05pp　10/20　1.000 | ⚪ |

**⇒ 顯著的那一對是「階梯 vs 一律65」，不是我第一版寫的「一律70 vs 一律65」。**

**★ 而這個組合是有機制的，拆開來看很乾淨：**

```
階梯 = 把門檻拉高（≈-0.15 ~ -0.19pp，不顯著）
     ＋ <45 停止進場（≈-0.12 ~ -0.13pp，不顯著）
     ───────────────────────────────────────
     合計 -0.23 ~ -0.25pp  ⇒ 跨過顯著門檻（3/20、4/20）
```

**兩個成分各自都檢不出來，疊起來才顯著** ——這解釋了為什麼
「階梯 ≈ 一律70」是完美 null（因為 70 只含第一個成分），
而「階梯 vs 一律65」顯著（它含兩個成分）。

#### ⇒ 能說與不能說

| | |
|---|---|
| ✅ **可以說** | **在 5 檔配置下，現行階梯顯著差於「完全不看大盤、一律 65 分」**（-0.25pp、4/20、p=0.012；另一份快取 3/20、p=0.003）|
| ✅ 可以說 | **「隨大盤調整」這一維的貢獻是零**——階梯 ≈ 一律70 兩份都是 10/20、p=1.000 的完美 null（第二次得到同一結論，而且這次 S4 是好的）|
| ⚠️ **不能說** | 「門檻拉高到 70 顯著有害」——單獨拆出來是 6/20、7/20，**方向相同但沒跨過**。同理 `<45 封鎖` 也測不出來 |
| 🚨 **我第一版寫錯的** | 「**一律70 vs 一律65：2/20、p=0.000、唯一顯著**」——那是 `sorted()` bug 的產物，**整段已重寫** |

**⇒ 9/10 那句「階梯的好處幾乎全部來自門檻拉高到 70」兩頭都站不住：**
「拉高」不是好處（階梯 ≈ 一律70 是完美 null），而**階梯整體顯著差於固定 65 分**。

#### 🚨 而 `backtest_structure_bear.py` 的同族 bug 更嚴重（也已修）

它是**懶惰指派**，而且寫在被規則擋住的進場分支裡：

```python
pref = {}
...
if len(held) < SLOTS and i < n - 1 and mkt_ok:   # ← 這個分支會被規則擋掉
    for code in uni_at[i]:
        if code not in pref: pref[code] = rnd.random()
```

第 0 天所有規則都有空位，所以當時在宇宙裡的檔是一致的；
**但 `uni_at` 是逐月調整的點時間宇宙**，後來才進榜的檔會在「各規則第一次走到
那個分支」時才拿到偏好——而**空手型規則（g/h/i、淨值 j~m）跳過的日子與
滿倉型不同** ⇒ **配對隨時間逐漸失效，完全不報錯。**
已改成在函式開頭對 `sorted(close)` 一次指派完。
**10/07 與 10/08 兩節的小效果配對必須重跑**（那兩節已加補註）。

#### ⭐ 方法論（三點，都是新的）

**(a) 隨機排序鍵的來源必須與快取的建構路徑無關。**
只要它來自 `dict` 的迭代順序，而那個 dict 是不同程式路徑建的，
**配對設計的「同一組運氣」前提就破了，但數字看起來完全正常。**
⇒ 一律用 `sorted()` 之類的確定性順序。
**而且「懶惰指派」比「未排序」更糟**——後者至少在同一份快取內一致，
前者連同一份快取裡的不同規則都會錯開。

**(b) 兩份獨立產生的快取跑同一個測試，是最便宜也最有效的交叉驗證。**
本次就是它抓到 bug 的：**六個配對有兩個不一致 ⇒ 立刻知道「同一組運氣」沒成立。**
修好之後六個判定全部一致，才是可以寫進結論的狀態。
⇒ **要寫進 CLAUDE.md 當結論的配對檢定，至少在兩份獨立快取上跑過。**

**(c) 擋下這個錯誤的不是我的審查，是使用者在自己機器上跑了一次。**
我第一版已經寫了「唯一顯著」「18 條裡 18 條更差」這種強度的字，
甚至把「證據指向換回固定 65 分」寫進結論。
**那個方向後來證明是對的，但當時支撐它的那個數字是錯的。**
⇒ **方向對 ≠ 證據對。** 不能因為結論「看起來合理」就少驗一次。

#### ✅ 2026-10-16 補做：換 seed base 之後，20 條全部不可靠；加到 100 條才有答案

**做法：** 給腳本加 `seedbase=` 與 `seeds=` 兩個 CLI 參數
（⚠️ `main()` 裡必須寫 `global SEED_BASE, N_SEEDS`，否則賦值會變成區域變數、**參數靜默無效**）。

**★ 先換三組 base 各跑 20 條——六個配對的判定幾乎全部翻來翻去：**

| 配對 | 7000 | 8000 | 9000 | 6000 |
|---|---|---|---|---|
| ★★ 階梯 vs 一律70 | 10/20 ⚪ **1.000** | 8/20 ⚪ .503 | **5/20 ❌ .041** | 7/20 ⚪ .263 |
| **階梯 vs 一律65** | **4/20 ❌ .012** | **11/20 ⚪ .824（方向翻正）** | **5/20 ❌ .041** | 6/20 ⚪ .115 |
| 階梯 vs 策略C | 6/20 ⚪ .115 | 12/20 ⚪ .503 | **5/20 ❌ .041** | **5/20 ❌ .041** |
| `<45` 封鎖 | 7/20 ⚪ .263 | 9/20 ⚪ .824 | **4/20 ❌ .012** | 7/20 ⚪ .263 |
| 一律70 vs 一律65 | 7/20 ⚪ .263 | 11/20 ⚪ .824 | 10/20 ⚪ 1.000 | 7/20 ⚪ .263 |
| 一律75 vs 一律70 | 10/20 ⚪ 1.000 | 7/20 ⚪ .263 | 6/20 ⚪ .115 | 8/20 ⚪ .503 |

**`seedbase=8000` 那一組六個全 ⚪、`9000` 那一組四個 ❌。**
連原本被當成「完美 null」的「階梯 ≈ 一律70」都在 9000 跑出 5/20、p=.041。
⇒ **20 條在這個效果量級上，個別判定幾乎沒有資訊。**

**★★ 正確的反應不是挑一組報出去，是加條數。100 條、兩個獨立 base：**

★ 第三組（9000）是**在使用者本機的 `_pf_slots_cache_market.pkl` 上跑的**
⇒ 同時滿足「換 seed base」與「換快取」兩個條件（10/16 那條規矩）。

| 配對 | 7000~7099<br>沙盒 | 8000~8099<br>沙盒 | **9000~9099<br>★本機快取** | 判定 |
|---|---|---|---|---|
| **★★ 階梯 vs 一律70** | -0.05pp　45/100　.368 | -0.05pp　46/100　.484 | **-0.04pp　45/100　.368** | ⚪ **3/3 一致，而且 45/46/45 極緊** |
| **🚨 階梯 vs 一律65** | **-0.12pp　37/100　.012** | **-0.11pp　39/100　.035** | **-0.18pp　29/100　.000** | **❌ 3/3 一致** |
| **🚨 階梯 vs 策略C** | **-0.17pp　35/100　.004** | **-0.15pp　38/100　.021** | **-0.17pp　32/100　.000** | **❌ 3/3 一致** |
| `<45` 封鎖的貢獻 | -0.10pp　**37/100　.012** | -0.08pp　43/100　.193 | -0.05pp　42/100　.133 | ⚠️ **2/3 ⚪**（7000 是離群）|
| 一律70 vs 一律65 | -0.09pp　**39/100　.035** | -0.04pp　46/100　.484 | -0.13pp　40/100　.057 | ⚠️ **2/3 ⚪**，方向 3/3 都負但跨不過 |
| 一律75 vs 一律70 | -0.04pp　46/100　.484 | -0.14pp　**37/100　.012** | -0.04pp　49/100　.920 | ⚠️ **2/3 ⚪**（8000 是離群）|

**★ 本機那一組的各規則中位 alpha 把同一件事講得更直接：**

```
A 不看大盤・一律 65（基準）   中位 alpha **+0.18%**
C ★現行 UI 階梯             中位 alpha **-0.07%**   ← 唯一是負的
★E 不看大盤・一律 70         中位 alpha  +0.04%
```

#### ⇒ 這一輪的淨結果：兩條站得住、三條仍不可下結論

| | |
|---|---|
| ✅ **確定**（100 條 ×**3**、含一組**不同快取**） | **現行階梯顯著差於「不看大盤、固定門檻」**——vs 一律65 是 37／39／**29**/100、vs 策略C 是 35／38／**32**/100。Δ中位 **-0.11 ~ -0.18pp** |
| ✅ **確定**（100 條 ×3） | **「隨大盤調整」這一維的貢獻是零**——階梯 ≈ 一律70，**45／46／45**/100（三次幾乎同一個數）。**第二次得到同一結論，而且這次有足夠檢定力** |
| ⚠️ **仍測不出來** | **`<45` 封鎖**、**拉高到 70**、**拉高到 75** 這三個成分**各自**都不穩（三組裡各有一組離群，且離群的是不同組）⇒ **2/3 指向 ⚪**，與本節原本的寫法一致，**不用改** |
| 🚨 **要注意的** | 20 條版本的 Δ中位（-0.25pp）**比 100 條（-0.12pp）大一倍**——條數少時中位數本身也偏得厲害，不只是 p 值不穩 |

**⇒ 所以結論的方向沒變（階梯不如固定門檻、隨大盤調整沒用），但證據從
「一組 20 條」升級成「兩組 100 條」。** 仍然不動規則——理由見本節末，
那兩條（陷阱44 的永久限制、只有一段 9 年歷史）都沒有因為加條數而改變。

#### ⭐ 方法論（這是本次最重要的收穫，也是新的一條）

**「換 seed base 重跑」不只是驗證，它同時在告訴你條數夠不夠。**

10/16 早上立的規矩是「結論要在兩份獨立快取上跑過」。這次執行它的時候發現
**更根本的問題**：四組 base 的判定互相矛盾 ⇒ 那不是「哪一組才對」的問題，
**是 20 條這個設計本身在這個效果量級上沒有解析度**。

⇒ **換 base 判定會翻，是「條數不足」的症狀，不是「結果不可信」的終點。**
正確的下一步是**加條數**（本次 20 → 100，成本只是跑久一點），
而不是在幾組之間挑一個報出去、或直接宣告「測不出來」。

**判斷方法：** 換一組 base 重跑，若判定翻 ⇒ 先加條數再看；
加到足夠條數後仍然翻（本次的 `<45`、拉高到70、拉高到75 三項）⇒ **那才是真的測不出來。**

#### 🚨 機制：兩個假設都被自己的測試推翻了

**假設一：候選不足導致槽位填不滿**（10/14 月營收那節立的通則，B2＞B3 就是這個機制）

```
規則         有訊號天數   候選中位   單日≥5檔
一律65          2,041        92     99.3%
階梯            1,416        26     95.1%
一律70          2,037        41     98.7%   ← 填得滿，假設不成立
一律75          2,018        12     90.9%
```
**❌ 推翻。** 一律70 有 98.7% 的日子候選 ≥5 檔，不是槽位閒置。

**假設二：65–69 那一段本身帶著 alpha，拉到 70 就把它排除掉**

| 評分區間 | 筆數 | 報酬 | **同期大盤** | alpha | 勝率 |
|---|---|---|---|---|---|
| 65–69 | 26,909 | +1.26% | **+1.09%** | **+0.17%** | 43.9% |
| 70–74 | 17,141 | +1.24% | +1.12% | +0.11% | 42.5% |
| 75–79 | 7,456 | +1.33% | +1.19% | +0.14% | 41.6% |
| ≥80 | 1,874 | +1.60% | **+1.64%** | **-0.04%** | 42.3% |

```
全距 0.21pp　vs 雜訊帶 0.45pp  ⇒ ⚪ 分不出來
```
**⚠️ 方向一致（65–69 最高、≥80 最低）但在雜訊帶內 ⇒ 機制沒有被獨立證實。**

**但這張表順手重現了 9/24 的兩個型態，而且這次是在「門檻之上」的子樣本裡：**
- **`同期大盤` 隨評分單調上升（+1.09% → +1.64%），而 alpha 不動**
  ⇒ 評分高＝吃到更多 **beta**，不是更多 alpha（「評分是後照鏡」的直接後果）
- **勝率隨評分下降**（43.9% → 41.6%）⇒ 與 9/24 同方向，這是**第四次**量到

#### ★ `<45 停止進場`：淨值是過熱偵測器，在交易層看得比 10/08 更清楚

| 年 | 階梯 alpha | 不封鎖 alpha | 差 | **被擋筆數** |
|---|---|---|---|---|
| **2018 ★空頭（-9.2%）** | +0.35% | +0.39% | -0.05pp | **15** |
| 2019 | +0.44% | +0.45% | -0.02pp | 23 |
| **2020 ★空頭（V轉）** | +0.28% | +0.18% | +0.10pp | 60 |
| 2021 | +0.46% | +0.56% | -0.10pp | 83 |
| **2022 ★空頭（-22.6%）** | +0.76% | +0.75% | **+0.01pp** | **17** |
| 2023 | +0.65% | +0.70% | -0.06pp | 56 |
| 2024 | -0.49% | -0.41% | -0.08pp | 41 |
| 2025 | -0.08% | -0.15% | +0.07pp | 59 |
| **2026（+70% 大多頭）** | +0.51% | +0.68% | **-0.17pp** | **136** |
| **★ 三空頭年合計** | +0.51% | +0.48% | **+0.03pp** | 92 |
| **其他六年合計** | +0.23% | +0.29% | **-0.06pp** | 398 |

**★ 決定性的那一欄是「被擋筆數」：**
**2022（唯一真空頭年、指數 -22.6%）只擋掉 17 筆，而 2026（+70% 大多頭）擋掉 136 筆。**
相差 8 倍，方向完全反了。

⇒ 10/08 用「逐年觸發率」量到的那件事（net≥2 在 2022 是九年最低 20.7%、
2026 最高 40.8%），在**交易層級**得到同一個答案：
**`<45 停止進場` 擋得最兇的時候是市場最強的時候，而在真正該擋的 2022 幾乎不作用。**

#### 結論：不改規則，但這一則與 9/10 的定位完全不同

| | |
|---|---|
| ❌ **不能說** | 「階梯是壞的、該拆掉」——「階梯 vs 一律65」只有 p=0.115 |
| ✅ **可以說** | ①「隨大盤調整」這一維的貢獻**第二次**測不出來，而且這次是完美 null（10/20、p=1.000）<br>②**階梯整體顯著差於「不看大盤、一律 65 分」**（4/20、p=0.012；另一份快取 3/20、p=0.003）。但拆開看「拉高到 70」與「`<45` 封鎖」**各自都不顯著**，是兩者疊加才跨過<br>③ `<45 停止進場` 的機制已明確：**它在空頭年最少啟動** |
| ⚠️ **9/10 那句話要改掉** | 「階梯的好處幾乎全部來自門檻拉高到 70」——那個「好處」在修好 S4 + 全市場 + 配對設計之後，**量到的是害處** |

**⇒ 若日後要動這條規則，方向是「把階梯換回固定 65 分」**
（那會多 **89%** 的進場機會：28,613 vs 15,176 筆）。
**而修正 `sorted()` bug 之後，這個方向的證據是兩份獨立快取一致的**
（3/20、p=0.003 與 4/20、p=0.012）。
✅ **(a) 已完成（10/16 當日）**：換了三組 20 條（互相矛盾）之後加到
**100 條 × 三個獨立 base，其中一組跑在使用者本機的另一份快取上**
——「階梯 vs 一律65」三次都 ❌（37/.012、39/.035、**29/.000**）、
「階梯 ≈ 一律70」三次都 ⚪ 且 **45/46/45 幾乎同一個數**
⇒ **這兩條的證據已經站得住**。詳見上方「換 seed base 之後」那節。
⚠️ **(b) 仍未處理，而且修不掉**——陷阱44：「65 分」在樣本前後段不是同一個篩選器
（基本面 25% 在 2026-05 之前恆為 50），而本節測的正是門檻。
⚠️ 另外仍然**只有一段 9 年的歷史**（配對設計消不掉「這 9 年剛好是什麼行情」）。
**本次不動規則。**

#### 限制（引用任何上述數字時必須一起講）

1. **除權息無法調整**（陷阱50）⇒ 絕對 alpha 系統性低估。`exdiv.py` 只能用在「兩組相減」。
2. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）⇒ 「65 分」在樣本前後段
   不是同一個篩選器。**這讓所有「門檻」類比較天生帶一層雜訊**，而本節測的正是門檻。
3. **未調整收盤價**（陷阱49）⇒ 分割日會有假停損。
4. 只有上市股；上櫃無籌碼資料，不在宇宙內。
5. **配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」**
   ⇒ p=0.000 的意思是「在這段歷史上方向穩定」，**不是**「換一段歷史也成立」。
6. 2016~2017 已裁掉（陷阱51 限制第5條）。實測那兩年 `<45` 只有 5.0%／6.2%，
   而 2018+ 是 20.7%~41.5%——**差 4~8 倍，混進去等於把兩套系統當成一套。**

#### 🚨 順帶抓到：陷阱51 那條通則**第四次**出現，而且就在這支測試自己的入口

使用者在本機跑 `backtest_market_ladder.py` 時出現「找不到快取」——
因為**專案所有快取都在 `/tmp`**，那是沙盒的 `/tmp`，使用者機器上從來沒建過。

而查 `backtest_portfolio_slots.py` 的 CLI 時發現更嚴重的事：

```python
if 'cache' in args:
    build_cache('market' if mkt else 'watchlist')    # ← 沒傳 days
```

`build_cache()` 的預設是 `days=600`（＝2024-05 起）。所以：

> **使用者照著「`cache market`」建快取 ⇒ 只會得到 600 天、一個空頭年都沒有、
> 而且完全不報錯。** 然後這支測試會跑出一份看起來正常、但其實只有多頭的結果
> ——而本次要回答的問題正是「`<45` 在空頭年有沒有用」。

**兩個修正：**

| | 做法 |
|---|---|
| `backtest_portfolio_slots.py` CLI | 接受 `days=NNNN`；`days ≤ 600` 時印警告。用法：`cache market days=2600` |
| `backtest_market_ladder.py` | ① 依序尋找兩種候選快取（本測試**不需要**月營收排名）<br>② **阻斷式涵蓋檢查**：三個空頭年沒全在就 `sys.exit`，不讓它靜默跑完 |

**★ 阻斷式守衛兩個方向都實測過**（照 10/07「成對造情境」那條）：
真快取 → `✅ 三個空頭年都在 ⇒ 前提成立`；
刻意裁成 600 天的假快取 → `🚨 快取沒有涵蓋 ['2018','2020','2022'] ⇒ 中止`。

**⭐ 這條通則前三次的位置：** 陷阱32（`calc_all()` 餵 30 天，`pos_250` 靜默變成
「近 30 日位置」）、陷阱51（`_build_market_signals()` 寫死 600）、
10/14（`build_cache()` 五處寫死 600）。
**這次是第四次，而且出現在「我自己剛寫的腳本的資料入口」**
——前三次都是「既有程式沒跟上回填」，這次是**新寫的程式沿用了一個會給錯預設值的 CLI**。
⇒ **寫任何依賴快取的腳本時，入口就要阻斷式檢查「這份快取涵蓋我需要的期間嗎」，
不能只檢查「檔案存在嗎」。**

#### ⚠️ 連帶的結構問題（已知，未改）：所有快取都在 `/tmp`

`CACHE`／`CACHE_MARKET`／`backtest_revenue_filter.CACHE` 全部指向 `/tmp/*.pkl`。
後果是**沙盒建的快取使用者拿不到、使用者建的沙盒也拿不到**，每次換環境都要重建
（全市場 2018~2026 約 20~40 分鐘）。
放 `/tmp` 本身是對的（100MB+ 的 pickle 不該進 git），
但**跨環境協作時要先講清楚「這份快取在誰的機器上」**，否則就是這次這種狀況。

#### ⭐ 方法論收穫（兩點，第一點是新的）

**(a) 修好一個壞掉的訊號之後，要回頭看它改變了哪些「分布型」的結論，不只數字。**
9/10 寫著「`≥70` 516 天只出現 15 天，實質上不存在」——那句話當時是對的，
**但它描述的是「S4 死掉時的 net 分布」，不是系統本身的性質。**
修好 S4 後 `≥70` 變成 9.1%。
⇒ **「某一檔實質上不存在」這類結論，必須在訊號修好後重新確認**，
因為它量的是分布，而分布正是壞掉的訊號最會扭曲的東西。

**(b) 提出機制假設之後要真的去測它，而且要接受被推翻。**
本次兩個假設（候選不足、65–69 帶 alpha）都是**合理且有前例**的
（前者是 10/14 真正量到過的機制），但**實測都不支持**。
⇒ 誠實的結論是「**方向穩定，但機制未知**」。
這比硬挑一個說得通的解釋寫上去要有用——下次有人想改這條規則時，
會知道「我們知道它偏負，但不知道為什麼」，而不是帶著一個假的因果去延伸。

---

### 組合層級：「最多持5檔 + 依最高分最高波動挑股」（2026-09-17 驗證，結論：**六組全在雜訊帶內，不採用**）

**要驗證的問題：** 使用者問「若採大盤應許進場，以**最高分最高波動**的持股購入 **5 檔**，相信系統而進場，結果會如何？」腳本：`backtest_portfolio_slots.py`（已進版控）。

**這句話包含三個互相獨立的元素，必須拆開測**，否則三者的效果會混在一起：

| 元素 | 先前狀態 |
|---|---|
| A 大盤評分階梯 | ✅ 已測（2026-09-10，維持現狀） |
| B **同時最多持 5 檔** | ❌ 沒測過——**正好就是「單日進場集中度」那則標著「尚未設計對策」的風險** |
| C **波動度當排序鍵** | 相關性測過（corr 0.053），但**當排序鍵沒測過**；已知高波動組勝率最低 |

**⚠️ 為什麼要另外寫腳本：`_run_backtest()` 是 per-stock 迴圈，結構上無法表達組合層級的限制。** 每檔股票各自跑完整條時間軸、各自持有，「同時最多 N 檔」需要在**同一個時間點**比較所有候選股。改成兩段式：第一段逐股逐日算評分與波動度存快取（最貴，74 檔約數分鐘）；第二段依日期重播、維護 ≤N 檔的組合。**日後任何組合層級的規則（部位數上限、資金配置、產業分散）都要用這支腳本的架構，不能硬塞進 `_run_backtest()`。**

| 規則 | 筆數 | 勝率 | 報酬 | 同期大盤 | **alpha** | 停損率 | 均波動 |
|---|---|---|---|---|---|---|---|
| A 基準：現行階梯，**不限檔數** | 243 | 54.3% | +5.50% | +3.05% | **+2.44%** | 16.5% | 3.14 |
| B 5檔・依評分高→低 | 82 | 58.5% | +5.17% | +3.79% | +1.38% | 18.3% | 2.90 |
| **C 5檔・評分高→低，同分波動高→低**（＝使用者提案） | 86 | 52.3% | +4.71% | +3.22% | **+1.49%** | 24.4% | 3.24 |
| D 5檔・純依波動高→低 | 94 | 53.2% | +5.59% | +2.83% | +2.76% | 26.6% | 3.81 |
| E 5檔・純依波動低→高（反向對照） | 88 | 48.9% | +3.75% | +3.13% | +0.62% | 14.8% | 2.34 |
| **★F 5檔・依股票代號（中性對照）** | 84 | 54.8% | +6.24% | +3.45% | **+2.79%** | 16.7% | 2.95 |

**第一個反直覺結果：中性對照 F（隨便挑）alpha 最高，比「挑最高分」的 B 高 1.41pp。** 照字面讀會得到「挑最高分反而有害」——但這個結論是錯的，見下。

**⚠️ 決定性的一步：先問「這些差距有沒有超過雜訊」。** 從基準組 243 筆隨機抽 85 筆、重抽 1000 次：

```
基準全體 alpha          +2.44%
隨機抽85筆的 alpha 分布   5%分位 +0.23%　中位 +2.39%　95%分位 +4.69%
                        → 光是抽樣雜訊就能造成 4.47pp 落差
六組實測 alpha 範圍       +0.62% ~ +2.79%（落差僅 2.17pp）
```

**整張對照表的全距（2.17pp）比抽樣雜訊的 90% 區間（4.47pp）還小——六組彼此無法區分。** 所以「F 最好」「B 較差」全是雜訊，不可解讀。

**獨立驗證（改用基準組 243 筆，樣本大一倍，直接看排序鍵有沒有預測力）：**

| 進場評分 | 筆數 | alpha | | 進場波動度 | 筆數 | alpha |
|---|---|---|---|---|---|---|
| 65–69 | 21 | **+6.12%** | | 最低 1/4 | 60 | -0.35% |
| 70–74 | 169 | +1.82% | | 次低 | 61 | +1.01% |
| 75–79 | 40 | +1.37% | | 次高 | 61 | **+6.21%** |
| ≥80 | 13 | **+7.90%** | | 最高 1/4 | 61 | +2.84% |

**兩邊都非單調**（評分是兩端高中間低、波動是次高組最好）。這證實了：

1. **評分在已達標的樣本內，高低不預測報酬。** 「挑最高分」等於用一個沒有鑑別度的鍵去排序。
2. **波動度當排序鍵同樣無效**，與 404 筆那次「corr(vol, 損益)=0.053」一致，這次換個角度再次確認。

> **⚠️ 本節第 1 點原本寫「65 分這條線有效（已驗證多次）」——那句話是錯的，當天稍後就被推翻，見下一節「65 分門檻本身從來沒有被驗證過」。**
> 寫的當下以為門檻驗過、只有排名沒驗過，但回查記錄後發現**專案從來沒有測過「達標 vs 沒達標」**。這是一個因為「熟悉而誤以為驗證過」的例子。

**「5 檔上限」本身：alpha +0.35pp（F 2.79% vs A 2.44%），但進場機會少 65%（84 vs 243 筆）——同樣在雜訊範圍內。**

**但均值看不見的那件事，才是這次真正有價值的發現：**

| | 單日進場中位數 | 單日最大 | 最傷的一批（≥3檔） |
|---|---|---|---|
| A 不限檔數 | 2 檔 | **7 檔** | 2026-06-02 共 3 檔，**平均 -10.00%（全數停損）** |
| F 5檔上限 | 1 檔 | 5 檔 | 2025-08-11 共 4 檔，平均 **+2.99%** |

**5 檔上限確實壓掉了「整批一起進場、整批一起受傷」的尾部風險**——那正是 2026-08-14 單日 15 檔、整批 -4.28% 的那個病。它換到的不是更高的期望值（alpha 沒差），而是**更窄的結果分布**。

**結論：不改規則，但理由與前幾次不同。** 前幾次（移動停損、策略F、ER過濾）是「實測明確變差」；這次是**「六組根本分不出來」**——在無法區分的情況下，預設應該是**維持現狀**，因為現行規則的進場機會多 3 倍，而少掉的 65% 交易換不到可辨識的 alpha 改善。

**⚠️ 但「5 檔上限」與其他五組不同，不該直接歸檔。** 它的價值在**降低尾部風險**而非提高期望值，而本專案的統計方式（看均值 alpha）天生看不見這一點。真要評估它，需要換指標（最大回撤、批次最差表現、報酬分布的離散度），那是另一次驗證的題目。**目前的定位：已知有效果、但效果不在現有的評估框架內，暫不納入規則。**

**方法論收穫（三點）：**

1. **⭐ 比較多組規則之前，先算「雜訊帶有多寬」。** 做法很簡單：從基準組**重抽**與各組同樣筆數的子集數百次，看 alpha 的 5–95% 分位。**若各組的全距比雜訊帶窄，整張表就不必解讀了。** 這次若少了這一步，會從 F 比 B 高 1.41pp 得出「挑最高分有害」這個完全錯誤的結論。**這一步應該成為日後所有多組對照的標準前置動作**——它跟「必須設無條件基準」「必須看 alpha」是同一族的防護，差別在前兩者防的是「量尺選錯」，這一則防的是「把雜訊當訊號」。
2. **「門檻」與「排名」是兩回事，不可混用。** 一個變數能當有效的**過濾門檻**，完全不代表它能當有效的**排序鍵**。評分就是最好的例子：65 分這條線驗證過有效，但跨過線之後的高低完全不預測報酬。日後看到「用某個既有指標來挑最好的 N 個」這類提案，要先單獨檢查「該指標在已過濾的樣本內，與報酬是否單調相關」。
3. **組合層級的規則需要組合層級的回測架構。** per-stock 迴圈永遠測不出「同時持 N 檔」「資金分配」「產業分散」這類限制，因為它們的本質是**在同一時點的競爭關係**。

### 65 分門檻本身從來沒有被驗證過（2026-09-17，**最重要的一次發現**）

**起因：** 使用者讀完上一節後問「**也就是說，個股評分的高低並不代表跟結果有一致性的走向，是吧？**」——為了精確回答而去查「門檻本身驗過沒有」，結果發現**沒有**。

**回查專案全部記錄，門檻 65 的驗證狀況：**

| 比較過什麼 | 有沒有做過 |
|---|---|
| 65 vs 70 vs 75（**全都在門檻之上**） | ✅ 做過（十五章 Q2、停損校準同批） |
| 策略 A/B/C/D、持有天數、停損距離、移動停損… | ✅ 都做過，但**全部固定用 65** |
| **≥65 vs ＜65（達標 vs 沒達標）** | ❌ **從來沒做過** |

**整套策略最核心的那條線，是唯一沒被檢驗過的。** 所有回測都把 65 當前提，在前提之上比較其他參數。

**實測（用組合層級腳本的快取，只換「收哪一段評分」，大盤規則完全不動）：**

| 進場評分區間 | 筆數 | 報酬 | 同期大盤 | **alpha** | 勝率 |
|---|---|---|---|---|---|
| ＜40（極低） | 292 | +3.54% | +1.87% | **+1.67%** | 53.8% |
| 40–49 | 699 | +4.18% | +2.62% | +1.56% | 53.5% |
| 50–59 | 824 | +4.80% | +2.60% | **+2.20%** | 49.8% |
| 60–64（差一點） | 652 | +3.34% | +2.40% | +0.94% | 50.5% |
| **≥65（現行門檻）** | 528 | +4.65% | +2.99% | **+1.66%** | 48.3% |

**`≥65` 的 alpha（+1.66%）與 `＜40`（+1.67%）幾乎完全相同，還低於 `50–59`（+2.20%）。而且勝率是五組裡最低的。**

**⚠️ 但照本章剛立的規矩，先算雜訊帶再解讀（用基準組重抽估計）：**

| 樣本數 | alpha 的 5–95% 分位 | 帶寬 |
|---|---|---|
| n=85 | +0.25% ~ +4.62% | 4.37pp |
| n=300 | +1.08% ~ +4.03% | 2.95pp |
| **n=500** | **+1.38% ~ +3.65%** | **2.27pp** |
| n=800 | +1.50% ~ +3.27% | 1.77pp |

**五個區間的 alpha 全距是 1.26pp，各組 n 介於 292~824 → 雜訊帶寬約 1.8~2.9pp。全距仍然小於雜訊帶。**

**所以正確的結論不是「門檻無效」，而是——**

> **這個測試的解析度不足以驗證門檻。** 若 65 分門檻有 **>2pp** 的 alpha 效果，這個測試看得到；結果沒看到。**因此門檻的效果（若存在）小於 2pp**，遠小於原本預設的「這是整套策略的核心假設」那種份量。

**⚠️ 這句話要非常小心，兩個方向都不能過度延伸：**
- **不能說「評分沒用、可以拿掉」**——沒測到差異 ≠ 證明沒有差異。
- **也不能繼續說「65 分驗證過」**——那是今天之前一直在用、但從來沒有根據的說法。

**四個結構性限制（都會壓縮門檻的可見效果，必須一起講）：**

1. **樣本全在大多頭**（2025-09~2026-09，指數期間大漲）。多頭市場裡低分股照樣漲，任何「挑好股」的機制在這種環境都難以顯出差距——這與「必須看 alpha」那則是同一個病根的延伸：alpha 扣掉了大盤，但沒扣掉「多頭讓爛股也能漲」這個效應。
2. **各區間是不同的交易集合，有狀態依賴**（同一檔被某區間持有就不會出現在別的區間），跨組比較本來就不嚴謹——與十五章 Q3 那三條限制同一性質。
3. **只測「單一區間」，沒測「排除低分」的組合效果**。實務上不會只買 50–59，而是「排除 <65」。要測那個需要另一種設計。
4. **評分是三面加權合成的**（技術40%／籌碼35%／基本面25%）。合成分數沒有鑑別度，不代表個別分項也沒有——**下一步應該拆開測分項**，那比繼續測總分有意義。

**目前處置：不動任何規則。** 理由與上一節相同——在無法區分的情況下維持現狀。但**這一則的定位與其他驗證完全不同**：其他是「提案被否決」，這一則是**「既有的核心假設被發現從未驗證，且初步測試沒能支持它」**。這是待辦，不是結案。

**⚠️ 日後引用「評分門檻」時的說法必須改變：**
- ❌ 不可再寫「65 分門檻已驗證有效」
- ✅ 正確說法：「65 分門檻是設計時選定的，2026-09-17 首次嘗試驗證，**在現有樣本（全多頭、n≈500/組）下無法檢出效果**，效果上限約 2pp alpha」

**方法論收穫（本專案至今最重要的一條）：**

> **⭐ 越是「大家都預設成立」的前提，越可能從來沒被驗證過。**
>
> 本專案對周邊參數的驗證極其嚴謹——停損距離掃描六個值、移動停損測三種幅度、confirm_days 測五個、大盤階梯做了 Q1/Q2/Q3 三輪——**但那些全都建立在「65 分門檻有效」這個從未檢驗的地基上**。原因很直覺：門檻是最早定下來的，之後每一次驗證都把它當常數，久了就被當成「驗證過的東西」。
>
> **檢查方法：列出所有回測的「固定不變的參數」，那些才是最可疑的。** 會被反覆測試的參數，恰恰是大家已經在懷疑的；從來沒進過對照組的參數，才是真正的盲區。

### 🚨 回測期間有一半以上的日子，評分只有技術面在作用（2026-09-17，**本專案最嚴重的發現**）

**起因：** 上一節結尾說「總分沒鑑別度不代表分項也沒有，下一步應該拆開測分項」。拆開之後，**分項測試本身的結果不重要，因為在測的過程中發現回測資料根本不支援這件事。**

**第一個異常訊號：** 基本面 40–54 那一格跑出 **alpha +35.38%**（n=135）。這種數字必然是假的，所以先查分項的實際分布，而不是報出去：

| 分項 | 權重 | 25%分位 | 中位 | 75%分位 | 最常出現的值 |
|---|---|---|---|---|---|
| 技術面 | 40% | 45 | 65 | 82 | 分散 |
| **籌碼面** | **35%** | **50** | **50** | **50** | **50 分 × 9,593（佔 61%）** |
| **基本面** | **25%** | **50** | **50** | **50** | **50 分 × 10,292（佔 65%）** |

**`score = 50` 是 `scorer.py` 裡兩個分項函式的起始值**（`score_chips()` 開頭 `score = 50` 且 `if not chips_list: return score`；`score_fundamental()` 同樣從 50 起算，PE/PB/殖利率/EPS 全缺就原封不動回傳）。**大量精準落在 50 = 那些日子根本沒有資料。**

**根本原因：那兩張表的歷史資料遠比價格短。**

| 表 | 自選股的資料起點 |
|---|---|
| `prices` | 2017 起（回測用 600 日） |
| **`chips`** | **87 檔中 68 檔最早只到 2026-02；17 檔（全部上櫃股）完全沒有** |
| **`fundamentals`** | **全部 87 檔都從 2026-05 才開始** |

**量化（回測評分區間 2025-07-10 ~ 2026-09-16，291 個交易日）：**

| 分項 | 有真實資料的天數 | 佔比 | **只有預設值 50** |
|---|---|---|---|
| 技術面（40%） | 291 | 100% | 0% |
| **籌碼面（35%）** | 151 | 52% | **48%** |
| **基本面（25%）** | 82 | 28% | **72%** |

**⇒ 只有最後 82 天（28%）三項齊全，與線上實際運作的評分同構。**

**⚠️ 後果：同一個「65 分門檻」，在回測的前後兩段是完全不同的篩選器。**

前段（籌碼與基本面都是 50）時，總分退化成技術面的線性函數：

```
總分 = 0.40×技術 + 0.35×50 + 0.25×50 = 0.40×技術 + 30
→ 要達到總分 65，技術面必須 ≥ (65−30)/0.40 = 87.5 分
```

**實測完全吻合：**

| 達到總分 ≥65 的評分點 | 筆數 | 技術面中位數 | 技術面**最低** |
|---|---|---|---|
| 前段（<2026-04） | 1,510 | **95** | **87** |
| 後段（≥2026-04） | 1,799 | 85 | **32** |

**前段只有技術面近乎滿分（≥87）的股票進得去；後段技術面 32 分的也能靠籌碼＋基本面補進來。** 這是兩套完全不同的系統，被當成同一套在統計。

**這解釋了上一節那個「65 分門檻測不出效果」的結果**——不是門檻無效，而是**「65 分」在樣本的不同時期指的不是同一件事**，混在一起自然抵銷成雜訊。上一節的結論要再補一層限制：那個測試不只受多頭樣本影響，**它測的對象本身就不是一個穩定的東西**。

**⚠️ 這件事對「線上系統」與「回測」的影響完全不同，不可混為一談：**

| | 受影響嗎 |
|---|---|
| **線上每日評分**（你實際看到的分數） | ❌ **不受影響**。今天三項資料都在，評分是完整的 |
| **所有回測結論** | ✅ **全部受影響**。十五章每一節的數字，都混合了「只有技術面」與「三項齊全」兩種期間 |
| 個股頁的評分歷史走勢圖（回溯 90 日） | ⚠️ 2026-05 之前的點同樣是「技術面 +30」，不是完整評分 |

**能不能補救：**

| 分項 | 能否回補歷史 | 依據 |
|---|---|---|
| 籌碼面 | **可以**（上市股）——T86 的 `date` 參數實測有效（陷阱41 已驗證） | 上櫃股永遠沒有（T86 不含上櫃） |
| **基本面** | **❌ 不行** | BWIBBU_ALL 的 `date` 參數無效（陷阱44 實測），只拿得到最新一份報表 |

**所以基本面這一項（25% 權重）永遠無法用超過 2026-05 之前的資料驗證。** 這是結構性限制，不是待辦。

**目前處置：只記錄，不動任何規則、不動評分邏輯。** 但這一則改變了**所有既有回測結論的可信度層級**：

> **⚠️ 引用十五章任何回測數字時，都要附上這條限制：該數字的樣本期間有 48%～72% 的日子，評分系統實際上只有技術面在運作。** 這不會讓那些結論變成錯的，但會讓它們的意義從「驗證了三面加權的評分系統」降為「大致驗證了技術面為主的評分系統」。

**下一步該做什麼（依價值排序，都還沒做）：**

1. **回補上市股的籌碼歷史**（T86 date 參數有效），把籌碼面的可驗證區間從 52% 拉高。成本：87 檔 × 數百天的 API 呼叫。
2. **所有回測加一個「僅用三項齊全期間」的子集對照**——那 82 天筆數太少，但至少能看出方向是否一致。
3. **重新檢視 `scorer.py` 用 50 當「無資料」預設值這個設計。** 目前「資料缺失」與「資料顯示中性」得到完全相同的分數，外部無法區分。**更安全的做法是資料缺失時回傳 `None`，由呼叫端決定要不要計分**（與陷阱43 的「找不到對應日期就不計分」同一個原則）。但這會改動評分邏輯，必須先評估對線上的影響。

### ✅ 籌碼歷史已補齊（2026-09-17 當日完成）＋ 補完後重驗的結果

**執行：** `backfill_chips_history.py`（已進版控，預設試跑，`--apply` 才寫入）。T86 是「一天一個請求拿全市場」，不是逐股抓——**159 個交易日只花約 5 分鐘**，與原先「87 檔 × 數百天」的直覺差了兩個數量級。

**實際結果（使用者本機執行，一次成功）：**

```
補齊 159 天　查無資料 0 天　日期不符 0 天　失敗 0 天
重算後仍缺 0 天 ✅
自選股籌碼涵蓋：上市 70 檔有資料；上櫃 17 檔永遠沒有（T86 不含上櫃）
```

**補完前後的分項分布：**

| 分項 | 權重 | 補之前最常出現 | **補之後** | 25%／中位／75% |
|---|---|---|---|---|
| 技術面 | 40% | 分散 | 分散 | 45／65／82 |
| **籌碼面** | **35%** | **50分 × 61%** | **50分 × 30%** | **45／50／62** ✅ |
| 基本面 | 25% | 50分 × 65% | 50分 × 65% | 50／50／50 ❌ 補不回來 |

**⇒ 現在「技術40% + 籌碼35% = 75% 的權重」在全期 292 個交易日都有真實資料**（補之前籌碼只有 48% 的日子）。基本面那 25% 維持原狀，只有 28% 的日子有資料。

**⚠️ 補完後重跑「≥65 vs ＜65」——結論不但沒變，差距反而縮小：**

| 進場評分 | 筆數 | 報酬 | 同期大盤 | **alpha** | 勝率 | （補之前 alpha） |
|---|---|---|---|---|---|---|
| ＜40 | 319 | +3.19% | +2.14% | +1.05% | 53.6% | +1.67% |
| 40–49 | 680 | +4.13% | +2.50% | +1.63% | 53.2% | +1.56% |
| **50–59** | 803 | +4.19% | +2.35% | **+1.84%** | 50.2% | +2.20% |
| 60–64 | 648 | +3.86% | +2.42% | +1.45% | 51.9% | +0.94% |
| **≥65（現行門檻）** | 542 | +4.92% | +3.19% | **+1.74%** | **45.4%** | +1.66% |

```
五組 alpha 全距   0.79pp   （補之前 1.26pp）
n=500 雜訊帶寬    2.76pp
→ 仍在雜訊帶內，分不出來
```

**這次的意義與上一節完全不同——「資料不完整」這個解釋已經被排除了 75%。**

上一節說「測不出效果可能是因為回測期間一半以上只有技術面在跑」。現在籌碼那 35% 補滿了，**結論不變，而且五組更靠近**。所以：

- ❌ **不能再用「資料不夠」解釋** ——至少對 75% 的權重而言不能
- ⚠️ **仍然不能說「門檻無效」** ——雜訊帶 2.76pp 代表這個測試只看得見 >2.76pp 的效果；真有 1pp 的效果依然是隱形的
- ✅ **正確說法：補完籌碼歷史後重驗，65 分門檻在現有樣本下仍無法檢出效果，且五組差距比補之前更小**

**一個值得留意但還不能下結論的型態：`≥65` 的勝率兩次都是五組最低**（補之前 48.3%、補之後 **45.4%**），而 `＜40` 兩次都最高（53.8%／53.6%）。五組勝率全距 8.2pp，n≈500~800 的二項式標準誤約 2.2pp——**大約 2~3 個標準誤，處在「可能有東西、但還不夠硬」的邊界**。不可據此宣稱「分數越高越差」，但**下次擴大樣本時應該特別盯這一欄**。

**仍然存在的三個限制（與上一節相同，沒有因為補資料而消失）：**

1. 樣本全在大多頭
2. 各區間是不同的交易集合，有狀態依賴
3. 基本面 25% 仍是預設值（永久）

**下一步唯一能把雜訊帶壓下來的方法，是擴大標的數、不是等時間。** 實測數據：

| | |
|---|---|
| 現行規則的交易產生速度 | **每個交易日 0.47 筆**（每月約 9 筆） |
| 要把雜訊帶壓到 1.5pp | 需 1,145 筆 → **還要 8.1 年** |
| 要壓到 1.0pp | 需 2,576 筆 → **還要 20.9 年** |

**等時間這條路走不通。** 但樣本數 = 時間 × 標的數，而目前回測只跑 74 檔自選股——`prices`／`chips`／`fundamentals` 三張表本來就存全市場。**標的數 ×7 → 筆數約 1,700，立刻跨過「分辨 1.5pp」的門檻。** 而且對「評分能不能挑出好股」這個問題，用全市場比用自選股更對：自選股是已經精選過的，等於在一群好學生裡面比。

**方法論收穫（兩點，都很重要）：**

1. **⭐ 看到離譜的好數字（本例 alpha +35%），第一反應要是「去查資料」而不是「報出去」。** 這次若直接把分項表格交出去，會變成「基本面 40–54 分是甜蜜點」這種完全錯誤、而且聽起來很像真的結論。**離譜的數字幾乎永遠是資料問題，不是發現。**
2. **⭐ 驗證一個「合成指標」之前，先看它每個成分的分布。** 一個成分若大量精準落在單一數值（本例 50），那幾乎一定是預設值／缺資料，而不是真實訊號。**檢查方法極便宜：印出 25%／中位／75% 分位，若三者相同就是警訊。** 本專案對「資料缺漏」已有完整的監控（十九章），但那套只檢查「該有的日期有沒有資料列」，**完全看不到「有資料列、但欄位是預設值」這種缺法**——這是監控的第三個盲區（前兩個是缺漏日與重複日）。

### 大盤評分加上無條件基準之後是輸的（2026-09-23，**推翻既有說法**）

**起因：** 使用者說「大盤評分看起來預估的準確度還高，但個股評分近數月感覺敏感度不足」。
為了精確回答而去補做一直沒做的基準對照——結果**前半句是反的**。

**做法：** 用 `_build_market_signals()` 取 S1–S8 的逐日 net（525 天），
對照 TAIEX 隔日漲跌。`net<0`＝預測漲、`net>0`＝預測跌、`net=0` 不計。

| 全期間 524 天 | n | 準確率 | vs 基準 |
|---|---|---|---|
| **★ 基準：每天都猜漲** | 524 | **55.9%** | — |
| 全部訊號 | 404 | 52.7% | **-3.2pp** |
| 強訊號 \|net\|≥3 | 67 | **47.8%** | **-8.2pp** |

**訊號越強、越不準。** 分期間：2025 全年 -3.4pp、2026H1 **-11.9pp**、近三個月 +3.1pp（n=58，雜訊）。

**拆多空看則各自略優於自己的基準，但都在一個標準誤內：**

| | n | 準確率 | 各自基準 | 差 | 標準誤 |
|---|---|---|---|---|---|
| 喊偏多 → 隔日漲 | 216 | 58.8% | 55.9% | +2.9pp | ±3.4pp |
| 喊偏空 → 隔日跌 | 188 | 45.7% | 44.1% | +1.7pp | ±3.6pp |

合起來卻輸給「每天猜漲」——因為**多頭市場裡它常喊偏空，而喊偏空在上漲的大環境本身就是扣分的**。

**⚠️ 這推翻了九章那個警語框裡「評分的方向驗過」的說法。** 那句話之所以站得住，
純粹是因為 51.4% / 59.5% 這兩個數字從來沒有旁邊那一欄可比。

**⭐ 方法論（第三次應驗同一條）：** 「必須設無條件基準」在 2026-09-01 測「先殺後拉」時就立過
（當時發現基準 55.9%、訊號 50%），**但沒有回頭套用到既有的 `backtest.py` 上**。
**立下一條新規矩時，要順手檢查它推翻了哪些舊結論**——否則新規矩只約束新工作，
舊數字繼續以「已驗證」的身分被引用。

---

### 個股評分是後照鏡，不是預警器（2026-09-23）

**要驗證的問題：** 把「敏感度不足」翻成可測的東西——
**評分的變化，跟哪一段時間的價格最相關？** 用組合層級快取的逐日評分，
算 `corr(近5日評分變化, 各種時間窗的報酬)`。

| 相關的時間窗 | 全期 | 近數月 |
|---|---|---|
| 過去 10 日 | -0.13 | -0.11 |
| **過去 2~4 日** | **+0.24 ~ +0.19** ← 峰值 | **+0.27 ~ +0.20** |
| 當下（過去5日） | +0.18 | +0.22 |
| **未來 2 日** | +0.04 | +0.07 |
| **未來 5 日** | **0.00** | **-0.01** |
| **未來 10 日** | **0.00** | +0.02 |

n≈15,700（全期）／5,550（近數月）。**峰值落在「過去」，未來全部是零，而且它還落後價格約 2 天。**

**直接的預警測試（更白話）：**

| | 事前 5 日評分已掉 ≥5 分的比例 |
|---|---|
| 未來 10 日大跌 ≥8% 的個案（2,000 次） | 34.8% |
| 沒大跌的個案（13,027 次） | **34.7%** |

亮燈時真的大跌的機率 **13.3%**，而不看訊號的無條件大跌率也是 **13.3%**——**零資訊**。

**這是三個既有結論的共同病因：**

| 何時 | 症狀 |
|---|---|
| 2026-09-17 | 分數高低不預測報酬（五組 alpha 全在雜訊帶內）|
| 2026-08-20 | 策略F：評分衰退就出場，扣成本後由賺轉賠（851 筆）|
| **2026-09-23** | **病因：評分變化與未來報酬 corr = 0，與過去 = +0.25** |

**為什麼必然如此——看組成就知道：** 技術面 40% 是價格的函數、籌碼面 35% 是昨天的成交結果、
基本面 25% 落後 1~3 個月。**100% 的輸入都是已經發生的事。**
所以「讓它更敏感」只會讓你更頻繁地對著已經過去的路況踩煞車，每踩一次付 0.47% 來回成本。

**⚠️ 這一則不改變任何規則，但它改變「該對評分有什麼期待」：**
評分是**描述器**，不是**預測器**。UI 上任何暗示它能預警的文字都要重新檢查（陷阱48 的延伸）。

---

### 🚨 全市場擴充：雜訊帶終於壓下來，但揭穿了自選股回測的倖存者偏誤（2026-09-24）

**動機：** 前面三次驗證（65 分門檻、大盤階梯、評分領先性）全部卡在同一件事——
**n=243、雜訊帶 2.76pp，分不出是效果還是運氣**。時間那一維走不通
（實測 0.47 筆/交易日，要壓到 1.5pp 還要 8.1 年），所以放大標的數。

**前置：`backfill_prices_history.py`（已進版控）。** 動手前先查，發現
**全市場價格只有近 87 個交易日**（其餘 299 天只有自選股那 58 檔）——
籌碼 9/17 已補成全市場，卡住的是價格。而 `MI_INDEX?date=` 同樣是
「一天一個請求拿全市場」，**439 個交易日約 15 分鐘、56 萬列，一次成功零失敗**。

補到 **2024-07-29**（不是 chips 起點 2025-07）是刻意的：`pos_250`/`ma240` 需要 250 日暖身，
否則全市場新股的技術面會靜默退化（陷阱32），重演「同一個 65 分在不同子樣本指不同東西」。

**宇宙定義（`market_universe()`）：** 上市普通股（T86 不含上櫃）＋ 4 碼數字非 `00` 開頭
（排除 ETF／權證／特別股）＋ 日均成交金額 ≥ 0.5 億（冷門股的回測成交價不現實）
→ **510 檔**，全部都有 ownership 與籌碼資料（無混基準問題）。

**成果一：解析度提高了 4.6 倍。**

| | 2026-09-17（自選股 74 檔） | **2026-09-24（全市場 510 檔）** |
|---|---|---|
| 基準組筆數 | 243 | **3,450** |
| 雜訊帶（n≈500 / n≈5,600） | 2.76pp | **0.60pp** |

**成果二：65 分門檻的效果上限從 2pp 降到 0.6pp（仍測不出來）。**

| 進場評分 | 筆數 | 報酬 | 同期大盤 | **alpha** | 勝率 |
|---|---|---|---|---|---|
| ＜40 | 5,643 | +1.04% | +1.73% | **-0.70%** | 45.6% |
| 40–49 | 11,401 | +1.42% | +1.86% | -0.44% | 44.8% |
| 50–59 | 12,570 | +1.70% | +2.04% | -0.34% | 44.6% |
| 60–64 | 8,247 | +1.74% | +2.17% | -0.42% | 43.2% |
| **≥65（現行門檻）** | 6,660 | +1.87% | +2.19% | **-0.32%** | **41.8%** |

五組 alpha 全距 **0.37pp** ＜ 雜訊帶 **0.60pp** → 仍無法區分。
但**「效果上限」這個說法比以前緊得多**：若門檻有 >0.6pp 的 alpha 效果，現在看得見；沒看到。

**成果三：兩件終於被檢出來的事。**

**(a) 評分高 ＝ 吃到更多 beta，不是更多 alpha。**
「同期大盤」那一欄隨評分**單調上升**（+1.73% → +2.19%），而 alpha 完全不動。
意思是：高分股的進場時點，剛好是市場本身也在漲的時候——
**這正是「評分是後照鏡」的直接後果**（分數高＝最近漲過＝市場最近也在漲）。
評分實際在調節的是**你的市場曝險程度**，不是選股品質。

**(b) 勝率隨評分單調下降，而且這次超出雜訊。**
45.6% → 44.8% → 44.6% → 43.2% → **41.8%**，五段全單調。
`＜40` 與 `≥65` 差 **3.8pp**，差值標準誤 √(0.7²+0.6²)=0.92pp → **約 4.1 個標準誤**。
（2026-09-17 兩次分別是 48.3%、45.4% 最低，這是**第三次**，現在終於硬了。）
與 (a) 併起來解釋得通：**高分＝強勢股，較常回檔（勝率低），但續漲時漲幅大**，
淨結果 alpha 不變。⚠️ 但各組是不同交易集合、有狀態依賴，標準誤是低估的。

**🚨 成果四（本節最重要，也最不舒服）：所有標著「alpha +1.8% ~ +2.4%」的回測數字，
都是在一份「事後才組成的股票清單」上量出來的。**

全市場 510 檔、同一套規則，基準組 **alpha -0.32%**（n=3,450）。
而 2026-09-17 在自選股上量到的是 **+2.44%**（n=243）。差 **2.76pp**，遠大於兩者的雜訊帶。

去查 `watchlist.added_at` 才發現原因：

```
2026-05  13 檔    2026-06  43 檔    2026-07  22 檔    2026-08   9 檔
→ 87/87 檔（100%）都是在 2026-05 之後才加入的
→ 而回測期間從 2024-07-29 開始
```

**清單是「現在」的，回測期是「過去」的。** 一檔股票之所以會被加進自選股，
往往正是因為它已經表現不錯——把今天的清單套回兩年前，等於**先看答案再考試**。
`1303 南亞` 近四個月 +174% 就是典型：它是因為漲了才進清單，不是進清單後才漲。

**所以：**
- ❌ **不可再引用自選股回測的 alpha 當「策略有效」的證據** ——
  十五章絕大多數數字（策略 A/B/C/D、停損校準的 +2.06%、階梯的 +2.33%、組合層級的 +2.44%）都受影響。
- ✅ **全市場的 -0.32% 才是對「規則本身」比較公正的估計。** 扣掉 0.47% 來回成本後，
  這套規則在全市場上的期望值是**明確落後於單純持有指數**的。
- ⚠️ **但不能因此說「使用者的選股沒有價值」** —— 選股技巧與後見之明在這份資料上**無法區分**，
  因為清單全部成形於回測期之後。要驗證選股能力，只能**從今天起**記錄「加入清單的當下」
  並往前看，那是未來的事，不是回測能回答的。

**⭐ 方法論（本專案至今最重要的第二條，與「越是預設成立的前提越可能沒被驗證」並列）：**

> **回測宇宙的「組成時間」必須早於回測期間的起點。**
> 這件事在專案裡從頭到尾沒有人問過——因為 `get_watchlist()` 用起來太自然，
> 而「自選股」聽起來像一個中立的標的清單。**它不是，它是一份結果。**
>
> **檢查方法極便宜：** 比對「標的清單的建立時間」與「回測期間的起點」。
> 前者晚於後者，那份回測就含有後見之明，幅度未知但可能很大（本例 2.76pp，
> 比專案過去所有參數調整的效果加起來都大）。

**仍然存在的限制（沒有因為擴大標的而消失）：**
1. 樣本期間仍**全在多頭**（2024-07~2026-09 指數大漲）
2. **基本面 25% 在 2026-05 之前仍是預設值 50**（BWIBBU date 參數無效，陷阱44，永久）
3. 各評分區間是不同的交易集合，有狀態依賴
4. 只有上市股；上櫃（含 17 檔自選股）無籌碼資料，不在宇宙內

**腳本：** `backfill_prices_history.py`（回填價格）、
`backtest_portfolio_slots.py cache market`（建全市場快取，約 13 分鐘）、
`backtest_score_bands.py market`（分段測試＋雜訊帶，已把 bootstrap 的算法固定下來）。

---

### 策略 vs 買進持有 ETF：第一次用資金曲線比（2026-10-05/06）

**起因：** 使用者問「這幾個月選股一直不順，指數漲卻選不到合適股，是不是直接買 ETF 效果好？」

**⚠️ 這個問題之前無法回答，因為既有回測全部是 per-trade alpha——那個指標看不到最關鍵的一塊：空手時間。**
在一個指數大漲的期間，沒進場的日子是巨大的機會成本，但 per-trade alpha 只比較
「有進場的那幾天 vs 同期指數」。**「策略 vs 買進持有」必須用資金曲線比。**
腳本：`backtest_vs_etf.py`（已進版控）。

#### 資金模型（不講清楚數字就沒有意義）

**N 格等權 + 現金不計息**：資本切 N 格、每格 1/N（每日再平衡）、空格是現金報酬 0、
成本逐筆扣在進出場當天（買 0.0855%／賣 0.3855%）。

**⚠️ 刻意不跑「不限檔數」的基準組（A）**——它**沒有可定義的資金模型**
（同一天可能持 1 檔也可能持 7 檔，每檔該押多少無從決定）。
per-trade alpha 可以不管這件事，**資金曲線不行**。

#### 結果（513 檔全市場宇宙、2024-07-29~2026-10-05）

**⚠️ 必須分段看。2026-05 是分界線**（`fundamentals` 全部從 2026-05 才開始），
之前的評分實質上只有技術面——混在一起等於把兩套系統當成一套。

| 前段 2024-07~2026-04（425 天） | 報酬 | 最大回檔 | 在場內 |
|---|---|---|---|
| 策略 5檔（評分） | +19.00% | -27.16% | 69% |
| 買進持有 0050 | **+100.27%** | -28.47% | 100% |
| 買進持有 0056 | +6.36% | -26.72% | 100% |
| 加權指數 | +75.63% | -26.71% | — |
| ★ 隨機 5 檔中位（20條） | **+27.47%** | — | — |
| 　└ 5~95% 分位 | **-8.78% ~ +134.44%（帶寬 143.2pp）** | | |

| ★ 2026-05 起（107 天，＝現在的系統） | 報酬 | 最大回檔 | 報酬/回檔 |
|---|---|---|---|
| **策略 5檔（評分）** | **+29.80%** | **-9.59%** | **3.11** |
| 策略 5檔（代號）⚠️有產業偏誤 | +13.83% | **-9.27%** | 1.49 |
| 策略 10檔（評分） | +23.57% | -11.73% | 2.01 |
| 買進持有 0050 | +28.12% | -15.88% | 1.77 |
| 買進持有 0056 | **+41.44%** | -14.36% | 2.89 |
| 加權指數 | +27.71% | -16.36% | 1.69 |
| ★ 隨機 5 檔中位（20條） | +16.01% | — | — |
| 　└ 5~95% 分位 | **-3.73% ~ +37.06%（帶寬 40.8pp）** | | |

近 3 個月（63 天）：策略 **+7.56%**／-4.93%、0050 +7.01%／-13.71%、0056 +9.46%、
加權 +6.27%、隨機中位 -7.29%（5~95%：-16.87% ~ **+3.19%**，帶寬 20.1pp）。

#### 四個結論

**① 報酬：評分排序沒有通過雜訊檢定。**
全期間與前段**輸給隨機中位數**（54.45 vs 59.91；19.00 vs 27.47）；
2026-05 起與近 6 個月高於中位但**仍在 95% 分位內**；
只有近 3 個月超出帶外（+7.56% ＞ +3.19%），而那是最短、最不可靠的區間。

**② 回檔：策略穩定小很多，而且這一項不依賴選股。**
決定性證據是「代號」那條——**報酬只有一半，但回檔一樣小**（-9.27% vs -9.59%）。
⇒ 小回檔來自**結構**（10% 停損 ＋ 10 日週期 ＋ 5 檔上限 ＋ 部分時間空手），不是評分。
~~**這是整個系統目前最站得住腳的一項性質。**~~

> **❌ 這句話 2026-10-07 被推翻，見本章末「用空頭樣本拆解『結構』」。**
> 回填 2018 後用**同持股數的配對對照**（同樣 5 檔、同樣隨機排序、**同一個 seed**，
> 唯一差異是有沒有停損和換股）重測 8 年：**Δ|回檔| +0.43%、10/20、p=1.000
> ——完全檢不出差異。** 8 年最大回檔：有結構 47.4%、**什麼都不做 45.6%**、0050 36.4%。
>
> 本次之所以看起來成立，有兩個原因：(a) **107 天、一條曲線**；
> (b) 比較對象是 0050，即**拿 5 檔等權去比 50 檔市值加權**，不是同一件事。
> **真正有回檔保護的是「空手」，而且必須是「出清」而非只「停買」。**

**③ 歸因：「指數漲卻賺不到」一大半是結構，不是選股技巧。**

| | 市值加權指數 | 2330 台積電 | **513 檔等權平均** |
|---|---|---|---|
| 前段 | +75.63% | +126.17% | **+36.78%** |
| 2026-05 起 | +27.71% | +20.61% | **+20.96%** |
| 近 3 個月 | +6.27% | +5.32% | **-0.78%** |

**「平均一檔股票」的漲幅一直遠低於指數**（前段差 39pp）。
持 5 檔等權，對手是「台積電佔約 57% 權重」的 0050——**這個結構差距兩段都存在**。
策略 2026-05 起 +29.80% 其實**贏過等權基準 8.8pp**（克服了這個劣勢），但仍在雜訊帶內。

**④「買 ETF」不是免選擇，而且代價更大。**
0050 vs 0056：前段 +100.27% vs +6.36%（**差 94pp**），2026-05 起反過來 +28.12% vs +41.44%。
**選錯 ETF 的差距遠大於「策略 vs ETF」的差距。**

#### 兩個洞（引用上表時必須一起講）

1. **樣本裡完全沒有空頭**（2024-07~2026-10 指數 +124%）。而「回檔小」這項優勢
   **真正重要的時候正是空頭**——偏偏那是唯一沒有資料的環境。該優勢目前是推論，不是實測。
   → **2026-10-07 補上空頭樣本後實測：檢不出來**（見本章末）。這個「洞」是真的洞。
2. **買進持有未計股利。** 0056 近一年殖利率約 7~8%，**真實報酬比上表更高**；
   這是對買進持有不利地低估。

#### ⭐ 方法論收穫（三條，都是新的）

**(a) 一條資金曲線只是一個樣本，不是 N 筆交易。**
2026-09-17 立的「比較多組前先算雜訊帶」在資金曲線上的版本是：
**跑多條隨機排序取 5~95% 分位**。本次實測帶寬 **20~143pp**——
光是「持 5 檔」的運氣成分就能造成這麼大的落差。
**少了這一步，會把「策略 +54% vs 0050 +157%」或「評分 +54% vs 代號 +22%」讀成訊號。**

**(b)「依股票代號」不是中性對照——這是 2026-09-17 那次留下的錯誤。**
per-trade 層級只比平均報酬，用代號還勉強可以。
但在**槽位競爭**下，代號排序會持續把槽位給小代號股票，
而台股 1xxx 是水泥食品塑膠紡織、28xx 金融，電子在 23xx~8xxx／3xxx／6xxx
⇒ **它偷偷變成「偏重傳產」的策略**，在電子領漲的期間必然墊底。
**「評分 vs 代號」那 32pp 裡有多少是評分、多少是產業偏誤，完全分不開。**
正解是**真隨機排序跑多條**（每檔給一個固定隨機偏好，與代號同性質但無產業結構）。

**(c) 只核對「全期間」不足以驗證切片邏輯。**
第一版 `buyhold_curve()` 回傳 `len(cal)` 格、`strategy_curve()` 回傳 `len(cal)+1` 格
（多一格期初），`_slice()` 對兩者一視同仁 → **買進持有的子區間兩端各偏移一天**。
而 2026-05-04 指數剛好 **+4.57%**：前段的 ETF 被高估約 8pp、2026-05 起被低估約 4.6pp
⇒ 「策略贏 0050 七個百分點」裡有 **4.6pp 純粹是 off-by-one**（修正後只贏 1.7pp）。
**全期間剛好不受影響（i0=0、i1=len），所以人工核對 0050 全期間完全看不出來。**
⇒ **驗證切片類邏輯，必須至少核對一個「中間區間」，不能只驗頭尾。**

---

### 「第一層」：加入自選股這個決定本身有沒有預測力（2026-10-06，**本專案第一個沒有後見之明的測試**）

**起因：** 使用者問「說要驗證選股能力，不是會在投資策略中看評分高的嗎？」
——那是**第二層**。這個系統是兩層漏斗，而**只有第二層被驗證過**：

| | 誰在篩 | 狀態 |
|---|---|---|
| **第一層**：哪些股票進自選股（98 檔 ← 約 1,000 檔上市股） | **使用者** | ❌ 從沒驗過 |
| **第二層**：對那些檔評分、挑 ≥ 門檻的 | 系統評分 | ✅ 驗過，測不出（上限 0.6pp）|

**評分再準，也只能從使用者放進去的池子裡挑。** 而 2026-09-24 量到的
自選股 +2.44% vs 全市場 -0.32%（差 **2.76pp**）**全部落在第一層**——
當時無法歸因，因為 87/87 檔都是回測期（2024-07 起）之後才加入的。

**這次樣本是乾淨的：** 加入的決定在前、表現在後。腳本 `backtest_watchlist_picks.py`（已進版控）。

**時點約定：** `added_at` 多為盤後（如 `2026-05-24 20:32`），當天收盤已過
⇒ base = **之後第一個交易日**收盤（與策略「D 日決策 → D+1 進場」一致）。
可用 87 檔（98 檔中 11 檔加入後不足 20 個交易日）。

#### 結果

| | 檔數 | 報酬 | ★等權基準 | 加權指數 | vs 等權 | 勝率 |
|---|---|---|---|---|---|---|
| 全部 | 87 | +4.65% | +5.96% | +10.37% | **-1.31%** | 36% |
| 只算上市（與基準同宇宙） | 70 | +6.49% | +6.29% | +10.56% | **+0.19%** | 39% |
| 只算上櫃（基準不含，n 太小） | 17 | -2.90% | +4.60% | +9.60% | -7.50% | 24% |

**雜訊帶（從 512 檔宇宙隨機抽，⚠️ 保留同一組 base_date，800 次）——三個指標全部帶內：**

| 指標 | 隨機 5~95% | 實際（上市 70） | 判定 |
|---|---|---|---|
| 平均 | -5.13% ~ **+6.48%** | +0.19% | ⚪ 帶內 |
| 中位數 | -10.04% ~ -1.78% | -7.51% | ⚪ 帶內 |
| 勝率 | 27% ~ 47% | 39% | ⚪ 帶內 |

帶寬 **11.6pp**（n=87、窗口 40~107 日）。事前預期「測不出」，**預期正確**。

#### ⚠️ 差點誤讀的地方（本則最重要的方法論）

看到「**勝率只有 36%、中位數 -8.90%**」，直覺會判「三分之二的選股輸給隨便挑，很糟」。

**但隨機抽也是這樣**（勝率 27~45%、中位數 -9.6% ~ -2.3%）。
原因：**個股報酬是右偏的**，少數大贏家把平均拉高
⇒ 任何單一檔「贏過等權平均」的機率本來就低於五成。
**那是股市的特性，不是使用者的特徵。**

⇒ **只對照「平均」不夠，中位數與勝率也各自要有隨機對照。**
這是「必須設無條件基準」在**分布形狀**上的延伸：
前幾次立的規矩防的是「量尺選錯」「把雜訊當訊號」，
這一則防的是**「把母體本身的性質誤判成個體的能力」**。

#### 報酬集中度（這一項是真的，而且有實務意涵）

| | 平均 vs 等權 | **拿掉最強 5 檔後** |
|---|---|---|
| 全部 87 | -1.31% | **-6.67%** |
| 只算上市 70 | +0.19% | -5.94% |

前五名：南亞 **+128pp**、創意 +92pp、川湖 +73pp、南亞科 +70pp、精材 +69pp。
**87 檔裡的 5 檔（6%）決定了整體結果。**

這與 2026-10-05「隨機 5 檔的資金曲線帶寬 20~143pp」是同一件事的兩種呈現：
**報酬集中在極少數標的，所以持 5 檔時命中那幾檔的機率本來就不高。**

#### 結論

| | |
|---|---|
| ❌ **不能說** | 「選股沒價值」——帶寬 11.6pp，真有 1~3pp 的能力依然隱形 |
| ✅ **可以說** | **沒有證據支持「9/24 那 2.76pp 主要是能力」。** 若是，這個乾淨樣本該看到正值超出帶外；沒有。⇒「主要是後見之明」仍成立且更簡約 |
| ✅ 可以說 | 「勝率低」不是使用者的問題，是股市右偏 |
| ⚠️ **待觀察** | **上櫃 17 檔明顯差**（-7.50%／勝率 24%／拿掉最強5檔 -21.07%）。但基準不含上櫃、n=17，**不可解讀**。另註：那 17 檔本來就沒有籌碼資料（T86 不含上櫃），評分只剩技術＋基本面 |

**不要解讀的兩個數字：** 月份模式（06月 +2.23%／08月 -7.92%，n 只有 9~43）；
隔日跳空吃掉 0.70pp（很小）。

#### 限制

1. n=87，各檔窗口不等長（40~107 個交易日）
2. 樣本仍全在多頭（2026-05~10 指數上漲）
3. **`added_at` 未必等於「決定要買」**——可能只是隨手加觀察名單。
   此偏誤方向**保守**（把不打算買的也算進去）
4. 自選股含 17 檔上櫃，而 512 檔宇宙只有上市 ⇒ 另跑「只算上市」一組對等比較

**下一步（唯一能提高解析度的方向）：** 不是等時間，而是
**從現在起記錄「加入清單的理由」**。目前 `watchlist` 只有 `added_at`，
無法區分「看到它漲所以加」與「判斷它會漲所以加」——
而這兩者的差別正是「能力 vs 追高」。加一個 `add_reason` 欄位成本極低，
日後樣本累積到 n≈300 時（帶寬約 6pp）才有機會分辨。

---

### 🚨 2018 起的歷史回填：第一次有空頭樣本（2026-10-06/07）

**⚠️ 這一則的影響比下面那個月營收發現更廣——它改變了十五章每一節的可驗證範圍。**

**起因：** 要測月營收（105 個月）時發現**價格只到 2024-07-29**，所以只有 26 個月能算報酬。
但順著查下去才意識到：**專案裡每一個「⚠️ 限制：樣本全在多頭」的警語，根源都是這一條。**

**關鍵依賴鏈（之前沒人追過）：**
```
TAIEX 長度  →  決定 backfill_prices_history.py 的交易日日曆
            →  決定全市場個股價格能補多長
            →  決定整個專案有沒有空頭樣本
```
`fetch_taiex()` 原本的 period 上限是 `5y`（約到 2021-10），**不足以支援 2018**
⇒ 2026-10-06 擴充映射：`>60月→10y`、`>120月→max`。
刻意不另寫一份 yfinance 抓取——那會複製陷阱35 修過的 `change_pct` 計算邏輯。

**執行結果（使用者本機，零失敗）：**

| | 回填前 | 回填後 |
|---|---|---|
| TAIEX | 533 筆（2024-07-29 起）| **2,431 筆（2016-10 起）** |
| `prices` | 793,449 列 | **2,585,603 列**（+179 萬）|
| 全市場覆蓋 | 533 天 | **2,127 天**，每日 1,041~1,859 檔 |
| 補齊 1,594 天 | — | 查無資料 0、日期不符 0、失敗 0、**重算後覆蓋不足 0 天** |

**★ 終於有的空頭樣本：**

| 年 | 年報酬 | 最大回檔 | |
|---|---|---|---|
| **2018** | **-9.2%** | -15.8% | 負年 |
| 2020 | +21.8% | **-28.7%** | COVID，V 轉 |
| **2022** | **-22.6%** | **-31.6%** | **完整空頭年** |
| 2024 / 2025 / 2026 | +29 / +27 / +70% | -18.7 / -26.7 / -16.4% | 多頭中的回檔 |

**⇒ 以下這些「標著沒驗過」的，現在第一次可驗：**

| 項目 | 原本的狀態 |
|---|---|
| **「回檔小」**（原稱最站得住腳的優勢，2026-10-05） | 「該優勢目前是推論，不是實測」——它的價值本來就該在空頭顯現，而那是唯一沒資料的環境。**→ 當天就驗了，結果是檢不出來**（見本章末） |
| **停損 10%** | 明寫「真的崩盤時 10% 會比 8% 每檔多賠 2pp」，從未驗證 |
| **`<45 停止進場`** | 「價值本來就該在空頭才顯現」 |
| **策略 D／E 的空頭段** | 只有 2026-07 那兩週一個樣本；而 2026-08 那次重跑確認「那週根本不是大盤轉空」 |
| 大盤評分的方向性 | 2026-09-23 量到輸給無條件基準，但樣本全多頭 |

**⚠️ 重跑時的注意：**
1. `backtest_portfolio_slots.py cache market` 要重建（宇宙與期間都變了），全市場會比 13 分鐘久很多
2. **公司行為事件從 3 檔變 7 檔**（宇宙內，8 事件）——仍少，`_corporate_actions()` 的守衛處理得了
3. **但除權息變成嚴重問題**，見陷阱50

**⭐ 方法論：「限制」欄位裡反覆出現的同一句話，往往指向一個單點依賴。**
本專案十五章有至少五節寫著「樣本全在多頭」，而那其實不是五個獨立的限制，
**是同一個原因（TAIEX 只有 533 筆）造成的五個症狀**。
**看到同一條限制重複出現，要去追它的共同上游，而不是每次都只在結論後面加註。**
追上去之後發現解法只要兩行（period 映射）＋ 55 分鐘的回填。

---

### ✅ 月營收 YoY：第一個通過完整對照檢定的訊號（2026-10-07）

**⚠️ 這是本專案六次「型態類提案實測無效」之後，第一次有東西通過。**
前六次（🎯🔥型態、移動停損、confirm_days=1、策略F、ER過濾、先殺後拉、量能水位、類股占比）
**全部都是把價格重新排序**。

**為什麼會想到月營收——一個該早點說的觀察：**

| 分項 | 權重 | 它的「日變動」來自哪 |
|---|---|---|
| 技術面 | 40% | 價格的函數 |
| 籌碼面 | 35% | 昨天的成交結果 |
| **基本面** | **25%** | **PE/PB/殖利率 → 分母是價格、分子一季才動一次** ⇒ **日變動幾乎也全部來自價格** |

**⇒ 三面加權裡，真正獨立於價格的成分幾乎是零。** 這就是 2026-09-23 量到
「評分與未來報酬 corr=0、與過去 corr=+0.25」的結構原因——**不是調參能解決的**。

月營收是第一個真正正交的輸入：營運事實、分子自己會動、有明確公布節奏。

#### 資料（`monthly_revenue` 表，105 個月）

來源 **MOPS t21sc03**（`mopsov.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月}_0.html`），
腳本 `backfill_monthly_revenue.py`（已進版控，預設試跑）。

| | |
|---|---|
| 成本 | **一個請求一個月全市場**（993 檔）⇒ 105 個月約 5 分鐘 |
| 結果 | **97,701 列、2018-01~2026-09、993 檔、零失敗零年月不符** |
| **編碼** | **`cp950`**（實測 `big5` 嚴格解碼**失敗**）⚠️ 舊程式對 TAIFEX 用 `big5,errors='ignore'`，照抄會靜默丟字 |
| 資料列辨識 | **11 欄 且 [0] 是 4 碼代號**（同頁 34 個 `<table>`，一產業一張；2/4/10 欄是標題與表頭）|
| 內部一致性驗證 | **MOPS 自己的 `yoy_pct` vs 用我們解析的 `revenue` 反算 → 97,177/97,177 相符（100.000%）** |

**★ `avail_date` = 營收月的次月 11 日 —— 防 look-ahead 的核心，絕對不要「優化」掉。**

沒有任何來源給逐股公布日。三個看起來像的都不是：

| 欄位 | 實際是什麼 | 證據 |
|---|---|---|
| FinMind `create_time` | FinMind 批次補寫時間 | **2 月與 3 月營收共用 `2026-04-21`** |
| FinMind `date` | 營收月的**次月 1 日** | date 2026-09-01 ↔ revenue_month 8；而法規是 10 日前公布 ⇒ **偷看 10 天** |
| MOPS「出表日期」 | MOPS 產報表的日期 | 實測 115/10/06，與營收月份無關 |

**實證「保守不是多慮」：** 2026-10-06 查 9 月營收只有 **176/993 檔**已公布。
若用 `date`（10/1），當天拿到的是「只有 18% 公司、而且偏向先公布者（業績通常較好）」
——那是比單純偷看 10 天**更惡性的選擇偏誤**。

**存成實體欄位**而非靠註解提醒，是因為這樣任何查詢都不可能忘記加這個限制。

**⚠️ 同一月份必須重複抓：** 次月 1~10 日資料逐日累積
⇒ 日後接每日更新要重抓「**當月 + 前兩個月**」，**不可用「抓過就跳過」的水位線邏輯**（陷阱45 的病根）。

#### 檢定一：有預測力嗎（`backtest_revenue_signal.py`）

**Fama-MacBeth**——因為月營收是**全市場同月一起公布**，
105 個月 × 約 1,000 檔 ≈ 10 萬筆**不是 10 萬個獨立樣本**（同 2026-09-15「量能水位」n=15 實際 n≈4 的病根）。
**有效樣本 = 月數，標準誤 = SD(月度差)/√月數。**

★ 主檢定（**事前指定**：YoY 水準・產業內排名・20 日持有）：

```
高YoY − 低YoY   +1.98%/月   SE 0.31   t = +6.44   月勝率 69%   n=101
  高分組 +2.47%　無條件基準 +1.46%　低分組 +0.49%     ← 兩端對稱
```

**🚨 除權息診斷（本次最大的地雷，差一點踩中）：**

| | spread | t |
|---|---|---|
| 6~9 月（除息月） | **+1.72%** | +2.96 |
| 其他 8 個月 | **+2.12%** | +5.91 |

**若是股利造成的，除息月應該要更高。結果是更低 ⇒ 不是股利。**
（8月 +0.95%、9月 -0.07% 是全年最弱兩個月 ⇒ 除息反而可能在**壓抑**真實效果。）

兩個支持它為真的證據：
- **60 日 ≈ 20 日的 2.2 倍**（+4.37% vs +1.98%）⇒ 效果**累積**，符合「漂移」特徵；若是除息那種一次性跳水，60 日會與 20 日相近
- **三段期間都正**（2018-20 +1.20%／2021-23 +2.11%／2024-26 +2.69%）

#### 檢定二：是不是動能的代理（`backtest_revenue_vs_momentum.py`）—— 決定真偽的那一步

**可能推翻一切的解釋：** 營收好 → 股價已先漲過 → 高 YoY 組 ＝ 最近漲過的股票
→ 20 日前瞻報酬只是動能延續 ⇒ 那它就**不是正交的新資訊**。

**A 診斷：** corr(YoY, 前20日報酬) = **+0.145**、corr(YoY, 前60日報酬) = **+0.224** ⇒ 混淆本來就不嚴重。

**B 雙重排序**（先按公布前報酬分 5 組，**組內**再取 YoY 前後 1/3）：

| | spread | t | 保留 |
|---|---|---|---|
| 未控制 | +1.74% | +6.18 | — |
| **控制前20日報酬** | **+1.48%** | **+5.84** | **85%** |
| 控制前60日報酬 | +1.27% | +5.32 | 73% |

**C Horse race**（三個變數同時進迴歸）：

```
★ YoY 排名        +2.02%   t = +5.44   ★ 顯著
  前20日報酬排名   +0.08%   t = +0.14   ⚪ 不顯著  ← 幾乎是 0
  前60日報酬排名   +1.77%   t = +3.06   ★ 顯著
```

**B 與 C 用不同方法得到一致結論：只有 15~27% 是動能，YoY 有獨立且更強的貢獻。**

**⚠️ 單元測試必須成對做（這次的方法論收穫）：** 用合成資料驗雙重排序時，
造了**兩個**世界——「YoY 其實沒用」（單排序 +4.69% → 雙重 +1.01%，剝離成功）
與「YoY 真有貢獻」（+9.29% → +4.27%，真訊號保留）。
**只驗前者會以為「數字變小就是方法有效」，但也可能它連真訊號都殺。**

#### ⚠️ 最重要的實務發現：動能交互作用

```
第1組（動能最弱）  +0.61%   t = +1.42   ← 不顯著
第2組              +0.99%   t = +2.92
第3組              +1.72%   t = +5.16
第4組              +1.55%   t = +3.69
第5組（動能最強）  +2.55%   t = +5.21
```

**大致單調：動能越強，YoY 的效果越大；動能最弱那組 YoY 幾乎沒用。**

⇒ **「營收好」單獨不夠，要搭配「股價沒在走弱」。**
而現有評分的技術面 40% 正是在測股價強弱
⇒ **YoY 與現有評分可能是互補，而不是取代**——這與原本「找正交輸入來取代後照鏡」的預期不同。

#### 主動檢查的四個偏誤——三個方向對結論不利

| 偏誤 | 方向 |
|---|---|
| 停牌/下市（需 t1 有價格才納入） | 暴跌停牌多為低 YoY → **低 YoY 組被高估** → spread 被低估 ✅ |
| 減資（股價人為上升，比例常在 [0.7,1.3] 守衛內漏過） | 減資公司多虧損 → 低 YoY → 同上 ✅ |
| 除息 | 診斷已排除 ✅ |
| ⚠️ **MOPS 是「最終版」資料** | 若有公司事後更正營收，拿到的是更正後 ⇒ **輕微 look-ahead**。月營收極少更正，但這是唯一方向不利的 |

另外確認：**這確實不在現有評分裡**（基本面 25% 是 PE/PB/殖利率，不含營收）。

#### 🚨 可實施性——這是最大的限制，而且與現行做法衝突

```
long-only 高分組（約 74 檔）  +2.47%/月
無條件基準                    +1.46%/月
alpha                        +1.01pp/月
每月換倉成本                  − 0.47pp
淨                           ≈ +0.54pp/月 ≈ +6.7%/年
```

**但那是 74 檔等權。** 2026-10-05 實測**隨機 5 檔的資金曲線帶寬 40.8pp / 107 天 ≈ ±8pp/月**。

> **0.5pp/月 的優勢，在 5 檔的配置下完全看不見。**

⇒ 這個訊號要能用，**部位數必須是 30~70 檔**，或者它只能當
**「進場的額外篩選條件」而非獨立策略**。而 prior 組的交互作用也指向後者。

#### 限制與未做（引用上面任何數字時必須一起講）

1. **除權息無法調整**（見陷阱50）。產業內排名只是控制，不是消除
2. **空頭時測不出**：2018+2022 的 t=1.52（n=22）。方向仍正，樣本不足
3. `avail_date` 保守（次月11日）⇒ 抓不到公布後 1~2 天的效果。但那也抓不到實際操作（盤後資料、隔日動作）
4. 上櫃不在宇宙內；**KY 股 30 檔沒有月營收**（MOPS 列在另一區段）
5. 測了 8 組 ⇒ 只有★主檢定可當結論（即使 Bonferroni 校正，t=5.84 仍遠超門檻）
6. ~~**尚未做**~~ **✅ 兩項都做完了**：
   「現有策略 ＋ YoY 篩選」→ 2026-10-14（通過全套對照，alpha +0.28% → +0.64%）；
   「當第四個分項 vs 當篩選門檻」→ **2026-10-18（第四個分項顯著更好，
   78/100、p=0.000；而且機制是「篩選門檻讓槽位填不滿」）**。兩節都在本章下方。
   ⚠️ 兩次的結論都是**不改規則**，理由不同——前者是量級太小，後者是會動到
   `scorer.py` ＋ 陷阱44 讓「稀釋舊總分」在樣本前後段不是同一件事。

---

### ✅ 現有策略 ＋ 月營收 YoY 篩選：第一個通過全套對照的篩選條件（2026-10-14）

**⚠️ 但「通過」不等於「可以採用」——有一個診斷項目不利，而且量級極小。先讀完再引用。**

腳本：`backtest_revenue_filter.py`（已進版控）。這是十五章月營收那節標著
「**尚未做**」的兩項之一：10/07 測的是「理想化月度換倉組合」（74 檔等權、每月重排），
**不是**現行策略（5 檔、10 日週期、續抱、10% 停損、大盤階梯）。

#### ★ 事前預期（先寫下再跑，照策略F／D 的慣例）—— 對了一半

> 「**可能測得出來，而且與 10/07 的悲觀結論不衝突。** 10/07 說 0.5pp/月 在 5 檔
> 配置下看不見，那個 ±8pp/月 帶寬來自**隨機 5 檔的資金曲線**，量的是「抽到哪幾檔」
> 的運氣；而配對設計正好把它消掉。」

| 預期 | 結果 |
|---|---|
| 配對設計會給出無條件比較沒有的檢定力 | ✅ **對**（B2 vs A1：17/20、p=0.003）|
| 最有效的會是對應 10/07「高分組」的**前 1/3** | ❌ **錯**。前 1/3 在 5 檔配置下**測不出來**（12/20、p=0.503）；有效的是**產業內中位**|
| 技術面 40% 可能已吃掉一部分增量資訊 | ⚠️ 機制不同但方向相關，見下方「為什麼 B2 > B3」|

#### 樣本與前提（與 10/07 的結構測試差異很大，必須先講）

| | |
|---|---|
| 期間 | **2018-01-02 ~ 2026-10-14（2,132 個交易日）** |
| 宇宙 | 512 檔上市普通股（日均成交 ≥0.5 億），**455 檔有產業內排名**（89%）|
| 評分點 | **949,133** 個 |
| ★ 與 10/07 結構測試的關鍵差異 | **這次用得到個股評分**——`chips` 在 2026-10-08 已回填到 2017-12（2,137 天），而 10/07 當時實查是 **0 天**，所以那次刻意不用評分。現在技術40%＋籌碼35% = **75% 的權重有真實資料** |
| 仍然缺的 | 基本面 25% 在 2026-05 之前是預設值 50（陷阱44，永久）|

#### ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）

| 規則 | 筆數 | alpha | **扣 0.47% 成本後** | 勝率 |
|---|---|---|---|---|
| A0 現行策略（全宇宙） | 15,176 | +0.31% | -0.16% | 42.9% |
| **A1 現行策略（限有營收資料）** | 13,289 | **+0.28%** | **-0.19%** | 43.3% |
| B1 ＋YoY > 0 | 9,277 | +0.55% | +0.08% | 43.5% |
| **B2 ＋YoY 產業內 ≥ 中位** | 7,719 | **+0.64%** | **+0.16%** | 44.3% |
| B3 ＋YoY 產業內 前1/3 | 5,437 | +0.63% | +0.16% | 44.3% |
| **★C ＋YoY 產業內 後1/3（反向對照）** | 4,598 | **-0.28%** | **-0.75%** | 40.9% |
| ★D 隨機篩掉同比例（中性對照，5 seed） | ~8,880 | **+0.21% ~ +0.38%**（中位 +0.33%）| — | — |

```
各組 alpha 全距 0.91pp　vs 最寬雜訊帶 0.46pp（n≈4,600 重抽 600 次）
⇒ ★ 全距超出雜訊帶 ⇒ 可以解讀（9/17 立的標準前置動作）
```

**★ 三個對照合起來才構成證據，缺任何一個都會誤判：**

| 對照 | 作用 | 結果 |
|---|---|---|
| **★D 隨機篩同比例** | 任何篩選都會減少筆數，而**筆數變少本身就改變 alpha 分布** | **+0.33% ≈ A1 的 +0.28%** ⇒ 「篩掉 59% 的交易」本身**毫無效果** ⇒ B2 的 +0.64% 歸因於 YoY 這個維度 |
| **★C 反向（後1/3）** | 若是雜訊，前後 1/3 會差不多 | **-0.28%，低於 A1** ⇒ 方向性成立 |
| 單調性 | — | **C(-0.28) ＜ A1(+0.28) ≈ D(+0.33) ＜ B3(+0.63) ≈ B2(+0.64)** |

#### ② 5 檔配置・配對比較（20 條，同一 seed 同一組隨機排序）

```
檢定力：20 條之下最少要 20/20 才有 p<0.05 的「全勝」門檻；
        但符號檢定排除平手後，17/20 即 p=0.003（雙尾）
```

| 配對 | Δ中位 | 勝場 | p | 判定 |
|---|---|---|---|---|
| **B2 vs A1** | **+0.37pp** | **17/20** | **0.003** | ✅ |
| B3 vs A1 | +0.09pp | 12/20 | 0.503 | ⚪ **測不出來** |
| **★C（反向）vs A1** | **-0.39pp** | 4/20 | 0.012 | ❌ 反向對照正確作用 |
| **★★ B3 vs C（前後1/3對決）** | **+0.42pp** | **18/20** | **0.000** | ✅ |

**⇒ 操作點是「產業內 ≥ 中位」（B2），不是「前 1/3」（B3）。**

#### ★ 為什麼 5 檔時 B2 ＞ B3（反直覺，但機制很乾淨）

| 規則 | 有進場訊號的天數 | 單日候選中位 | **單日 ≥5 檔的天數** |
|---|---|---|---|
| A1 | 1,257 | 6 檔 | 744（**59%**）|
| B2 | 1,167 | 4 檔 | 549（**47%**）|
| B3 | 1,085 | 3 檔 | 413（**38%**）|

**B3 篩太兇 ⇒ 5 個槽位有 62% 的日子填不滿 ⇒ 部位閒置、或被迫留著較差的續抱。**
per-trade 上 B2 與 B3 幾乎相同（+0.64% vs +0.63%），**差異完全發生在組合層級**。

> **⭐ 方法論（新的一條）：篩選器的「強度」有最適點，而那個點只有在**
> **組合層級測得出來。** per-trade 層級看不到「候選不足導致槽位填不滿」這件事
> ——它只統計已經成交的交易。這與 9/17「組合層級的規則需要組合層級的回測架構」
> 同一族，但方向相反：那次講的是「限制」測不出來，這次是「篩選強度」測不出來。
> **判斷方法極便宜：印出「單日候選 ≥ 槽位數」的天數比例。**

#### 內建診斷一：分期間——空頭年沒有翻轉（這是比 10/07 強的地方）

| 期間 | B2 筆數 | B2 alpha | C alpha | **B2−C** |
|---|---|---|---|---|
| **2018 ★空頭（-9.2%）** | 535 | +0.10% | +0.12% | **-0.02pp** ⚪ |
| 2019 | 930 | +0.64% | +0.16% | +0.48pp |
| **2020 ★空頭（V轉）** | 731 | +0.93% | -0.96% | **+1.88pp** |
| 2021 | 695 | +0.87% | -0.36% | +1.23pp |
| **2022 ★空頭（-22.6%）** | 1,006 | +0.96% | +0.50% | **+0.46pp** |
| 2023 | 1,016 | +1.30% | +0.22% | +1.08pp |
| 2024 | 1,043 | -0.32% | -0.93% | +0.60pp |
| 2025 | 957 | +0.39% | -0.65% | +1.03pp |
| 2026 | 806 | +0.80% | -0.67% | +1.47pp |

**B2−C ＞ 0 的年份：8/9。** 唯一非正的 2018 是 **-0.02pp（實質是零，不是翻轉）**。
⇒ 這比 10/07 的「空頭時測不出來（2018+2022 的 t=1.52，n=22 月）」**明確改善**。

#### 🚨 內建診斷二：除權息——**這一項不利，而且與 10/07 方向相反**

| 進場月 | B2 alpha | C alpha | **B2−C** |
|---|---|---|---|
| **6~9 月（除息月，佔全年除息 93.6%）** | +0.33% | -0.66% | **+0.99pp** |
| 其他 8 個月 | +0.81% | -0.06% | **+0.87pp** |

**自我診斷的邏輯：若效果是股利造成的，除息月的 spread 應該要更高。**
這次**除息月確實略高（+0.99 vs +0.87，差 0.12pp）**——
⚠️ **方向與 10/07 相反**（那次是其他 8 月 +2.12% ＞ 除息月 +1.72%，所以地雷沒引爆）。

**但不能因此判為假訊號，理由有兩個：**
1. 差距 **0.12pp** 相對於總效果 **0.87~0.99pp** 很小（n≈2,800／1,667，在雜訊內）
2. **效果在非除息的 8 個月裡清楚存在（+0.87pp）** ⇒ 不可能主要來自股利

**⇒ 誠實的說法：這次無法像 10/07 那樣乾淨地排除股利，但也不支持「主要是股利」。**
真正的修法是陷阱50 標著的待辦——**抓除權息歷史**，
那會同時改善**所有**既有回測，不只這一題。

#### ✅ 2026-10-15 補做：除息調整後，這個不利診斷消失了

除權息已回填 2018~2026（**9,574 列**，逐年 823~1,358，陷阱52），
所以不必再靠「效果有沒有集中在除息月」反推，可以**直接把股利加回個股報酬**。
共用模組 `exdiv.py`（已進版控，含合成資料自我測試）。

**★ 為什麼「只調整個股那一邊」在這一題是正確的（這是本次最關鍵的判斷）：**

```
alpha = 個股報酬 − TAIEX 報酬
```
TAIEX **也是價格指數、同樣不含股利** ⇒ 只把左邊加上股利、右邊不動，
alpha 會憑空多出整個市場的殖利率（台股約 3~4%/年）——那是假的改善。
**但 B2−C 是兩個 alpha 相減：**
```
(個股B2 − 市場) − (個股C − 市場) = 個股B2 − 個股C     ← 市場項精確消掉
```
⇒ **基準含不含股利完全不影響這個差值。這一題剛好只需要個股端。**

⚠️ 反過來說：**`pnl_div` 的絕對 alpha 不可拿去跟既有數字並列**。
要做「絕對 alpha 的除息調整版」必須同時換成**總報酬基準**
（TWSE 發行量加權股價報酬指數，或 FinMind `TaiwanStockTotalReturnIndex`）
——那是另一個題目，`exdiv.py` 刻意不猜。

**結果（同一份快取、同一組交易，筆數與 10/14 完全一致 7719／5437／4598）：**

| B2−C | 未調整 | **除息調整後** | 變化 |
|---|---|---|---|
| 6~9月（除息月） | **+0.99pp** | **+0.90pp** | -0.09pp |
| 其他 8 個月 | +0.87pp | +0.87pp | -0.00pp |
| **差（除息月 − 其他）** | **🚨 +0.12pp** | **+0.03pp** | **-0.09pp** |

B3−C 同向：差距由 **+0.17pp → +0.05pp**。

**⇒ 殘餘 +0.03pp 相對於 n≈4,600 的雜訊帶 0.46pp，是 1/15——與零無法區分。**
10/14 標著「唯一不利的診斷項目」那一條，**解除**。

**★ 機制與事前預測完全吻合，這是比數字本身更強的證據：**

| | 股利加回後的報酬提升 | 疑似除息假停損率 |
|---|---|---|
| B2（高成長＝低殖利率） | **+0.28pp** | **1.10%** |
| B3 | +0.28pp | 1.16% |
| **★C（低成長＝高殖利率）** | **+0.32pp** | **1.67%** |

**C 組被除息拖累得更多**（提升幅度更大 ＋ 假停損率高出 0.57pp）
——正是陷阱50 當初預測的方向（低成長股殖利率高 ⇒ 除息拖累大 ⇒
製造假的「高成長組贏」）。**預測的方向、受害的組別、量級都對上了。**

⚠️ **殘餘的 +0.03pp 最可能的來源是假停損，而那一項沒有被修。**
C 組多 0.57pp 的交易因除息跳水觸發 10% 停損，粗估對報酬的影響正好是
0.02~0.05pp 這個量級。真正的修法是用**還原股價**跑整個回測
（會改動所有既有基準，是另一個題目）。`exdiv.suspect_false_stops()`
會把這類交易列出來——**只揭露、不假裝沒事**。

**⇒ 連帶：10/14 那三個「不採用的理由」現在只剩兩個**（量級極小、
以及陷阱44 的「65 分在前後段不是同一個篩選器」）。
量級那一條仍然致命：alpha +0.28% → +0.64%，扣 0.47% 成本後是
**-0.19% → +0.16%**，「從明確落後指數變成大致打平」，不是「會賺」。
**所以結論仍然是不改規則。**

#### 結論：不改規則，但這一則的定位與前七次否決完全不同

| | |
|---|---|
| ❌ **不能說** | 「找到有效的篩選條件了，可以加進規則」|
| ✅ **可以說** | **這是專案第一個同時通過「反向對照」「中性對照」「單調性」「分期間 8/9 一致」「空頭年不翻轉」的篩選條件** |
| ⚠️ 為什麼仍不採用 | 見下方三個理由 |

**三個不採用的理由 → ✅ 2026-10-15 已解決一個，剩兩個：**

1. **量級極小（仍然致命）。** alpha 由 +0.28% 提到 +0.64%，扣掉 0.47% 來回成本後是
   **-0.19% → +0.16%**——意思是「從明確落後指數變成大致打平」，**不是「會賺」**。
2. ~~**除權息診斷不利。**~~ **✅ 已解除（2026-10-15）**：回填 2018~2026 的
   除權息、把股利加回個股報酬後，除息月與其他 8 月的差距由 **+0.12pp → +0.03pp**
   （雜訊帶 0.46pp 的 1/15），而且受害的組別、方向、量級全部與陷阱50 的預測吻合。
   詳見上一節「除息調整後」。
3. **「65 分」在這段樣本與今天不是同一個篩選器**（陷阱44：基本面 25% 在
   2026-05 之前恆為 50）。9/17 已記過這個問題——它讓「現行策略」這個對照組
   本身在樣本前後段不是同一個東西。**這一條是永久限制，修不掉。**

**⇒ 所以結論不變：不改規則。** 但理由從「三個」變成「兩個」，
而且擋路的那一個（量級）是**量的問題不是方法的問題**
——若日後找到能把 alpha 再推高 0.5pp 的東西，這個篩選條件就值得重新討論。

#### 限制（引用任何上述數字時必須一起講）

1. **除權息無法調整**（陷阱50）⇒ 所有報酬系統性低估；而 B 組偏向高成長股
   （＝低殖利率＝除息拖累小）⇒ **這個偏誤的方向對 B 組有利**。
2. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）。
3. **未調整收盤價**（陷阱49）⇒ 分割日會有假停損。
4. **上櫃不在宇宙內**；KY 股沒有月營收（本次實測 1256／1337／1338／1340／
   1341／1589／1590／1591 全部 0 筆，與十五章記載一致）。
5. `avail_date` 保守（營收月的次月 11 日）⇒ 抓不到公布後 1~2 天的效果。
6. **配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」**。
7. 2016~2017 已刻意裁掉（陷阱51 限制第 5 條：S2/S3/S4 只回填到 2018-01-01）。

#### 🚨 順帶抓到：`build_cache()` 把視窗寫死 600 天（陷阱51 那條通則第三次出現）

`backtest_portfolio_slots.build_cache()` 有**五處**寫死 600：
`_build_market_signals()` 沒傳 days、TAIEX、個股 `prices`／`fundamentals`／`chips`。
⇒ 2026-10-08 回填 2018 歷史之後，**它仍然只看 2024-05 起，一個空頭年都沒有，
而且不報錯。** 已全部參數化（`days=600` 維持既有呼叫不變）。

**前兩次：** 陷阱32（`calc_all()` 只餵 30 天，`pos_250` 靜默變成「近 30 日位置」）、
陷阱51（`_build_market_signals()` 寫死 600）。
**⇒ 這條通則要再強調一次：回填歷史之後，grep 全部 `days=`／`[-N:]`／`LIMIT N`。**

#### 兩個實作上值得記的決定

| | 做法 | 理由 |
|---|---|---|
| 不另寫 simulate | 給既有 `simulate()` 加 `entry_filter` 參數（評分門檻通過後再 AND 一道）| filter=None 時與改版前**位元級相同** ⇒ **根本不需要對帳**。⚠️ **2026-10-22 更正（陷阱56）：這句話只在「同一份快取內」成立**——FMTQIK 每日 UPDATE 近 12 個月的 `prices.value`、S8 讀它 ⇒ 大盤淨值會回溯改變，跨 session 重建必然不同。10/07 那條「給對照組命名要逐條核對現行規則」的通則，最可靠的落實方式是**不要有第二份實作** |
| 價格視窗截斷 | `full_score(prices[i-299:i+1])` 取代 `prices[:i+1]` | 原本對 2,133 筆是 O(n²)。`calc_all()` 最長只需 250 筆 ⇒ 取 300。**實測 2330 逐日逐欄 2042/2042 完全相同、快 1.4×**。⚠️ 日後新增週期 >300 的指標必須同步加大（陷阱32）|

#### ⚠️ 腳本裡刻意留著的兩道守衛（都是從錯誤學來的）

1. **退化配對偵測**：若 20 個 seed 給出**完全相同**的 alpha，代表 5 檔上限從未
   綁定、隨機排序不起作用 ⇒ 符號檢定讀到的是「同一個數字抄 20 次」，會印出
   20/20 與 p<0.001 看起來極顯著。**煙霧測試（12 檔宇宙）就真的觸發了這個情形**，
   當時印出 6/6、p=0.031。已改為偵測到就標 🚨 並註明「p 不可讀」。
   這與 10/07 的「錯誤二」（符號檢定把平手算成輸）同一族。
2. **合併快取時檢查塊數完整**：缺塊就拒絕合併。合併不完整的快取會讓宇宙
   悄悄縮小，而結果看起來完全正常——那正是陷阱41/42/45 的共同形狀。

---

### 🚨 月營收 YoY「當第四個分項」vs「當篩選門檻」：本專案至今最強的正面結果（2026-10-18）

**⚠️ 這是十五章月營收那節標著「尚未做」的最後一項，而結果與我的事前預期相反。**
**⚠️ 但「最強」不等於「可以直接改規則」——兩個限制還在，w≥50% 那半邊還不能讀。先讀完。**

腳本：`backtest_revenue_component.py`（已進版控）。

#### 兩者的差別不是寫法，是「能不能互相抵銷」

| | 規則形狀 | 後果 |
|---|---|---|
| **當篩選門檻**（10/14 已測，B2） | 評分 ≥ 門檻 **之後再 AND 一道** YoY ≥ 產業內中位 | YoY 低就直接排除，評分再高也沒用（**不可抵銷**）|
| **當第四個分項**（本次） | 成長分數進入加權和，與技術／籌碼／基本面一起算 | YoY 低但其他面強 ⇒ 仍可能達標（**可抵銷**）。而且**它同時影響續抱**（續抱門檻也是看總分），篩選門檻那版不會 |

#### ★ 實作上最關鍵的判斷：不改篩選邏輯，改「分數本身」

「等比例稀釋現有三面、再加一個權重 w 的新面」在數學上**精確等於**對舊總分做加權平均：

```
新 = (1-w)×(0.40技 + 0.35籌 + 0.25基) + w×成長
   = (1-w) × 舊總分 + w × 成長分數        ← 只需要總分
```

兩個好處：
1. **不需要重建快取**（快取裡只有總分、沒有三個分項；重建要 20~40 分鐘）
2. **`simulate()` 完全照原樣跑**——階梯、65 門檻、續抱、10% 停損全不動，
   **沒有任何新的規則邏輯**（「不要有第二份實作」那條通則；10/14 與 10/16 兩次都靠它免除對帳）

成長分數 = **產業內 YoY 百分位 ×100**（0~100，與其他分項同尺度；
`rev_rank` 走 `avail_date` 的 bisect ⇒ 點時間，不偷看）。
無排名的 (股,日) 給 **50**（`scorer.py` 對「無資料」的既有慣例）——而所有組的進場
都用 `entry_filter=has_rev` 限制在「有營收資料」的子集內（與 10/14 的 A1 同一母體），
所以那個 50 只影響續抱。

#### ★ 事前預期（先寫下再跑）—— **主預期錯，而我自己標的「反方向」對了**

> 主預期：**第四個分項會弱於篩選門檻，甚至測不出效果。**
> ① 10/07 量到**動能交互作用**——動能最弱那組 YoY 幾乎沒用（+0.61%、t=+1.42）。
>    而第四個分項正好會讓「技術面弱但 YoY 高」的股票靠成長分補進來，
>    **那正是 YoY 無效的那一組**。
> ② 篩選門檻是 AND，保證「技術強 **且** 成長好」；加權和允許抵銷。
>
> 反方向的可能（我認為機率較低）：第四個分項**不減少候選**（只重排），
> 所以不會有 10/14 那個「候選不足、槽位填不滿」的問題。

**結果：反方向那一條才是對的，而且機制已經量到**（見下方候選數那欄）。

#### ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）

🚨 **`alpha` 這一欄不可跨組直接比**——各組的持有長度不同，必須看 `★a/日`。

| 規則 | 筆數 | 報酬 | 同期大盤 | alpha | 扣成本 | 停損 | 勝率 | 均持有 | **★a/日** | 候選中位 | ≥5檔 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 現行策略（限有營收資料） | 13,289 | +1.25% | +0.97% | +0.28% | -0.19% | 14.3% | 43.3% | 14.3 | **+0.0197%** | 21 | 89.0% |
| B2 篩選門檻 YoY ≥ 產業內中位 | 7,719 | +1.60% | +0.97% | +0.64% | +0.17% | 14.3% | 44.3% | 14.5 | **+0.0438%** | 12 | **79.6%** |
| G15 第四個分項 w=15% | 9,454 | +1.74% | +1.04% | +0.70% | +0.23% | 15.2% | 44.4% | 14.7 | +0.0478% | 15 | 82.9% |
| **★G25 第四個分項 w=25%（主規格）** | 8,811 | +2.10% | +1.21% | +0.89% | **+0.42%** | 17.1% | 44.0% | 16.5 | **+0.0540%** | 19 | **90.0%** |
| G35 w=35% | 8,442 | +2.74% | +1.50% | +1.24% | +0.77% | 18.7% | 43.3% | 19.5 | +0.0635% | 28 | 94.3% |
| G50 w=50% | 7,798 | +4.34% | +2.29% | +2.05% | +1.58% | 24.2% | 43.9% | **26.6** | +0.0773% | 52 | 95.8% |
| G75 w=75% | 6,980 | +7.18% | +3.50% | +3.68% | +3.21% | 32.6% | 44.4% | **37.5** | **+0.0981%** ←峰值 | 92 | 95.8% |
| G100 成長取代全部 | 7,024 | +7.81% | +4.00% | +3.81% | +3.34% | 36.9% | 44.9% | **42.0** | +0.0908% | 118 | 95.8% |
| **★GC25 反向：成長取 (1-百分位)** | 8,237 | +1.04% | +1.19% | **-0.15%** | -0.62% | 14.2% | 43.0% | 15.4 | **-0.0096%** | 15 | 82.7% |

```
各組 alpha 全距 3.96pp　vs 雜訊帶 0.39pp（從 A1 重抽 n=6,980、600 次）
⇒ ★ 遠超雜訊帶 ⇒ 可以解讀
★ 對帳點：B2 跑出 7,719 筆 / alpha +0.64%，與 10/14 **位元級一致** ✅
```

**🚨 「同期大盤」那一欄從 +0.97% 升到 +4.00%（4 倍）就把陷阱講出來了：
持有期被拉長了**（高成長股會一直續抱，因為續抱門檻也是看總分）。
per-trade alpha **沒有除以持有長度** ⇒ 單調上升有一大半是這個造成的。
**除以持有天數之後效果仍然在**（0.0197% → 0.0981%，峰值在 w=75%），
而**反向對照是負的（-0.0096%/日）** ⇒ 不是純粹的持有期假象。

#### ② 逐年 alpha（★=空頭年）

| 年 | A1 | B2 | **★G25** | ★GC25 |
|---|---|---|---|---|
| **2018 ★** | +0.36% | +0.10% | **+0.62%** | +0.75% |
| 2019 | +0.36% | **+0.64%** | +0.56% | +0.13% |
| **2020 ★** | +0.33% | +0.93% | **+1.38%** | -0.66% |
| 2021 | +0.39% | +0.87% | **+1.60%** | -0.13% |
| **2022 ★** | +0.72% | +0.96% | **+1.43%** | +0.71% |
| 2023 | +0.78% | +1.30% | **+1.38%** | +0.23% |
| 2024 | -0.64% | -0.32% | **+0.01%** | -1.18% |
| 2025 | -0.09% | +0.39% | **+0.92%** | -0.54% |
| 2026 | +0.44% | **+0.80%** | +0.25% | -0.29% |
| **★三空頭年合計** | +0.51% | +0.75% | **+1.21%** | +0.26% |
| **其他六年合計** | +0.19% | +0.59% | **+0.76%** | -0.32% |

**G25 ＞ A1：8/9 年**（唯一例外 2026）。**G25 ＞ B2：7/9 年**（例外 2019、2026）。
**三個空頭年全部是 G25 最高**，而 2018 那年 B2 幾乎沒用（+0.10%）、G25 有 +0.62%。

#### ★★ ③ 5 檔配置・100 條配對（seed 7000~7099，同一組排序）

| 規則 | 中位 alpha |
|---|---|
| A1 基準 | **-0.05%** |
| B2 篩選門檻 | +0.20% |
| G15 | +0.44% |
| **★G25（主規格）** | **+0.68%** |
| G35 | +0.88% |
| **G50** | **+3.31%** ←峰值 |
| G75 | +2.80% |
| G100 | +3.09% |
| ★GC25 反向 | **-0.44%** |

| 配對 | Δ中位 | 勝場 | p | 判定 |
|---|---|---|---|---|
| **★★ 第四個分項(w25) vs 篩選門檻(B2)** | **+0.37pp** | **78/100** | **0.000** | ✅ |
| **第四個分項(w25) vs A1 基準** | **+0.69pp** | **92/100** | **0.000** | ✅ |
| 篩選門檻(B2) vs A1（對帳 10/14） | +0.27pp | 73/100 | 0.000 | ✅ |
| **★ 反向(GC25) vs A1** | -0.37pp | 22/100 | 0.000 | ❌ |
| **★ 反向(GC25) vs 第四個分項(w25)** | **-1.02pp** | **5/100** | **0.000** | ❌ |
| w15 vs w25 | -0.21pp | 35/100 | 0.004 | ❌ |
| w35 vs w25 | +0.29pp | 66/100 | 0.002 | ✅ |
| w50 vs w25 | +2.28pp | 93/100 | 0.000 | ✅ |
| w75 vs w50 | +0.33pp | 54/100 | 0.484 | ⚪ |
| w100 vs w50 | +0.33pp | 54/100 | 0.484 | ⚪ |

**⇒ 第四個分項顯著贏過篩選門檻，而且 w=25% 已經不是最低有效權重**
（w15 顯著差於 w25 ⇒ 15% 太輕）。w≥50 之後就分不出來了。

#### ★ 機制：10/14 那個「候選不足」的機制，這次站在第四個分項那一邊

| 規則 | 候選中位 | **單日 ≥5 檔** |
|---|---|---|
| A1 | 21 | 89.0% |
| **B2 篩選門檻** | **12** | **79.6%** ← 五分之一的日子槽位填不滿 |
| **★G25 第四個分項** | 19 | **90.0%** ← 比 A1 還高 |

**篩選門檻是「排除」⇒ 候選變少 ⇒ 槽位閒置；第四個分項是「重排」⇒ 候選幾乎不變。**
這正好是 10/14 量到「B2 ＞ B3 因為 B3 篩太兇」的同一個機制，
只是這次它站在第四個分項那一邊。**而這也是我事前預期錯誤的原因**——
我把重點放在「可不可以抵銷」（抽象），忽略了「候選夠不夠填滿槽位」（具體且已量過）。

#### ✅ 除息診斷：這次的偏誤方向**對成長組不利**，所以未調整的數字是保守的

高成長＝低殖利率 ⇒ 10/14 擔心的是「除息拖累低成長組、製造假的成長組贏」。
用 `exdiv.py` 把股利加回個股報酬（**只能看兩組相減**，市場項才會消掉——10/15 的判斷）：

| | 未調整 | **除息調整後** | 變化 |
|---|---|---|---|
| **G25 − B2** | +0.26pp | **+0.31pp** | **+0.06pp** |
| **G25 − A1** | +0.61pp | **+0.65pp** | +0.04pp |
| G50 − B2 | +1.42pp | +1.69pp | +0.27pp |
| B2 − A1（對帳） | +0.35pp | +0.34pp | -0.02pp |

**差距變大，不是變小。** 原因是成長組持有期較長（16.5 vs 14.5 天）⇒ 吃到更多次除息
（股利提升 +0.34pp vs B2 的 +0.28pp）。疑似除息假停損：A1 1.30%／B2 1.10%／
G25 1.24%／G50 1.96%（w 越大、持有越長 ⇒ 越多）。
⇒ **10/14 標著「唯一不利的診斷」那一條，在這一題上方向是反的。**

#### 結論：不改規則，但這一則的證據強度與前八次都不同

| | |
|---|---|
| ❌ **不能說** | 「找到了，可以把成長加進 `scorer.py`」 |
| ✅ **可以說** | **「當第四個分項」顯著優於「當篩選門檻」**（78/100、p=0.000），而且 **顯著優於現行策略**（92/100、p=0.000）；反向對照乾淨（5/100）；逐年 8/9 一致；三個空頭年全勝；**除息調整後差距變大**；**而且三組 seed base × 兩份獨立快取、15 個判定全部一致**（見下方交叉驗證那節）|
| ✅ 可以說 | 機制已量到：**篩選門檻會讓五分之一的日子槽位填不滿，第四個分項不會** |
| ⚠️ **不能讀** | **w≥50% 那半邊**——均持有從 14 天變成 27~42 天，**那已經不是現行策略了**（變成「抱住高成長股」）。評估它必須用**資金曲線**（10/05 的框架），不是 per-trade alpha。**沒做。** |

**三個不改規則的理由：**

1. **這會動到 `scorer.py`——本專案從來沒有因回測改過評分邏輯**
   （唯一改過的正式參數是停損距離，而那條依據 10/16 也被推翻了）。
   動評分會讓**所有**既有數字換基準，必須先想清楚怎麼對帳。
2. **陷阱44 這次特別致命**：基本面 25% 在 2026-05 之前恆為 50
   ⇒ 被我稀釋的那個「舊總分」在樣本前後段本來就不是同一個東西
   （前段退化成 `0.40×技術 + 30`）。**而本次測的正是「稀釋舊總分再加新面」。**
   這是永久限制，修不掉。
3. **量級雖然是專案最大的，絕對值仍然小**：扣掉 0.47% 來回成本後
   A1 **-0.19% → G25 +0.42%**。那是「從明確落後指數變成小幅領先」，
   不是「會賺」。而 5 檔配置的中位 alpha 是 -0.05% → +0.68%。

**⇒ 下一步該做什麼（依價值排序）：**

1. ~~**用資金曲線重評**~~ **✅ 已完成（2026-10-18 當日）**，見下方
   「資金曲線重評」那節——**不是量尺造成的，但機制與原本以為的完全不同。**
2. ~~**把 G25 跑第二組 seed base ＋第二份快取**~~ **✅ 已完成（2026-10-18 當日）**，
   見下一節——**三份 run、15 個判定全部一致**。
3. **「成長分數」的尺度換一種做法再測一次**（例如用 YoY 的滾動百分位，
   而不是產業內橫斷面百分位）⇒ 確認結論不依賴這一個設計選擇。

#### ✅ 三份獨立 run 的交叉驗證：15 個判定全部一致（2026-10-18 當日補做）

腳本：`verify_revenue_component.py`（已進版控）。它**不做任何新測試**，
只把上面那段 5 檔配對抽出來、讓它能跑在**任意一份快取**上。

**⚠️ 為什麼需要另寫一支：** `_pf_slots_cache_market.pkl`
（`backtest_portfolio_slots.build_cache()` 建的）**沒有 `rev_rank`**——那支 builder
完全不碰月營收。但**排名只是一次 SQL 查詢**（`build_revenue_ranks()`），
貴的是逐日評分那部分 ⇒ **把排名掛上去即可，不必花 20~40 分鐘重建快取。**

| 配對 | 7000~7099<br>沙盒 `_rev_filter_cache` | 8000~8099<br>沙盒 | **9000~9099<br>★本機 `_pf_slots_cache_market`** | 判定 |
|---|---|---|---|---|
| **★★ 第四個分項(w25) vs 篩選門檻(B2)** | **+0.37pp　78/100　.000** | **+0.52pp　79/100　.000** | **+0.42pp　69/100　.000** | ✅ **3/3** |
| **第四個分項(w25) vs A1 基準** | +0.69pp　92/100　.000 | +0.71pp　90/100　.000 | +0.80pp　86/100　.000 | ✅ **3/3** |
| 篩選門檻(B2) vs A1 基準 | +0.27pp　73/100　.000 | +0.21pp　72/100　.000 | +0.38pp　79/100　.000 | ✅ **3/3** |
| **★ 反向(GC25) vs A1 基準** | -0.37pp　22/100　.000 | -0.31pp　28/100　.000 | -0.30pp　26/100　.000 | ❌ **3/3** |
| **★ 反向(GC25) vs 第四個分項** | -1.02pp　5/100　.000 | -0.97pp　1/100　.000 | -0.95pp　4/100　.000 | ❌ **3/3** |

各規則中位 alpha：A1 -0.05／-0.07／**-0.10%**；B2 +0.20／+0.20／**+0.29%**；
G25 +0.68／+0.67／**+0.65%**；GC25 -0.44／-0.37／**-0.34%**。

**★ 三份之間的差異是內部一致的，不是亂跳：** 本機那份的 B2 較強
（中位 +0.29%、vs A1 是 79/100），所以「第四個分項 vs 篩選門檻」相應變窄
（69 而非 78）。**兩個數字同向移動 ⇒ 指向同一個原因，而不是雜訊。**

**★ 與階梯那次形成對比（這點值得記）：** 10/16 測階梯時，20 條在四組 base 之間
判定翻來翻去、加到 100 條才有答案；這次 100 條在三組 base 上直接一致
——**效果量級比階梯那個大得多**（階梯的 Δ中位是 -0.11~-0.18pp，這裡是 +0.37~+0.52pp）。

#### ★ `selftest` 模式：驗「掛排名」這段程式本身（照 10/07「成對造情境」那條）

把一份**已有** rev_rank 的快取刻意拿掉 rev_rank、再從 DB 掛回去，
**兩邊逐條逐規則必須完全相同**。實測 ✅ 通過，而且腳本會另外確認
「掛排名的那段程式真的有被執行到」——否則「兩邊相同」可能只是因為它根本沒跑。

#### ⚠️ 這次驗證**沒有**排除的三件事

1. **三份 run 共用同一段 9 年歷史。** 配對設計消掉「抽到哪些股票」的運氣，
   消不掉「這 9 年剛好是什麼行情」。p=0.000 的意思仍然只是「在這段歷史上方向穩定」。
2. **兩份快取不是完全獨立。** 同一個 DB、同一套宇宙定義，
   差別只在**建構路徑**（分塊合併 vs 循序）與下面第 3 點。
3. **`build_revenue_ranks()` 直接查 `monthly_revenue`，不經過完整度守衛**
   （陷阱53）⇒ 本機的 2026-09 已重抓成 994 檔、沙盒那份仍是 176 檔。
   那個月 `avail_date` 是 10-11 ⇒ 只影響樣本最後約 3 個交易日。
   **這是兩份結果之間一個真實存在的差異，不是 bug**，但也因此
   「本機那份」算是比沙盒那份更乾淨的一次驗證。

#### 限制（引用任何上述數字時必須一起講）

1. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）⇒ 見上方理由 2
2. **未調整收盤價**（陷阱49）⇒ 分割日有假停損；而**公司行為的真實檔數是 24 檔不是 3 檔**
3. 除權息已調整（`exdiv.py`），但**絕對 alpha 仍是未調整基準**（需總報酬指數，陷阱52 的待辦）
4. 上櫃不在宇宙內；KY 股沒有月營收
5. `avail_date` 保守（營收月的次月 11 日）
6. **配對設計消掉「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」**
7. 2016~2017 已裁掉（陷阱51 限制第 5 條）

---

### 🚨 資金曲線重評：效果是真的，但**大部分不是成長資訊**（2026-10-18 當日）

**⚠️ 這一節把上一節的結論整個拆開了。** 上一節說「第四個分項顯著優於篩選門檻」
——那個方向仍然成立，但**它的機制與原本以為的完全不同**。

腳本：`backtest_revenue_component_curve.py`（已進版控）。
重用 `backtest_vs_etf.py` 的 `strategy_curve()`／`_metrics()`／`buyhold_curve()`，
不另寫一份。**順手修掉 `buyhold_curve()` 寫死 `days=1200`**（≈2023-07 起）
——那是陷阱51 那條通則**第五次**，而且會讓買進持有基準靜默只涵蓋後段。

#### ★ 為什麼非做不可：per-trade alpha 對「改變持有長度」的規則天生不公平

```
均持有天數   A1 14.8 日 → G50 32.4 → G100 46.4      （差 3.1 倍）
同期大盤     +0.97%     → +2.29%   → +4.00%          （差 4 倍）
```

**per-trade alpha 沒有除以持有長度** ⇒ 同一筆交易抱久一點，alpha 自然變大。
而 w 一拉高就是在拉長持有期（高成長股會一直續抱，因為續抱門檻也看總分）。
⇒ 總報酬與最大回檔**會正確吃到持有長度與空手時間**，是唯一公平的量尺。

#### ★ 事前預期（先寫下再跑）—— **主預期錯了**

> 「**w=50% 的 +3.31% 很可能大部分是量尺造成的。** 均持有差 2~3 倍，
> 而 per-trade alpha 沒有正規化 ⇒ 換成資金曲線後差距應該會大幅縮小。」

**結果：完全相反，差距還放大了**（G50 vs G25 中位 **+390pp**、19/20）。
⚠️ 但**真正的機制不是成長資訊**——那是靠下面那組中性對照才看出來的。

#### 結果（5 檔等權、2018-01-02 ~ 2026-10-14、20 條配對 seed 7000~7019）

| 規則 | 總報酬中位 | 5%分位 | 95%分位 | **帶寬** | 最大回檔 | 在場內 | 均持有 | 筆數 |
|---|---|---|---|---|---|---|---|---|
| **A1 基準（現行策略）** | **+73.67%** | -19.52% | +270.44% | 290pp | -44.63% | 85.7% | 14.8 | 619 |
| B2 篩選門檻 | +115.06% | +4.26% | +329.14% | 325pp | -42.96% | 85.4% | 14.8 | 615 |
| **★G25 第四個分項 w=25%** | **+244.89%** | +44.69% | +570.17% | 526pp | -40.87% | 87.7% | 17.4 | 539 |
| G35 | +317.29% | +113.83% | +705.55% | 592pp | -41.65% | 89.1% | 20.7 | 460 |
| **★G50 w=50%** | **+611.40%** | +247.16% | +5416.81% | **5170pp** | -37.99% | 91.4% | **32.4** | 302 |
| G75 | +555.77% | +122.46% | +6030.69% | **5908pp** | -37.90% | 92.4% | **42.4** | 234 |
| G100 成長取代全部 | +634.46% | +235.80% | +4625.29% | 4390pp | -36.90% | 92.6% | **46.4** | 216 |
| ★GC25 反向 | +17.90% | -22.38% | +184.63% | 207pp | -46.86% | 86.6% | 15.9 | 582 |
| **★★R50a 固定隨機成長**（中性對照①） | **+590.26%** | +192.53% | +1327.04% | 1135pp | -35.18% | 93.8% | **80.4** | **129** |
| ★★R50b 同上第二個實現 | +406.46% | +177.87% | +1226.21% | 1048pp | -38.72% | 93.9% | 77.4 | 135 |
| **★★★M50a 逐月隨機成長**（中性對照②） | **+260.51%** | +69.91% | +594.11% | 524pp | -36.40% | 88.0% | 18.0 | 521 |
| ★★★M50b 同上第二個實現 | +126.55% | +1.08% | +509.11% | 508pp | -44.19% | 87.9% | 17.9 | 526 |
| 買進持有 0050 | **+446.75%** | — | — | — | -36.38% | 100% | — | 0 |
| 買進持有 0056 | +136.96% | — | — | — | -35.47% | 100% | — | 0 |
| 加權指數（不可投資） | +353.99% | — | — | — | -31.63% | — | — | 0 |

**🚨 先看最刺眼的那一列：現行策略（A1）8.7 年中位 +73.67%，而買進持有 0050 是 +446.75%。**
這是本專案第一次在**長期資金曲線**上並列兩者。與既有結論一致
（9/24 量到全市場 per-trade alpha -0.32%、扣成本後明確落後指數），
但這個尺度上看起來更直接。

#### ★★★ 三個成分的拆解（本節的核心，而且是靠中性對照才拆得出來的）

**兩組中性對照，成長分數換成「完全沒有資訊的隨機值」、但同樣會拉長持有期：**

| 對照 | 做法 | 均持有 | 問題 |
|---|---|---|---|
| **R50**（①） | 每檔一個**固定**隨機值 | **80 天** | 值永遠不變 ⇒ 一進場就無限續抱 ⇒ **在持有長度這一維過度矯正** |
| **M50**（②） | 每 (檔, 營收月) 一個隨機值 | **18 天** | **更新頻率與真實 YoY 排名一致** ⇒ 較乾淨，但沒對齊「持續性」 |

| 配對（看總報酬） | Δ中位 | 勝場 | p | 判定 |
|---|---|---|---|---|
| ★★ w50 vs w25 | **+389.82pp** | 19/20 | 0.000 | ✅ |
| ★★ w25 vs A1 基準 | **+186.09pp** | 19/20 | 0.000 | ✅ |
| w25 vs 篩選門檻 B2 | +199.10pp | 17/20 | 0.003 | ✅ |
| ★ 反向 GC25 vs w25 | -229.80pp | 0/20 | 0.000 | ❌ |
| w35 vs w25 | +89.96pp | 14/20 | 0.115 | ⚪ |
| w75 vs w50 | -81.02pp | 8/20 | 0.503 | ⚪ |
| w100 vs w50 | -143.77pp | 8/20 | 0.503 | ⚪ |
| **★ R50a（固定隨機）vs A1** | **+493.46pp** | **20/20** | 0.000 | ✅ |
| ★★ w50 vs R50a | +60.22pp | 11/20 | 0.824 | ⚪ |
| ★★ w50 vs R50b | +212.52pp | 15/20 | 0.041 | ✅ |
| **★ M50a（逐月隨機）vs A1** | **+183.63pp** | 18/20 | 0.000 | ✅ |
| ★ M50b vs A1 | +88.84pp | 14/20 | 0.115 | ⚪ |
| **★★★ w50 vs M50a** | **+326.01pp** | **18/20** | 0.000 | ✅ |
| **★★★ w50 vs M50b** | **+438.45pp** | **19/20** | 0.000 | ✅ |
| （對照）M50a vs M50b | +105.06pp | 16/20 | 0.012 | ✅ |

**⇒ 拆解結果：**

| 成分 | 證據 | 判定 |
|---|---|---|
| **① 少換手／抱更久** | R50a（**無任何資訊**，只是抱 80 天）vs A1 = **+493pp、20/20** ⇒ 而 w50 vs R50a 是 ⚪／✅ 混合 ⇒ **「抱很久」單獨就追平了真成長** | **巨大，而且不需要月營收** |
| **② 稀釋評分門檻**（讓低分股進得來） | M50a vs A1 +184pp（18/20 ✅）但 **M50b vs A1 +89pp（14/20 ⚪）** ⇒ 兩個實現不一致，而 M50a vs M50b 本身就 16/20 顯著不同 | ⚠️ **條數不足、測不出來**（10/16 那條規矩）|
| **③ 成長資訊本身** | w50 vs M50a **+326pp（18/20）**、vs M50b **+438pp（19/20）** ⇒ **兩個實現都 ✅** | ✅ **有獨立貢獻，這一項站得住** |

#### ★ 機制：換手成本，而且這是 10/07「續抱是核心」的第二次出現

```
規則    筆數   每槽來回次數   純成本拖累（簡單加總，非複利）
A1      619      123.9        ≈ 58.2%
G25     539      107.9        ≈ 50.7%
G50     302       60.5        ≈ 28.4%
G100    216       43.1        ≈ 20.3%
R50a    129       25.8        ≈ 12.1%     ← 無資訊，但成本最低
```

**w 拉高 → 持有變長 → 換手變少 → 成本拖累從 58% 降到 20%。**
⇒ 這與 10/07 量到的「續抱 (e vs d)：換手 1,102 → 57 次、純成本拖累
-64.6% → -5.3%、Δ報酬 +169pp、20/20」**是同一件事從另一條路再次出現**。

#### ★ 回檔的配對檢定：同樣主要來自「少換手」，不是成長

| 配對（|回檔| 的差，負值＝更淺＝更好） | Δ中位 | 勝場 | p | 判定 |
|---|---|---|---|---|
| G25 vs A1 | -5.63pp | 5/20 | 0.041 | ✅ |
| **M50a（無資訊）vs A1** | **-8.79pp** | **2/20** | 0.000 | ✅ |
| **R50a（無資訊）vs A1** | **-11.46pp** | **3/20** | 0.003 | ✅ |
| G100 vs A1 | -8.01pp | 3/20 | 0.003 | ✅ |
| G50 vs G25 | -3.16pp | 7/20 | 0.263 | ⚪ |
| **G50 vs M50a** | +0.72pp | 11/20 | 0.824 | ⚪ |
| G50 vs M50b | -5.06pp | 4/20 | 0.012 | ✅ |

**無資訊的對照組回檔改善得最多（-8.8pp／-11.5pp）**，而 G50 vs M50a 是完美 ⚪
⇒ **回檔變淺來自「少換手」，與成長資訊無關。**
這與 10/07 的「回檔保護不來自停損與 10 日週期」一致，但**指向一個新的來源：換手率**。

#### 🚨 已排除：公司行為不是右尾的來源（動手查過，不是推論）

w≥50 的 95% 分位爆到 +5400%，第一個該懷疑的是陷阱49（未調整收盤價）
——持有越長，跨過減資造成的假暴漲的機會越多。實測：

```
宇宙內公司行為 26 檔次 / 24 檔（與陷阱49 修正後的數字一致）
A1    12,389 筆交易中   5 筆跨過（0.04%）
G50    6,050 筆交易中   3 筆跨過（0.05%）
G100   4,313 筆交易中   1 筆跨過（0.02%）
```

而且 ×<1（分割）那幾筆**全部吃到 -10% 停損**（停損本來就封頂），
只有一筆 ×1.52（減資）是 +61.4%。⇒ **右尾是真的複利，不是假跳動。**

#### 🚨 最嚴重的限制（新的，而且正好打在做功的那一維）

**倖存者偏誤 × 持有長度的交互作用。**

512 檔宇宙是用**全期**日均成交金額 ≥0.5 億篩出來的（9/24 的 `market_universe()`）
⇒ **期間崩掉／下市／流動性枯竭的股票根本不在裡面**。
而本次量到的主要機制正是「**持有變長**」——**持有越長，從這個偏誤受益越多。**

⇒ **成分①（少換手／抱更久）的 +493pp 有多少是真的、多少是倖存者偏誤，現有快取分不開。**
要分開必須用**點時間宇宙**（`backtest_structure_bear.py` 的 `uni_at`，逐月調整），
那是另一次重跑。**在那之前，成分① 的量級不可引用。**

#### 結論：不改規則，而且這一則讓上一節的「下一步」整個換方向

| | |
|---|---|
| ❌ **不能說** | 「月營收當第四個分項能把報酬從 +74% 拉到 +611%」——其中大部分是「抱更久」，而那一項的量級受倖存者偏誤汙染 |
| ✅ **可以說** | ① **效果不是 per-trade 量尺造成的**（我的事前預期錯了）<br>② **成長資訊在扣掉頻率對齊的隨機稀釋之後仍有獨立貢獻**（+326／+438pp，兩個實現都 ✅）<br>③ **但主要成分是「少換手／抱更久」，那個不需要月營收**<br>④ **回檔變淺完全來自少換手**（G50 vs M50a 是完美 ⚪）|
| ⚠️ 不可解讀 | 所有**絕對**數字。帶寬 290pp（A1）到 5908pp（G75），只有配對差值可讀 |

**⇒ 真正該測的下一題變了（而且更簡單）：**

1. **直接放寬續抱條件**（例如續抱門檻由 65 降到 50、或「獲利就續抱」）。
   如果主要效果來自「抱更久」，**那不需要月營收也拿得到**，而且不必動 `scorer.py`。
   10/07 已經量到續抱是整個結構裡最強的一項（+169pp、20/20）——
   **這一節是第二次指向同一個方向。**
2. **用點時間宇宙重跑**，把倖存者偏誤 × 持有長度那個交互作用拆掉。
   在那之前「抱更久」的量級不可引用。
3. **造一個「有持續性但無資訊」的隨機訊號**（例如隨機 AR(1)）。
   M50 只對齊了更新頻率，**沒對齊持續性**——真 YoY 排名有持續性
   （真成長均持有 32 天 vs M50 的 18 天），所以成分③ 的量級仍然偏高。

#### ⭐ 方法論（兩條，第一條是新的）

**(a) 「換一個量尺」與「加一個中性對照」要一起做，只做前者會得到相反的結論。**
本次換成資金曲線之後，差距**放大**（+3.31% → +390pp）⇒ 若就此收工，
會寫出「效果比 per-trade 看起來的更大」這個**方向正確但歸因完全錯誤**的結論。
真正的資訊是中性對照給的：**一個完全沒有資訊的隨機數，只要同樣拉長持有期，
就能拿到大部分的效果。**
⇒ **任何「改變了結構性參數（持有長度、換手率、部位數）」的規則，
中性對照必須在那個結構維度上與它對齊**，否則比的是兩件不同的事。

**(b) 中性對照本身要跑兩個以上的隨機實現。**
本次 M50a vs A1 是 **18/20 ✅**、M50b vs A1 是 **14/20 ⚪**，
而 M50a vs M50b 自己就 16/20 顯著不同（+105pp）
⇒ **單一隨機實現的噪音，大到足以決定一個配對的判定。**
這是 10/16「換 seed base 判定會翻 ⇒ 條數不足」那條規矩在**對照組構造**上的版本：
不只 seed 要換，**對照組的隨機實現也要換**。
本次 ③（成長資訊）之所以站得住，正因為它在兩個實現上都 ✅。

#### 🚨 跑這支腳本時踩到的沙盒限制（記下來，不然下次又會以為「跑很久」）

| 現象 | 真因 |
|---|---|
| 背景程序跑到第 5~6 條規則就**無聲消失**，log 沒有任何錯誤 | 沙盒的背景程序約 **10 分鐘**就會被砍。9 條規則 × 100 條 seed 一次跑完必然超過 |
| 第一版更早就死 | **預先建好 9 份 growth 快取**（每份 512 檔 × 2000 日的 dict）把 3.9GB 記憶體吃光 ⇒ OOM，同樣無聲 |

**處置：** ① growth 快取改成用到才建、用完 `del`；
② 配對段拆成**一條規則一個獨立程序**、結果存 `/tmp/pair_{規則}_{seedbase}.pkl`，最後合併。

**⭐ 通則：背景程序「跑很久沒輸出」要先確認它還活著**（`ps` / `pgrep`），
不要直接等。本次連續兩次在相近位置消失，就是「被砍」而不是「在算」的指紋
——**兩次死在同一個進度**，真正在算的程序不會這麼巧。
這與陷阱51 那條「零結果會被印成什麼？」同一族：
**失敗必須長得跟成功不一樣，而「被外力砍掉」是唯一無法由程式自己印出來的失敗**
⇒ 只能靠「死在同一個地方」這個外部跡象認出來。

---

### 🚨 用空頭樣本拆解「結構」：續抱是核心，而「回檔小」檢不出來（2026-10-07）

**⚠️ 這一節推翻了 2026-10-05 的主要結論。** 那次寫著
「**回檔穩定小很多，而且這一項不依賴選股**⇒ 這是整個系統目前最站得住腳的性質」，
並明載「⚠️ 該優勢目前是推論，不是實測——樣本裡完全沒有空頭」。
回填 2018 之後第一次能實測，而**同持股數的配對對照下它消失了**。

腳本：`backtest_structure_bear.py`（已進版控）。

#### 為什麼刻意不用評分（不是偷懶）

> **✅ 2026-10-16 已用修好的 `pref` 重跑完畢（`sorted(close)` 一次指派）。**
> 舊版是**懶惰指派**（`if code not in pref: pref[code] = rnd.random()` 寫在
> 被 `len(held) < SLOTS and mkt_ok` 擋著的進場分支裡）⇒ **空手型規則
> （g/h/i、淨值 j~m）跳過的日子與滿倉型不同，加上 `uni_at` 是逐月調整的宇宙
> ⇒ 配對隨時間逐漸失效，而且完全不報錯。**
>
> **重跑結果——壓倒性的全部保留，而小效果的有兩欄翻了：**
>
> | 配對 | 舊（懶惰指派） | **新（sorted）** | |
> |---|---|---|---|
> | 續抱 Δ報酬 | +126pp　19/20 | **+169pp　20/20** | ✅ 不變（更強）|
> | 真D vs 真C（兩指標） | 0/20　0/20 | **0/20　0/20** | ✅ 完全不變 |
> | ≥4 vs ≥2・連2日確認 | 20/20 | **20/20** | ✅ 不變 |
> | **🚨 真C vs 基準 Δ\|回檔\|** | **-1.00pp　✅15/19　p=.019** | **-0.00pp　⚪8/17　p=1.000（平手3）** | **翻了：顯著 → 完美 null** |
> | **🚨 代理：出清 vs 停買 Δ報酬** | +7.96%　⚪11/20　p=.82 | **-30.90%　❌3/20　p=0.003** | **翻了：⚪ → 顯著更差** |
> | 代理：出清 vs 停買 Δ\|回檔\| | -8.77%　✅18/20 | **-3.11%　✅15/20　p=0.041** | ⚠️ 仍顯著但**幅度減半** |
> | 整套結構 vs 買進持有（兩指標） | +0.43%　⚪10/20 | **-0.52%　⚪11/20　p=0.824** | ✅ 結論不變 |
>
> **⚠️ 兩個必須一起講的限制：**
> ① 重跑的期間是 **2018-01-02 ~ 2026-10-15（2,133 日）**，舊版是 10-08（2,129 日）
> ⇒ **差異不能全部歸給 `sorted()` 修正**，多出的 4 個交易日也有份。
> ② 10/07 那張表的「**空手・停買 (g vs e)**」（-4.10%、✅15/20、p=.041）
> **無法重跑**——10/08 改版時那個配對已從 `PAIRS` 移除（換成淨值版的真C）。
> 它最接近的對照就是上表那個**翻成完美 null** 的真C。
>
> **⭐ 這次重跑本身就是「p≈0.02~0.05 不穩」那條通則的第二次實證**：
> 三個小效果裡兩欄翻向、一欄幅度減半，而四個壓倒性結果一個都沒動。
> 同族的 bug 在 `backtest_market_ladder.py` 上造成「頭條結論互換」，
> 完整記錄見十五章「階梯的第二次驗證」那節的 `sorted()` 那段。


實查 2018~2024：`prices` ✅ 完整；**`chips`／`fundamentals`／`market_margin`／
`futures_institutional` 全部 0 天**。⇒ 個股評分會退化成 `0.40×技術面 + 30`
（要達總分 65 需技術面 ≥87.5，9/17 那個問題的極端版），大盤 S3/S4/S10 全缺、
階梯根本算不出來。**而 10/05 的「代號」對照已證明回檔小不依賴選股
⇒ 測結構就好，結構只需要價格。**

#### 設計：九組，只差三個維度（到期規則／停損／大盤空手）

| | 到期 | 停損 | 大盤 |
|---|---|---|---|
| (a) 買進持有 5 檔 | 無 | ❌ | — |
| (b) 無條件10日換倉 | 無條件 | ❌ | — |
| (c) 只有 10% 停損 | 無 | ✅ | — |
| (d) 無條件換倉＋停損 **⚠️不是現行策略** | 無條件 | ✅ | — |
| **(e) 續抱代理＋停損** | **獲利就續抱** | ✅ | — |
| (f) 續抱代理、無停損 | 同上 | ❌ | — |
| **(g) (e)＋MA60 停買** | 同上 | ✅ | **≈策略C** |
| **(h) (e)＋MA60 出清** | 同上 | ✅ | **≈策略D** |
| (i) (e)＋MA20 停買 | 同上 | ✅ | robustness |

**續抱代理 = 「到期時若仍獲利就不換股」**（現行是「評分 ≥65 就續抱」，但算不出評分）。
續抱時**只重設計時起點，不動 `entry_px` 與 `stop`**——與 `renew_position()` 一致（陷阱47）。
**MA60／MA20 是「大盤評分 <45」的代理，不等價**：能回答「空手這個動作有沒有用」，
**不能**回答「現行那條規則的刻度對不對」。

#### ⭐ 關鍵方法：配對比較（本節最重要的技術貢獻）

**同一個 seed 在所有規則之間用的是同一組隨機偏好**（`random.Random(seed)` 只決定
排序鍵、與規則無關）⇒ `runs[A][s]` 與 `runs[B][s]` 面對**完全相同的選股順序**
⇒ **差額只來自規則本身，共同的運氣成分被消掉。** 判準用符號檢定（不依賴分布假設）。

**這是 2026-09-17「比較多組前先算雜訊帶」的強化版**：雜訊帶防的是「把雜訊當訊號」，
配對設計是**直接把那個雜訊消掉**。

**⚠️ 而且它解釋了為什麼第一版（6 條）什麼都讀不出來——事前就該算這個數字：**

```
 6/6 全勝 → p = 0.031   ← 必須全勝才勉強過關
 5/6      → p = 0.219   ← 等於什麼都沒說
15/20     → p = 0.041   ← 20 條才有容錯空間
```

**⇒ 條數不足時，問題不是「帶寬太寬」而是「檢定力為零」。
日後跑多組對照，先算「N 條之下最小可檢出的勝場數」再決定要跑幾條。**

#### 結果（全期間 2018-2026，20 條配對）

| A vs B | Δ報酬 | | Δ\|回檔\| | |
|---|---|---|---|---|
| **續抱 (e vs d)** | **+126.35%** | ✅19/20 p<.001 | **-11.77%** | ✅17/20 p=.003 |
| 空手・停買 (g vs e) | -42.42% | ⚪7/20 p=.26 | -4.10% | ✅15/20 p=.041 ⚠️**無法重跑**（10/08 已從 PAIRS 移除）|
| 空手・出清 (h vs e) | -58.66% | ❌4/20 p=.012 | -12.07% | ✅17/20 p=.003 |
| **出清 vs 停買（D vs C）** | +7.96% | **⚪11/20 p=.82** | **-8.77%** | ✅18/20 p<.001 |
| 　└ 🚨 **10/16 重跑** | **-30.90%** | **❌3/20 p=.003（翻向）** | **-3.11%** | ✅15/20 p=.041（幅度減半）|
| MA20 vs MA60 | +8.17% | ⚪11/20 | **+0.04%** | ⚪10/20 p=1.00 |
| **整套結構 vs 買進持有 (e vs a)** | -27.08% | **⚪8/20 p=.50** | **+0.43%** | **⚪10/20 p=1.00** ✅10/16 重跑仍 ⚪（-0.52%、11/20、p=.824）|

**① 續抱確認，是整個測試最強的結果。** 中位 +126pp、報酬 19/20、回檔 17/20，
**2022 完整空頭年也成立**（報酬 18/20、回檔 18/20）。機制是算術不是統計：

```
(d) 無條件換倉  換手 1,102 次  純成本拖累 -64.6%   全期 -16.63%
(e) 續抱代理    換手    57 次  純成本拖累  -5.3%   全期 +127.79%
```

成本解釋約 59pp；而扣掉成本後 (f) vs (b)（兩組都無停損、只差到期規則）
毛淨值仍是 1.90 vs 1.32 ⇒ **不只省成本，確實也避開了「砍掉正在漲的那幾檔」**
（同日量到 87 檔自選股裡 **5 檔（6%）決定整體結果**）。
唯一反例：2020 的回檔 ❌4/20（+2.72pp）——V 轉急殺時續抱會抱住正在崩的部位。

**② 空手買到的是回檔、不是報酬。而且完整空頭年「停買」不夠、必須「出清」。**

| 空頭年 Δ\|回檔\| vs (e) | 2018★ | 2020★（V轉） | **2022★（完整空頭年）** |
|---|---|---|---|
| 只停買 (g) | ✅19/20 -3.79 | ✅20/20 -7.80 | **⚪14/20 p=.115** ← 測不出來 |
| 出清 (h) | ✅20/20 -13.99 | ✅20/20 -21.50 | ✅19/20 **-15.22** |

機制：**停買只能讓倉位慢慢空出來**（要等到期或停損釋出，續抱還會留住獲利的），
緩跌盤來不及；**出清是立即的**。
⇒ **現行規則是停買（策略C 明文「不因大盤轉弱出場」），而 2022 說那在緩跌盤幾乎沒用。**

**🔄 ③ 出清（≈D）沒有付出可檢出的長期報酬代價——與十五章方向相反。**

全期間報酬 **11/20、p=0.82**（分不出來），回檔卻 ✅18/20 改善 8.77pp；
2018／2022 連報酬都是 ✅（+9.24%、+6.95%）。
**⚠️ 不能說推翻十五章「D 在多頭是錯殺」**：觸發條件不同（MA60 vs 大盤淨值 ≥2），
且那組是自選股上的 per-trade alpha（含後見之明，9/24）。
但這是**第一個長歷史、全市場、組合層級**的證據，方向相反 ⇒ **那條結論值得重測。**

**🚨 ④ 整套結構 vs 買進持有 5 檔：報酬與回檔雙 ⚪ ——「回檔小」檢不出來。**

(a) 是最乾淨的對照：同樣 5 檔、同樣隨機排序、**同一個 seed**，唯一差異是
「有沒有停損和換股」。結果 Δ|回檔| **+0.43%、10/20、p=1.000**。

```
8 年最大回檔：  (e) 47.4%    (a) 什麼都不做 45.6%    0050 36.4%
```

10/05 量到的「策略 9.59% vs 0050 15.88%」是 **107 天、一條曲線、
而且拿 5 檔等權去比 50 檔市值加權**（不是同一件事）。
⇒ **結構的回檔保護要空手才有（而且要出清）；停損與 10 日週期本身，貢獻檢不出來。**

**⑤ Robustness 完美 null**：MA20 換 MA60，Δ|回檔| **+0.04%、10/20、p=1.000**
⇒ 結論完全不依賴 MA 長度這個參數。

#### 🚨 兩個顯示層錯誤（都讓結論完全顛倒，數字算對了但讀出來是反的）

**錯誤一（第一版）：核心表的符號標籤寫反。** 原本寫「負值 = 回檔更小（更好）」，
但**回檔本身是負數**：`-39.07 − (-28.15) = -10.9pp` 實際代表**深了** 10.9pp＝更糟。
⇒ 改為顯示 `|回檔| 的差`（正值 = 更深 = 更糟）並直接標 ✅/❌。

**錯誤二（第三版，合成資料測試抓到）：符號檢定把「平手」算成「輸」。**
MA20 與 MA60 在合成資料上完全相同（Δ=0）⇒ `x > 0` 全為 False ⇒ `0/20, p=0.000`
⇒ **把「沒有差異」印成「顯著更差」**。標準符號檢定本來就丟掉平手、只數有向配對。
⇒ 改為排除平手、另列平手數，並以 ✅/❌/⚪ 三態呈現。

> **⭐ 通則：呈現「差異」時，若原始量本身帶符號、或可能恰為零，
> 一定要改成絕對值差、或直接標 ✅/❌/⚪，不要讓讀者自己推符號。**
> 這與陷阱30（相對日期用字寫死）同一族——**都是顯示層的語意錯誤：
> 數字是對的，但讀出來的結論是反的。** 而這類錯誤**單元測試抓得到**：
> 本次錯誤二就是靠合成資料（刻意造出 Δ=0 的情境）發現的。

#### 另一個標籤錯誤：把 (d) 標成「＝現行結構」

第一版的 (d) 漏了**續抱**與**空手**兩個要素。證據：**換手 1,102 次**
（8 年 2,128 日 ÷ 10 日 × 5 檔 ≈ 1,060）——實際策略因續抱遠低於此（57 次）。
⇒ 改名「無條件換倉（⚠️ 不是現行策略）」並新增 (e)(f)。
**通則：給對照組命名時，要逐條列出現行規則並核對，不能憑印象說「這組≈現行」。**

#### 限制（引用任何上述數字時必須一起講）

1. **除權息無法調整**（陷阱50）。對「回檔比較」影響較小（各組程度相似），
   但**所有報酬都被系統性低估**，買進持有被低估最多（持有期最長）。
2. 測的是**結構**，不是現行完整策略——後者還有大盤階梯與評分門檻，
   而那兩者在 2018~2024 算不出來。
3. 排序鍵是**真隨機** ⇒ 這些數字**完全不含選股效果**（刻意如此）。
4. 5 檔等權、每日再平衡、現金不計息。(a)~(f) 永遠滿倉 96%；(g)~(i) 會空手。
5. **配對設計消掉的是「抽到哪些股票」的運氣，消不掉「這 9 年剛好是什麼行情」**
   ⇒ p<0.05 的意思是「在這段歷史上方向穩定」，**不是**「換一段歷史也成立」。
6. 所有組都遠輸 0050（+456.69%）。主因是 **5 檔等權 vs 市值加權**
   （10/05 量到 513 檔等權前段 +36.78% vs 市值加權 +75.63%，差 39pp 來自台積電權重），
   加上兩邊都沒計股利。

#### 下一步（依價值排序，都還沒做）

1. **重測十五章的策略D**。本節量到「出清沒有可檢出的長期報酬代價」，
   與那條結論方向相反。要用同一套觸發條件（大盤淨值）＋全市場＋配對設計重跑。
2. **重新檢視「5 檔上限」**。2026-09-17 測過，當時結論是「效果不在現有評估框架內」；
   現在框架有了（配對 + 資金曲線 + 空頭樣本），而答案指向
   **它的尾部保護被自己的集中度吃掉**。該測 10／20／30 檔。
3. **停損 10% 要在空頭樣本上重驗**。8/27 那次校準是自選股（倖存者偏誤）＋全多頭，
   而本節量到 (c) 單獨的停損在多數年份貢獻極小、(f) 無停損與 (e) 有停損全期分不出來。

---

### 🚨 策略D 第一次用真觸發條件重測：否決，而且是專案最乾淨的一次（2026-10-08）

**要驗證的問題：** 十五章長年寫著「D 在多頭是錯殺、在空頭是保命」，但那條結論的
兩半都有問題——多頭那半是 176 筆時代的自選股 per-trade alpha（含後見之明，9/24），
空頭那半只有 2026-07 兩週，而 2026-08 重跑確認**那兩週淨值從未達 +2，根本不是大盤轉空**。
而 10/07 的 MA60 代理測出「出清沒有可檢出的長期報酬代價」，**方向與文件相反**。

**設計：把 10/07 的結構測試只換一個東西**——市場觸發條件從 MA60 換成**真正的大盤淨值**，
其餘（續抱代理、10% 停損、5 檔、真隨機排序、同一 seed 配對）完全不動。
⇒ Δ 直接回答「真 D 有沒有代理那麼好」。13 組規則 × 20 條配對、2018-01-02 ~ 2026-10-08。

> **✅ 2026-10-16 已用修好的 `pref` 重跑完畢（`sorted(close)` 一次指派）。**
> 舊版是**懶惰指派**（`if code not in pref: pref[code] = rnd.random()` 寫在
> 被 `len(held) < SLOTS and mkt_ok` 擋著的進場分支裡）⇒ **空手型規則
> （g/h/i、淨值 j~m）跳過的日子與滿倉型不同，加上 `uni_at` 是逐月調整的宇宙
> ⇒ 配對隨時間逐漸失效，而且完全不報錯。**
>
> **重跑結果——壓倒性的全部保留，而小效果的有兩欄翻了：**
>
> | 配對 | 舊（懶惰指派） | **新（sorted）** | |
> |---|---|---|---|
> | 續抱 Δ報酬 | +126pp　19/20 | **+169pp　20/20** | ✅ 不變（更強）|
> | 真D vs 真C（兩指標） | 0/20　0/20 | **0/20　0/20** | ✅ 完全不變 |
> | ≥4 vs ≥2・連2日確認 | 20/20 | **20/20** | ✅ 不變 |
> | **🚨 真C vs 基準 Δ\|回檔\|** | **-1.00pp　✅15/19　p=.019** | **-0.00pp　⚪8/17　p=1.000（平手3）** | **翻了：顯著 → 完美 null** |
> | **🚨 代理：出清 vs 停買 Δ報酬** | +7.96%　⚪11/20　p=.82 | **-30.90%　❌3/20　p=0.003** | **翻了：⚪ → 顯著更差** |
> | 代理：出清 vs 停買 Δ\|回檔\| | -8.77%　✅18/20 | **-3.11%　✅15/20　p=0.041** | ⚠️ 仍顯著但**幅度減半** |
> | 整套結構 vs 買進持有（兩指標） | +0.43%　⚪10/20 | **-0.52%　⚪11/20　p=0.824** | ✅ 結論不變 |
>
> **⚠️ 兩個必須一起講的限制：**
> ① 重跑的期間是 **2018-01-02 ~ 2026-10-15（2,133 日）**，舊版是 10-08（2,129 日）
> ⇒ **差異不能全部歸給 `sorted()` 修正**，多出的 4 個交易日也有份。
> ② 10/07 那張表的「**空手・停買 (g vs e)**」（-4.10%、✅15/20、p=.041）
> **無法重跑**——10/08 改版時那個配對已從 `PAIRS` 移除（換成淨值版的真C）。
> 它最接近的對照就是上表那個**翻成完美 null** 的真C。
>
> **⭐ 這次重跑本身就是「p≈0.02~0.05 不穩」那條通則的第二次實證**：
> 三個小效果裡兩欄翻向、一欄幅度減半，而四個壓倒性結果一個都沒動。
> 同族的 bug 在 `backtest_market_ladder.py` 上造成「頭條結論互換」，
> 完整記錄見十五章「階梯的第二次驗證」那節的 `sorted()` 那段。


**⭐ 這次先寫下事前預期再跑**（照策略F 那次的慣例）：
「真 D 的空頭保護會遠弱於 MA60 代理，因為淨值在 2022 的觸發率是九年最低。」
**預期方向正確，但嚴重低估程度——實際是完全相反，不是『較弱』。**

#### 結果（全期間 2018-2026，20 條配對）

| | 全期報酬 | 最大回檔 | 換手 | 在場內 |
|---|---|---|---|---|
| (j) 淨值≥2「停買」＝**真C** | **+142.90%** | -45.48% | 52 | 96% |
| (k) 淨值≥2「出清」＝**真D** | **-72.65%** | **-76.50%** | **1,967** | 67% |
| (l) 淨值≥4「出清」＝UI紅框 | -23.70% | -55.37% | 1,054 | 87% |
| (m) 淨值≥2 連2日確認出清 | -8.77% | -54.75% | 1,004 | 85% |
| (e) 基準（不看大盤） | +123.97% | -46.47% | 57 | 96% |
| (h) MA60「出清」【代理】 | +73.42% | **-35.05%** | 396 | 66% |
| (a) 買進持有 5 檔 | +143.48% | -45.50% | 0 | 96% |

**配對比較（同一 seed 同一組排序）：**

```
★★真D vs 真C         Δ報酬 -209.82%  ❌ 0/20 p<.001   Δ|回檔| +33.08%  ❌ 0/20 p<.001
★★真D vs MA60代理D    Δ報酬 -137.05%  ❌ 0/20 p<.001   Δ|回檔| +39.01%  ❌ 0/20 p<.001
  ≥4 vs ≥2           Δ報酬  +50.75%  ✅20/20          Δ|回檔| -20.95%  ✅20/20
  連2日確認 vs ≥2      Δ報酬  +61.86%  ✅20/20          Δ|回檔| -22.99%  ✅20/20
  真C vs 基準          Δ報酬   +5.98%  ⚪12/20 p=.50    Δ|回檔|  -1.00%  ✅15/19 p=.019
  🚨 以上「真C vs 基準」那一列已被 10/16 的重跑推翻 ⇒ Δ|回檔| -0.00%、⚪8/17、p=1.000
```

**兩個指標、20 條配對、全部 0/20。這是本專案至今最乾淨的否定結果。**
三個空頭年也全部更糟（2018 -21.8%／2020 -16.8%／2022 -35.6%）。

#### ★ 機制：淨值≥2 是「高頻閃動」的訊號

決定性的對照——**同樣的空手時間，換手差 5 倍：**

```
(h) MA60 出清   在場內 66%　換手   396 次　純成本拖累 -31.2%
(k) 真D  出清   在場內 67%　換手 1,967 次　純成本拖累 **-84.3%**
```

淨值≥2 在 2,129 天裡觸發 641 天（30%）但**不連續**——每閃一次就把 5 檔全出清再買回。
**-84.3% 的純交易成本幾乎解釋了全部的 -72.65%。**
而兩個降低閃動的做法（≥4、連2日確認）都大幅改善 ✅20/20，但**仍然全部是負的**。

#### 🚨 更根本的原因：大盤淨值不是空頭偵測器，是過熱偵測器

`compare_market_net.py` 量出的逐年觸發率：

| 年 | net≥2 | net≥4 |
|---|---|---|
| **2022（唯一真空頭年 -22.6%）** | **20.7% ← 九年最低** | **3.7% ← 九年最低** |
| **2026（+70% 大多頭）** | **40.8% ← 九年最高** | 13.6% |
| 三個★空頭年平均 | 27.3% | 8.3% |
| 其他六年平均 | **32.0%** | **10.3%** |

**它在最糟的那一年叫得最少，在最好的那一年叫得最多。**

原因看組成就知道：系統的「偏空」訊號大多是**過熱類**（BIAS 過高、`pos_250` 偏高、
融資急增），那些東西在**市場強勢上漲時**才觸發。
**這與 2026-09-23 量到「大盤評分方向性 52.7% 輸給每天猜漲 55.9%、強訊號 47.8% 更差」
是同一件事的兩個角度**——而這次看得出機制。

這也解釋了為什麼 **真C（停買）在 2022 完全沒作用**：
Δ報酬 +0.00%、Δ|回檔| -0.00%、20 條裡 5 條平手。觸發率最低的那一年，停買幾乎沒啟動。

#### 結論與已執行的動作

| | |
|---|---|
| **真 D（依淨值出清）** | **否決。** 不是「代價較大」，是 9 年兩個指標全 0/20 更糟 |
| **真 C（依淨值停買）** | ❌ **原記「回檔改善 1.00pp（✅15/19 p=.019）」已被 10/16 修 `sorted()` 後的重跑推翻 ⇒ -0.00pp、⚪8/17、p=1.000（平手3）＝完美 null。** 連「極小但顯著」都不成立；2022 有 10/20 平手（觸發率最低那年幾乎沒啟動）|
| **UI 的減碼警報** | **全部改為「這一級不構成出場理由」**，詳見陷阱48 的後續 |
| **MA60 出清** | 回檔最小（全期 -35.05%、三空頭年 19.7/12.5/15.5% 全最小），但報酬輸真C。**這是今天才出現的新候選規則，不在現行系統裡** |

#### ⭐ 方法論收穫（兩點，第一點最重要）

**(a) 代理測試的結論，不保證轉移到真訊號上——而且可能方向相反。**
10/07 用 MA60 代理得到「出清沒有可檢出的報酬代價、回檔改善 8.77pp」，
看起來像是在支持 D。但 MA60 **真的在追蹤空頭**（跌破月季線就是空頭），
而大盤淨值**在空頭年觸發最少**。兩者只是「都叫做大盤濾網」，行為完全不同。
⇒ **用代理做測試時，必須另外檢查「代理與真訊號的行為相不相似」**，
不能因為兩者語意上都叫「大盤轉空」就假設可以互換。
本次的檢查方法極便宜：**比對兩者的逐年觸發率**（MA60 在空頭年高、淨值在空頭年低）。

**(b) 「在場內比例」相同不代表「交易頻率」相同。**
(h) 與 (k) 的在場內都是 66~67%，看起來像同一種東西，但換手差 5 倍。
⇒ **評估任何「空手型」規則時，在場內比例與換手次數必須一起看**——
前者決定你吃到多少市場報酬，後者決定你付多少成本，而兩者可以完全脫鉤。

#### 限制（引用任何上述數字時必須一起講）

1. **除權息無法調整**（陷阱50）⇒ 所有報酬系統性低估，持有期長的被低估最多
2. 測的是**結構**，不含評分門檻與大盤階梯（基本面 2026-05 前永久缺，陷阱44）
3. 排序鍵**真隨機** ⇒ 完全不含選股效果（刻意如此）
4. 配對消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**
5. **2016~2017 不可用**：S2/S3/S4 只回填到 2018-01-01，那兩年只有 5 個訊號在跑、
   淨值天生偏小（實測 max 僅 3，2018+ 是 8~11）。回測起點必須 ≥ 2018-01-01

---

### 🚨 停損距離在空頭樣本上的重驗：8/27 那次的峰值是樣本造成的（2026-10-16）

**⚠️ 這一節推翻了本專案唯一一條「因回測而變更的正式規則」的依據。**
規則本身（10%）**維持不變**，但理由從「alpha 在 10% 見頂」改成
「**八個距離都分不出來，所以維持現狀**」——那是完全不同性質的結論。

腳本：`backtest_stop_distance.py`（已進版控）。

#### 為什麼要重跑：8/27 那次的兩個問題都是之後才發現的

| | 問題 | 何時發現 |
|---|---|---|
| ① | 跑在**自選股**上 ⇒ 倖存者偏誤。同一套規則自選股 alpha **+2.44%** vs 全市場 **-0.32%** | 2026-09-24 |
| ② | 樣本**全在多頭**（2024-07~2026-08 指數 +102%）。而那節自己寫著「真的崩盤時 10% 會比 8% 每檔多賠 2pp，**從未驗證**」 | 2026-10-06/07 回填 2018 後才能驗 |

**設計：只動一個維度。** 給既有 `simulate()` 加 `stop_ratio=None` 參數
（預設 ⇒ 與改版前**位元級相同**，不需對帳——「不要有第二份實作」那條通則），
其餘（大盤階梯、65 分門檻、續抱、10 日週期、5 檔、真隨機排序、同一 seed 配對）全不動。

**★ 內建對帳點：** `★10%` 那一組跑出 **15,176 筆、alpha +0.31%**，
與 10/14 的 `A0 現行策略`、10/15 的 `C 現行 UI 階梯` **完全相同**
⇒ `stop_ratio=0.90` 與 `STOP_LOSS_RATIO` 位元級一致。
⚠️ **2026-10-22 更正（陷阱56）：只在同一份快取內成立**，跨 session
重建會得到 15,221／+0.24%（大盤淨值因 FMTQIK 回溯改寫而變）。

#### ★ 事前預期（先寫下再跑）—— 兩半都對了

> 主預期：**alpha 的峰值會從 10% 往外移，或整條曲線變平測不出來。**
> 理由：10/07 的結構測試已量到「只有停損那組在多數年份貢獻極小」、
> 「無停損 vs 有停損全期分不出來（10/20、p=1.000）」。
> **我認為「測不出來」機率更高。**
> 反方向的可能：空頭年會把寬停損罰得比多頭重 ⇒ 若 2018／2022 出現
> 「越寬越差」，那就是 8/27 因為沒有空頭樣本而**系統性高估了寬停損**。

| 預期 | 結果 |
|---|---|
| 測不出來 | ✅ **對**（全距 0.10pp ＜ 雜訊帶 0.28pp；配對五對全 ⚪）|
| 「反方向」：空頭年偏好較緊 | ✅ **對，而且逐年看非常乾淨**（見下）|

#### ① per-trade（不限檔數 ⇒ 排序無關、確定性、n 最大）

| 停損 | 筆數 | 報酬 | 同期大盤 | **alpha** | 扣成本 | 停損率 | 勝率 | **最大單筆** |
|---|---|---|---|---|---|---|---|---|
| 8%（舊值） | 15,450 | +1.15% | +0.91% | +0.24% | -0.23% | 22.7% | 41.5% | -8.0% |
| **★10%（現行）** | 15,176 | +1.26% | +0.96% | **+0.31%** | -0.16% | 14.4% | 42.9% | -10.0% |
| 12% | 15,070 | +1.33% | +0.99% | **+0.34%** | -0.13% | 9.3% | 43.6% | -12.0% |
| 15% | 15,014 | +1.33% | +1.02% | +0.31% | -0.16% | 5.1% | 43.9% | -15.0% |
| 25% | 14,985 | +1.33% | +1.04% | +0.30% | -0.17% | 0.7% | 44.0% | -25.0% |
| 幾乎不停損 | 14,983 | +1.31% | +1.04% | +0.27% | -0.20% | 0.0% | 44.0% | **-90.5%** |

```
六組 alpha 全距 0.10pp　vs 雜訊帶 0.28pp（從現行組重抽 n=14,983、600 次）
⇒ ⚪ **不可解讀**
```

> 🚨 **上表 `最大單筆` 那一欄的 `幾乎不停損 -90.5%` 是錯的**，正確值是 **-49.0%**
> ——那筆 -90.5% 是 1:10 分割造成的假崩盤（陷阱49）。詳見下方「已解開」那節。
> **有停損的三組（-8.0／-10.0／-15.0%）不受影響**，因為停損本來就封頂。

**⚠️ 而且扣掉 0.47% 來回成本後六組全是負的（-0.13% ~ -0.23%）**
——這張表比的是「哪一組虧得少一點」。

#### ✅ 跨快取交叉驗證（使用者本機的 `_pf_slots_cache_market.pkl`）—— 每個判定都一致

照 2026-10-16 立的規矩（結論要在兩份獨立快取上跑過）：

| | 沙盒 `_rev_filter_cache` | **本機 `_pf_slots_cache_market`** |
|---|---|---|
| 六組 alpha 全距 | 0.10pp | **0.09pp** |
| 雜訊帶 | 0.28pp | **0.26pp** |
| 判定 | ⚪ | **⚪ 相同** |
| 2018 空頭年 | +0.39 → +0.18（單調遞減）| **+0.40 → +0.20 相同** |
| 2026 大多頭 | +0.22 → +0.77（單調遞增）| **+0.27 → +0.80 相同** |
| 三空頭年峰值 | 10%（+0.51%）| **10%（+0.51%）相同** |
| 其他六年峰值 | 12%（+0.28%）| **12%（+0.27%）相同** |
| **幾乎不停損最大單筆** | **-90.5%** | **-90.5% 完全相同** |

⇒ **唯一站得住的那條結論（停損不能拿掉）在兩份快取上是同一個數字。**

⚠️ 兩份快取的筆數略有不同（★10% 組 15,176 vs **15,169**），所以
「`★10%` 跑出 15,176 筆 ⇒ 與 10/14 的 `A0 現行策略` 完全相同」那個對帳點
**只在沙盒那份成立**。這代表兩份快取的宇宙／價格涵蓋有微小差異，
**不影響任何判定**（全距與雜訊帶都算在各自那份內）。

#### ✅ 已解開：`最大單筆` 那一欄有兩個獨立問題，而且**第二個推翻了本節的結論數字**

使用者在本機跑診斷指令，一次就定位了：

```
超過下限 3 筆
2454  2026-09-18 → 2026-10-15  -11.57  回測結束
2408  2026-09-22 → 2026-10-15  -11.57  回測結束
6805  2026-10-02 → 2026-10-15   -8.44  回測結束
```

**🚨 問題一：`收尾` 用 `prices[-1]`，而那根K可能在 `tpx_dates` 之外。**

```python
# simulate() 最後
for code, pos in held.items():
    last = stocks[code]['prices'][-1]      # ← 該檔在快取裡的最後一根K
    pos.update(exit_reason='回測結束', pnl=(last['close'] - ep) / ep * 100)
```
主迴圈只跑 `for d in cache['tpx_dates']`，而**出場日 2026-10-15 比
`tpx_dates[-1]`（2026-10-14）晚一天** ⇒ 那根K從來沒有進過停損檢查。

| | `tpx_dates[-1]` | 個股價格超出它的檔數 |
|---|---|---|
| 沙盒 `_rev_filter_cache` | 2026-10-14 | **0 / 512** ⇒ 重現不出來 |
| 本機 `_pf_slots_cache_market` | 2026-10-14 | **＞0** ⇒ 出現 |

**⚠️ 刻意不修 `simulate()`。** 改 `收尾` 會動到 148~154 筆「回測結束」交易，
**所有既有基準的位元級一致性就斷了**（10/14、10/15、10/16 三次都靠
「15,176 筆、alpha +0.31%」對帳）。而這個偏差只影響**最後一根K的一天**、
且只影響仍持有的部位 ⇒ 改報告比改模擬划算。
**⇒ `最大單筆` 這一欄日後要排除 `回測結束`，或至少標註。**

#### 🚨 問題二（更嚴重）：`幾乎不停損` 的 -90.5% 是**假崩盤**，不是真虧損

順手查「無停損」那組最差 6 筆，全部是 `持滿10日`（經過完整檢查），
但**價格路徑一看就不對**：

```
4763   885.00 → 90.50   單日 -89.8%   而且 06/18 → 06/30 中間空白 12 天
8422   250.00 → 24.70   單日 -90.1%   11/05 → 11/17 空白 12 天
2327   546.00 → 143.00  單日 -73.8%   08/13 → 08/25 空白 12 天
2540   150.00 → 80.00   單日 -46.7%   09/16 → 09/19 空白 3 天
```

**`4763` 是精確的 ×10.0 ⇒ 1:10 分割。那段空白正是分割換發的停止交易期間。**

#### 🚨🚨 連帶揭穿：陷阱49 的全表掃描漏掉 **81%** 的公司行為

陷阱49 寫著「相鄰交易日 |漲跌| ＞30%，**排除跨多日缺口**」，
而**分割／減資換發必然伴隨停止交易** ⇒ 那個排除條件正好濾掉最典型的案例。

實測同一組 512 檔宇宙、2018 起、比值落在 `[0.65, 1.5]` 之外：

| | 檔次 |
|---|---|
| 陷阱49 的條件（gap ≤7 天）抓到 | **5**（1808、2540×2、2603、6669）|
| **被「排除跨多日缺口」濾掉的（gap >7 天）** | **21** |
| 合計 | **26 檔次 / 24 檔** |

⇒ **陷阱49 說「510 檔宇宙內只有 3 檔」，真實是 24 檔——低估 8 倍。**

**★ 而且兩個方向都有，這點陷阱49 完全沒提到：**

```
×>1  假崩盤（分割）     6949 1490→67.1（×22）、8422（×10.1）、4763（×9.8）…
×<1  假暴漲（減資）     2603 長榮 80.8→169.0 一天「+109%」、3532 79.3→163.0…
```

**假暴漲 11 檔次、假崩盤 9 檔次** ⇒ 在**平均**上互相抵銷
（這就是為什麼 alpha 幾乎不動），**但尾部完全被汙染**。

#### ✅ 排除公司行為後重算——結論保住，數字要改

| 停損 | 原最大單筆 | **排除公司行為後** | 受影響筆數 |
|---|---|---|---|
| 8% | -8.0% | **-8.0%** | 7 |
| **★10%（現行）** | -10.0% | **-10.0%** | 6 |
| 15% | -15.0% | **-15.0%** | 7 |
| **幾乎不停損** | **-90.5%** | **🚨 -49.0%** | 7 |

**★ 有停損的三組完全不變**——因為停損本來就把單筆損失封頂，
假崩盤那天 `low ≤ stop` 照樣以 `stop` 價出場。**只有「無停損」那組被汙染。**

**-49.0% 是真的：** 3504 於 **2020-03-05 → 03-19**（COVID 崩盤）跌 49%，
連續跌停 7 天就是 `0.9^7 = 0.478` ⇒ 完全在合理範圍，無公司行為。

⇒ **「停損不能拿掉」這條結論仍然成立，但唯一的依據數字要從 -90.5% 改成 -49.0%**
（仍是 10% 停損的 **4.9 倍**）。

#### ⭐ 方法論（新的一條，而且它推翻了我自己前一節剛寫的東西）

**「排除異常情況」的過濾條件，可能正好濾掉你要找的那個東西。**

陷阱49 加「排除跨多日缺口」的用意是對的（避免把季度資料的跳空誤判成日漲跌，
那是陷阱26 的教訓）。**但分割的特徵恰恰就是「跳水 ＋ 跨多日缺口」**
——那個缺口不是雜訊，**是公司行為的指紋**。
⇒ **寫過濾條件時要問一句：我排除的那一類，會不會正好就是我要找的那一類？**

這與本節上半的教訓（「子期間全在多頭 ⇒ 那個一致性最沒有鑑別力」）是同一族：
**都是「防護做得很用力，但那個防護剛好把關鍵證據擋在外面」。**

#### ★★ ② 5 檔配置・配對比較（100 條，seed 7000~7099）

| 配對 | Δ中位 | 勝場 | p | 判定 |
|---|---|---|---|---|
| **★★ 10% vs 8%（＝8/27 改的那個方向）** | **+0.00pp** | **50/100** | **1.000** | ⚪ **完美 null** |
| 10% vs 12% | -0.08pp | 40/100 | 0.057 | ⚪ |
| 10% vs 15% | -0.01pp | 50/100 | 1.000 | ⚪ |
| 10% vs 25% | +0.01pp | 51/100 | 0.920 | ⚪ |
| 10% vs 幾乎不停損 | +0.06pp | 60/100 | 0.057 | ⚪ |

各組中位 alpha：8% -0.05%、**10% -0.04%**、12% +0.03%、15% -0.05%、25% -0.07%、無 -0.07%。

**⇒「8%→10%」這個改動，在 100 條配對上是 50/50。** 8/27 那個 +0.38pp
的改善是**自選股的倖存者偏誤 ＋ 全多頭的 beta** 兩者疊出來的。

#### 🚨 ③ 逐年 alpha —— 這是 8/27 完全沒有的東西，也是本次最有價值的一欄

| 年 | 8% | 10% | 12% | 15% | 25% | 幾乎不停損 |
|---|---|---|---|---|---|---|
| **2018 ★空頭（-9.2%）** | **+0.39%** | +0.35% | +0.29% | +0.19% | +0.15% | **+0.18%** |
| 2019 | +0.39% | +0.44% | +0.43% | **+0.47%** | +0.46% | +0.46% |
| **2020 ★空頭（V轉）** | +0.12% | **+0.28%** | +0.24% | +0.22% | +0.25% | +0.20% |
| 2021 | **+0.46%** | +0.46% | +0.42% | +0.36% | +0.38% | +0.37% |
| **2022 ★空頭（-22.6%）** | +0.72% | **+0.76%** | +0.74% | +0.68% | +0.65% | +0.63% |
| 2023 | +0.63% | +0.65% | +0.68% | **+0.69%** | +0.67% | +0.68% |
| 2024 | -0.52% | -0.49% | **-0.41%** | -0.48% | -0.50% | -0.49% |
| 2025 | -0.16% | -0.08% | **+0.01%** | -0.06% | -0.11% | -0.28% |
| **2026（+70% 大多頭）** | **+0.22%** | +0.51% | +0.71% | **+0.77%** | +0.76% | +0.75% |
| **★ 三空頭年合計** | +0.45% | **+0.51%** | +0.47% | +0.42% | +0.40% | +0.39% |
| **其他六年合計** | +0.15% | +0.23% | **+0.28%** | +0.27% | +0.25% | +0.22% |

**★ 兩個端點的方向完全相反，而且都是單調的：**

```
2018 空頭年        8% +0.39% ────▶ 幾乎不停損 +0.18%    單調遞減（越緊越好）
2026 +70%大多頭    8% +0.22% ────▶ 15%        +0.77%    單調遞增（越寬越好）
```

⇒ **8/27 那次的樣本全在多頭，所以它必然會指向「放寬」。
那個峰值的位置是樣本決定的，不是停損這個參數本身的性質。**

**順帶：現行 10% 剛好落在三個空頭年的峰值上**（+0.51%），
而其他六年的峰值在 12%（+0.28%）。⚠️ 但兩組的內部全距都只有 0.12~0.13pp
⇒ **不可解讀**，只能說「10% 不是個壞選擇」。

#### ⭐ 唯一站得住的結論：停損不能拿掉，但理由在尾部不在期望值

```
幾乎不停損的最大單筆虧損  -49.0%  ← 2026-10-16 修正（原記 -90.5%，那是 1:10 分割的假崩盤）
                                   真實案例：3504 於 2020-03 COVID 連續跌停 14 天
                                   仍是 10% 停損的 4.9 倍
而六組的 alpha            全距 0.10pp ⇒ 分不出來
```

⚠️ **8/27 那次記的 -67.6% 同樣沒有排除公司行為**，所以那個數字也不可信
（而且那次的樣本是自選股，陷阱49 實測自選股 0 檔公司行為 ⇒ 可能是對的，
但沒驗過，不要引用）。

**⇒ 停損對期望值沒有可檢出的貢獻，它買的是「不會有一筆打掉 90%」。**
這與 2026-09-17「5 檔上限」的結論是同一個形狀——
**價值在尾部風險，而本專案看均值 alpha 的統計方式天生看不見它。**

#### 結論：不改規則，但依據完全換掉

| | |
|---|---|
| ❌ **不可再說** | 「停損 10% 經過回測校準、alpha 在 10% 見頂」 |
| ✅ **正確說法** | 「停損 10% 是 2026-08-27 依自選股＋全多頭樣本選的；2026-10-16 在全市場＋三個空頭年＋配對設計上重驗，**8~25% 六個距離的 alpha 分不出來（全距 0.10pp ＜ 雜訊帶 0.28pp）**，`10% vs 8%` 是 50/100 的完美 null ⇒ **維持現狀**」 |
| ✅ 可以說 | **停損本身不能拿掉**——不是因為 alpha，是因為「幾乎不停損」的最大單筆是 **-49.0%**（排除公司行為後的真值，是 10% 停損的 4.9 倍）|
| ⚠️ 新發現，但不可解讀 | 空頭年偏好較緊（峰值 10%）、多頭年偏好較寬（峰值 12%），兩端 2018／2026 單調且方向相反。**但組內全距只有 0.12pp** |

**⇒ 既有持倉的 `stop_price` 與券商預掛單都不需要動。**

#### ⭐ 方法論（這是新的一條，而且是本專案最常犯的那類錯的根源）

**「參數掃描找到的峰值」本身就是一個會隨樣本移動的量 ——
它的位置可能完全由樣本的市場環境決定，而不是參數的性質。**

8/27 那次的做法已經很嚴謹了：掃六個值、看 alpha 不看原始報酬、
拆四個子期間確認一致、還加了「同等平均值的固定值」當對照。
**但那四個子期間全部在多頭裡面**，所以「四個子期間結論一致」這個檢查
**恰好是最沒有鑑別力的那一種一致性**——它們共用同一個市場環境。

⇒ **判斷方法：掃描參數之後，問一句「我拆的那些子期間，彼此的市場環境
真的不同嗎？」** 若全部同向（都是多頭／都是空頭），那個「一致」不構成證據。
本次把 2018 與 2026 並排，立刻看出方向相反。

這與 9/24「回測宇宙的組成時間必須早於回測期間起點」是同一族：
**都是「對照組設計得很用力，但共用了一個沒被質疑的前提」。**

---

### 🚨🚨 清地基：修掉宇宙的倖存者偏誤之後，alpha 掉 0.33~0.44pp（2026-10-21/22）

**⚠️ 這一節的影響範圍是十五章的全部。** 它不是否決某條規則，是**所有既有
alpha 的共同基準被發現偏高**——而且偏的幅度（0.33~0.44pp）比專案歷史上
任何一次參數調整的效果都大。

腳本：`backtest_pit_universe.py`（已進版控）。完整的機制與程式面見**陷阱55**。

#### 起因與事前查證（這一段比結果更值得讀）

10/18 的「資金曲線重評」自己標了最嚴重的限制：「512 檔宇宙是用**全期**日均
成交篩的 ⇒ 期間崩掉／下市的股票不在裡面，而主要機制正是**持有變長**
⇒ 持有越長受益越多 ⇒ 成分① 的 +493pp **量級不可引用**」。

動手查之後發現問題比那段話更基本：

```
market_universe() 的流動性是用 UNI_SINCE='2025-09-01' 起算、n>=180
  ⇒ 任何在那之前消失的股票，條件必然不成立，一律排除
而 market='TWSE' 又是查**今天的** stocks 表
  ⇒ 兩個條件都擋，後者是決定性的
```

實測：`prices` 裡 2018 起的 4 碼普通股 2,040 檔，**73 檔在 `stocks` 查不到**
（21 檔達流動性門檻、18 檔是歷史退場），含 **6452 康友-KY**（2020-08
財報造假下市、日均成交 2.89 億、639 個交易日 ⇒ 完全達標，但從來沒有
出現在任何回測裡）。

#### ★ 事前預期（先寫下再跑）—— **第二半對了，第一半大錯**

> ① 第一半（流動性 look-ahead）影響**小**——評分門檻 65 本來就偏向成交
>   活絡的強勢股 ⇒ 重疊度高、擋掉的應該不多。
> ② 第二半（母體缺失）較大但有界——18 檔多為**合併換股**（2311 日月光→
>   日月光投控、2448 晶電→富采、2888 新光金、3682 亞太電→遠傳），股東有
>   對價、不是全損；真正全損只有 6452 一檔。
> ③ 18/594 ≈ 3% ⇒ A1 的 alpha 變動應在 **±0.1pp** 內。
>   **若明顯更大，先查是不是陷阱49 的假崩盤。**

| | 實測 | 預期 |
|---|---|---|
**第二半 母體缺失** | 432 筆＝**1.8%**、alpha **-0.50%**（vs 全體 +0.05%）⇒ 貢獻 **≈ -0.01pp** | ✅ **對** |
**第一半 流動性 look-ahead** | 擋掉 **43.4%** 的進場，被擋那批原本 alpha **+0.31%**（全體 +0.05%）⇒ 貢獻 **≈ -0.38pp** | ❌ **大錯**：「重疊度高」這個假設完全不成立 |

**⇒「被擋掉的那批交易比全體好」就是倖存者偏誤的直接顯影**——那些交易之所以
存在，正因為我們用「它**後來**變得夠流動」這個未來資訊把它放進宇宙。

#### ★★ 主結果：兩個層級、兩種量尺，給出同一個數字

對照的是 **R（舊宇宙 513 檔，＝10/14~10/18 所有數字的基準）**
vs **L+P（點時間宇宙，每月依當時流動性重算）**：

| | 舊做法 R | 修正後 L+P | Δ |
|---|---|---|---|
per-trade（2018~2026） | +0.24% | **-0.15%** | **-0.39pp** |
per-trade（2019~2026） | +0.23% | **-0.17%** | **-0.40pp** |
**5 檔配對 100 條（2018~2026）** | -0.050% | **-0.380%** | **-0.33pp　13/100　p=0.000 ❌** |
**5 檔配對 100 條（2019~2026）** | -0.040% | **-0.416%** | **-0.44pp　14/100　p=0.000 ❌** |

**★ Robustness 通過，而且方向出乎意料：切掉 2018 之後效果變大（-0.33 → -0.44pp）。**
2018 的月宇宙平均只有 192 檔（價格回填邊界，見下方限制 1），而
`槽位滿` 從含 2018 的 84~86% 跳到不含 2018 的 95.8~99.4%
⇒ **2018 那段是「槽位填不滿」的時期，它在稀釋效果而不是製造效果。**
兩個診斷互相印證。

#### ⚠️ `L+P vs L` 那個 ⚪ 是假問題（差點誤讀）

第一版只放了 `L+P vs L`（872 檔固定宇宙 vs 872 檔＋點時間），結果 +0.02pp、
52/100 ⚪ ——看起來像「修正沒有影響」。**但 `L` 從來不是任何人用過的基準**：
歷史上所有數字用的是 `market_universe()` 的 513 檔。

```
5 檔配置的中位 alpha：
  R   舊宇宙 513 檔（＝既有基準）   -0.050%
  L   全宇宙 872 檔、無 PIT        -0.343%   ← 沒人用過這個
  L+P 全宇宙 872 檔 ＋ 點時間      -0.380%
```

⇒ **對照組要對的是「實際被取代掉的那個做法」，不是「最接近的那個設定」。**
這與 10/07 那條「給對照組命名時要逐條核對現行規則」同一族，但更隱蔽：
那次是命名錯，這次是**整個對照軸選錯**，而數字看起來完全正常。

#### 機制：候選不足**不是**原因（我的推論被自己的診斷推翻）

原本推論「5 個槽位本來就不缺候選，所以砍掉 43% 的候選對階梯組幾乎無影響」。
用 10/14 立的便宜判準（單日候選 ≥ 槽位數的比例）實測：

| 規則 | 候選中位 | ★槽位滿（2018起／2019起） |
|---|---|---|
L 現行階梯 | 22 → **29** | 85.0% ／ **96.4%** |
L+P ＋點時間 | 18 → **21** | 84.1% ／ **95.8%** |
F 一律65 | 114 → **129** | 85.5% ／ **99.4%** |
F+P ＋點時間 | 68 → **78** | 86.1% ／ **99.1%** |

**前半證實（5 槽位確實不缺候選，砍掉 43% 候選後槽位滿只動 0.9pp），
但後半不成立**——既然兩組都填得滿，「候選不足」就不能解釋
為什麼 `L+P vs L` 在階梯組是 ⚪ 而在一律65 組是 ❌（-0.26~-0.29pp）。

⇒ **誠實的結論：方向穩定（主結果 ❌ 顯著），但「階梯組為何在那個對照軸上
免疫」的機制未知。** 這與 10/15 那次（候選不足、65–69 帶 alpha 兩個假設
都被自己的測試推翻）同一個處理方式——不要硬挑一個說得通的解釋寫上去。

#### ⇒ 對既有結論的影響（**還沒重測，但方向是確定的**）

十五章 10/14~10/18 那幾節的「扣掉 0.47% 成本後**大致打平**或**小幅領先**」
全部要往下修 0.33~0.44pp：

| 既有說法 | 扣掉本節的偏誤之後 |
|---|---|
10/14 B2 篩選門檻「-0.19% → +0.16%，從明確落後變成大致打平」 | 仍然**明確落後** |
10/18 G25 第四個分項「A1 -0.19% → G25 +0.42%，從落後變成小幅領先」 | 大半被吃掉 |
10/16 停損距離「六組全是負的（-0.13 ~ -0.23%）」 | 更負 |

**⚠️ 但「組與組之間的相對優劣」不必然改變**——配對設計比的是同一份宇宙內的
兩個規則，偏誤是共同項。真正受影響的是**絕對水準**，也就是
「這套策略會不會賺」這個問題。⇒ **重測的優先序應該是「絕對 alpha 類的結論」
而不是「規則 A vs 規則 B」那類。**

#### 限制（引用任何上述數字時必須一起講）

1. **2018 的月宇宙平均只有 192 檔**（2019 起 265~496）——**全市場個股價格
   只回填到 2018-01-02**（TAIEX 有 2016-10，個股沒有），前 60 個交易日
   湊不滿 130 日回看窗。那不是 PIT 造成的。**要補完整需回填 2017 的
   全市場價格**（`MI_INDEX` 逐日，約 250 天、十幾分鐘）——尚未做。
2. **跨 session 的絕對數字不可與 10/14~10/18 並列**（陷阱56）。本節所有
   比較都在**同一份快取內**，差異只來自宇宙定義 ⇒ 內部比較有效。
3. 除權息未調整（陷阱50）；未調整收盤價（陷阱49，公司行為 24 檔）。
4. 基本面 25% 在 2026-05 之前恆為 50（陷阱44，永久）。
5. 配對設計消掉「抽到哪些股票」的運氣，**消不掉「這 9 年剛好是什麼行情」**。
6. 點時間宇宙只擋**進場**、不強制出場——它回答「那一天你買得到嗎」，
   不是「現在還該不該持有」。已持有的部位照既有規則走完。

#### ⭐ 方法論（三條，第一條最重要）

**(a) 對照組要對的是「實際被取代掉的那個做法」，不是「最接近的那個設定」。**
見上方「`L+P vs L` 是假問題」。判斷方法：**問一句「這個基準組，是不是
真的有人用它產生過我要推翻的那些數字？」** 若不是，它就只是一個旁邊的設定。

**(b) 用一個「會隨時間改變的函式」當對帳基準是無效的。**
第一版拿 `market_universe()` 當對帳點，而它用 `UNI_SINCE` 起算的近一年
流動性 ⇒ **新上市股會隨時間累積到 180 天而陸續「長進」宇宙**。靶會自己移動。
（本次實測那 17 檔新股只貢獻 16 筆，所以不是對帳失敗的主因——真因見陷阱56
——但這個設計缺陷本身是真的。）**對帳點必須是凍結的**：明確的代號清單，
或明確的日期界線。

**(c) 阻斷式守衛要問「這份快取夠不夠」，不是「這次要跑哪一段」。**
守衛第一版放在 `start=`／`end=` 裁切**之後** ⇒ 刻意的 robustness 檢查
（`start=2019-01-01`）被誤判成「快取建太短」而中止。
⇒ 刻意縮短區間是合法的分析選擇，守衛不該擋；但要**明講少了哪些空頭年**。

---

### 🚨🚨 放寬續抱條件：評分在續抱決策上的資訊量是零，而「少交易」解釋一切（2026-10-23/24）

**⚠️ 這一節同時給出兩個結論，而第二個比第一個重要得多：**
① **「評分 ≥65 才續抱」對上「隨機但同樣抱 14 天」是完美 null**（49/100、44/100）。
② **「優於同持有長度隨機對照」的程度，與「評分用得多不多」完全反向**
　 ⇒ 那個優勢**很可能是對照設計的缺陷，不是訊號**。

腳本：`backtest_renew_scan.py`（已進版控）。`simulate()` 新增 `renew` 參數
（`None` ⇒ 位元級不變／數字 ⇒ 換續抱門檻／`'profit'` ⇒ 仍獲利就續抱／
`('rand', p, salt)` ⇒ 中性對照）。

#### 為什麼測這個：兩條獨立的路都指向「抱更久」

| 何時 | 證據 |
|---|---|
| 2026-10-07 | 續抱 (e vs d)：換手 1,102 → 57 次、成本拖累 -64.6% → -5.3%、**Δ報酬 +169pp、20/20** |
| 2026-10-18 | **一個完全沒有資訊的隨機數**，只要同樣拉長持有期 ⇒ **+493pp、20/20** |

10/18 那節的「下一步」第 1 項就是本測試：**若效果來自「抱更久」，
那不需要月營收、也不必動 `scorer.py`——只要改 `RENEW_THRESHOLD` 一個數字。**
這是整個專案最便宜的候選改動。

#### ★★ 三個必要設計（缺任何一個結論就不能讀）

| | 做法 |
|---|---|
| ① 主量尺是**資金曲線** | 放寬續抱會改變持有長度，而 per-trade alpha **沒有除以持有天數** ⇒ 抱久一點 alpha 自然變大（10/18 的教訓） |
| ② 中性對照在**持有長度**這一維對齊 | `('rand', p, salt)`：到期時以固定機率 p 續抱、完全不看資訊。腳本印出各規則均持有、**自動挑最接近的兩組**，差 >30% 標 🚨 不給判定 |
| ③ 每個對照跑**兩個隨機實現** | 10/18 實測 M50a vs A1 是 18/20 ✅ 而 M50b 是 14/20 ⚪ ⇒ 單一實現的噪音足以決定判定 |

續抱決定由 `(salt, code, i)` 決定、**與排序 seed 無關** ⇒ 100 條配對共用同一組
續抱決定，差額只來自排序運氣，不會混進「對照自己也在隨機」這第二個噪音源。

#### ★ 事前預期（先寫下再跑）—— (a) 對、(b) 錯，而錯的那個更有意義

> **主預期：放寬續抱會提高報酬，但扣掉同持有長度的隨機對照之後，
> 「依評分續抱」的淨貢獻會很小、甚至測不出來。**（9/23 已量到評分與未來報酬 corr=0）
>
> 第二輪（掃 N45/N35/N30 找轉折點）的預期：
> **(a) N65 vs 隨機 ⇒ ⚪。(b) 會有轉折，而且在 N35~N30 之間**
> ——評分低於 35 的日子極少，門檻降到那裡等於「幾乎永不出場」，
> 與 p→1 的隨機對照越來越像 ⇒ Δ 應該收斂到 0。
>
> ⚠️ **我自己標的反方向：** 若 N30 仍顯著優於 R995，那就不是「只砍最差的」
> ——那會比較像「持有期越長越好，而隨機淘汰會誤殺」，**是另一個機制，得重想**。

| 預期 | 結果 |
|---|---|
| 放寬續抱提高報酬 | ✅ **對**（vs N65 全部 ✅，+77~+197pp） |
| 扣掉同持有長度對照後淨貢獻很小 | ⚠️ **一半對**（N65／N50 ⚪，但 N40/N35/N30 ✅） |
| (a) N65 vs 隨機 ⇒ ⚪ | ✅ **對**（49/100、44/100，完美 null） |
| (b) N35~N30 之間出現轉折 | ~~❌ 大錯：完全相反，越往下越強~~ → **✅ 其實是對的，連位置都對**（見下方「第三輪」：用機制對齊的對照重測，轉折確實落在 N35 與 N30 之間。當天判它錯的那個對照本身有缺陷）|
| ⚠️ 「反方向」：隨機淘汰會誤殺 | ✅ **被證實**（而這正是 (b) 被誤判的原因——固定危險率在長持有端製造假 ✅）|

#### 結果（5 檔等權、2018-01-02 ~ 2026-10，100 條配對 seed 8000~8099）

| 規則 | 報酬中位 | 5~95% | 回檔 | 在場內 | 均持有 | 筆數 |
|---|---|---|---|---|---|---|
| **N65 ★現行** | **+9.21%** | -42.78 ~ +125.90 | -48.60% | 79.6% | **14.9** | 574 |
| N50 | +96.00% | +0.70 ~ +305.68 | -42.98% | 83.8% | 31.9 | 282 |
| N45 | +130.81% | +26.44 ~ +416.57 | -38.55% | 84.9% | 44.5 | 205 |
| N40 | +161.16% | +27.60 ~ +476.67 | -38.73% | 85.8% | 65.0 | 142 |
| N35 | +171.38% | +53.74 ~ +387.59 | **-32.76%** | 76.5% | 107.2 | 78 |
| **N30** | **+208.11%** | +19.26 ~ +694.18 | -34.63% | 78.2% | **205.3** | **43** |
| **買進持有 0050** | **+417.23%** | — | **-36.38%** | 100% | — | 0 |
| 買進持有 0056 | +123.84% | — | -35.47% | 100% | — | 0 |
| 加權指數（不可投資） | +329.86% | — | -31.63% | — | — | 0 |

🚨 **絕對數字不可解讀**（帶寬 148~675pp），只有配對差值可讀。

**vs 現行 N65（總報酬）：** N50 +77.08pp（90/100）、N45 +120.79（95）、
N40 +159.14（94）、N35 +150.80（96）、N30 +196.62（92），**全部 p=0.000 ✅**。
**回檔同向全部 ✅**（+5.82 ~ +16.35pp，70~98/100）。

#### ★ (a) 現行規則贏不過隨機——配對這次幾乎完美（14.9 vs 14.1／14.3 日）

```
N65 vs R400b   -2.27pp   49/100   p=0.920   ⚪
N65 vs R400a   -5.27pp   44/100   p=0.271   ⚪
```

**「評分 ≥65 才續抱」對上「隨機但同樣抱 14 天」是完美 null。**
與 9/23（corr=0）、9/17／9/24（≥65 無鑑別度）一致——**同一件事第四次出現，
而這次是在「續抱決策」上**（前三次在進場門檻與分數高低排序上）。

⚠️ 2026-10-23 那一輪的這一格是**無效的**：只跑了 N65/N50/N40 + R800/R900，
`combine` 就把 N65（14.9 日）配到 R800（33 日、**差 116%**）⇒ 當時印出
「-60.36pp、21/100 ❌」看起來是個強結論，實際上是拿兩件不同的事在比。
守衛那天只加在 `pertrade`、漏了 `combine`（見下方「順帶抓到」）。

#### ⚠️ (b) 第一版的讀法（用固定機率對照）—— **已於同日被更正，保留供對照**

當天只有 `('rand', p)` 這一個家族，量到的是**單調**：N65 ⚪⚪ → N30 ✅✅（+134/+79），
於是寫成「評分用得最少的 N30 優勢最大 ⇒ 排序與『評分有資訊』矛盾 ⇒ 最可能是對照缺陷」。

**那個單調是對照的缺陷造成的，不是訊號的性質。** 隔天換成「打亂評分」家族
（出場機制相同）並把持有長度對齊之後，**形狀變成倒 U，而 N30 的 ✅✅ 消失**。
完整記錄見下方「第三輪」。⇒ **(b) 這一節的結論作廢，只留「現行 N65 是零」那一半。**

```
隨機對照 = 固定危險率（每次到期都以機率 1-p 出場）
         ⇒ 持有長度是**指數分布** ⇒ **會隨機砍掉正在複利的贏家**
真規則   = 出場條件是「評分跌破門檻」這種罕見事件 ⇒ 幾乎不打斷複利
⇒ **平均持有長度對齊了，但「出場時機的分布」沒對齊** ⇒ 在長持有端製造假 ✅
```

⚠️ 這是「中性對照必須在那個結構維度上與被測規則對齊」（10/18 立的規矩）
**第二次不夠**——10/18 對齊了「更新頻率」卻沒對齊「持續性」；
這次對齊了「平均持有長度」卻沒對齊「出場時機的分布」。

#### 回檔：第五次確認「來自少換手，與評分無關」

```
vs 同持有長度對照：N65 ⚪⚪　N50 ⚪⚪　N45 ⚪⚪　N40 ⚪⚪　N30 ⚪⚪
                   唯一例外 N35 +3.13／+3.58（71／75 ✅✅）
```
⚠️ N30 那兩格有平手 6／11 筆——交易只有 43 筆，部分 seed 的曲線完全相同。

前四次：10/07（整套結構 vs 買進持有雙 ⚪）、10/18（G50 vs M50a 完美 ⚪）、
10/23 的 20 條、本次。

#### 🚨 而最該記住的是這個

```
門檻一路放寬到「幾乎永不出場」（N30：8.7 年 43 筆、每年 5 筆）
  N30 +208%　N35 +171%　N40 +161%
  買進持有 0050                      **+417%**
```

**9 個門檻 × 20 組對照，一組都沒贏過買進持有 0050。**
唯一第一次贏過 0050 的是 **N35 的回檔**（-32.76% vs -36.38%），但報酬只有它的 41%。

> **整條線收斂到一句話：這套策略的價值幾乎全在「少交易」，
> 而推到極限就是買進持有——而買進持有 0050 比它好。**

⚠️ 其中一部分是**結構差距而非選股**：5 檔等權 vs 50 檔市值加權（台積電約 57%
權重），10/05 量到那個差距是 39pp；而兩邊都沒計股利（0056 殖利率 7~8%
⇒ 買進持有被低估更多）。

#### 結論：不改規則

| | |
|---|---|
| ❌ **不能說** | 「放寬續抱到 N30 可以把報酬從 +9% 提到 +208%」——那大半是「抱更久」，而那一項的量級受倖存者偏誤 × 持有長度汙染（10/18 的限制，本次用點時間快取已修掉宇宙那半，但**配對仍共用同一段 9 年歷史**） |
| ✅ **可以說** | ① **「評分 ≥65 才續抱」的資訊量測不出來**（完美 null，第四次）<br>② ~~「優於隨機對照」與「評分用得多寡」反向 ⇒ 最可能是對照缺陷~~ → **作廢**，那個「反向」是對照缺陷造成的；修好後形狀是倒 U，見「第三輪」<br>③ **回檔變淺完全來自少換手**<br>④ **沒有任何門檻贏過買進持有 0050** |
| ✅ **已解決的混淆** | 隨機對照的**出場時機分布**與真規則不同（固定危險率 vs 罕見事件）⇒ 2026-10-24 用「**打亂評分**」家族拆掉了，見下方「第三輪」。**那一輪才是本節的結論。** |

**為什麼即使 N30 看起來好也不改規則（三個理由）：**
1. **那不是參數微調，是另一套策略。** 均持有 205 日（現行 14.9）、每年 5 筆
   ——10 日週期、65 分門檻、大盤階梯**全部實質失效**。
2. **仍大幅輸買進持有 0050**（+208% vs +417%）。若真要走「少交易」這條路，
   誠實的終點是直接買 ETF，不是把續抱門檻調到 30。
3. **主要機制未被證實**（見上方混淆）。在機制未知的情況下動正式規則，
   與「因為數字好看就改」沒有差別。
   ⚠️ 2026-10-24 補註：**而 N30 後來證實是零**（對齊後 ⚪⚪），
   所以這三個理由的前提「N30 看起來好」本身已經不成立。

#### ✅ 第三輪：打亂評分 ＋ 持有長度對齊（2026-10-24，**這一輪才是結論**）

**對照的設計：`('shuffle', thr, salt)`** ——把每檔股票固定指派到另一檔，
續抱時查**那一檔**的評分。出場的**時機分布、自相關、橫斷面分布全部保留**，
唯一的差別是「這個評分屬於這一檔，還是別人」。

**🚨 但第一次跑就踩到自己的守衛漏洞（陷阱30 那條通則第三次）。**
我把 SHUF 配對**硬寫死成「同門檻」**、連 `GAP_MAX` 都沒套，
理由寫「出場機制完全相同所以不需要持有長度配對」。**實測否證：**

```
同門檻的打亂版系統性抱得更短
  N65 14.9→11.3 日（-24%）　N50 31.9→20.9（-34%🚨）
  N40 65.0→41.0（-37%🚨）　 N30 205.3→151.7（-26%）
```

**機制（而且它本身就是答案的一部分）：** 進場條件是「**自己的**評分 ≥ 階梯門檻
（65+）」，而評分有持續性 ⇒ 到期時自己的評分仍偏高、很少跌破續抱門檻；
別人的評分是從**無條件分布**抽的 ⇒ 更容易跌破 ⇒ 出場更多、抱更短。

⇒ 修法：**把打亂版的門檻往下調**，並給一道梯子
（`SHUF_T = 65/58/50/45/40/36/32/30/25/20`）由實測持有長度自動挑最接近的兩個
——**刻意不手動校準**，手動挑一個值等於多一個自由度。
守衛改成兩個家族共用 `nearest()`，結構上不可能再漏掉一邊。

**★ 要補回同樣的持有長度，打亂版的門檻得往下調 4~10 分**
（N65↔S58、N50↔S45、N40↔S36、N35↔S32、**N30↔S20**）
——那個落差就是「進場條件的持續性」的大小，是本輪順帶量到的。

#### 🚨🚨 結果：形狀是**倒 U**，不是單調

| 門檻 | 均持有 | 打亂版（對齊後，差距） | Δ中位／勝場／p | 判定 |
|---|---|---|---|---|
| **N65 ★現行** | 14.9 | S58a（14.3／4%）<br>S58b（14.2／5%） | +9.20　58/100　.133 ⚪<br>**-17.27　33/100　.001 ❌** | **a/b 不一致** |
| **N60** | 18.9 | S50a（20.7／10%）<br>S50b（21.1／12%） | **-23.78　34/100　.002 ❌**<br>**-12.03　36/100　.007 ❌** | 🚨 **兩個都 ❌（反向）** |
| N55 | 23.8 | S50b／S50a（11~13%） | +12.92　56 ⚪／+17.41　58 ⚪ | **零** |
| N50 | 31.9 | S45b／S45a（13~14%） | +10.59　52 ⚪／+22.86　63 ✅ | a/b 不一致 |
| **★N45** | 44.5 | S40b（8%）／S40a（8%） | **+72.73　79 ✅／+37.78　66 ✅** | ✅ **有邊際** |
| **★N40** | 65.0 | S36a（**1%**）／S36b（6%） | **+47.46　75 ✅／+53.24　68 ✅** | ✅ **有邊際** |
| **★N35** | 107.2 | S32b（7%）／S32a（8%） | **+91.99　82 ✅／+59.94　68 ✅** | ✅ **有邊際** |
| **N30** | 205.3 | S20b（10%）／S20a（17%） | +37.71　59　.089 ⚪／+36.17　60　.057 ⚪ | **零**（見下）|
| PRF | 144.8 | S30b（1%）／S30a（8%） | +22.30　61 ✅／+4.27　51 ⚪ | a/b 不一致 |

**⇒ 唯一「兩個實現一致 ✅」的是 N45／N40／N35 這個中段，而兩端都掉回零。**

#### ★★ 兩個家族在 N30 直接衝突，而打亂版才是對的

```
N30 vs R995（固定機率、同持有長度）  +133.72／+79.30　85／75 /100　✅✅
N30 vs S20 （打亂評分、同持有長度）  +37.71／+36.17　59／60 /100　⚪⚪
```

**同一個規則、同一組 seed、持有長度都對齊，兩個對照家族給出相反的判定。**
而打亂版是機制對齊的那一個 ⇒ **R 系列在長持有端的 ✅ 是「固定危險率隨機砍掉
複利贏家」的產物**。10/23 原本就是這個懷疑，只是當天被單調的排序帶走了。

⚠️ 10/24 第一輪那個 `N30 vs S30 ＝ +109/+109（78/84 ✅✅）` **也是假的**
——S30 只抱 151.7 日、比 N30 短 26%。對齊到 S20（225/239 日）之後就變 ⚪⚪。

#### ★ 我 10/23 標成「大錯」的那個預期，其實是對的

10/23 寫：「**會有轉折，而且在 N35~N30 之間**——評分低於 35 的日子極少，
門檻降到那裡等於幾乎永不出場，與 p→1 的對照越來越像 ⇒ Δ 應該收斂到 0。」
當天根據 R 系列的單調結果把它標成「❌ 大錯：完全相反」。

**對齊之後：N35 是 +92/+60（✅✅），N30 是 +38/+36（⚪⚪）
⇒ 轉折點就落在 N35 與 N30 之間，位置也猜對了。**

> **⭐ 這是本專案第一次出現「事前預期被一個有缺陷的對照判成錯誤，
> 之後被修好的對照平反」。** ⇒ **把預期標成「錯」之前，要先確認
> 判它錯的那個對照本身站得住。** 否則錯誤的紀錄會被後人當成已知事實引用
> （而 10/23 那節正是這樣寫的，已加作廢註記）。

#### 回檔：第七次確認不是評分的功勞

打亂版 18 格裡只有 **N45 vs S40b（+2.48pp、61/100）一格 ✅**，
而 **N40 vs S36b 是 -3.28pp、34/100 ❌**（方向相反）。其餘全 ⚪。
⇒ 在**機制與持有長度雙對齊**的對照下，回檔的優勢完全消失。

前六次：10/07、10/18、10/23 的 20 條、10/23 的 100 條、10/24 第一輪、本輪。

#### 結論：不改規則（按事前約定的停止條件，不再加第四種對照）

| | |
|---|---|
| ✅ **可以說** | **評分在續抱決策上確實有可檢出的邊際價值，但只在「門檻 45~35」這個中段**——而且這是專案第一次在「機制 ＋ 持有長度**雙對齊**」的對照下測到評分的價值 |
| ✅ 可以說 | **現行 N65 的位置是零**（固定機率 ⚪⚪；打亂版 a/b 不一致）——第五次 |
| ✅ 可以說 | **極低端 N30 也是零**（+38/+36、p=.057/.089，方向一致但跨不過）|
| ✅ 可以說 | **回檔的優勢完全不是評分的功勞**（第七次，這次對照最乾淨）|
| 🚨 可以說 | **9 個門檻 × 22 組對照，沒有一個贏過買進持有 0050（+417%）**。最好的 N30 是 +208% |
| ⚠️ **不能說** | 「把續抱門檻改成 40 就會變好」——見下方三個理由 |
| ⚠️ 不能說 | 「N60 比打亂版差」是真的——兩個都 ❌ 但打亂版抱長 10~12%，用 R 系列的持有長度斜率估算約 +9pp 來自那個差距，殘差仍負但很小 |

**三個不改規則的理由：**
1. **那不是調一個數字，是換一套策略。** N45 均持有 44.5 日／205 筆、
   N40 65.0 日／142 筆、N35 107.2 日／78 筆——**10 日週期實質失效**。
2. **仍然大幅輸買進持有 0050。** 若真要走「少交易」這條路，
   誠實的終點是直接買 ETF。
3. **「中段才有價值」這個形狀本身是個新假設，沒有獨立驗證。**
   它是這一輪的產物，而這一輪的前兩版讀法都被推翻過。
   在只有一段 9 年歷史、而形狀又是倒 U（兩個自由度）的情況下動正式規則，
   與「因為數字好看就改」沒有差別。

#### 限制（引用任何上述數字時必須一起講）

1. 點時間宇宙已套用（陷阱55），但**配對設計消不掉「這 9 年剛好是什麼行情」**。
2. 除權息未調整（陷阱50）；未調整收盤價（陷阱49）——**持有越長，
   跨過公司行為的機會越多**，而本節的重點正是持有長度。
3. **基本面 25% 在 2026-05 之前恆為 50**（陷阱44，永久）⇒ 本測試測的正是評分門檻。
4. 5 檔等權、每日再平衡、現金不計息；買進持有未計股利。
5. **跨 session 的絕對數字不可與 10/14~10/18 並列**（陷阱56）。
6. 持有長度對齊到 1~17%，**不是 0%**。緊端（N65 4~5%、N40 1%）可忽略，
   但 N30（17%）與 N55/N50（11~14%）仍有幾 pp 由它貢獻。
7. N30／N35 筆數只有 43／78 ⇒ 配對會出現平手。

#### ⭐ 方法論（三條，第一條是本輪最重要的）

**(a) 「對照的某個維度沒對齊」在同一個題目裡出現了三次，每次都改變結論。**

| | 對齊了什麼 | 漏了什麼 | 後果 |
|---|---|---|---|
| 10/18 | 更新頻率 | **持續性** | 高估成長資訊的貢獻 |
| 10/23 | 平均持有長度 | **出場時機的分布** | 在長持有端製造假 ✅（單調假象）|
| **10/24** | 出場機制與分布 | **平均持有長度** | 同門檻的打亂版短 24~37% ⇒ 又一組假 ✅ |

⇒ **「對齊」不是一個勾選項，是一份清單，而清單的長度等於被測規則用了幾個機制。**
判斷方法：**問「如果我的對照真的完全沒有資訊，它為什麼會輸／贏？」**
——三次的答案分別是「它換手太頻繁」「它會隨機砍掉贏家」「它出場太多」，
每一個都是一個沒對齊的維度。

**(b) 參數掃描的「形狀」比任何單一 p 值有資訊，但形狀本身會被對照的缺陷扭曲。**
10/23 從單調的形狀推出「與評分有資訊矛盾」——推理是對的，**但那個形狀是假的**。
⇒ **要用形狀當證據之前，先確認每一格的對照都是同一個品質。**
（這修正了 10/23 立的那條「單調方向可以當機制的檢定」——它仍然成立，
但前提是對照沒有系統性偏斜，而那正是當時沒有檢查的事。）

**(c) 守衛要放在每一個會做那件事的地方——第三次。**
10/23 `pertrade` 有守衛、`combine` 沒有；10/24 兩個都有了，
但**新加的 SHUF 家族是硬寫死的配對、整個繞過守衛**，
而且我在程式註解裡替它寫了一個「不需要配對」的理由。
⇒ 根治方法不是「記得兩邊都加」，是**讓兩個家族走同一支函式**
（現在的 `nearest()`）。**只要還存在「第二條路徑」，它就會在某次新增功能時繞過守衛。**

---

### 重要陷阱

- `scan_hold_days()` 的「◀ 最佳」標記需先收集所有 rows 再決定最佳，不能在 append 時即時判斷（會讓每列都被標記）
- `market_net` 字典由 `_market_score_history`（Signal 1–8 回溯）提供，格式：`{date_str: net_int}`
- 回測資料範圍約 2024 至今，均為台股多頭環境，偏空策略系統性低估

---

## 十六、主題輪動頁（theme_rotation.py）（2026-07 新增）

**路由值：** `'theme_rotation'`，側邊欄按鈕「🔄 主題輪動」觸發。

**設計原則：完全獨立模組**
- 所有邏輯封裝在 `theme_rotation.py`，`app.py` 只改了 3 處共 8 行（import + 側邊欄按鈕 + 路由）
- 不依賴 DB、不依賴 `github_sync.py`、不需要 `IS_LOCAL` 分支
- 資料來源：yfinance（雲端本機均可用）
- 快取：`@st.cache_data(ttl=900)`，15 分鐘

### 主題定義（THEMES dict）

| 主題鍵 | Ticker | 說明 | 是否基準 |
|--------|--------|------|---------|
| `'台灣寬基'` | `0050.TW` | 元大台灣50，RS 計算的分母 | ✅ |
| `'台灣半導體'` | `00891.TW` | 中信關鍵半導體 | — |
| `'高股息'` | `0056.TW` | 元大高股息 | — |
| `'費城半導體（美）'` | `00830.TW` | 國泰費城半導體，涵蓋 NVIDIA/AMD | — |

新增主題只需在 `THEMES` dict 加一筆，其餘計算和圖表自動包含。

### 核心計算函式

```python
_fetch() -> pd.DataFrame
# @st.cache_data(ttl=900)，下載所有主題 ETF 近 1 年日收盤
# 回傳寬表 columns=ticker，index=date
# 任一 ticker 失敗不影響其他

_calc_rs_lines(df, n_days) -> dict
# 各主題相對強度折線，區間起點標準化為 100
# RS_Line = theme / benchmark，normalize to 100 at period start
# 回傳 {theme_name: pd.Series}

_calc_rrg(df) -> list
# JdK RS-Ratio & RS-Momentum（簡化版）
# RS_Ratio   = (price/bench) / SMA52(price/bench) * 100
# RS_Momentum = RS_Ratio / SMA10(RS_Ratio) * 100
# 週取樣，回傳最近 8 個週資料點（含尾跡）
# 每筆：{'theme', 'label', 'color', 'points': [{'ratio', 'moment', 'date'}, ...]}

_quadrant(ratio, moment) -> (str, str)
# 回傳（象限名稱, 顏色）
# 領先（右上）：ratio≥100 & moment≥100，#22c55e
# 轉弱（右下）：ratio≥100 & moment<100，#f59e0b
# 落後（左下）：ratio<100 & moment<100，#ef4444
# 改善（左上）：ratio<100 & moment≥100，#3b82f6
```

### 頁面結構

1. **時間區間選擇**：1個月 / 3個月 / 6個月 / 1年（影響 RS Line 圖）
2. **RS Line 折線圖**：各主題相對 0050 的強弱走勢，基準線 = 100
3. **RRG 四象限圖**：X 軸 RS Ratio、Y 軸 RS Momentum，含近 8 週虛線尾跡
4. **文字摘要**：各主題象限位置 + 選定區間的相對強度百分比

### RRG 象限解讀

| 象限 | 位置 | 顏色 | 意義 |
|------|------|------|------|
| 領先 | 右上 | 🟢 | 強勢延續，相對強度高且動能持續 |
| 轉弱 | 右下 | 🟡 | 強勢但動能衰退，注意高點 |
| 落後 | 左下 | 🔴 | 持續弱勢，迴避 |
| 改善 | 左上 | 🔵 | 弱勢但動能回升，輪動進場的早期訊號 |

主題通常依 領先 → 轉弱 → 落後 → 改善 → 領先 順時針循環。
最有意義的切入點：主題從「落後」進入「改善」象限。

### 注意事項

- RRG 需要至少 60 個交易日資料，ETF 上市未滿 60 日不顯示
- RS Ratio 計算使用 52 週 SMA，需要足夠歷史才穩定（00891 上市 2021/09，00830 上市 2019）
- RRG 顯示範圍自動依實際資料調整（`xmin/xmax/ymin/ymax` 動態計算，pad=1.5）
- 日期格式：`2026年7月19日`（中文格式）
- 所有象限名稱使用中文：領先/轉弱/落後/改善

---

## 十六之二、類股資金流向（sector_flow.py）（2026-10-04 新增）

**路由值：** `'sector_flow'`，側邊欄按鈕「💧 類股資金流向」。**本機算 DB、雲端讀 JSON，兩邊都能用。**

**為什麼做：** 原本的「🔄 主題輪動」只有 4 檔 ETF，其中 3 檔是半導體相關
（0050／00891 關鍵半導體／0056 高股息／00830 費半），**看不到航運、金融、塑化、生技、
電機、汽車在幹什麼**——它實際上是「半導體 vs 高股息」，不是類股輪動。

**2026-09-23 補完全市場價格之後條件才成立：**

| | |
|---|---|
| 510 檔流動性宇宙的產業代碼涵蓋率 | **100%**（實測 513/513） |
| `prices` 可用歷史 | 527 個交易日 × 約 1,077 檔上市股 |
| `value`（成交金額）欄 | 一直都在，**但在此之前從來沒有任何功能用過** |

**選「成交金額占比」而不是「價格強弱」的理由：** 占比回答「**資金正在流進哪裡**」，
價格回答「**哪裡已經漲過**」。在 2026-09-23 量到「評分是後照鏡」之後，前者至少是個不同的問題。

### 產業代碼對照（已用已知股票驗證）

`stocks.industry` 存的是 TWSE 產業別**數字代碼**，`IND_NAMES` 是對照表。
驗證方式：2330→`24` 半導體、2317→`31` 其他電子、2882→`17` 金融保險、1301/1303→`03` 塑膠、
2603→`15` 航運、2412→`27` 通信網路、3008→`26` 光電、2207→`12` 汽車、6505→`23` 油電燃氣。

⚠️ 全表 `industry` 涵蓋率只有 52%（1089/2095，缺的多為上櫃與冷門股），
**但 510 檔宇宙是 100%**，所以本頁不受影響。

### 三個計算與各自的分母（⚠️ 十八章通則：算占比前先確認分母）

| 數字 | 分母 |
|---|---|
| 類股占比 | **上市普通股**（4碼數字、有產業代碼）當期成交金額合計 → 加總 ≈ 100%（實測 100.0%） |
| 「占本類股%」 | **該類股自己** —— 用來看類股內部的資金集中在哪幾檔 |
| 「vs 近N日」 | 同一個分母的兩個視窗相減，單位是**百分點 pp** |

**不含上櫃、ETF、權證、TDR**（`length(code)=4 AND code GLOB '[0-9][0-9][0-9][0-9]'` + `market='TWSE'`）。
換分母會得到完全不同的數字，**UI caption 必須寫明**。

### 版面

1. **橫向長條圖**：X 軸＝占比變化 pp，🔴紅＝流入／🟢綠＝流出（台灣慣例）／灰＝變化 <0.3pp
2. 占比 <0.3%（兩視窗都低）的類股合併成「其他小類股（N類）」一列，避免 33 列擠爆
3. **點類股名稱下鑽**（再點一次收起）→ 該類股 60 日占比走勢 + 成分股明細
4. 成分股明細六欄：股票／**最新價**／日均成交(億)／占本類股%／vs 長窗 pp／短窗漲跌%
   - 最新價跟著漲跌上色；<50 元顯示兩位小數、≥50 元顯示一位（高價股掛兩位小數太佔空間）

**實例（2026-10-02 資料）：** 電子零組件 24.33%→28.23%（**+3.90pp**）、半導體 38.01%→35.35%（-2.66pp）。
下鑽才看得出那 +3.90pp 不是整個類股在動，是**載板／被動元件**
（國巨 +9.25%、南電 +20.66%、聯茂 +26.25%）在吸錢，而台達電反而 -2.8pp。
**這一層是本頁的價值所在——單看類股層級會誤判成「整個類股轉強」。**

### 雲端支援（方案B）

雲端沒有全市場價格（只同步自選股 JSON），所以採**本機算好→匯出 JSON→雲端讀**，
與 `chips_market_agg.json` 同一個模式。

| | 本機 | 雲端 |
|---|---|---|
| 主圖＋60日走勢 | ✅ | ✅ |
| 下鑽成分股 | 前 40 檔 | **前 20 檔**（`EXPORT_TOP_N`） |
| 比較視窗 | 三種可切 | **固定近5/20**（`EXPORT_WINDOW`） |

檔案大小 **92 KB**（對照：`stocks.json` 188KB、`TAIEX.json` 48KB）。
三種完整度都量過：僅類股層級 54KB／本方案 92KB／全成分股×3視窗 329KB。

**⚠️ `export_json()` 刻意不迴圈呼叫頁面那些 `_sector_*()` 函式。** 那樣每類股查兩次 DB，
33 類 × 2 = 66 次查詢，**實測 15 秒**，掛在每日同步上會明顯變慢。
改成**一次 `GROUP BY date, industry` 全抓**再於記憶體彙總 → **0.5 秒**。
匯出值與本機算法逐項核對相符。

**⚠️ `init_cloud_data()` 的個股迴圈 skip 名單已加入 `'sector_flow'`**（第六章規定），
否則會被當成股票代號解析。

### ⚠️ 定位（UI caption 必須保留）

**純資訊顯示，未經任何回測驗證：不計入評分、不影響進場門檻、不可當作進出場理由。**
與 🎯🔥 型態、量能水位完全相同的定位。

理由：**占比同樣是「昨天的成交結果」算出來的**，與 2026-09-23 量到「評分是後照鏡」
是同一個病根。本專案已六次驗證出「看起來合理的訊號實測無效」，先驗機率不高。

**日後若要當規則用，必須先回測**——好消息是全市場樣本讓雜訊帶降到 0.60pp（2026-09-24），
**0.6pp 以上的效果現在看得見**，這是九月之前做不到的。

**討論過但還沒做的三項（同一批提案）：** 類股 RS Line／RRG（把現有 ETF 邏輯換成 33 類股，
且**等權與市值加權要並排**——半導體市值加權等於台積電一檔決定）、類股廣度（幾成個股站上月線）、
以及**「類股成交占比上升但價格還沒漲」**（量價背離的類股層級版本；Signal 8 在大盤層級做過，
類股層級沒做過，是這批裡唯一不只是「把價格重新排序」的東西）。

---

## 十七、程式說明頁 — 資料時效性與落差說明（app.py `render_doc()`，2026-07 新增）

**背景：** 使用者反映不清楚哪些資料是「當日即時」、哪些天生有延遲（例如季度 EPS 常落後公司實際公告 1–2 個月），原本的「三、資料來源」表格統一寫「每日 16:30」，容易誤導。

**修正：** 在 `render_doc()` 的「三、資料來源」與「個股評分邏輯」之間插入新章節「四、資料時效性與落差說明」，後續章節（原四～九）依序遞增為五～十。

**新章節內容涵蓋：**

| 資料 | 落差原因 |
|------|---------|
| 季度 EPS（quarterly_financials） | yfinance 比公司實際公告慢 1–2 個月同步 |
| EPS TTM 三層 fallback | TWSE反推（即時）／quarterly_financials（可能延遲）／yfinance trailingEps（24h快取），新鮮度不同 |
| 除權息 | 預告（TWT48U）vs 正式（TWT49U）金額可能有出入 |
| ETF 成分股 | 人工整理，每季手動更新 |
| 大盤市值校準係數 | 每 6–12 個月人工校準一次 |
| 台指期夜盤 | 僅本機版（FinMind Token），雲端無此區塊 |
| 雲端版資料 | 需本機按「🚀 更新並同步到雲端」才會推送，非自動即時 |

並附上法定財報申報期限對照（Q1/Q3 季度結束後45天內；Q2半年報約8/14；年報隔年3月底前），方便使用者知道「公司公告了」和「工具資料更新了」是兩件事。

**版本紀錄同步更新：** 加入 `v3.1 | 2026/07/21 | 新增「資料時效性與落差說明」章節、大盤成交量圖單位修正`。

**維護提醒：** 未來新增任何「非即時 / 有延遲」的資料來源時，應同步在此章節的表格加一列，避免使用者誤判資料新鮮度。

---

## 十八、持倉追蹤（positions 表，2026-07 新增）

**定位：** 與「自選股」分工——自選股是**候選池**（還沒買），持倉追蹤是**已進場部位**（追蹤策略 C 的 10 日持有週期）。

**本機為主，雲端唯讀（2026-08 起）：** `positions` 本質上是個人交易紀錄，寫入操作（新增/續抱/出場/編輯）**永遠只能在本機做**。雲端版原本完全不處理這張表，2026-08 新增了「雲端唯讀檢視」——側邊欄持倉觀察可以在雲端看，但需要密碼解鎖，且資料本身是加密過的，詳見下方新增小節。

### config.py 交易成本參數

```python
HOLD_DAYS    = 10          # 標準持有天數（交易日）
FEE_RATE     = 0.001425    # 手續費率
FEE_DISCOUNT = 0.6         # 券商折扣（電子下單常見 6 折；無折扣填 1.0）
FEE_MIN      = 20          # 單筆手續費低消 —— 零股小額交易常卡此門檻
TAX_RATE     = 0.003       # 證交稅（僅賣出）
```

### app.py helper（模組頂層，`_CHART_CONFIG` 下方）

```python
_trading_days_since(entry_date, code='TAIEX') -> int   # 用 prices 表算交易日，第一天=1
_trade_cost(amount, is_sell=False) -> float            # 單邊成本（含低消與證交稅）
_position_pnl(entry, exit, shares) -> (毛%, 淨%, 毛額, 淨額, 總成本)
_latest_close(code) -> float | None                    # IS_LOCAL 走 DB、雲端走 JSON
_position_status(pos, cur_price, market_net) -> (旗標, 顏色, 文字)
```

**`_position_status()` 優先序（重要，2026-10-08 已改）：**
`停損 🔴 ＞ 到期 ⏰ ＞ 接近停損 ⚠️（≤停損×1.02）＞ 大盤偏空 📉（純資訊）＞ 持有中 🟢`

> **❌ 原本是「停損 ＞ 大盤轉空（net≥+4）＞ 到期 ＞ …」，理由寫「空頭回測顯示
> 大盤層級訊號比個股訊號更早也更有效」——那個理由 2026-10-08 被推翻**
> （依淨值出清在 2018~2026 的 20 條配對上，報酬與回檔都是 0/20 更糟，見十五章末）。
>
> 而且排在「到期」之前有個實際危害：**一筆已滿 10 日、該重新評分的部位，
> 畫面上只顯示「大盤轉空」，策略C 真正的出場條件被遮蔽。**
> 📉 的文字也由「大盤轉空，建議減碼」改為「大盤偏空（不構成出場理由）」、顏色改中性灰。

### UI 位置

| 區塊 | 位置 | 功能 |
|------|------|------|
| 側邊欄「📌 持倉觀察」 | 自選股清單**之上** | 只顯示（旗標／天數／毛淨損益／停損價），不放操作按鈕（空間有限） |
| 進場登錄 | 投資策略頁「符合進場條件」清單第 5 欄 📌 | 點擊展開表單，代號/名稱/進場價（預設最新收盤）/股數/停損價（×0.90）預填 |
| 持倉管理 | 投資策略頁，退場警示之後 | 每檔一列 + 🔄 續抱、📤 出場；到期時自動依評分給建議 |
| 退場警示列 📤 | 退場警示清單第 4 欄 | 該股若在持倉中直接出現，不用另外找 |
| 歷史交易紀錄 | 持倉管理區下方 expander | 勝率、平均損益、累計淨損益，與回測基準對照 |

**持倉成本佔比與資金配置警示（2026-08 新增）：**

側邊欄「📌 持倉觀察」每筆持倉的損益那行，新增「佔比 XX%」——分母是**目前所有持倉成本總和**（`sum(entry_price × shares)`，跨全部 `status='holding'` 的部位，不分股票），不是帳戶總資金。分母選擇是刻意的：系統目前沒有任何地方記錄使用者的總資金／現金水位（`positions` 表只知道每筆持倉自己的成本），要準確算「佔總資金 20%」需要額外請使用者手動輸入總資金並存進 DB，使用者評估後選擇先用「持倉成本總和」當分母（等於假設沒有現金水位，把資金集中度視為「持倉之間的相對佔比」而非「相對整體資產」），日後若要更精確可以再加總資金欄位。

投資策略頁「📌 持倉管理」區塊、在持倉列表之前，新增資金配置警示框（樣式比照多殺多/斷頭警告框，橘色 `#f59e0b` 邊框）。對應「策略規則」裡本來就寫好、但過去只是靜態文字、沒有真的檢查的兩條規則：
- 單一標的（同代碼多筆分批合計）佔目前持倉成本 **> 20%**
- 同時持有 **> 5 檔**（不同代碼數，`_uniq_codes`）

兩條都沒觸發時不顯示這個框，不佔版面。「大盤偏空時縮減至 50% 以下」這條規則因為需要知道「現金水位」才能檢查，在目前分母定義下無法有意義地計算（持倉本身永遠是自己的 100%），刻意不做成自動警示，維持策略規則區塊的靜態文字提醒即可。

**通則：** 這類「佔比／集中度」計算前一定要先確認分母是什麼——「佔目前持倉的比重」和「佔總資金的比重」是完全不同的兩個數字，混著看容易低估風險（尤其當使用者其實留了大筆現金水位時，用持倉總和當分母會讓集中度顯得比實際佔總資產的比重更高，這是保守方向的失真，比往樂觀方向失真安全，但使用者要清楚知道這個限制）。

**持倉成本佔比圖（2026-08 新增）：** 資金配置警示框下方新增一個可摺疊區塊（`st.expander`，預設展開），用水平長條圖視覺化每檔持倉的成本佔比，取代純文字列表。與警示框共用同一份 `_cost_by_code`／`_total_cost` 計算結果，不重複算。設計重點：
- 依佔比由小到大排序（`sorted(..., key=lambda kv: kv[1]['cost'])`），最大的一檔會排在圖表最上方（Plotly 水平長條圖預設由下往上畫，由小到大排序後最大值會出現在視覺上方，符合「重點在上面」的直覺）
- 顏色只有兩種：橘色（`#f59e0b`，佔比 >20%）／藍色（`#3b82f6`，正常範圍），跟資金配置警示框的橘色示警色呼應，一眼就能對到是哪幾檔觸發了警示
- 用 `add_vline(x=20, ...)` 畫一條「單檔上限 20%」的參考虛線，不用等看警示文字才知道門檻在哪
- hover 同時顯示佔比 % 與實際成本金額（元），文字列表版本沒有金額只有百分比，圖表補上這個細節
- 高度依持倉檔數動態計算（`max(160, 40 * 檔數)`），檔數少時不會過度壓扁，檔數多時不會擠成一團
- `_total_cost > 0` 才畫圖（避免除以零），跟警示框的顯示條件一致

**續抱機制（策略 C）：** `renew_position()` 把 `entry_date` 重設為今天並 `renew_count +1`，天數重新起算 10 日。「進場日」欄位因此代表**本輪起算日**。

> **✅ 2026-09-12 已補上 `original_entry_date` 欄位（陷阱47）。** 起因是發現 `entry_price` 從來不隨續抱改變，導致「進場日」與「進場價」脫鉤——緯創登錄 8/13＠169.5，但 8/12 收 193.5、隔天跌停也只到 174.2，**根本不可能成交在 169.5**。
>
> 現在的分工：`entry_date` = 本輪起算日（續抱會重設）；`original_entry_date` = 最初買進日（續抱不動，與 `entry_price` 同一時點）。既有 6 筆已用 `repair_original_entry_date.py` 推估回填，**推估值可在持倉列的 ✏️ 編輯表單修正**。

**到期建議來源：** 讀 `st.session_state['_wl_scores']`（自選股頁計算的評分快取）。若使用者沒先進過自選股頁，建議文字會顯示「請先計算評分」而不是給錯誤建議。

**零股支援：** `shares` 欄位以「股」為單位（1 張 = 1000 股），表單預設 1000 但可填任意值。淨損益計算會套用 `FEE_MIN` 低消，小額零股交易的成本比例明顯較高（實測：10 股台積電來回成本約佔 0.65%，100 股約 0.49%，1000 股整張則降到 0.4% 以下）。

**毛/淨損益的用途區隔：** 毛損益（純價差）與 `backtest_stocks.py` 的回測基準同基礎，可直接對照；淨損益是實際入袋金額。歷史紀錄區兩者都顯示，避免拿淨損益去跟回測數字比較而誤判策略失效。

### 分批獨立追蹤與策略驗證（2026-07 補強）

**同股多筆（分批 / 加碼）：** 刻意**不採用先進先出或加權平均**，改為「每次進場各自一筆」。理由：策略 C 的核心是每筆各自持有 10 個交易日、各自設停損；若合併成一筆，7/20 買的到期了但 7/28 加碼的才第 3 天，無法判斷出場，停損價也只剩一個平均值，與券商實際掛的多張停損單對不起來。

- `get_positions_by_code(code, status)` 回傳該檔全部持倉；`get_position_by_code()` 只回最新一筆（保留舊呼叫相容）
- 符合清單的 📌 按鈕在已持有時顯示 `📌N`（N=已持有筆數），仍可再按 = 加碼
- 退場警示列的 📤 在多筆時預設帶出**最早一筆**（先進先出精神），其餘至持倉管理區逐筆處理

**進場評分記錄（策略驗證的關鍵）：** `entry_score`（個股評分）與 `entry_ms`（大盤評分）在按 📌 時自動由 `sc` 與 `st.session_state['_market_ms']` 帶入。沒有這兩欄就無法回答「65 分門檻有沒有用」「大盤評分高時進場是否真的較好」——這正是整套策略的核心假設。

> **⚠️ `entry_ms` 有兩個已知限制（2026-09-12，陷阱46）：**
> 1. 它記的是**即時評分（S1–S11）**，而回測基準是**回溯評分（S1–S8）**，兩者差距可達 55 分（S9 最多給 11 分多方）。**拿它去對照回測結論等於兩把尺混用。**
> 2. 2026-09-12 之前登錄的紀錄，`_market_ms` 沒有帶資料日期，可能是更早某天的分數（實際資料中 8/14 兩筆一筆 100、一筆 60）。**既有 6 筆未回填，做分組統計時應排除或另行標註。**
>
> 之後登錄的紀錄，📌 表單會明白顯示「將記錄 X 日的大盤評分 NN 分」，過期會擋下來警告。

**出場原因（`exit_reason`）：** 出場表單的下拉選單（到期出場／停損／大盤轉空減碼／評分轉弱／主動獲利了結／其他），並依 `_position_status()` 的旗標自動預選（🔴→停損、📉→大盤轉空、⏰→到期），減少手動選擇的誤差。

**策略驗證儀表板（持倉管理區下方）：**

| 區塊 | 內容 |
|------|------|
| 未實現總覽 | 投入成本、目前市值、未實現毛/淨損益（持倉中，以最新收盤估算） |
| 已實現總覽 | 筆數、勝率、平均毛損益、累計淨損益；勝率與平均損益的 delta 直接對照回測基準（60.6% / +10.20%） |
| 依出場原因 | 停損 vs 到期 vs 大盤轉空各自的勝率與平均損益 |
| 依進場個股評分 | ≥75 / 70–74 / 65–69 三組——驗證評分門檻是否真的有鑑別度 |
| 依進場大盤評分 | ≥70 / 55–69 / 45–54 / <45 四組——驗證大盤過濾是否有效 |
| 續抱 vs 未續抱 | 對照回測的「續抱子集勝率 83.3%、均報酬 +27.2%」 |

**樣本數警語：** 已平倉 <20 筆時顯示提醒「差異多為隨機波動」，避免用個位數樣本推翻回測結論。

**毛/淨基準對齊：** 儀表板主要指標用**毛損益**與回測對照（回測算的是純價差），淨損益另外顯示為實際入袋金額。這個區隔在 UI 上要一直保持，否則會拿含手續費的數字去比不含手續費的回測而誤判策略失效。

**🚨 「勝率 vs 回測 60.6%」這個對照本身有兩個問題（2026-10-14 補記）：**

起因：使用者讀 2026-09-24 全市場那張表時問「**這樣的意思是當大盤可以進場時，
個股評分低於40的勝率是比較高？**」——讀法沒錯（該測試五組都有套大盤階梯，
程式只換 `score_filter`），但那張表揭露的事情連帶推翻了儀表板的勝率基準。

| 進場評分 | 筆數 | **報酬** | 同期大盤 | alpha | **勝率** |
|---|---|---|---|---|---|
| ＜40 | 5,643 | **+1.04%** | +1.73% | **-0.70%** | **45.6%** |
| 40–49 | 11,401 | +1.42% | +1.86% | -0.44% | 44.8% |
| 50–59 | 12,570 | +1.70% | +2.04% | -0.34% | 44.6% |
| 60–64 | 8,247 | +1.74% | +2.17% | -0.42% | 43.2% |
| **≥65** | 6,660 | **+1.87%** | +2.19% | **-0.32%** | **41.8%** |

**★ 兩欄是反向單調的：評分越高 → 報酬越高（+1.04%→+1.87%）、勝率越低（45.6%→41.8%）。**
機制：高分＝強勢股，「贏的次數少但贏得多」；低分＝弱勢股，「常常小贏但贏不多」。
而 `＜40` 的 **alpha 是五組最差的（-0.70%）**，`≥65` 反而最好 ⇒
**「低分勝率高」完全不能當成買低分股的理由。**

⇒ **儀表板那格「勝率 vs 回測」有兩個獨立的問題：**

| # | 問題 |
|---|---|
| ① | 基準 **60.6% 來自 176 筆時代的自選股**回測，而 2026-09-24 已確認那批數字含後見之明（自選股 +2.44% vs 全市場 -0.32%，差 2.76pp）|
| ② | **高分策略天生勝率低。** 照規則買 ≥65，勝率落在 **42% 附近是正常的**，不是策略失效 |

**⇒ 看到勝率那格偏紅，不可當成「策略壞了」。** 真正該看的是平均報酬與累計淨損益。
（UI 已於 2026-10-14 在那格下方加上這段說明——只寫在本文件不算數，陷阱48 的教訓。）

**⚠️ 這張表的三個限制必須一起引用：**
1. **五組 alpha 全部是負的**（-0.70% ~ -0.32%），都跑輸同期大盤；扣 0.47% 成本後更差。
   這張表比的是「哪一組虧得少一點」，不是「哪一組會賺」。
2. **alpha 那一欄其實分不出來**：五組全距 0.37pp ＜ 雜訊帶 0.60pp。
   **只有勝率那一欄超出雜訊**（3.8pp ≈ 4.1 個標準誤，而且是第三次量到同方向）。
3. 各區間是不同的交易集合、有狀態依賴 ⇒ 標準誤是低估的。

> **⭐ 方法論：勝率與期望值可以反向，所以勝率不適合當頭條指標。**
> 本專案這是第二次被它誤導——第一次是 2026-08 的「C 的尺量 D 的結果」（見下一段），
> 這次是「用一個與高分策略天性相反的指標去評價高分策略」。
> **判斷方法：任何「勝率 vs 基準」的對照，都要先問兩件事——
> (a) 基準是在哪一份樣本上算的？(b) 這個策略的設計，本來就該讓勝率往哪個方向走？**
**⚠️ 儀表板基準與實際執行規則可能不一致（2026-08 發現 → 同日已處理）：** 頂部四格 metric 的 `vs 回測` 差值寫死用**策略C**的基準（60.6%／+10.20%）。但使用者實際操作若走「大盤轉空減碼」提前出場，跑的其實是**策略D**的邏輯，而 D 自己的基準本來就低於 C。等於拿 C 的尺量 D 的結果，即使完美執行 D 也會兩格全紅、看起來像「策略失效」，可能誘使去動其實沒問題、且已用 404 筆驗證過的進場門檻或評分邏輯——真正的差異只在**出場規則**這一項。

**處理方式（2026-08-20，兩處）：**

1. **「📖 策略規則」區塊把 C 與 D 拆開標示**（原本兩者混在同一個「持有管理」清單裡，是混淆的源頭）：
   - 標題改為「**持有管理（正式規則＝策略 C）**」，並新增一行明講「持有期間**不因大盤轉弱自動出場**（這是 C 與 D 的關鍵差異）」
   - 原本埋在清單裡的「大盤淨值 ≥+4 全面減碼」抽出成獨立區塊「**⚠️ 大盤警報＝策略 D，非正式規則**」，寫明這是提醒不是規則、照 D 操作時別拿 C 的數字對照
   - 回測依據標題改為「回測依據（策略 C，**僅適用上方 C 規則**）」，下方 caption 完整說明基準對照注意事項
2. **儀表板新增自動偵測警示框**：計算已平倉紀錄中 `exit_reason == '大盤轉空減碼'` 的佔比，**≥30% 時**跳出橘色框，說明「上方 vs 回測 比的是 C 的基準，但你有 X% 是 D 的出場方式，差值偏紅不代表策略失效」，並指引改看「依出場原因分組」的「大盤轉空」那組。

**實作注意：** 佔比的分母必須與 `_stat()` 一致（同樣只算 `exit_price` 有值的紀錄），否則兩個數字的母體不同、佔比會失真。程式內已加註解。

**驗證：** 以當時實際資料測試——3 筆已平倉、3 筆都是「大盤轉空減碼」，佔比 100%，警示框正確顯示。

**仍未做（刻意）：** 沒有加「基準切換」或「自動改用 D 基準」。理由：D 的舊基準（2026-06 的 184筆／51.1%／+5.51%）是在資料範圍較短、且 Signal 4 門檻尚未經陷阱34校準前跑的，與現行 C 基準不同源，直接並列反而會製造新的誤導。等下次同一批資料重跑出 C／D 兩組可比的數字後再考慮。

### 評分衰退提示搬到持倉列表（2026-08 新增，純資訊揭露）

**問題：** 使用者反映「整體來說，還是感覺有些地方的敏感度不夠」。拆解後發現要區分兩種敏感度：

1. **規則的敏感度**（要不要更早出場）——已驗證三次（移動停損、confirm_days=1、策略D本身），結論一致：更敏感 → 空頭少賠 → 但常態下報酬被大幅侵蝕（移動停損最極端，EV +3.54%→+0.91%、勝率 50.8%→33.9%）。**不改。**
2. **資訊呈現的敏感度**（該看到的東西有沒有出現在會看到的地方）——這裡確實有缺口，而且改了不影響任何回測結論。

**具體缺口：** 「買入訊號衰退警告」（峰值≥65 且回落≥5分）原本只畫在個股頁的「⭐綜合評分」分頁，必須主動點進該股再切分頁才看得到；但使用者每天實際會看的是**側邊欄持倉觀察**與**投資策略頁持倉管理**。微星 2026-08-18 評分自峰值掉了 19 分，警告**確實有觸發**，卻因為埋在個股頁而沒被看見，兩天後（8/20）才以停損 -9.39% 收場。**不是系統沒偵測到，是偵測到了但講在不會去的地方。**

**做法：** 新增兩個 helper（定義在 `_position_status()` 正上方）：

- `_position_score_trend(code)`：取最近 5 個評分點（每 3 個交易日一點，約 15 日），回傳 `{'curr','peak','decline'}`。峰值取「不含今日」的前 4 點最大值，與個股頁邏輯完全一致。
- `_position_score_alert(trend)`：轉成 `(文字, 顏色)`，觸發條件同個股頁（峰值≥65 且回落≥5分）；今日 <65 用紅色、≥65 用橘色。

接入兩處：側邊欄持倉觀察每筆的損益那行下方、投資策略頁持倉管理每列下方（到期建議之前）。顯示格式 `📉 評分 56（近期峰值 82，-26）`。

**效能：** 單檔算 5 點約 0.6 秒，故以 `st.session_state` 快取，key 為 `_pos_trend_{code}_{最新價格日期}`，資料更新後自動失效重算。持倉通常僅數檔，首次渲染成本可接受。

**⚠️ 實作陷阱（第一版寫錯、已修正）：** `full_score()` 要的 ownership 參數是**正規化後的持股結構 dict**（`{'foreign','trust','dealer','director','retail'}`），不是 `get_ownership()` 的原始回傳（`{'foreign_pct','date'}`）。第一版直接把原始列傳進去，會導致**同一檔股票在持倉列與自選股頁算出不同分數**。正確組法必須與 `render_sidebar()` 內自選股評分那段完全相同（`_fpct = round(_own['foreign_pct'],1) if _own else 52`，再組 5 個 key）。程式內已加註解提醒。

**驗證（4檔實際持倉，以 2026-08-18 為基準日回測）：**

| 股票 | 8/18 評分（峰值） | 觸發 | 後續實際 |
|---|---|---|---|
| 微星 | 69（76，-7） | 🟡 | 8/20 觸發停損 -9.39% |
| 緯創 | 71（92，**-21**） | 🟡 | 8/19 出場 +5.01% |
| 國泰金 | 87（92，-5） | 🟡 | 8/19 出場 -2.57% |
| 南亞科 | 77（73，**+4**） | — | 撐過 8/19 大跌，8/20 反彈續抱 |

四檔中三檔在 8/18 就亮燈，而**唯一沒亮燈的南亞科正好是唯一撐過來的那檔**。鑑別度不是新設計出來的，偵測邏輯完全沿用既有的，只是搬到看得到的位置。**但這是 4 檔、1 天的觀察，不足以當統計證據，不可據此宣稱有預測力。**

**定位：純資訊提示，不是出場指令。** 出場仍依停損／到期評分／大盤警報三項既有規則，未改動任何已驗證邏輯，不影響任何回測結論。UI 文字明確寫出這點，避免被當成第四種出場規則。

**⚠️ 這個定位已經過回測驗證、不可更改（2026-08-20）：** 使用者隨後提出「看到亮燈就自行出場，應該更能保全獲益」，實測結果是**扣掉交易成本後由賺轉賠**（+0.17% 毛EV、勝率僅26.6%、交易次數翻倍到851筆）。詳見十五章「策略F：評分自峰值衰退即出場」。**每次亮燈都出場，長期是虧錢的**——這個提示的正確用法是「這檔要特別盯著」，不是「立刻出場」。日後若有人想把它升級成規則，先讀那一節。

**通則：** 「系統敏感度不夠」的抱怨，要先分清是**規則不夠敏感**（改了有代價，須回測）還是**資訊沒出現在使用者會看的地方**（改了沒代價）。本專案已累積不少「有偵測、但只畫在深層頁面」的功能（個股轉折觀察清單、軋空偵測 🌀⚡ 旗標只在自選股清單、過熱衰竭清單等），日後遇到類似回饋，**先檢查是不是後者**，優先做零成本的資訊搬移，再考慮動規則。

### 手動登錄持倉：登錄入口不可綁在推薦清單上（2026-08 修正）

**問題（使用者實際遇到）：** 買進某檔後又跑了一次資料更新，該股從「符合進場條件」清單消失，**於是已經成交的部位反而無法登錄**。

**根本原因（設計缺陷，非操作錯誤）：** 原本唯一的登錄入口是投資策略頁「符合進場條件」清單第 7 欄的 📌 按鈕，而且進場登錄表單本身也**巢狀寫在 `if qualified:` 區塊內**——該股不在清單上，表單根本不會渲染。但那份清單每天會隨資料更新變動：個股評分下滑、或大盤評分下降導致門檻提高（例如大盤由 70 掉到 50，門檻從 65 跳到 75），都會讓剛買進的股票消失。

**設計原則：交易紀錄是既成事實，不該取決於系統當下推不推薦這檔股票。** 推薦邏輯（會變動）與紀錄功能（不可變動）必須解耦。

**做法：** 新增 `_render_manual_add_position()`（定義在 `_render_position_manager()` 正上方），以 `st.expander('➕ 手動登錄持倉（任一檔，不受進場清單限制）')` 放在「📌 持倉管理」區塊最上方——該區塊**不論有無持倉、不論清單內容都會渲染**。輸入代號後用 `search_stock()` 帶出名稱、`_latest_close()` 帶出收盤價、`_score_for_code()` 算今日評分。可登錄任意代號（含非自選股）。

**同時新增 `_score_for_code(code)`：** 算單一檔今日綜合評分的共用 helper，ownership 組法與 `render_sidebar()` 自選股評分完全一致（同十八章那個 ownership 正規化陷阱）。

**⚠️ 關鍵設計：`entry_score` / `entry_ms` 改為可手動修改。** 📌 按鈕那條路徑是「當下看到清單就登錄」，帶入的今日評分即進場評分，沒有問題；但手動登錄的典型情境是**買進後隔一兩天才補登錄**，此時今日評分已不等於進場當天的評分。這兩個欄位是策略驗證分組統計的依據（驗證「65分門檻是否有效」「大盤過濾是否有效」），填錯會讓驗證失真，因此欄位預設帶今日值但可改，並在表單內附警語。不確定當初數值時，也可先登錄、之後用持倉列的 ✏️ 編輯表單修正。

**通則：** 凡是「記錄既成事實」的功能（持倉登錄、出場登錄、筆記），入口都不可以依附在「系統當下的推薦/篩選結果」上——推薦邏輯是會隨資料變動的，而事實不會。設計時要檢查：這個表單是不是巢狀在某個 `if 條件成立:` 底下？如果是，那個條件會不會在使用者需要用它的時候剛好不成立？

### 紀錄編輯與資料正確性（2026-07 補強）

**問題：** 手動鍵入的進場/出場價若打錯（例如 1180 打成 118），會直接汙染策略驗證的所有統計數字，且錯誤會永久留在歷史裡。

**做法：** 持倉列與歷史明細列都有 ✏️ 按鈕，開啟共用的編輯表單：
- 持有中：可改進場日／進場價／股數／停損價／進場評分／大盤評分／備註
- 已平倉：另可改出場日／出場價／出場原因，表單即時預覽修正後的毛/淨損益
- 表單內含 🗑 刪除，供整筆誤植時移除

**關鍵：`recalc_position_pnl(pid)`** —— `pnl_pct` 是在 `close_position()` 當下算好存起來的，編輯價格後**必須呼叫此函式重算**，否則統計會用到舊值。`update_position()` 本身不會自動重算（它是通用的欄位更新），所有改動 entry_price / exit_price 的地方都要記得補這一行。

**`update_position()` 的 allowed 白名單：** 新增欄位時要同步加入，否則該欄位會被靜默忽略（不報錯），這是容易漏掉的地方。目前允許：entry_date, entry_price, shares, stop_price, note, exit_date, exit_price, status, entry_score, entry_ms, exit_reason, pnl_pct, name。

**回測與實際紀錄的分工（設計原則）：**

| | 回測（backtest*.py） | 實際持倉紀錄（positions） |
|---|---|---|
| 資料 | 全體歷史，模擬嚴格照規則執行 | 使用者真實買賣的少數筆 |
| 驗證對象 | 策略規則本身是否有效 | 實際執行結果（含人為判斷與成本） |
| 樣本 | 數百筆，統計意義高 | 累積慢，但真實 |

兩者**都要保留、並排對照**。差距本身就是資訊：實際明顯差於回測時，通常是執行落差（未照規則出場、追高進場、手續費侵蝕），而非策略失效。日後重跑回測仍以整體歷史資料為準，不因實際紀錄而改變回測邏輯。

### 雲端唯讀同步與密碼／加密保護（2026-08 新增）

**動機：** 使用者想在外面（非本機電腦）也能看側邊欄的持倉觀察，但 positions 是個人交易紀錄，不能像大盤分析一樣直接公開。設計目標：雲端只能「看」，不能「寫」；就算資料被同步上 GitHub，沒有密碼也看不到內容。

**範圍刻意收斂：** 只有側邊欄「📌 持倉觀察」這個唯讀清單會出現在雲端；投資策略頁的持倉管理（續抱/出場/編輯表單）維持 `if IS_LOCAL:`，雲端完全不顯示。原因：雲端 DB 是暫時性的（每次重新部署就重建），寫入操作在雲端做了也留不住，還會誤導使用者以為真的改到了本機資料。

**原本想法（已放棄）：把 GitHub repo 設為 Private。**
流程上這是最乾淨的做法——repo 私有後，就算同步了明文 JSON，外人也看不到。但實際操作卡在 Streamlit Community Cloud 的 GitHub 連接方式：這個帳號是用**舊式 OAuth App**（GitHub → Settings → Applications → *Authorized OAuth Apps* 裡的「Streamlit」，不是 *Installed GitHub Apps*）連接的，repo 改 Private 後 App 直接壞掉（log 顯示 `Cloning repository... Failed` / `Failed to download the sources`）。嘗試「Revoke 舊授權 → 重新連接」也沒有觸發預期中的重新授權畫面，反覆 Reboot 仍是同樣的錯誤。折騰約 40 分鐘後放棄，**改回 Public**，App 立刻恢復正常——這證實問題確實出在 Private 化後的授權銜接，不是程式碼或別的原因。

**教訓：** 如果之後想再試一次 Private repo，要先確認 Streamlit Cloud 的 GitHub 連接方式是新版 GitHub App（有 Repository access 清單可以勾選 repo，像 Vercel 那樣）還是舊版 OAuth App（只有整包授權/撤銷，沒有細部設定）。是舊版 OAuth 的話，靠「Revoke + 期待自動跳出新同意畫面」不可靠，得先在 Streamlit Cloud 自己的介面裡找到明確的「重新連接 GitHub」按鈕主動觸發，不能只在 GitHub 那側操作。

**最終做法：repo 保持 Public，資料本身加密。**

三層防護疊起來：

| 層 | 做法 | 防的對象 |
|---|---|---|
| 1. 資料加密 | `positions.json` 內容用 XOR + base64 打亂，不是明文 | 直接逛 GitHub repo 的人 |
| 2. App 密碼關卡 | 雲端側邊欄持倉觀察需輸入密碼解鎖 | 打開 App 網址亂看的人 |
| 3. 唯讀 | 雲端完全沒有寫入 UI | 就算密碼外流，頂多看到資料，改不了 |

**明確定位：這是「防君子」等級，不是真加密。** XOR 不是密碼學安全的演算法，只是讓內容從「一眼看懂的 JSON」變成「看不懂的亂碼」，擋的是「剛好逛到你 repo 的路人」，擋不住「刻意想破解、寫程式硬爆的人」。使用者已明確認可這個防護等級（原話：「防君子的做法就可以」），不需要為了做到更強的加密再引入額外套件或服務。

**加解密實作（`github_sync.py`）：**
```python
def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def _encrypt_json(obj, key: str) -> str:
    raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    return base64.b64encode(_xor_bytes(raw, key.encode('utf-8'))).decode('ascii')

def _decrypt_json(token: str, key: str):
    raw = _xor_bytes(base64.b64decode(token.encode('ascii')), key.encode('utf-8'))
    return json.loads(raw.decode('utf-8'))
```
只依賴標準函式庫（`base64`），沒有加新的 pip 套件——刻意選擇，避免 Streamlit Cloud 部署時多一個套件安裝失敗的風險點。

**金鑰存放：** `POSITIONS_ENC_KEY` 本機存在 `config_local.py`（不上傳 Git），雲端存在 Streamlit Cloud 的 Secrets，兩邊要完全一致，否則雲端解密會直接噴例外（`_decrypt_json` 沒有 try/except，錯誤金鑰產生的 bytes 通常不是合法 JSON，`json.loads` 會丟 `JSONDecodeError`，外層 `init_cloud_data()` 的 try/except 會吞掉並印「持倉部位匯入失敗」，畫面上就是雲端持倉區塊沒有資料——追查時先確認這把金鑰兩邊有沒有貼一致）。`_get_positions_enc_key()` 統一處理「雲端讀 `st.secrets`、本機讀 `config.py`（來自 `config_local.py`）」的分支，其他程式碼不用關心來源。

**密碼關卡（`app.py` `_positions_unlocked()`）：** 本機一律回傳 `True`（自己的電腦不需要密碼）；雲端檢查 `st.session_state['_pos_unlocked']`，沒解鎖就在側邊欄畫一個密碼輸入框，`POSITIONS_PASSWORD` 沒設定時直接回傳 `False` 且不顯示任何輸入框（保守預設：沒設密碼視同還沒準備好，不會意外曝光）。呼叫端寫法：`if IS_LOCAL or _positions_unlocked():`——`IS_LOCAL` 為真時靠短路求值直接跳過函式呼叫，本機完全不受這段邏輯影響。

**資料流（`export_to_json()` → `init_cloud_data()`）：**
1. 本機 `export_to_json()`：`SYNC_POSITIONS_TO_CLOUD=True` 且 `POSITIONS_ENC_KEY` 有值時，才把 `get_positions(None)`（全部，含 holding 與 closed）加密寫入 `positions.json`，格式 `{'enc': <密文>, 'exported_at': ...}`；金鑰未設定時直接跳過匯出並印警告，不會意外寫出明文。
2. 雲端 `init_cloud_data()`：讀到 `positions.json` 後解密、呼叫 `database.import_positions(rows)` 整批覆寫雲端暫存 DB 的 `positions` 表（先 `DELETE FROM positions` 再逐筆 `INSERT`，保留原始 `id`）。
3. `positions` 已加入個股 JSON 迴圈的 skip 名單，避免被誤判成股票代號。

**`database.py` 新函式：** `import_positions(rows)`——雲端唯讀匯入專用，本機端不應呼叫（本機一律用 `add_position` 等既有 CRUD 函式）。

### 評估出場決策的窗口長度（2026-09-12，**推翻了一個既有結論**）

**起因：** 使用者說「近數個月的盤真不好做…像國泰，進了場一直不動，賣掉了它就一直漲上去；其它也有些利潤，但沒兩天利潤就被吃掉」。為了回答而去查四筆已平倉紀錄**出場之後 15 個交易日**發生了什麼。

| | 出場日／原因 | 出場後 15 日 | 最高 | 判定 |
|---|---|---|---|---|
| 緯創 | 8/19 大盤轉空減碼 | **+6.2%** | +11.2% | ❌ 賣飛 |
| 微星 | 8/19 大盤轉空減碼 | **+7.6%** | +11.0% | ❌ 賣飛 |
| 國泰金 | 8/19 大盤轉空減碼 | **+12.3%** | +16.9% | ❌ 賣飛 |
| 所羅門 | 9/9 **停損**（唯一照規則走的） | -4.1% | — | ✅ 賣對 |

**兩個發現：**

1. **前三筆是同一天、同一個決定**，不是三次獨立失誤。而那天系統淨值只有 +1，**兩個減碼警報（+2／+4）都沒觸發**。

> **❌ 本則原本寫「是人為推翻規則」——那個歸因是錯的，2026-09-17 由使用者更正：**
> 「那幾張未持滿10天而出清的個股，**我是看了大盤的評分上的評語才出清**」。
> 查證後屬實：大盤分析頁的綜合判斷框從 `net≥1` 起就在暗示降部位，而該框**完全沒有**
> 提到策略C。**不是使用者不照規則，是 UI 叫他這樣做的。** 完整記錄見陷阱48。
2. **策略 D 的回測結論在此再次應驗**：大盤轉空提前出場在多頭段是錯殺（十五章空頭段驗證），8/19 大盤淨值 +1 根本不是空頭。

**⚠️ 方法論收穫（本則的主要價值）：評估出場決策的窗口長度，必須對齊策略的持有期。**

策略C 的持有期是 **10 個交易日**，那麼「這次出場是對是錯」就該用 10–15 日的窗口看。上一節（策略E第二次驗證）當初用 **1 個交易日** 的漲跌下了「事後看方向正確、整體划算」的結論——同一批交易、同一個決定，**換成 15 日窗口後三筆全部翻盤**。

這與十五章「必須看 alpha 不能看原始報酬」、「必須設無條件基準對照組」是同一族的錯誤：**都是評估的量尺本身選錯，而不是數字算錯**。差別在於前兩者是「扣掉什麼」，這一則是「看多久」。

**判斷方法：問一句「如果我把觀察窗口拉長到一個完整持有期，這個結論還成立嗎？」** 尤其在「事後看某個決定對不對」這種回顧時——短窗口幾乎必然偏向「當下感覺對」的那一邊，因為人通常是在短期不利的當下才做出那個決定的。

**同時記錄的市場背景（供日後比對）：** 2026-07-17～09-11 指數 42,671 → 46,185（**+8.23%**），但期間最低 39,933、最高 47,326，**振幅 18.5%**。這是「上漲但反覆甩轎」的盤型，10 日持有期正好卡在最難受的長度（不夠短到躲開震盪，不夠長到吃到趨勢）。使用者「利潤兩天就被吃掉」的體感是真實的市場特徵，**但那不是這四筆虧損的主因**——主因是上面那個人為決定。**回答「最近是不是特別難做」這類問題時，要把「盤的特性」與「執行落差」拆開講，兩者都真實但對策完全不同。**

---

### 33. fetch_chips() 投信/自營商欄位索引錯誤（2026-07 修正）

**現象：** 大盤評分某日跳到 100 分。追查 S4（法人現貨）時發現 `chips_market_agg` 的數字不合理：
- 自營商淨額**每天都是 0**
- 投信**每天都是大幅買超**（3.8萬～12萬張），連續 15 個交易日沒有一天賣超
- 單日檢查：7/30 共 1344 檔，投信買超 988 家、**賣超 0 家**（不可能）
- 外資偶爾出現 ±127 萬張的離譜值

**根本原因：** `fetch_chips()` 的 T86 欄位索引抄錯。T86 正確欄位順序（`fetch_t86()` 的註解有正確版本，但 `fetch_chips()` 沒沿用）：

```
[2][3][4]    外陸資 買進/賣出/買賣超（不含外資自營商）
[5][6][7]    外資自營商 買進/賣出/買賣超
[8][9][10]   投信 買進/賣出/買賣超
[11]         自營商買賣超（合計）
[12][13][14] 自營商 買進/賣出/買賣超（自行買賣）
[15][16][17] 自營商 買進/賣出/買賣超（避險）
```

舊版誤用：
| 欄位 | 舊版索引 | 實際抓到的內容 | 後果 |
|------|---------|--------------|------|
| `trust_net` | `[13]` | 自營商**賣出股數**（自行買賣） | 永遠是正值 → 投信永遠「買超」 |
| `trust_buy` | `[11]` | 自營商買賣超（合計） | 語意錯亂 |
| `dealer_net` | `[7]` | **外資自營商**買賣超 | 多數股票為 0 → 自營商全空 |

**影響範圍：** S4（法人現貨）長期給出偏多的假訊號——投信那項幾乎永遠 +1 分。個股籌碼頁的投信/自營商欄位同樣失真。

**修正：** `fetch_chips()` 主路徑、備援路徑、歷史補抓共 3 處改為：
```python
'trust_buy':    row[8],  'trust_sell': row[9],  'trust_net': row[10],
'dealer_buy':   row[12] + row[15],   # 自行買賣 + 避險
'dealer_sell':  row[13] + row[16],
'dealer_net':   row[11],             # 自營商合計
```
並在函式 docstring 補上完整欄位對照與此錯誤的說明。

**歷史資料回填：** 既有 chips 資料全部受污染，提供 `backfill_chips_fix.py`（一次性腳本）重新向 TWSE 抓取近 N 個交易日並用正確索引覆寫（預設 60 日，可傳參數）。腳本結尾會自動驗證「投信賣超家數 > 0」「自營商合計 ≠ 0」。

**通則：** 同一支 API 在專案內被多處解析時（本例 T86 被 `fetch_t86()` 與 `fetch_chips()` 各自解析一次），欄位對照應集中在一個地方或至少互相引用註解。`fetch_t86()` 的註解寫著「依診斷確認」，代表當初有人踩過坑並修正，但 `fetch_chips()` 沒同步。**發現某支 API 的欄位定義後，要搜尋全專案是否有第二處解析同一支 API。**

---

### 34. Signal 4 門檻未隨資料來源改版而校準（2026-07 修正）

> **🚨 這一則的修正本身有三個問題，2026-10-07 已被陷阱51 取代。先讀那一則。**
> 1. 本則說「抓 50–250 日的實際分布算百分位」，但**實際只用了 51 天**。
>    拉到 258 天，新門檻的觸發率是 **1.6／5.0／7.8%**，而本則自訂的目標是 5／15／30%。
> 2. 量級會隨市場規模漂移（外資 p95：2025 是 366,841、2026 是 544,660，**差 48%**）
>    ⇒ **任何絕對張數的門檻都不可能同時適用 2018 與 2026。** 已改為滾動百分位。
> 3. 本則寫了「三處門檻要一起改」並照做了，**但沒同步「資料來源」**——
>    回測讀 `t86_ranking`、app.py 讀 `chips` 彙總，於是 chips 校準的門檻
>    套在 t86_ranking 加總上，**回測的 ±3分觸發率是 0.0%（一次都沒觸發過）**。
> 4. 另外 `chips` 全表加總含 ETF，而主動型 ETF 的「外資買賣超」是申購買回量
>    ⇒ **11% 的日子外資方向被整個翻轉**。

**現象：** 大盤評分連續多日接近 100 分，即使市場處於明顯空頭。追查發現 S4（法人現貨）幾乎每天都給滿分偏多。

**根本原因（延續陷阱 10 的後遺症）：** 陷阱 10（2026-06）為了讓頁面上下數字一致，把 S4 的資料來源從 `get_t86_market_aggregate()`（只加總 T86 排行**前 15 名**，數值幾千張）改為 `chips_market_agg`（**全市場 1300+ 檔**加總，數值數十萬張），**但門檻沒有跟著改**。

**實測觸發頻率（近 51 個交易日）：**

| 舊門檻 | 觸發天數 | 佔比 |
|---|---|---|
| 外資 \|net\| ≥ 150,000（±3分） | 41/51 | **80.4%** |
| 外資 \|net\| ≥ 50,000（±2分） | 45/51 | 88.2% |
| 投信 \|net\| ≥ 50,000（±1分） | 30/51 | 58.8% |

實際分布：外資絕對值中位數 **374,801 張**、投信 **59,393 張**。等於 S4 退化成「今天合計是正的就 +3、負的就 -3」，完全沒有強弱鑑別度。

**新門檻（比照 S3 台指期的校準原則：±3分約5%天數、±2分約15%、±1分約30%）：**

| 訊號 | 舊 | 新 | 對應百分位 |
|---|---|---|---|
| 外資 ±3分 | 150,000 | **1,050,000** | p95 |
| 外資 ±2分 | 50,000 | **800,000** | p85 |
| 外資 ±1分 | 10,000 | **650,000** | p70 |
| 投信 ±1分 | 50,000 | **100,000** | p70 |

**同步修改處：** `app.py` Signal 4 區塊、`backtest.py`、`backtest_stocks.py`（後兩者原本用更舊的 3,000/1,000/2,000，是三份不同步的門檻）。

**回測影響（452 交易日）：** 有方向準確率 51.4%（不變）、強訊號準確率 60.0% → **60.6%**（略升）。準確率無顯著變化，但強訊號天數從 89 天降到 79 天，代表訊號變得更有選擇性。

**實例（2026-07-30）：** 外資 +177,761 張、投信 +36,381 張 —— 舊門檻給 +3 分偏多，新門檻給 **0 分**。大盤評分因此從 100 降到合理區間。

**通則：** 修改訊號的**資料來源**時（尤其是換成不同涵蓋範圍的資料表），必須同步重新校準門檻。判斷方法：抓 50–250 日的實際分布算百分位，確認「強訊號」的觸發頻率落在 5–10%，而不是 80%。這類 bug 不會報錯，只會讓訊號安靜地失去作用。**專案內有多份實作同一訊號時（app.py / backtest.py / backtest_stocks.py），三處門檻要一起改。**

---

### 35. prices.change_pct 欄位約 4.7% 資料被誤存為 0（2026-08 發現，尚未修復）

**現象：** 驗證「波動度是否影響策略績效」時，用 `change_pct` 欄位算個股近 20 日日報酬標準差，發現 404 筆回測交易中有 140 筆波動度剛好等於 `0.00`——機率上不可能。

**追查：** 直接查該股當期 `close` 序列（例如 6274：257.44→256.45→251.49→259.42…），收盤價逐日確實在變動，但同期 `change`／`change_pct` 卻是字面上的 `0.0`。確認是資料寫入錯誤，不是市場真的沒有變化。

**規模：** 全表掃描後，`prices` 表約 **7,095 / 150,332 筆（4.7%）**受影響，涵蓋 **1,496 檔股票**，時間分布平均橫跨 2025-03 至 2026-08 全區間（不是單次批次匯入造成的一次性瑕疵，較可能是某條抓取路徑持續性地在特定情況下漏算）。根本原因（是哪個 `fetcher.py` 路徑、什麼條件觸發）**尚未查明**。

**目前處置（繞開，非修復）：** 任何需要「日報酬率」的新計算一律**不信任 `change_pct` 欄位**，改由 `close` 價格逐日反推：`(close_today - close_yesterday) / close_yesterday * 100`。`indicators.py` 新增的 `vol20`（見四、database.py 章節下方 indicators 說明）即採此作法，程式內有對應註解。

**尚待辦：** 這則只是記錄發現，**尚未追查 `fetcher.py` 寫入 `change`/`change_pct` 的邏輯**、也**尚未回填既有錯誤資料**。日後若有人要處理，建議：
1. 先確認受影響筆數是否還在增加（如果新抓的資料也中招，代表 bug 還活著，要優先修 `fetcher.py`；如果只在舊資料，回填一次即可）
2. 全表掃描邏輯：`SELECT code, date FROM prices WHERE change_pct = 0` 再逐筆比對前一日 `close` 是否真的相同，排除真正平盤的正常案例
3. 回填時比照陷阱 27／33 的模式寫一次性腳本，而不是手動改 DB

**通則：** 涉及「報酬率／漲跌幅」的欄位，若該欄位是**寫入時計算好存起來**（而非用時現算），要對「是否可能存在計算失敗但仍寫入預設值 0」保持警覺——0 在這類欄位常常是「正常收盤持平」與「計算錯誤」兩種情況的疊加，光看數值分不出來，只能對照原始價格資料交叉驗證。

**✅ 2026-09-01 已查明根因並修復（含資料回填），以下為完整記錄：**

**觸發：** 使用者問「昨日大盤評分40，今日開盤大漲，評估原因」。檢視 TAIEX 時發現 2026-08-31 的 `change_pct` 存 **+0.33%**，但用收盤價實算是 **-0.44%**（46,331 → 46,128）。經 TWSE 官方 FMTQIK API 核對：8/31 收盤 46,128.47、漲跌 -202.98 點——**收盤價是對的，漲跌幅是錯的**。

**兩個根因：**

| # | 位置 | 問題 | 影響 |
|---|---|---|---|
| 1 | `fetch_history_tpex()`（約 931 行） | `'change': 0, 'change_pct': 0` **直接寫死** | 上櫃股票只要走過歷史回補，漲跌幅全部歸零——這是 1,496 檔大量歸零的主因 |
| 2 | `fetch_taiex()`（約 2789 行） | 用迴圈內遞推的 `prev_close` 變數算漲跌幅 | yfinance 回傳的 `hist` 只要少了某個交易日，基準就停在更早的日期，**算出錯值卻不報錯** |

**根因 2 的證據（診斷方法值得記下來）：** 掃描 TAIEX 400 筆找出 3 筆不符（2026-08-04／08-18／08-31），再用 `隱含前收 = close ÷ (1 + 存的pct)` 反推，發現三次的隱含前收**都精確對應到「前兩個交易日」的收盤**（43,119.75=7/31、45,811.01=8/14、45,975.22=8/27），即每次都剛好漏掉一個交易日。**用反推基準去對照歷史收盤，是定位這類「計算基準錯誤」問題最快的方法。**

**修復：**
1. `fetch_taiex()`：改成先把整份 `hist` 收成 `{date: close}` 對照表，用「該日在對照表中的前一個交易日」計算；查不到才退用 DB 的前一日收盤；兩者都沒有才給 0。
2. `fetch_history_tpex()`：改用相鄰收盤價計算，只有第一筆（無前一日）留 0。
3. `repair_change_pct.py`（一次性腳本，已進版控）：用 `close` 重算全表。

**⚠️ 修復腳本必備的兩道守衛（第一版沒有、試跑就爆掉）：**
- **日期斷層守衛**：相鄰兩「列」不等於相鄰兩「交易日」。第一版無條件用相鄰列計算，試跑出現 `0051 +357.72%`、`0053 +544.92%`——因為那些股票 2017-12-18 之後直接跳到 2026-05-22（相隔 3,077 天）。加上 `gap > 7 天就跳過`（同陷阱26「季度資料被當日資料算漲跌」的教訓）。
- **離譜值守衛**：算完仍 `|pct| > 40%` 就不寫入（台股有 10% 漲跌幅限制，除權息/減資/新上市首日會超過，40% 當異常門檻）。實際擋下 2 筆（00685L -96%、5314 -74.1%）。

**實際修復結果：** 掃描 186,795 筆，修正 **24,442 筆（13.08%）**、涉及 1,906 檔（比陷阱35當初估的 4.7% 高很多，因為當初只看 `change_pct = 0` 這一種樣態，沒算到「值是錯的但不是0」）。跳過日期斷層 2,067 筆、離譜值 2 筆，兩類保持原值。TAIEX 修復後與 TWSE 官方逐日核對**全部相符、剩餘不符 0 筆**。

**操作紀錄：** 執行前已備份 `data/stock.db.bak-20260901`。腳本預設試跑（只報告不寫入），加 `--apply` 才實際寫入。

**通則（補充）：** 任何「用迴圈內遞推變數當計算基準」的程式碼都是脆弱的——只要來源資料有缺漏，基準就會靜默偏移。**計算基準應該從權威來源（DB 或完整對照表）查，而不是從迴圈狀態推。** 而寫修復腳本時，「相鄰兩列 = 相鄰兩期」這個假設幾乎總是錯的，必須先加日期間隔守衛再動手。

---

### 36. git reset --hard 誤把本機新資料退回 8 天前（2026-08 發生）

**現象：** 推送波動度標示功能時，本機 git 分支與遠端分岔（本機領先 8 個 commit、落後遠端 344 個 commit），`git pull --rebase` 對上百個 `data/json/*.json` 檔案炸出衝突。改用 `git reset --hard origin/main` 再 `cherry-pick` 程式碼 commit 的方式解決分岔後，雲端版資料日期卻倒退回 **8/4**，即使本機資料庫明明已經更新到 8/12。

**根本原因：**
1. 本機這幾天（8/7～8/12）透過某個沙盒／掛載環境執行的 git 操作，累積了一串自己的「sync data」commit，但這些 commit **從未真正 push 上 GitHub**——只存在本機端的 git 歷史裡。
2. 與此同時，GitHub 遠端 repo 自己有一條獨立的「更新資料」commit 鏈，數量雖多（344個），但內容**沒有比本機新**——實際最新的一筆資料是 8/4。兩條歷史各自往前走、互不相通，才會出現「commit數量遠端領先很多、但內容反而更舊」這種反直覺情況。
3. 為了解決分岔，執行 `git reset --hard origin/main` 把本機分支重設到遠端最新狀態——這個指令**只重設 git 版本控制的歷史**，不會動到 SQLite 資料庫本身，但會讓「已經 commit 進 git、但還沒 push 的本機資料快照」（8/7～8/12 那幾筆）憑空消失，改成接上遠端那個較舊（8/4）的版本。

**修復：** 因為 SQLite 資料庫（`data/stock.db`）完全沒受 git 操作影響，本機重新按一次「🚀 更新並同步到雲端」（`export_to_json()` + `sync_via_git()`），直接從資料庫當下最新狀態（8/12）重新匯出 JSON 並推送，就把遺失的資料補回來了，不需要額外復原步驟。

**過程中的其他插曲：**
- 本機沙盒／掛載環境對這個 repo 的檔案操作權限有限，`git rebase --abort` 執行到一半因為 `unable to unlink ... Operation not permitted` 失敗，留下半殘的 rebase 狀態，最後只能請使用者回到自己 Mac 的真實 Terminal 處理，沙盒環境不適合對這個 repo 做涉及大量檔案增刪的 git 操作（rebase / checkout 大範圍切換）。
- rebase 卡住時本機 Streamlit App 還開著，搶 `.git/index.lock` 導致 `Another git process seems to be running` 錯誤——處理 git 分岔問題前，應先關閉本機執行中的 App（或至少確認沒有背景排程正在跑同步）。
- zsh 互動模式預設不支援貼上帶 `#` 開頭註解的指令行（跟 bash 不同），會噴 `command not found: #`；之後提供指令給使用者貼到 Terminal 時，一律不夾帶註解行。

**通則：**
1. `git reset --hard <remote>` 之前，不能只看「領先/落後幾個 commit」就假設遠端內容比較新——一定要先看遠端最新 commit 的**實際內容日期**（例如 `git log -1 origin/main` 的 commit 訊息或內容），數量多不代表內容新，尤其像本專案這種「有兩個獨立環境可能各自對同一個 repo 做過 git 操作」的狀況。
2. 這個專案的資料流是「SQLite DB（本機權威來源）→ export_to_json() → git commit/push」單向流程；git 歷史再怎麼亂，只要 DB 沒壞，永遠可以重新 export 一次補回最新狀態，不用著急用 git 手法硬救資料。真正需要小心保護的是**程式碼 commit**（人工寫的邏輯改動），資料類 commit 遺失了可以重造。
3. 沙盒／遠端掛載環境若對倉庫做 git rebase/reset/checkout 之類需要大量檔案 unlink 的操作卡住失敗，不要在同一個環境裡反覆重試——直接請使用者到本機真實 Terminal 處理，那裡才有完整檔案系統權限。

---

### 37. .git/refs/.DS_Store 造成 push 500 Internal Server Error（2026-08 發生）

**現象：** 解決陷阱 36 的分岔問題、本機 commit 都正常之後，`git push origin main` 卻連續失敗，錯誤是 `remote: Internal Server Error`（HTTP 層有收到 200，但 git-receive-pack 的回應內容本身回報伺服器端錯誤）。GitHub 官方狀態頁當下顯示一切正常，排除是大範圍事故。

**追查：** 用 `GIT_CURL_VERBOSE=1 git push` 確認連線、認證都正常（object 有成功上傳），問題出在 GitHub 收到 push 之後、處理 receive-pack 這一步。改用 `git fsck --full` 檢查本機倉庫完整性，發現兩個問題：
1. `error: refs/.DS_Store: badRefName`——macOS Finder 瀏覽 `.git/refs/` 資料夾時自動產生的 `.DS_Store` 隱藏檔，被 git 誤判成一個命名不合法的 ref。
2. 367 個 `garbage found: .git/objects/.../tmp_obj_*`——先前沙盒環境權限不足（見陷阱 36）導致 git 操作中斷，留下大量寫壞的暫存物件檔案。

fsck 沒有回報任何正式物件 `missing` 或 `corrupt`，代表倉庫實際內容是完整的，問題出在這兩類「垃圾檔案」上。

**修復：**
```bash
rm -f .git/refs/.DS_Store
find .git/objects -name "tmp_*" -delete
git fsck --full   # 確認乾淨（不再有 badRefName / garbage found）
git push origin main   # 這次成功
```

清乾淨後 push 立刻成功，證實問題就是這兩類垃圾檔案干擾了 GitHub 端處理 push 的邏輯（`.DS_Store` 那個假 ref 最可疑，push 時 git 要向遠端「廣告」本機所有 ref 狀態，一個格式不合法的 ref 很可能讓遠端解析邏輯出錯而回報 500）。

**通則：**
1. `.git/refs/.DS_Store` 這類問題通常是因為曾經用 macOS Finder（而非純指令列）瀏覽過 `.git` 內部資料夾，Finder 會自動在造訪過的資料夾留下 `.DS_Store`。**不要用 Finder 打開 `.git` 資料夾**，如果不小心打開過，之後可以順手檢查一下 `.git/refs/`、`.git/objects/` 底下有沒有意外出現 `.DS_Store`。
2. GitHub push 回報 `Internal Server Error` 但連線/認證都正常時，先懷疑本機倉庫本身有異常內容（垃圾 ref、殘留暫存物件），`git fsck --full` 是第一個該跑的診斷指令，比一直重試 push 更有效率。
3. 這類「垃圾檔案」清理是安全操作（`tmp_*` 只是未完成寫入的暫存物件，不是任何 commit 實際引用到的內容），不需要擔心誤刪正式資料；但 `.DS_Store` 這種非標準檔案在動手刪之前，還是先用 `git fsck --full` 確認過它真的只是垃圾、不是被哪個 ref 正常引用。

---

### 38. csv_with_date 逾時直接落到過時備援，晚間更新常卡在前一日資料（2026-08 修正）

**現象：** 2026-08-18 當天大盤大跌（-549點），晚上 21 點多連續按了好幾次「🔄 手動更新資料」，結果都顯示「TWSE 尚未發布今日(2026-08-18)收盤資料，目前最新為2026-08-17」，但實際上 TWSE 官方當時已經有 8/18 的資料了（用其他管道直接查證過）。

**追查：** 看實際錯誤訊息才發現真相——不是資料沒發布，是三層來源全部沒抓到當天資料，但原因各自不同：
1. `csv_with_date`（最可靠、優先使用的來源）：`Read timed out. (read timeout=20)`——真的是連線逾時，不是沒資料
2. `json_no_date`（備援一）：`Expecting value: line 1 column 1 (char 0)`——收到空白回應（陷阱21 也記錄過 TWSE 偶爾回傳空 body 的狀況，這不是單一端點的個案，TWSE 好幾支 API 都有這毛病）
3. `openapi`（備援二）：正常回應，但這個來源**本身更新就比較慢**，回傳的是 8/17 的資料

三層備援雖然有做，但 `csv_with_date` 逾時後直接放棄、falls through 到下一層，而下一層的資料本來就比較舊，等於「最準的來源一逾時，就必然拿到舊資料」。大跌當天 TWSE 網站流量大、回應變慢，正好放大了這個問題。

**修復（`fetcher.py` `fetch_today_prices()`）：** 比照陷阱21修 T86 的做法，`csv_with_date` 這一段改成失敗後隔 5 秒重試，最多 3 次，都失敗才真的落到 `json_no_date`／`openapi` 備援：
```python
if src_type == 'csv_with_date':
    r = None
    last_err = None
    for _attempt in range(3):
        try:
            r = requests.get(twse_url, headers=HEADERS, timeout=20, verify=False)
            break
        except Exception as _e:
            last_err = _e
            r = None
            if _attempt < 2:
                time.sleep(5)
    if r is None:
        raise last_err if last_err else ValueError('csv_with_date 重試3次均失敗')
    ...
```

**通則：** 多層備援設計（見陷阱14）解決的是「來源A沒有資料」，但沒有解決「來源A暫時連不上」——這是兩種不同的失敗模式，若不分開處理，會讓系統在最需要重試的時候（網站正忙、暫時性逾時）反而最快放棄最準確的來源、退而求其次用比較舊的備援，产生「明明資料已經有了，程式卻說沒有」的誤導訊息。**追查「資料抓不到」類問題時，一定要看實際的錯誤訊息內容**（逾時 vs 空回應 vs 格式錯誤 vs 真的沒資料），不能只看「失敗了」就假設是同一種原因。

---

### 39. 手動更新只抓「今日」資料，多日未更新會永久漏資料 → 新增智慧補齊機制（2026-08 新增）

**背景：** 使用者提出疑慮——如果出門幾天沒開電腦、沒按「🔄 手動更新資料」，回來後補按一次，漏掉的那幾天資料會不會就永久補不回來？

**追查結果（確認疑慮成立）：** 逐一檢查四個「當日」資料的抓取函式：
- `fetch_today_prices()`（上市收盤價）：只抓 `today_str`，沒有補歷史的邏輯
- `fetch_chips()`（T86 個股三大法人）：只抓「今天」，抓不到才退而求其次抓「昨天」，最多回看1天
- `fetch_market_margin()`（大盤融資融券）：往前找最近 6 天中第一個有資料的日期，但只存那一天，中間缺的日子不會補
- `fetch_t86()`（T86 排行榜）：本來就有逐日補齊迴圈（陷阱21留下的），但上限只有 **5 天**

也確認了會自動修復、不受影響的部分：`fetch_market_volume()`（FMTQIK 大盤成交量，陷阱27修過，逐月補全近12個月）、`fetch_taiex()`（支援 `force`/`period` 回填）、`fetch_market_margin_history()`（本身就是逐月批次補歷史，只是平常不會自動觸發）。**自選股個股價格**則有另一層保護：`fetch_all()` 對每檔自選股執行 `if len(existing) < 60: 補抓` ——但這個門檻是「總筆數 < 60」，只保護新加入、歷史稀疏的股票，對已有數百筆歷史的既有自選股無效（多日缺口不會觸發）。

**結論：** 大盤層級的四項核心資料（收盤價、個股籌碼、法人排行、融資融券）如果連續多天沒更新，回來後點一次「手動更新」只會抓到「今天」，中間漏掉的交易日會**永久空缺**，直接影響大盤評分回溯、Signal 1-11 的歷史比對、K線與均線計算。

**修復（`fetcher.py`，新增「智慧補齊」機制）：**

1. 新增共用 helper `_missing_weekdays(last_date_str, today=None)`：回傳「DB 最新日期」到「今天」之間的平日日期清單（只排除週末，國定假日靠逐日抓取「查無資料就跳過」自然處理，不會報錯中斷）。`last_date_str` 為空時回傳空清單（沒有基準點就不猜測要補多久，避免抓出離譜長區間）。
2. 四個函式都各自把「單一日期抓取＋存檔」的邏輯抽成獨立 helper（`_fetch_twse_csv_prices_for_date()` / `_fetch_t86_chips_for_date()` / `_fetch_market_margin_for_date()`），原本「抓今天」的呼叫改成呼叫這個 helper，同時在函式開頭加一段：查 DB 最新日期 → `_missing_weekdays()` 算出缺口 → 逐日呼叫 helper 補齊（每次間隔 0.5 秒，避免打太快被 TWSE 擋）→ 再照原邏輯抓「今天」。
3. `fetch_t86()` 本身已有逐日補齊迴圈，只把候選日上限從 5 天拉高到 **30 天**，避免使用者出門超過一週時補不完整。

**效果：** 使用者出門任意天數（只要不超過 T86 的 30 天上限）後回來按一次「🔄 手動更新資料」，四項核心資料都會自動把中間漏掉的交易日逐日補齊，不需要額外操作或記得哪幾天沒更新。

**已知限制（刻意不處理，非疏漏）：**
- **上櫃（TPEx）收盤價無法補歷史**：`fetch_today_prices()` 的智慧補齊只涵蓋「上市」部分，因為只有帶日期參數的 TWSE CSV 端點支援查任意歷史日期；TPEx 的 API 沒有日期參數、只能查當下快照，架構上無法回補。
- **APScheduler 排程本身仍不可靠**（陷阱15）：智慧補齊是「事後補救」，不是「事前保證」——如果使用者依賴排程自動更新，Mac 關機/App 沒開時排程本來就不會執行；智慧補齊解決的是「回來後補一次就好」，不是讓排程變得更可靠。
- 只鎖定使用者明確提出疑慮、且已確認會漏資料的四個函式（收盤價、個股籌碼、T86排行、融資融券）；`fetch_futures_institutional()`（台指期三大法人）與 `fetch_ownership()`（外資持股比例）尚未加上同樣機制，非本次範圍。
  - **2026-09-08 更新：** 台指期法人與選擇權P/C 已補上（見陷阱44），用的是 TAIFEX 的日期**區間**查詢而非逐日；大盤本益比驗證後確認**做不到**；`fetch_ownership()` 仍未處理。

**通則：** 「只抓今天」的函式在系統正常每日執行時看不出問題，只有在「使用者中斷使用一段時間後回來」這個情境才會暴露漏資料的缺陷。新增任何一支「抓當日資料」的 fetcher 時，應該一開始就設計成「查DB最新日期→補齊缺口→抓今天」的智慧補齊模式，而不是等使用者實際遇到缺口才回頭補。

**⚠️ 這個機制在 2026-09-08 被發現對「個股收盤價」完全無效——見陷阱41。**

---

### 41. STOCK_DAY_ALL 的 date 參數無效，智慧補齊靜默失敗（2026-09-08 修正）

**現象：** 使用者 9/7 沒做更新，9/8 更新時發現「有些資料沒有一起補進來」。實際盤點：

| 資料 | 9/7 | 陷阱39 智慧補齊是否涵蓋 |
|---|---|---|
| TAIEX 收盤 | ✅ | （本來就用 period 抓整段） |
| 個股籌碼 chips | ✅ | ✅ 有做，**生效** |
| 大盤融資融券 | ✅ | ✅ 有做，**生效** |
| **個股收盤 prices** | ❌ | ✅ 有做，**但沒生效** ← 本則 |
| T86 排行 | ❌（9/2、9/8 也缺） | ✅ 有做，但失敗原因不明 |
| 台指期／選擇權P/C／大盤本益比 | ❌ | ❌ 陷阱39 已載明未涵蓋 |

**根本原因：`STOCK_DAY_ALL?date=YYYYMMDD` 的 date 參數其實是被忽略的，永遠回傳最新交易日。**

實測 `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?date=20260907` 回傳：

```
日期,證券代號,證券名稱,...
"1150908","00400A","主動國泰動能高息",...     ← 要求 9/7，回傳 9/8
```

**這推翻了陷阱14 的結論**（當時記「帶日期版本可靠，永遠是指定日期」）——那個驗證應該是在「要求的日期剛好就是最新交易日」的情況下做的，所以看起來成立。

**為什麼是「靜默」失敗（這是最危險的部分）：**
1. 補齊迴圈要 9/7 → API 給 9/8 的資料
2. `_parse_twse_csv_all()` 用 **CSV 每列自帶的日期欄**存檔（不是用參數）——這個防禦寫法救了一命，**沒有把 9/8 的資料誤標成 9/7**
3. 但函式回傳 `count > 0`，迴圈判定成功，印出 **「[補齊] 2026-09-07：2356 筆」**
4. 使用者看到「補齊成功」，實際上只是把 9/8 的資料重寫了一次

**修正（`fetcher.py`）：**

1. 新增 `_fetch_mi_index_prices_for_date()`，改用 **`MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json`**——實測 date 參數**真的有效**，回傳「115年09月07日 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))」。
2. `fetch_today_prices()` 的補齊迴圈改呼叫它；**「抓今天」仍用 `STOCK_DAY_ALL`**（該端點對最新交易日是正確的，且 CSV 格式解析已驗證多年）。
3. `_fetch_twse_csv_prices_for_date()` 的 docstring 明確標註「只能抓最新交易日，不能補歷史」。
4. **加日期驗證守衛**：比對回傳表格 title 裡的民國日期字串，`≠ 要求日期就 return (0, None)` 並印警告，寧可當失敗也不靜默接受。

**MI_INDEX 欄位順序與 STOCK_DAY_ALL 不同（易錯）：**

```
STOCK_DAY_ALL: 日期,證券代號,證券名稱,成交股數,成交金額,開盤,最高,最低,收盤,漲跌價差,成交筆數
MI_INDEX:      證券代號,證券名稱,成交股數,成交筆數,成交金額,開盤,最高,最低,收盤,漲跌(+/-),漲跌價差
                [0]      [1]     [2]     [3]     [4]     [5] [6] [7] [8] [9]       [10]
```
差異：MI_INDEX **沒有日期欄**（日期在表格 title）、**成交筆數與成交金額對調**、漲跌拆成「方向(+/-)」與「價差」兩欄，且方向欄含 HTML（`<p style=color:red>+</p>`），需取符號後再乘上價差絕對值。

**回填：** `backfill_missing_days.py`（一次性腳本，已進版控）。用 TAIEX 的實際交易日當基準（TAIEX 由 yfinance 抓整段，缺口最少）比對 `prices` 與 `t86_ranking` 缺哪幾天，再逐日補抓。預設試跑只報告，加 `--apply` 才寫入。

**T86 排行的部分（未解）：** 缺 8/26、9/2、9/7、9/8，是零星漏失而非系統性。API 實測正常（`selectType=ALL&date=20260907` 回 `stat:OK`、`date:20260907`），`fetch_t86()` 的守衛條件與候選日計算讀起來也正確（9/8 時 `twse_date=9/8`、`last=9/4`，候選日會算出 9/7 與 9/8）。**沒有執行日誌無法確定失敗點**，下次更新時需保留輸出。`backfill_missing_days.py` 直接重抓，繞過該函式。

**附帶發現（非致命）：** `fetch_t86()` 用 `selectType=ALL`（含權證），單日約 15,853 筆；`fetch_chips()` 用 `ALLBUT0999`（不含權證）。上市股票僅約 1,000 檔，等於 t86_ranking 表白白膨脹十幾倍。不影響正確性，但日後若要瘦身可考慮改用 `ALLBUT0999`。

**通則（本則最重要）：**
1. **外部 API 的參數不一定有效——會被忽略但仍回 200 + 合法資料。** 補歷史類的功能，**必須驗證「回傳的日期就是要求的日期」**，不能只看「有沒有拿到資料」。這類 bug 不會拋例外、不會留錯誤日誌，只會安靜地讓補齊機制失效。
2. 「用回傳內容裡的真實日期存檔，而不是用請求參數存檔」是**正確且必要的防禦**——本次就是它擋下了資料汙染（否則 9/8 的價格會被寫成 9/7，比缺資料嚴重得多）。新寫任何「指定日期抓取」的函式都應照此設計。
3. 同一份文件裡的舊結論**可能是在特例下驗證的**（陷阱14 的「date 參數可靠」就是在「要求日=最新交易日」時測的）。日後引用既有結論做新功能時，要問一句「當初驗證的情境跟我現在要用的情境一樣嗎」。

---

### 42. 上櫃快照被蓋上錯誤日期，整個上櫃市場寫入重複資料（2026-09-08 修正）

**⚠️ 這是本專案目前發現過最嚴重的資料問題——不是「缺資料」，是「錯資料且看起來完全正常」。**

**發現經過：** 修完陷阱41、補齊 9/7 之後，順手做防呆檢查「9/7 的資料會不會其實是 9/8 的複製品」，結果 **2,356 檔中有 994 檔（42%）兩天的開高低收四欄完全相同**。抽查發現分界很乾淨：上市股（2330/2317/2377/2408）兩天都不同 ✅，上櫃股（6488 環球晶、3324 雙鴻）完全相同 ❌。994 ≈ 上櫃股總數（976）。

**掃描全期（相鄰交易日「四欄全等」檔數，分市場）：**

| 日期配對 | 上市相同 | 上櫃相同／總數 |
|---|---|---|
| 08-03→08-04 | 2 | **970 / 971** |
| 08-13→08-14 | 2 | **978 / 979** |
| 08-19→08-20 | 0 | **979 / 980** |
| 09-07→09-08 | 2 | **975 / 976** |
| （其餘日期） | 0–6 | 1–23（正常平盤股） |

全期共 **11 個日期**整批重複（最早回溯到 2026-05-25）。上市同期只有 0~6 檔，**證明不是市場現象而是寫入錯誤**。

**根本原因（`fetch_today_prices()` 上櫃區段）：** 舊版**強制沿用 `twse_actual_date`、完全不看 TPEx 自己回傳的日期欄位**。原註解的理由是「TPEx 的 Date 盤後會即時更新為今日，但 TWSE 有時延遲，以 TWSE 為基準確保全 DB 同一交易日」——這個推理只考慮了「TWSE 比較新」的方向，**沒考慮反向**：

> TPEx OpenAPI 只回傳「當下快照」（無日期參數）。若在「TPEx 已更新到今日、但 TWSE 尚未發布今日資料」的時間點按更新 → `twse_actual_date` = 昨日 → **今日的上櫃快照被寫成昨日的資料** → 隔天再更新一次，今日又存一份 → 兩天完全相同。

**為什麼特別危險：** 缺資料看得出來（陷阱39/41 那類），**錯資料看起來完全正常**——會直接汙染評分、均線、波動度、回測，而且不會有任何錯誤訊息。這正是陷阱41 通則第2點（「用回傳內容的真實日期存檔」）沒有被套用到上櫃路徑的後果：上市那邊用 CSV 自帶日期擋下了汙染，上櫃這邊卻刻意丟棄了自己的日期欄位。

**修正（三層，優先序由上而下）：**
1. **優先採用 TPEx 自身回傳的日期欄位**（`_tpex_api_date()`，支援民國7碼／西元8碼／`YYYY-MM-DD`，欄位名試 `Date`/`date`/`TradingDate`/`DataDate`）——那才是這份快照真正的日期。與 TWSE 日期不同時印提示但仍依 TPEx 自身日期存（兩市場發布時間本來就有落差）。
2. 取不到日期欄位時，**只在 `twse_actual_date == 今天` 時才存**（TWSE 已發布今日 ⇒ 今日已收盤 ⇒ TPEx 快照也是今日，兩者才對得起來）。
3. 其餘情況**一律跳過並印原因**——寧可少一天資料，也不要寫錯日期。

順帶修掉原本「週末執行會產生錯誤日期」的風險（第2層的 `== 今天` 條件天然擋住週末）。

**回填：** `repair_tpex_dupes.py`（一次性腳本，已進版控）。自動偵測「上櫃四欄全等比例 ≥80% 且上櫃檔數 ≥100」的日期，再用 **yfinance（`{code}.TWO`）**重抓真實歷史覆寫——yfinance 有正確的逐日歷史，不像 TPEx OpenAPI 只有當下快照。預設只修**自選股中的上櫃股**（17 檔，那些才進評分與回測），加 `--all` 可修全市場（數百次 yfinance 呼叫，很慢）。

**⚠️ 對既有回測結論的影響：** 受影響的 17 檔自選股包含 6488 環球晶、3324 雙鴻、3374 精材、4979 華星光、5347 世界、3491 昇達科等**曾出現在回測與持倉討論中的股票**。11 個錯誤日 / 約 500 交易日 ≈ 2.2% 的日期，且只影響上櫃股（17/87 ≈ 20% 的自選股），估計約 0.4% 的價格儲存格受汙染，對整體統計影響應該不大——**但重複日會讓當日報酬變成 0，壓低波動度、也可能改變那幾天的進出場判定**。修完後若要引用精確數字，建議重跑一次 `backtest_stocks.py`。

**通則：**
1. **「以某個權威來源的日期為準」這種設計，只有在該來源永遠不落後時才成立。** 兩個獨立市場/API 各有自己的發布節奏，強制對齊必然在某個方向出錯。正確做法是**各自用各自的日期**，不一致時提示而非強制覆蓋。
2. **偵測這類汙染的方法很便宜：檢查相鄰交易日「四欄全等」的檔數。** 正常市場單日平盤股只有個位數；一旦出現整批相同就是寫入錯誤。**這個檢查已納入例行的資料完整性檢查**（見下方「十九、資料完整性檢查」）——它抓得到「缺資料」檢查完全抓不到的問題。

---

### 43. Signal 3 用「表裡前一列」當前一交易日 + 三處門檻不同步（2026-09-08 修正）

**起因：** 使用者問「台指期、選擇權P/C、大盤本益比這三支缺資料，對評分和回測有沒有影響？」逐一查證後發現**答案差異極大**，而且查的過程中挖出兩個既有 bug。

**先回答影響範圍（查證結果）：**

| 資料 | 個股評分 | 大盤評分 | 回測 |
|---|---|---|---|
| 台指期法人 | ❌ 無 | ✅ **Signal 3** | ✅ **有**（`backtest.py`／`backtest_stocks.py` 都用） |
| 選擇權 P/C | ❌ 無 | ✅ Signal 11 | ❌ 無（回測只跑 S1–S8） |
| 大盤本益比 | ❌ 無 | ❌ **完全沒用在評分** | ❌ 無 |

**`scorer.py` 完全沒有引用這三支任何一支**——個股評分只用價格、基本面、籌碼，不受影響。大盤本益比全專案只有一處用到（`app.py` 估值走勢圖），純顯示，缺 12 天最多是圖有斷點。

**問題一：Signal 3 用索引取「前一日」，缺資料時會靜默算錯。**

```python
_f_net_prev = _fut[-2]['foreign_net']    # ← 表裡的「前一列」，不是「前一個交易日」
```

9/7 缺漏時，就變成拿 **9/8 減 9/4** 當「單日變化」。這與陷阱26（季度資料被當日資料算漲跌）、陷阱35（相鄰兩列≠相鄰兩期）、陷阱41（相鄰列假設）是**同一類錯誤在第四個地方重演**。

**量化影響（實測 400 日台指期資料）：**

| | 中位數 | ≥3000口(±1分) | ≥5000口(±2分) |
|---|---|---|---|
| 真正相鄰交易日 | 1,670 口 | 25% | 8% |
| **漏一天後的跨兩日** | **2,513 口** | **35%** | **16%** |

**±2分強訊號的誤觸率直接翻倍（8%→16%）**——門檻是照「單日變化」校準的，餵給它兩日變化必然偏多觸發。5日趨勢同理（`_fut[-5]` 實際會跨到第 6 個交易日）。

2026-09-08 當天剛好無害（9/8−9/4 = +127 口，仍判中性），純屬運氣。

**問題二：Signal 3 的門檻三處不同步。**

| 檔案 | 舊值 | 應為（TAIFEX 校準值） |
|---|---|---|
| `app.py` | 5000／3000／8000 ✅ | — |
| `backtest.py` | **3000／1000／2000** ❌ | 5000／3000／8000 |
| `backtest_stocks.py` | **3000／1000／2000** ❌ | 5000／3000／8000 |

**陷阱34 當初修 Signal 4 時明確寫了「三處門檻要一起改」，但 Signal 3 只改了 `app.py`，兩支回測沒跟上**——等於回測跑的 S3 比線上敏感得多，回測與實際線上判斷有系統性落差。

**修正（三處一起）：** 全部改為**用 TAIEX 交易日序列對齊**取「前一個交易日」與「5個交易日前」，對應日期在台指期資料裡找不到就**不計分**（`f_chg = None` 跳過），不用錯誤基準硬算。`app.py` 另在缺漏時顯示說明文字。門檻同步為 5000／3000／8000。

**⚠️ 回測基準已改變（重跑後更新）：**

| 期間 | 筆數 | 勝率 | 報酬 | alpha |
|---|---|---|---|---|
| 全期間 | 437 | 49.9% | +4.80% | +1.81% |
| 2025全年 | 182 | 56.6% | +5.57% | +2.47% |
| 2026H1 | 227 | 45.8% | +4.95% | +1.98% |

與「停損距離校準」那節的 10% 停損數字（412筆／51.2%／+5.22%／alpha +2.06%）相比，修正 Signal 3 後筆數略增、EV 略降——因為門檻拉高後 S3 觸發變少，擋掉的進場日也變少。**引用回測數字時以本表為準**（同時含 10% 停損 + Signal 3 修正）。

**通則（本專案第四次踩到同一類坑）：** **「時間序列的前一期」永遠要用日期查，不能用 `list[-2]` 這種索引。** 索引假設「資料完整無缺漏」，而本專案已反覆證明資料一定會有缺漏。判斷方法：看到 `[-2]`、`[-5]`、`[i-1]` 用在時間序列上時，問一句「如果中間少一天，這個算式還對嗎？」——不對就要改成日期查找，並在查不到時明確跳過而非硬算。

---

### 44. 給三支資料加智慧補齊時，挖出 BWIBBU_ALL 的日期晚一個交易日（2026-09-08）

**起因：** 執行陷阱43 之後說好的第三步——「給台指期、選擇權P/C、大盤本益比加智慧補齊」。照陷阱41 的教訓，**動手前先逐一實測 API 到底吃不吃歷史日期參數**。結果三支的答案完全不同，而且驗證過程中挖出一個從沒被發現的日期錯誤。

**實測結果（2026-09-08）：**

| API | 日期參數 | 結論 |
|---|---|---|
| TAIFEX `futContractsDateDown` | `queryStartDate`/`queryEndDate` **有效** | ✅ 可補齊 |
| TAIFEX `pcRatioDown` | 同上 **有效** | ✅ 可補齊 |
| TWSE `BWIBBU_ALL` | `date` **無效**（要求 20260901，回最新一份） | ❌ **補不回來** |

實測指令與回應：要求 `queryStartDate=2026/09/01&queryEndDate=2026/09/04`，TAIFEX 回的就是 09/01～09/04 這四天；要求 `BWIBBU_ALL?date=20260901`，回的是 `"date":"20260908"`——**與陷阱41 的 `STOCK_DAY_ALL` 是同一個坑，在同一份文件裡第二次出現。**

**順帶挖出的問題：BWIBBU_ALL 的 `date` 欄位比實際報表日期晚一個交易日。**

回應同時有兩個日期，兩者兜不起來：

```
"date" : "20260908"                          ← 程式一直用這個存檔
"title": "115/09/7 個股日本益比、殖利率及股價淨值比"   ← 才是真的報表日期
```

**判定方法（值得記下來）：** PE = 收盤價 ÷ EPS，而 EPS 一季才變一次。所以拿 `close ÷ pe` 反推 EPS，**用對日期的話應該是死平的**。實測三檔：

| 股票 | `close(同日)/pe` | `close(前一交易日)/pe` |
|---|---|---|
| 2330 | 84.3 ~ 87.5（亂跳） | **86.255 ~ 86.281** |
| 2317 | 14.87 ~ 15.69（亂跳） | **15.165 ~ 15.174** |
| 2454 | 58.3 ~ 66.6（亂跳） | **60.547 ~ 60.554** |

**前一交易日那欄穩到小數第二位，證明 title 才是對的、`date` 欄晚一天。** 這與陷阱35 用「隱含前收反推基準日」定位問題是同一套手法：**懷疑日期標錯時，找一個「日期對了就會是常數」的量，算出來看它穩不穩。**

**影響範圍：** 不只大盤本益比。`fetch_fundamentals()` 走的是 openapi 版 BWIBBU_ALL，那支**連日期欄位都沒有**，舊版直接用 `datetime.now()` 存檔——所以整張 `fundamentals` 表（PE/PB/殖利率，**佔個股評分基本面 25% 權重**、也是估值分析頁的資料來源）日期全部晚一天，而且**週末開 App 還會寫出週六/週日的資料列**（實測表中確實有 `2026-08-02` 這種週日日期）。

**修正（`fetcher.py`）：**
1. 新增 `_bwibbu_title_date()` + `_fetch_bwibbu_all()`，**一律以 title 的日期為準**；title 解析不出來就當失敗、不退回去用 `date` 欄位（寧可少存一天，也不要靜默標錯——陷阱41/42 的教訓）。
2. `fetch_fundamentals()` **從 openapi 版改用 www 版**，讓**資料與日期出自同一個回應**。這點很關鍵：如果為了拿日期而去打另一支 API，就是重蹈陷阱42 的「跨來源借日期」。順帶把「每檔各查一次 `get_prices`」（1,900+ 次 SQLite 查詢）改成一次撈當日全市場收盤。
3. `fetch_market_pe()` 移除原本那個 `days_back in range(0,6)` 的迴圈——date 參數既然無效，那個迴圈每圈拿到的都是同一份資料，是**假的補齊**，留著只會讓人以為補得回來。
4. `fetch_fundamentals_tpex()`（yfinance，無日期可用）至少把週末往回收到週五，不再產生週末資料列。

**⚠️ 既有歷史資料沒有修復，而且大致上修不回來。** 缺的不是資料而是「當初那次抓取是哪天跑的」——同一列可能晚一天、也可能因為週末連跑而晚兩三天，無從還原。真要修的話唯一可行的辦法是**逐日反推**：對每個日期，試 D、D−1、D−2 當候選，看哪一天的收盤價讓全市場的 `close/pe` 最接近各股的參考 EPS。做得到但工程量不小，而**修正後的影響很小**（PE 日變動約 1%，估值百分位是算 400 日分布），所以目前只記錄不做。日後若要重新驗證估值相關結論，要先把這件事納入考量。

**通則：**
1. **同一份文件裡的坑會重複出現在不同 API 上。** 陷阱41 記了 `STOCK_DAY_ALL` 的 date 參數無效，這次 `BWIBBU_ALL` 一模一樣。**任何「指定歷史日期」的功能，動手寫之前先花兩分鐘實測參數到底有沒有效**——成本極低，而且這類 bug 不會報錯。
2. **一個回應裡有兩個日期時，不要挑順手的那個用。** 要問「哪一個是資料本身的日期，哪一個只是伺服器回話當下的日期」。分不出來時，用上面那招（找一個日期對了就會是常數的量）去驗。
3. **做不到的事要明講，不要留一個看起來像在補齊的迴圈。** 舊版 `fetch_market_pe()` 的 6 天迴圈就是這種假象——它讓人以為漏掉的日子還有機會補回來，實際上永遠只拿得到同一份最新報表。

---

### 45. 用 `MAX(date)` 當補齊水位線，看不到「中間的洞」（2026-09-09 修正）

**⚠️ 這是陷阱44 的修正**本身**帶進來的 bug**，隔天就被使用者一句「確定有更新9/7？」抓到。記錄完整經過，因為它同時解釋了一個懸了很久的謎題。

**現象：** 陷阱44 給台指期與選擇權P/C 加了智慧補齊、也實測 TAIFEX 的日期區間參數有效。隔天（9/9）跑完更新後查 DB：

```
             08-31  09-01  09-02  09-03  09-04  09-07  09-08  09-09
台指期法人      ✅     ✅     ✅     ✅     ✅     ❌     ✅     ✅
選擇權P/C      ✅     ✅     ✅     ✅     ✅     ❌     ✅     ✅
```

9/9 有資料，代表新程式確實跑過了；但 **9/7 還是空的**。直接打 TAIFEX 確認 9/7 的資料**存在**（`pcRatioDown?queryStartDate=2026/09/05&queryEndDate=2026/09/08` 回傳 09/07 與 09/08 兩筆），所以不是資料源的問題。

**根本原因：`MAX(date)` 只看得到「尾端缺口」，看不到「中間的洞」。**

```python
last    = _last_date_of('futures_institutional')   # 9/8 已補進來 → MAX = 9/8
windows = _taifex_query_windows(last)              # → 9/9 ~ 9/9
```

時序是這樣的：9/7 沒更新 → 9/8 更新（舊程式，只抓當天）→ 9/8 寫進 DB → **MAX 前進到 9/8** → 9/9 跑新程式，算出來的補齊區間只有 9/9。**9/7 被 MAX 跨過去了，之後永遠不會再被碰到。**

**這不是罕見的邊角案例**——「今天成功、昨天失敗」正是最常見的失敗形狀（單日 API 逾時、空回應，見陷阱21/38）。只要發生一次，那一天就永久消失。

**順帶解開了陷阱41 的懸案。** 那則寫著「T86 缺 8/26、9/2、9/7、9/8，API 實測正常、守衛條件讀起來也正確，**沒有執行日誌無法確定失敗點**」。真正的原因就是這個，而且 `fetch_t86()` 疊了兩層：

```python
if last and last >= twse_date:      # ① 已是最新就直接 return
    return
from_date = last + 1 天              # ② 候選日從 last+1 起算
```

抓失敗一次，隔天 `last` 照樣前進，那一天就再也沒有重試的機會。**不是「查不出失敗原因」，是失敗之後根本沒有第二次機會**——當初查錯方向了：一直在找「為什麼那天抓取失敗」，但真正該問的是「失敗之後為什麼沒有重試」。

**修正：改用交易日日曆逐日比對。** 新增兩個 helper：

- `_trading_day_calendar(lookback_days=45)`：近 45 個日曆日的實際交易日，取自 TAIEX（全專案缺口最少的序列，`backfill_missing_days.py` 與資料完整性檢查早就用它當基準，這裡沿用同一個來源）。
- `_missing_trading_days(table, where='')`：拿日曆逐日比對該表，回傳**實際缺哪幾天**。日曆取不到時（全新 DB）退回舊的 `_missing_weekdays()` 保底。

`_taifex_query_windows()` 改成吃「缺漏日清單」、從**最早的缺漏日**開始查（一律含今天）。六支 fetcher 全部換掉：個股收盤／個股籌碼／融資融券／T86排行／台指期／選擇權P/C。

**修正後對真實 DB 實測（9/9）：**

| 資料 | 舊邏輯偵測到 | 新邏輯偵測到 |
|---|---|---|
| 台指期法人 | 0 天 | **9/07** |
| 選擇權P/C | 0 天 | **9/07** |
| T86 排行 | 0 天 | **8/04、8/06** |
| 融資融券 | 0 天 | **8/05、8/13** |

**後面兩列是意外收穫**——那四天是舊邏輯下**完全隱形**的洞，資料完整性檢查（十九章）雖然看得到，但沒有任何自動機制補得回來。

**通則（本專案第五次踩到「相鄰假設」這一類坑）：**

1. **「補齊到哪裡」的水位線不能用 `MAX(date)`。** 水位線模型隱含一個假設：資料是**連續累積、只會從尾端增長**的。而只要有任何一次「今天成功、昨天失敗」，這個假設就破了，且破洞會被水位線永久跳過。**正確做法是拿一份權威日曆逐日比對「應該有 vs 實際有」**，這樣才對「洞出現在哪裡」不敏感。
2. **判斷方法：問「如果中間某一天失敗了、但隔天成功了，這段邏輯還救得回來嗎？」** 救不回來就是水位線模型的受害者。這與陷阱43 的「`list[-2]` 不等於前一個交易日」是同一個病根的兩種變形——**都是把「順序」當成「連續」**。
3. **監控抓得到、但補不回來，是半套。** 十九章的完整性檢查早就顯示「法人排行缺2天／融資融券缺2天」，但因為補齊邏輯用水位線，按幾次更新都不會消失。**偵測與修復要用同一套日曆基準**，否則使用者只會看到一個永遠不消失的警告，然後學會忽略它。
4. **修 bug 的當下最容易引入新 bug。** 陷阱44 的重點全放在「API 的 date 參數有沒有效」，驗證做得很仔細（實測、離線測試四種情境都過），但那些測試全都在問「給定一個起點，區間算得對不對」，**沒有一個測試問「起點本身選得對不對」**。測試涵蓋了實作，沒涵蓋前提。

---

### 46. `_market_ms` / `_market_net` 沒帶資料日期，四處默默用舊分數（2026-09-12 修正）

**起因：** 討論「下個階段該看實盤效果」時，順手檢查了 6 筆實際持倉的 `entry_ms`，發現**全部與系統回溯算出來的歷史值對不上**。使用者接著問了一個很準的問題：「**我進場時看到的分數，和事後記錄下來的分數，會不一樣嗎？有可能是隔天的分數？**」——答案是會，而且兩個方向都可能。

**機制：** `_market_ms` / `_market_net` **整個程式只有 `render_market()`（大盤分析頁）會寫入**：

```python
st.session_state['_market_ms']  = _ms      # 即時評分，含 S9–S11
st.session_state['_market_net'] = _net
```

也就是它的值 = 「**你最後一次打開大盤分析頁**時算出來的分數」。但它被**四個地方**讀去用：

| 讀取點 | 用途 | 用到舊值的後果 |
|---|---|---|
| 側邊欄持倉觀察 | 「📉 大盤轉空」旗標 | 拿三天前的行情叫你減碼 |
| 投資策略頁 | **個股進場門檻**（65/70/75/停止） | 整頁的建議都是舊的 |
| 持倉管理 | 到期建議、旗標 | 同上 |
| 📌 進場登錄 | 寫進 DB 的 `entry_ms` | **永久汙染策略驗證的分組依據** |

舊版**只檢查「有沒有值」、不檢查「是哪一天的值」**（沒值會 `st.info('請先前往大盤分析頁')`，有值就直接用）。於是：

- App 一直開著、今天沒進大盤分析頁就去登錄 → 拿到**昨天或更早**的分數
- 而 📌 表單的「進場日」預設是 `datetime.now()`（今天）→ **`entry_ms` 與 `entry_date` 各自獨立，可能不同天**

**實際資料裡的證據（不是推論）：**

| | entry_ms |
|---|---|
| 緯創 8/13 | 100 |
| 微星 8/14 | 100 |
| 國泰金 8/14 | **60** |

**微星與國泰金同一天登錄，值卻不同**——同一天的大盤評分只會有一個值。與資料相符的解釋是：微星登錄時 `_market_ms` 還停在 8/13 的 100，之後重新載入了大盤分析頁（重算成 60），才登錄國泰金。

**⚠️ 順帶釐清一件容易誤判的事（我第一版判斷錯了，記下來）：** 六筆 `entry_ms` 與歷史回溯值差很多（100 vs 45），**這本身不是 bug**。因為：

- `entry_ms` 記的是**即時評分（S1–S11）**
- 回測與評分走勢圖用的是**回溯評分（S1–S8）**——S9 是 yfinance 即時資料，沒有歷史值可回溯

實際數過 Signal 9 的計分上限：**最多能給 11 分多方**（S&P +3、Nasdaq +2、費半 +2、TSM +2、VIX +1、台幣 +1）。net 差 11 → 評分差 **55 分**。所以「回溯 45、即時 100」完全在可解釋範圍內，代表那天外部市場很強。

**真正的問題是「兩把尺混用」**：儀表板「依進場大盤評分分組」用的是 S1–S11 的 `entry_ms`，要對照的回測結論卻全是 S1–S8 算的。用公分分組、拿英吋的結論比。

**修正（`app.py`，不動任何評分邏輯）：**

1. `render_market()` 多存一個 `st.session_state['_market_ms_date'] = _tpx_date`。
2. 新增 `_current_data_date()`（本機讀 DB TAIEX、雲端讀 `TAIEX.json`）與 `_market_state()`，後者回傳 `(ms, net, data_date, stale)`。**舊 session 沒有 `_market_ms_date` 這個 key 時一律判為 stale**（fail-safe：升級前留下的值不能無聲通過）。
3. 四個讀取點全改走 `_market_state()`：
   - 側邊欄與持倉管理：**stale 時把 `market_net` 設為 `None`**，暫停「📉 大盤轉空」旗標——顯示一個錯的旗標比不顯示更糟，使用者會照著它減碼。
   - 投資策略頁：顯示警告，明講「下方的個股建議門檻與減碼警報都是依這個分數算的」。
   - 📌 登錄表單：**明白寫出「將記錄 X 日的大盤評分 NN 分」**，stale 時升級成 warning。
   - 手動登錄表單：caption 標明預設值取自哪一天。

**⚠️ 一個差點寫錯的判斷：** 第一版在 📌 表單裡把「評分日期 ≠ 進場日」當成警告。**那是錯的**——策略本來就是「D 日評分達標 → **D+1** 進場」，所以「評分日期 = 進場日的前一個交易日」**才是對的**（那是決策日）。改成只陳述事實、只有 stale 才警告。**寫防呆時要先確認「不一致」在業務上是不是真的不正常。**

**既有 6 筆沒有回填**——無法還原當初那次抓取的即時 S9 值，硬算會是另一種假資料。

**通則：**
1. **陷阱40 的通則要涵蓋「被寫入的值」，不只「被快取的計算結果」。** 陷阱40 當時修了三個 key（`_market_score_history_v3_{date}`、`_score_hist_{code}_{date}`、`_wl_patterns_{date}`），判斷標準是「一個 session 只算一次的快取」。`_market_ms` 每次進大盤頁都會重寫，**看起來不像快取**，所以被漏掉了——但它的問題更嚴重，因為**它會被寫進資料庫**。判斷標準應該改成：**「這個 session_state 值，會不會在使用者沒察覺的情況下比當前資料舊？」**
2. **跨頁面傳值一定要連同「這個值是什麼時候算的」一起傳。** 只傳數字，接收端永遠無法判斷新舊。
3. **同一個量有兩種算法時（即時 S1–S11 vs 回溯 S1–S8），要在存下來的當下就標明是哪一種**，否則日後做分組統計必然混用。這次是事後才發現，而且差距可達 55 分。

---

### 47. 續抱把 `entry_date` 重設，與 `entry_price` 脫鉤（2026-09-12 修正）

**發現經過：** 使用者問「修正後隔日進場記錄的大盤分數是不是前一日的」，為了回答而去核對 `entry_price` 對應哪一天的價格，結果發現**六筆持倉沒有一筆的進場價落在登錄進場日的高低區間內**——但**四筆出場價全部落在當日區間內 ✅**。一邊全中、一邊全不中，代表不是隨機誤差。

**決定性證據（用漲跌幅限制反推）：** 緯創登錄 `entry_date=2026-08-13`、`entry_price=169.5`。但 8/12 收 **193.5**，台股有 10% 漲跌幅限制，**8/13 跌停也只到 174.2，不可能成交在 169.5**。而 169.5 正好落在 **2026-08-03**（低 169.5）的區間內——相差約一個持有週期。

**根本原因：** `renew_position()` 把 `entry_date` 重設為今天、`renew_count +1`，但**完全不動 `entry_price`**（那是最初的成交價，本來就不該改）。於是續抱過的部位：

- `entry_price` = **最初買進**的價格
- `entry_date` = **最後一次續抱**的起算日

兩者相差 `renew_count × 10` 個交易日。使用者六筆的 `renew_count` 全部 ≥ 1，所以全中。

十八章原本只寫了「進場日欄位會變成本輪起算日，原始進場日不保留」，**沒寫到它會與進場價脫鉤**，也沒寫到持有天數會因此嚴重低估。

**影響要分開看（這點很重要，不是全盤皆錯）：**

| 欄位 | 狀況 |
|---|---|
| `pnl_pct` | ✅ **正確**——用最初進場價算，是從頭到尾的真實報酬 |
| `entry_score` / `entry_ms` | ✅ **一致**——登錄當下記的，對應最初進場，與 pnl 同基準 |
| `entry_date` | ❌ 看起來像成交日，實際是本輪起算日 |
| 持有天數（`_trading_days_since`） | ❌ 只算本輪。微星續抱 3 次、實際抱了約 6 週，畫面顯示「第 3 天」 |

**所以策略驗證真正用到的三個欄位彼此是配套的，分組統計不會失真**；壞的是使用者眼睛會看的那兩個。

**修正：**
1. `positions` 新增 `original_entry_date` 欄位（migration 一行），`_POS_COLS` 同步加入。
2. `add_position()` 建檔時 `original_entry_date = entry_date`。
3. `renew_position()` **不動** `original_entry_date`；但若該欄為 NULL（升級前建立、之後才第一次續抱的舊資料），用 `COALESCE(original_entry_date, entry_date)` 補上續抱前的值。
4. `update_position()` 白名單加入該欄；編輯表單新增「最初進場日」，續抱過的部位附警語提醒對帳單核對。
5. 顯示層：側邊欄按鈕加「／累計N」、持倉管理的天數欄加一行「累計 N 天」、進場資訊行改成「**{最初進場日} 最初進場 @ {價格}　｜　本輪自 {entry_date} 起算**」——把兩個日期分開講，不再讓人以為「那天用那個價買的」。

**回填：`repair_original_entry_date.py`（已進版控，預設試跑）。** 續抱過的部位無法直接還原，用**兩段推估 + 價格驗證**：

1. 理論值：`entry_date` 往前推 `renew_count × HOLD_DAYS` 個交易日
2. 用 `entry_price` 驗證：在理論值附近找「當日 `low ≤ entry_price ≤ high`」的交易日
3. 找到就用它，找不到退回理論值並標記

**實測結果非常乾淨——六筆中五筆，理論值當天的高低區間本身就包含登錄的進場價**（兩個獨立方法互相印證）：

| | 本輪起算 | 進場價 | 推估最初進場 | 驗證 |
|---|---|---|---|---|
| 緯創（續抱1） | 08-13 | 169.5 | **07-30** | ✅ 區間相符 |
| 微星（續抱2） | 08-14 | 146.5 | **07-17** | ✅ 區間相符 |
| 國泰金（續抱1） | 08-14 | 101.0 | **07-31** | ✅ 區間相符 |
| 微星（續抱3） | 08-31 | 154.5 | **07-22** | 理論值 07-20，往後 2 天才相符 |
| 仁寶（續抱1） | 09-04 | 38.05 | **08-21** | ✅ 區間相符 |
| 所羅門（續抱1） | 09-04 | 153.0 | **08-21** | ✅ 區間相符 |

**通則：**
1. **一組「日期＋價格」欄位，如果只有其中一個會被更新，它們就會脫鉤。** 設計任何「重設某個時間欄位」的功能時，要列出所有與它同時點的欄位，決定是一起改、還是另開欄位保存原值。本例 `entry_price` 不該改是對的，錯在沒有替原始日期留位置。
2. **驗證「某個價格是不是那天成交的」，漲跌幅限制是最省事的判準。** 台股 ±10%，只要 `entry_price` 超出「前一日收盤 ×0.9 ~ ×1.1」就一定不是那天的價。這比逐日比對高低點更快，而且能給出「不可能」而非「看起來不像」的強度。
3. **推估歷史值時，盡量找兩個獨立的方法互相印證。** 本例「交易日推算」與「價格落在高低區間」彼此無關，六筆中五筆一致——這個一致性本身就是推估可信的證據。單用任何一個都說服力不足。

---

### 48. UI 的操作建議與正式規則互相矛盾，且完全沒有標註（2026-09-17 修正）

**⚠️ 這是本專案第一個「已造成實際金錢損失」的缺陷。** 前面所有陷阱不是資料問題就是統計問題；這一則是**系統直接叫使用者做出違反自己規則的事**。

**發現經過（重要，我一開始判斷錯了）：** 使用者說「感覺每一次的進場都無疾而終」。查紀錄發現 **5 筆已平倉只有 1 筆抱滿 10 天**，我因此判定為「人為推翻規則」。使用者隨即更正：

> 「那幾張未持滿10天而出清的個股，**我是看了大盤的評分上的評語才出清**」

**查證後屬實。** `render_market()` 綜合判斷框的原始文字：

| 淨值 | 原本寫的「操作建議」 |
|---|---|
| ≥ +6 | 「持股者**酌情減碼**或設停損」 |
| ≥ +3 | 「**逢反彈可減碼**」 |
| **≥ +1** | 「**保守持倉**，等開盤方向明朗後再決策」← 8/19 看到的就是這句 |

而正式規則（策略C）是：**持有期間不因大盤轉弱自動出場**。兩者直接矛盾，而**那個框裡沒有任何一個字提到策略C**。

**實際代價（同一天三筆，全數賣飛）：**

| | 實際 | 若抱滿10天 | 差距 |
|---|---|---|---|
| 緯創 | +5.01% | +7.37% | 少賺 2.4pp |
| 國泰金 | -2.57% | +1.49% | **少賺 4.1pp** |
| 所羅門 | -12.75% | -10.00%（第3天停損） | **多賠 2.8pp**（停損單沒掛） |
| 五筆合計 | **-11.65%** | **-3.87%** | **7.78pp** |

**⚠️ 這是 2026-08-20 那次修正的漏網之魚。** 十八章記著當時已經處理過「C 與 D 混淆」——但**只改了投資策略頁的「策略規則」靜態區塊**，大盤分析頁這個框、`_market_advice()` 的 `<45` 分支、個股評分衰退警告**三處全都沒跟上**。而使用者每天實際會看的是前兩處。

**同批查出的另外兩處（同一病灶的不同出口）：**

| 位置 | 原文 | 問題 |
|---|---|---|
| `_market_advice()` `<45` | 「持股**逢反彈減碼**」 | 策略D 邏輯，無標註。且此函式**大盤分析頁與投資策略頁共用**，等於兩頁一起錯 |
| `render_score()` 評分衰退框 | 「**考慮減碼或停損**」 | **違反它自己的定位**——十八章明文寫「正確用法是『這檔要特別盯著』，不是『立刻出場』」，策略F 已回測（851筆）證明每次亮燈就賣、扣成本後由賺轉賠 |
| `net≥2` 減碼警報框 | 「建議**開始減碼**」 | 策略D，無標註 |

**修正（四處，全部改為明確區分「未持有」與「已持有」）：**

1. 綜合判斷框三個偏空級距：抽出共用的 `_HOLD_RULE` 字串，每一級都附上「📌 已持有的部位：不因這個分數出場」＋策略C 的兩項出場條件，並明講「上面那句只針對還沒進場的資金」。`+1`／`+3` 另加一句「這一級不構成任何出場理由」。
2. `_market_advice()` `<45`：改成「暫停進場（**此句僅針對新資金**）；已持有的部位不因此出場」。
3. 評分衰退框：改成「**這是提醒盯緊，不是出場訊號**」＋附上策略F 的實測結論。
4. `net≥2`／`net≥4` 兩個警報框：標明「這是策略D 的提醒，不是正式規則」，`+4` 那框另加「照做的話請在出場表單選『大盤轉空減碼』，之後看績效要對照 D 的基準」。

**⚠️ `_HOLD_RULE` 只列策略C 的兩項（停損、滿10日評分不足），刻意**不**把 `+4` 警報寫進正式清單**——那是 D，寫進去就是新一輪的規則漂移。

**方法論收穫（兩點，第一點最重要）：**

1. **⭐ 使用者說「系統沒效」時，先查他看到的畫面寫什麼，不要先假設是執行落差。**
   我第一版直接從資料推論「只抱 5 天 → 沒照規則 → 執行問題」，數字全對、歸因全錯。
   **「他做了什麼」與「系統叫他做什麼」是兩個不同的問題，而後者才是可以修的那個。**
   判斷方法：問一句「他當時螢幕上看到的是什麼字？」——這個問題只有去讀 UI 字串才能回答，
   從資料庫永遠推不出來。

2. **⭐ 規則寫在文件裡不算數，寫在使用者會看的那個框裡才算數。**
   本專案的正式規則（策略C）在 CLAUDE.md 與投資策略頁的「策略規則」區塊寫得很清楚，
   但使用者每天實際盯的是大盤分析頁的綜合判斷框——**規則沒有出現在那裡，等於不存在**。
   這與十八章「評分衰退提示搬到持倉列表」是同一條通則的反面：那次是「有偵測但沒顯示」，
   這次是「有規則但沒顯示，而且顯示了相反的東西」。**後者嚴重得多。**
   **日後新增任何「操作建議」類文字，都要先問：這句話與正式規則衝突嗎？看到它的人分得出
   這是給新資金還是給持倉的嗎？**

#### ✅ 全檔掃描已完成（2026-10-08），又挖出三處衝突

本則原本的待辦是「做一次全檔掃描，把所有『建議/考慮 + 減碼/出場/停損』的字串
逐一檢查是否標註了適用對象」。2026-10-08 補做，**除了大盤減碼警報那四處之外，
又找到三處與正式規則直接衝突：**

| 位置 | 原文 | 問題 |
|---|---|---|
| **`_position_status()`** | 📉「大盤轉空，**建議減碼**」，而且排在**第二順位** | 見下，這一處最嚴重 |
| 個股 **目標參考價** 卡片 | 「到達此價位**可考慮分批獲利了結**」 | 策略C 明文「**不設固定停利**」⇒ 直接衝突。而 2026-06 的持有天數掃描已測過 20 日 EV 最高，提早出場是扣分的 |
| 個股 **籌碼面 verdict** | 「🔴 高度警戒，**建議大幅減碼**」 | 那三個籌碼訊號**從未經過回測**，不可用來指示出場 |
| 個股 **RSI>80** | 「回檔機率較高，**可考慮減碼**」 | ① 沒有與無條件基準並列（2026-09-01 的教訓）② 沒區分未持有／已持有 |

**🚨 `_position_status()` 那一處最嚴重，而且不只是文字問題。**

原本的優先序是 `停損 🔴 ＞ 大盤轉空 📉（net≥4）＞ 到期 ⏰ ＞ 接近停損 ⚠️ ＞ 正常 🟢`。
十八章當初寫的理由是「大盤轉空排在到期之前，因為空頭回測顯示大盤層級訊號比個股訊號
更早也更有效」——**那個理由 2026-10-08 被推翻**（依淨值出清 9 年兩指標全 0/20 更糟）。

而排在「到期」之前的實際後果是：**一筆已經滿 10 個交易日、該重新評分的部位，
畫面上只會顯示「大盤轉空」——策略C 真正的出場條件被遮蔽了。**

⇒ 已改為 `停損 🔴 ＞ 到期 ⏰ ＞ 接近停損 ⚠️ ＞ 大盤偏空 📉（純資訊、中性灰）＞ 正常 🟢`。

**沒有動的兩處（它們就是正式規則本身）：**
`⏰ 已到期｜評分 <65 → 建議出場`、`停損參考價 → 建議出場保護資金`。

> **⭐ 通則補充：這類掃描不能只 grep 動詞（減碼／出場），還要 grep「與規則衝突的名詞」。**
> 「獲利了結」那一處之所以漏掉兩個月，是因為它的用字完全沒有「減碼」「出場」，
> 而是「停利」這個**策略明文說不做的事**。
> ⇒ 正確的掃描方式是**先列出正式規則說「不做」的事**（不設固定停利、不因大盤出場、
> 不因評分衰退出場），再去搜尋那些行為的所有同義說法。

**⚠️ 另外新增了一個「單一真相來源」的做法：** 這次把實測數據抽成模組層級常數
`D_RETEST_FACT` / `D_RETEST_WHY`（`app.py` 頂層），三個 UI 使用處共用。
陷阱30 的病根就是「同一訊息文字散在多處、只改一處」，而這次有 4 處要改同一組數字。

---

### 49. `prices` 存的是**未調整收盤價**，ETF／個股分割會造成假崩盤（2026-10-05 發現）

**⚠️ 這是陷阱42「錯資料看起來完全正常」的同一族，但來源不是程式 bug 而是資料本身的性質。**

**發現經過：** 寫 `backtest_vs_etf.py` 時，買進持有 0050 算出 **-35.85%**，
但那段期間它明明大漲。查價格序列：

```
0050  2025-06-10 收 188.65  →  2025-06-18 收 47.57     （中間 5 天無資料）
```

**0050 在 2025-06 做了 1:4 分割**（188.65 / 47.57 = 3.966 ≈ 4），而 **DB 存的是未調整收盤價**。
把相鄰收盤直接相除 → 當天變成 **-74.8%** 的假崩盤。
還原後那天其實是 **+0.86%**，整段報酬 **+156.59%**（與人工分段核對差 0.0000pp）。

**順便注意：那 5 天「缺資料」不是漏抓，而是分割換發的停止交易期間**——
資料完整性檢查（十九章）會把它列成缺漏日，但那是正常的。

> **🚨 下面這個掃描漏掉了 81% 的公司行為（2026-10-16 發現）。**
> 「**排除跨多日缺口**」這個條件正好濾掉最典型的分割——**換發必然伴隨停止交易**。
> 實測同一組 512 檔宇宙、2018 起：gap ≤7 天只抓到 **5 檔次**，
> gap >7 天被濾掉 **21 檔次** ⇒ 真實是 **26 檔次 / 24 檔**，而非本節寫的「3 檔」。
> **而且兩個方向都有**：×>1 是假崩盤（分割）、**×<1 是假暴漲（減資）**
> ——例如 2603 長榮 2022-09-06→09-19 由 80.8 漲到 169.0，一天「+109%」。
> 完整記錄與修正後的影響見十五章「停損距離在空頭樣本上的重驗」那節。

**全表掃描（相鄰交易日 |漲跌| ＞30%，排除跨多日缺口）：共 10 筆**

| 範圍 | 檔數 |
|---|---|
| **自選股** | **0 檔** ✅ ⇒ 2026-09 之前所有自選股回測不受影響 |
| 510 檔全市場宇宙 | **3 檔**：6669 緯穎（1:3，2026-09-02）、1808 潤隆、2540 愛山林 |
| 其他（ETF／權證／冷門股） | 7 筆，含 0050、00738U、00642U、00715L |

**對全市場回測的影響有界但真實：** 策略有 10% 停損，跨到分割日時當天 `low ≤ stop`
會以「假停損」出場 ⇒ 單筆損失被限制在 **-10%**（而不是 -66%）。
3 筆 / 3,450 筆，對平均 alpha 的影響 ＜0.02pp。
`backtest_vs_etf.py` 的 `_split_warn_trades()` 會把跨過公司行為日的交易列出來，不藏。

**目前處置：只在「買進持有基準」這一個用途上就地還原，不回填 DB。**
`_corporate_actions()` 的做法：相鄰交易日比值落在 **[0.65, 1.5]** 之外就判定為公司行為
（台股 ±10%，跨一個缺口日也到不了），再找最接近的整數倍（1/4、1/3、1/2、2…）：
- **對得上就用那個倍數**（0050 → 4.00，還原後 +0.86%，合理）
- **對不上就把整段跳動全當公司行為**（該日報酬視為 0%）
  — 保守選擇：寧可少算一天的真實漲跌，也不要留一個 -75% 的假崩盤

**⚠️ 為什麼不回填 DB（刻意）：** 要做對必須同時處理**除權息還原**（不只分割），
而那會改動所有既有回測的基準、也會讓「個股頁顯示的歷史價」與券商對帳單不一致。
這是另一個題目，不在本次範圍。

**待辦（未做）：** 十九章的資料完整性檢查目前**偵測不到這類問題**——
它只看「缺漏日」與「相鄰日四欄全等」，而分割是「四欄全部不等、而且差很多」。
**可以便宜地補上第三種偵測：相鄰交易日 |漲跌| ＞30% 的檔數**（正常市場應為 0，
台股有 ±10% 限制）。這會是監控的第四類盲區被補上。

**通則：**
1. **凡是要算「跨越數月的累積報酬」，都要先問一句：這段期間有沒有分割／減資／大額配股？**
   判斷方法極便宜：掃一遍相鄰交易日的漲跌幅，台股有 ±10% 限制，
   **任何超過 ±15% 的單日變動都不可能是真實行情**。
2. **只核對「頭尾」驗不出這類問題**——0050 的分割在中間，而首尾比值剛好仍是個「看起來合理」
   的負數（-35.85%），不會觸發任何警覺。要掃**每一個相鄰日**。

---

### 50. `exdividend` 只有 2026 年：長歷史回測的系統性偏誤（2026-10-07 發現）

**⚠️ 這是陷阱49（未調整收盤價）在回填 2018 歷史後放大出來的後果，
而它差一點讓月營收的檢定產生假陽性。**

**發現經過：** 回填 2018 起的全市場價格之後，準備測月營收訊號，
動手前先問「除權息會不會干擾」。查 `exdividend`：

```
exdividend：2026-05-28 ~ 2026-10-29，1,069 列
2018 ~ 2025： 全部 0 筆
```

而 DB 存的是**未調整收盤價**（陷阱49）⇒ **2018~2025 的除息既無法調整、也無法排除。**

**量化（用 2026 那 1,069 筆推估）：**

| | |
|---|---|
| 集中度 | **6~9 月佔 93.6%**（7月 39.9%、6月 25.4%、8月 18.1%、9月 10.2%）|
| 幅度 | 中位 **3.11%**、平均 **3.91%**、p90 7.70%、>10% 佔 5.8% |

**為什麼會製造假訊號（這是關鍵）：它與訊號相關，不是隨機雜訊。**

```
高成長股（電子）  → 殖利率低 → 除息拖累小
低成長股（傳產/金融）→ 殖利率高 → 除息拖累大
```

⇒ 在 6~9 月的前瞻窗口裡，**低成長組會被系統性壓低**
⇒ 產生**假的「高成長組贏」**，量級 1~4pp ——**與要找的效果同一個數量級，可能完全主導結果。**

**處理方式（三道防線，寫進 `backtest_revenue_signal.py`）：**

| | 做法 | 作用 |
|---|---|---|
| ① | **主檢定用產業內排名** | 同產業除息時點與殖利率接近 ⇒ 控制掉大部分 |
| ② | **必做診斷：分 1~12 月各自的 spread** | **若訊號只出現在 6~9 月就知道是股利**（自我診斷，不需額外資料）|
| ③ | Robustness：6~9 月 vs 其他 8 月分開做 Fama-MacBeth | 量化確認 |

**實測結果：其他 8 月 +2.12% ＞ 除息月 +1.72% ⇒ 方向與假訊號相反，地雷沒引爆。**
（而且 8月 +0.95%、9月 -0.07% 是全年最弱 ⇒ 除息反而在**壓抑**真實效果。）

**⚠️ 對既有回測結論的影響（尚未重新評估）：**
2026-09-24 全市場那批數字（基準組 alpha **-0.32%**）同樣用未調整收盤價。
策略偏向挑強勢股（＝電子＝低殖利率），而基準含全市場（高殖利率拖累較大）
⇒ **策略的 alpha 可能被高估**，真值比 -0.32% 更差。
屬二階效應（alpha 已經是負的），但重跑時要記得。

**順帶：長榮 2023-06-30 的 155→93.5（×0.60）被公司行為掃描抓進去，
其實是大額除息不是分割。** `_corporate_actions()` 用「找最接近的整數倍」還原，
×0.60 對不上任何整數倍 ⇒ 落入保守分支（該日報酬視為 0）。
行為是正確的，但要知道那一類事件被歸到哪裡。

**✅ 待辦的第一步已完成（2026-10-15）：參數找到了，是 `startDate`／`endDate`。**
實測整年一次就拿得到（2022 → 1,027 筆、2018 → 825 筆），**9 次請求約 1 分鐘**。
腳本 `backfill_exdividend.py`（已進版控，預設試跑）。詳見下方陷阱52。
⇒ 剩下的才是重點：**改回測去算「除息調整後報酬」**。
有了資料不等於回測用到了——這與陷阱51 那條通則同一族。

**通則：**
1. **「資料表有資料」不等於「資料表涵蓋你的回測期間」。** `exdividend` 有 1,069 列、
   看起來很健康，但全部集中在最近 5 個月。**查涵蓋範圍要看 `MIN`/`MAX` 與逐年分布，
   不是看 `COUNT(*)`。** 這與十五章「驗證合成指標前先看每個成分的分布」同一族。
2. **會製造假陽性的干擾，必須在動手前就想過一遍，而且要設計成「自我診斷」。**
   本次 ② 那個分月份診斷不需要任何額外資料，就能回答「這是不是股利造成的」——
   **把診斷內建在檢定裡，比事後補一個 robustness check 可靠得多**（事後補的那個，
   通常是結果不如預期時才會想起來做）。

---

### 51. 🚨 Signal 4 的三個缺陷（兩個在線上）＋ 我自己犯的一次陷阱41（2026-10-07）

**⚠️ 這一則是「為了重測策略D 而做的前置檢查」挖出來的，但影響比原本那題大。**

**起因：** 使用者要重測策略D。D 的觸發條件是「大盤淨值 ≥2」，所以先查
「淨值能不能回溯到 2018」——逐一盤點 `_build_market_signals()` 的資料來源時，
順手比對 `chips` 彙總與 `t86_ranking` 彙總，發現同一天的外資合計**連方向都相反**。

#### 缺陷① ETF 汙染（在線上，是明確的錯誤）

`get_chips_market_aggregate()` 把 `chips` 全表加總，而 `chips` 含 ETF。
主動型 ETF 的「外資買賣超」其實是**初級市場的申購買回量**（發行量），
不是外資在買賣股票。拆解 2026-10-05：

```
普通股合計          -440,798 張
ETF 等              +826,038 張   ← 00403A +150,918、00406A +128,492、00981A +110,265…
現用總和（含 ETF）   +385,240 張   🚨 方向被整個翻轉
```

全期 258 個交易日量化：

| | |
|---|---|
| ETF 占外資絕對值 | **中位 41%** |
| **ETF 把方向整個翻轉的天數** | **29 / 258（11%）** |
| 外資絕對值中位數 | 只算普通股 152,426 ／ 含 ETF 239,848（**膨脹 57%**） |

⇒ 不是參數問題，是**把兩種性質不同的數字加在一起**。

#### 缺陷② 門檻是用 51 天校準的，258 天上完全不成立（在線上）

| | ±3分 | ±2分 | ±1分 |
|---|---|---|---|
| 陷阱34 的絕對門檻（1,050,000／800,000／650,000） | **1.6%** | 5.0% | 7.8% |
| **陷阱34 自己訂的校準目標** | **5%** | **15%** | **30%** |

陷阱34 明寫「抓 50–250 日的實際分布算百分位」，但實際只用了 **51 天**。

**而更根本的是量級會漂移：** 外資絕對值中位數 2025 是 134,810、2026 是 192,086
（p95 由 366,841 → 544,660，**差 48%**）。⇒ **任何絕對張數的門檻，套到 2018
（市場規模小得多）必然幾乎不觸發，S4 在空頭年會是死訊號——而那正是最需要它的時候。**

#### 缺陷③ 回測與線上不同源（陷阱34 只同步了門檻，沒同步來源）

`backtest.py` / `backtest_stocks.py` 的 S4 讀 `t86_ranking`，app.py 讀 `chips` 彙總。
而門檻是依 `chips` 分布校準的，套在 `t86_ranking` 的加總上實測：

```
t86_ranking（回測在用）  ±3分 0.0%　±2分 2.4%　±1分 5.9%   ← ±3分一次都沒觸發過
chips 彙總（app.py 在用）  ±3分 3.5%　±2分 11.8%　±1分 17.6%
```

**⇒ 回測裡的 S4 幾乎是死的。** 十五章所有牽涉大盤過濾的數字（A vs B、策略C、
階梯的 Q1/Q2/Q3）都是在「S4 基本沒發揮作用」的狀態下跑出來的。

#### 修正（三處一起，2026-10-07）

| 檔案 | 改動 |
|---|---|
| `indicators.py` | **新增 `pct_rank_score()`**（滾動百分位，尺度無關）＋ `_selftest_pct_rank_score()`。**三處共用同一份實作**——陷阱34／43 都是「同一訊號三份實作、只改一兩處」造成的，唯一的根治方法是只留一份 |
| `database.py` | `_ORDINARY_STOCK_SQL` 排除 ETF（4碼純數字、非 `00` 開頭）；`get_chips_market_aggregate(stocks_only=True)` **設為預設**；新增 `get_chips_market_series()` 供回測取全期序列（不受 `date('now', -N)` 限制） |
| `app.py` | S4 改用 `pct_rank_score`；`_t86_hist` 載入 300 天（百分位需 ≥60 天）；訊號文字加上「近N日第X百分位」 |
| `github_sync.py` | 雲端匯出 30 → **300 天**。否則**雲端的 S4 會永遠 0 分**，與本機差 ±4 分 ⇒ 評分差 ±20 分 |
| `backtest.py`／`backtest_stocks.py` | 來源改 `get_chips_market_series()`，與線上同源；同樣用 `pct_rank_score` |

**新舊對照（85 天重疊期）：**

```
S4 有意見的天數        23/85  →  50/85
對 net 的平均貢獻      0.29   →  0.87
最大絕對貢獻           2      →  4（滿分終於會出現）
新舊差異               中位 0 分、平均 -0.25 ⇒ 無系統性偏多/偏空
方向相反               4/85 天　評分影響最大 ±15 分
```

**⚠️ 百分位切點（95/85/70）尚未校準完成，這是已量測到的偏差：**

實際觸發率 ±3分 **11.6%**（目標 5%）、≥±2分 21.6%（15%）、≥±1分 38.7%（30%）。
原因**不是**視窗長度（60/90/120/250/300 日都差不多），而是
**把當期值放進自己的參考視窗**：有趨勢／叢發時「今天是近 N 日最大」的頻率高於 1/N
（實測百分位分布右偏，90~100 那格佔 15.1%，均勻該是 10%）。

目前不動切點的理由：`chips` 只有 258 天，**300 日視窗從來沒填滿過**（60→258 一路膨脹），
這個觸發率不具代表性。**回填 2018 之後必須重新量並校準**（已抽成 `PCT_HI/MID/LO` 常數）。

#### 🚨 我自己犯的一次陷阱41（記錄下來，因為它比上面三個缺陷更值得記）

查 S3（台指期）能不能回填時，我用 `futContractsDate`（HTML 頁）要求 2018/01/02，
頁面回了一張有數字的表格，我就宣告「**TAIFEX 有 2018 資料**」。

但那一頁自己標著「**日期2026/10/07**」——**它忽略了日期參數、回傳最新資料。**

我當時正在拿陷阱41 的規矩（「必須驗證回傳的日期就是要求的日期」）去檢查
別人寫的 fetcher，**自己卻沒有套用它**。

> **⭐ 通則：「有資料」與「有你要的那天的資料」是兩件事。**
> 而且**立規矩的人不會自動遵守規矩**——陷阱41 的通則寫得很清楚，
> 但它寫在「檢查既有程式」的脈絡裡，我在「探索新資料源」時沒想到要套用。
> **判斷方法極便宜：回應裡只要有任何日期字樣，就先核對它。**

#### 連帶：我的腳本也犯了同一類靜默失敗

`backfill_market_signals.py` 第一版的 S3 區塊**只計「例外」、不計「空回應」**，
於是 TAIFEX 對 2018 回 HTTP 200 + 空 body 時，印出來是
**「已寫入 0 天　失敗區間 0」**——看起來像沒事發生。已修成會明講
「HTTP 200 但內容為空（N bytes）」，並在全空時跳 🚨 指向探測腳本。

**⇒ 寫「回報」的時候要問：零結果會被印成什麼？** 若「什麼都沒做」與
「全部失敗」長得一樣，那就是下一個靜默失敗。

#### S3 的實測結論（`probe_futures_history.py`，已進版控）

```
TAIFEX futContractsDateDown 的歷史邊界 ≈ 2023-10-09 ~ 2023-10-19（二分搜尋）
  2018❌ 2019❌ 2020❌ 2021❌ 2022❌ 2023-09❌ │ 2023-10-19✅ 2024✅ 2025✅ 2026✅
  ⇒ **完全拿不到任何空頭年**（2018／2020／2022）

FinMind：
  TaiwanFuturesInstitutionalInvestors   2018 ❌（0 列）／2022 ✅
  ★ TaiwanFutOptInstitutionalInvestors  2018 ✅ ／2022 ✅   ← 採用（多一個 name 欄）
  TaiwanOptionInstitutionalInvestors    都 ❌
```

**★ 混用兩個來源前做了強制對帳（`backfill_futures_finmind.py`）：**
拿最近 120 個 TAIFEX 已有的交易日，逐日比對 FinMind 的三欄淨額
⇒ **120/120 = 100.0% 完全相等**，門檻 95%，放行。

對帳是**阻斷式**的（不到門檻就 return、不寫任何一列），而不是事後的 robustness check
——這是陷阱50 那條「把診斷內建在檢定裡」的延伸，也是陷阱42（跨來源借資料造成
本專案最嚴重汙染）的直接防護。預設回填終點設 **2023-10-01**（< TAIFEX 邊界），
讓兩個來源的期間**不重疊**，不會互相覆蓋。

#### ✅ 回填與校準全部完成（2026-10-08）

```
S4 法人現貨   2128 / 2128 天  100.0%   （4,500 次請求 3 次逾時，重跑補齊）
S2 融資融券   2128 / 2128 天  100.0%
S3 台指期    2128 / 2128 天  100.0%   （FinMind 1,396 天 + TAIFEX 582 天）
```

**零「日期不符」** ⇒ 沒有一天被寫錯日期（陷阱41 那個守衛全程沒報警）。

#### 🚨 校準結果：10/07 那個「11.6%」是視窗沒填滿造成的假象

| 切點 95/85/70 的觸發率 | ±3分 | ≥±2分 | ≥±1分 |
|---|---|---|---|
| 10/07（258 天、視窗一路膨脹） | 11.6% | 21.6% | 38.7% |
| **10/08（2,071 天、視窗填滿）** | **6.7%** | **16.3%** | **32.3%** |
| 設計目標 | 5% | 15% | 30% |

⇒ **舊切點其實已經很接近**。微調為 **96/86/72**（驗算 5.1/15.2/30.1%）。
投信在 72 這一檔約 33.6%，**刻意不另設一組切點**——「同一訊號兩套參數」
正是陷阱34／43 反覆踩到的坑，多 3.6pp 不值得換那個風險。

合成資料四組對照也支持「方法本身沒偏差」：量級固定＋無自相關＋視窗填滿時
±3分 = 5.6%；只加量級成長 → 8.7%（+3.2pp）；只加強自相關 → 5.8%（+0.2pp）。
**量級漂移是機制，自相關幾乎沒影響**（我 10/07 寫成「趨勢／叢發」只對了一半）。

#### 🚨 而我在 `calibrate_signal4.py` 寫的判準是錯的，已更正

第一版寫「**逐年全距 <10pp 才算解決漂移**」。實測全距 **21.4pp**，
按那條判準會判定「百分位失敗」。但那條判準本身有兩個錯：

1. **純抽樣雜訊的期望全距就有 9.4pp**（p=30%、n≈240/年、9 年）⇒ 全距小本來就不該期待
2. **真實的市場波動本來就會讓極端日的密度逐年不同**
   （2020 COVID 39.2%、2026 43.2% 真的多；2025 21.8% 真的平靜）——那是訊號在做它該做的事

★ **正確的判準有兩個，而第二個才是決定性的：**

```
① corr(逐年量級, 逐年觸發率) = +0.667（n=9，p≈0.05）  ← 不算低
② 同量級年份對照（決定性）：
     2020  量級中位 128,441 → ≥±1分 39.2%
     2025  量級中位 126,970 → ≥±1分 21.8%
   **量級只差 1.1%，觸發率差 17.4pp ⇒ 量級不是決定因素**
```

⚠️ **不可過度延伸成「百分位完全消除了漂移」**：r=+0.667 不低，而且
**量級與波動度本身互相混淆**（波動大的年份絕對流量也大），n=9 分不開。
誠實的說法是「**量級已不是主要驅動因素，但殘餘關聯無法與真實波動度分離**」。

腳本已改成自動找出「量級最接近的一對」來做這個判斷，不再只看全距。

#### 🚨 連帶抓到：`_build_market_signals()` 把視窗寫死 600 天

回填完成後才發現，`backtest_stocks._build_market_signals()` 的三個來源
（TAIEX／futures／margin）都寫死 `days=600`。2018~2026 是 2,130 個交易日
⇒ **資料全補好了，它還是只看最後 600 天（2024-05 起），一個空頭年都沒有，
而且不報錯。**

這是**陷阱32 的第二次出現**（`calc_all()` 只餵 30 天，`pos_250` 靜默變成
「近 30 日位置」）。已加 `days` 參數（預設 600，維持既有 11 處呼叫不變）。

> **⭐ 通則：任何「撈最近 N 天」的資料載入，在回填歷史之後都要回頭檢查一次。**
> **回填本身不會讓既有程式看得到新資料。** 判斷方法：grep 所有 `days=`／`[-N:]`／
> `LIMIT N`，問一句「這個 N 夠不夠涵蓋我剛補的歷史？」

**⚠️ 十五章所有牽涉大盤過濾／大盤階梯的數字都該重跑**
——它們是在「S4 幾乎是死的」狀態下跑出來的（回測 ±3分 觸發率 0.0%）。

> **✅ 2026-10-15 已重跑最重要的那一項（大盤階梯），而且結論變了。**
> 腳本 `backtest_market_ladder.py`。三個發現：
> ① `≥70` 那一檔從「15 天（2.9%）、實質上不存在」變成 **193 天（9.1%）**
>    ——9/10 那句話描述的其實是「S4 死掉時的 net 分布」，不是系統的性質；
> ② 「隨大盤調整」這一維**第二次測不出貢獻**，而且這次是完美 null（10/20、p=1.000）；
> ③ 9/10 歸功於階梯的「門檻拉高到 70」**不是好處**（階梯 ≈ 一律70 是完美 null）；
>    **而階梯整體顯著差於「一律 65 分」**（4/20、p=0.012，兩份快取一致）。
>    ⚠️ 我第一版報的「一律70 vs 一律65：2/20、p=0.000」是 `sorted()` bug 的產物，已更正。
> 完整記錄見十五章「階梯的第二次驗證」。
> **⏳ 仍未重跑：** 策略 A/B/C/D 四策略表、停損距離校準、`confirm_days`。

---

### 52. 🚨 TWT49U 的請求參數是 `startDate`，但回應欄位叫 `strDate`（2026-10-15）

**⚠️ 這是陷阱41／44 那一族的第三次，但形狀不同、而且更陰險——
前兩次是「參數被靜默忽略」，這次是「參數名猜錯，而錯誤訊息看起來像別的問題」。**

**起因：** 陷阱50 的待辦——`exdividend` 只有 2026 年，而 `prices` 存未調整收盤價（陷阱49）
⇒ 2018~2025 的除息既無法調整也無法排除，是**與訊號相關**的偏誤
（高成長股殖利率低、除息拖累小 ⇒ 製造假的「高成長組贏」，量級 1~4pp）。
使用者問「這一步要跑多久」，於是去實測參數。

#### 四種猜法的實測結果

| 參數 | 結果 |
|---|---|
| `date=20220601` | ⚪ **靜默忽略**，回傳今天（＝陷阱41／44 的同一個坑） |
| `strDate=...&endDate=...` | ❌ 報「查詢結束日期小於查詢開始日期」 |
| `queryStartDate=...` | ⚪ 靜默忽略（那是 **TAIFEX** 的參數名，不是 TWSE 的） |
| **`startDate=...&endDate=...`** | **✅ 正確** |

```
startDate=20220101&endDate=20221231  → OK  1,027 筆  111年01月12日 ~ 111年12月28日
startDate=20180101&endDate=20181231  → OK    825 筆  首筆 107年01月11日 6477 安集
```

欄位正好就是 `exdividend` 表需要的那些（資料日期／股票代號／股票名稱／
除權息前收盤價／除權息參考價／權值+息值／權息別）
⇒ `fetcher.py` 既有的解析區塊**逐欄可重用**，不必另寫一份。

⚠️ **整段（2018~2026 一次）會逾時**，所以逐年查。
⇒ **成本不是原先估的 20~40 分鐘，是 9 次請求、約 1 分鐘。**
（TWSE 的 notes 寫股利資料自民國 92 年起提供，要更早把 `START_YEAR` 往前調即可。）

#### ★ 本則最值得記的兩件事

**(a) 那個錯誤訊息從頭到尾都是正確的，是我誤判成格式問題。**

`strDate` 被忽略 ⇒ 開始日**預設成今天（2026-10-15）** ⇒ `endDate=2022-06-30`
**真的**小於開始日 ⇒ 「查詢結束日期小於查詢開始日期」字面上完全正確。
我當時以為是民國／西元的格式問題，又去試了 `1110601`（也被忽略），白繞一圈。

> **⭐ 看到「參數讀到了但語意不對」的錯誤，先懷疑「是不是只有一部分參數被讀到」，
> 而不是先懷疑格式。** 判斷方法極便宜：**只傳一個參數**，看回應怎麼變
> （本例單獨傳 `strDate=20220601` → 回傳今天 ⇒ 立刻知道它被忽略）。
> 這與陷阱44「一個回應裡有兩個日期時不要挑順手的那個用」是同一族，
> 差別在那次是讀錯日期，這次是**用回應的欄位名去猜請求的參數名**。

**(b) 從回應欄位名猜請求參數名，是不可靠的。**

回應明明寫 `"strDate":"20261015"`，請求卻要用 `startDate`。
**唯一可靠的辦法是看網頁實際發出的請求。** 本次用瀏覽器開 twse.com.tw 的任一頁，
在**同源**的 console 裡直接 `fetch()` 測各變體——比點 UI 翻 DevTools 快得多，
而且**同源 `fetch()` 不會像 `web_fetch` 那樣把 query 參數按字母重排**
（參數順序敏感的 API 一定要走這條路）。

#### 回填腳本 `backfill_exdividend.py`（已進版控，預設試跑）

兩道守衛（照陷阱41 的教訓，缺一不可）：

| | 守衛 | 防什麼 |
|---|---|---|
| ① | 回傳的 `strDate`／`endDate` **必須等於**要求的區間，不符就當失敗、不寫入 | 「參數被忽略但仍回 200 + 合法資料」 |
| ② | **逐列**核對資料日期的年份落在要求的年份內 | 整年請求卻回傳今天那種退化 |

`is_confirmed=1`（TWT49U 是正式資料）⇒ `save_exdividend()` 走 `INSERT OR REPLACE`，
會覆蓋既有的 TWT48U 預告資料，這是對的。

**⚠️ 沙盒跑不動**（proxy 擋 twse.com.tw，9 年全部 `ProxyError`），必須在本機 Terminal 跑。
**但那次試跑本身有收穫：9 年全部印 🚨 而不是靜默地「共取得 0 筆」**
——這正是陷阱51 那條「零結果會被印成什麼？」的落實。

#### ✅ 回填完成（2026-10-15，使用者本機一次成功）

```
9,574 列　2018-01-11 ~ 2026-10-29
逐年：2018:823　2019:880　2020:887　2021:973　2022:1026
      2023:1086　2024:1184　2025:1358　2026:1357
```

#### ✅ 接進回測：`exdiv.py`（共用模組，已進版控）

**為什麼獨立成一個模組：** 陷阱34／43 的病根都是「同一邏輯三份實作、只改一兩處」。
除息調整會被 `backtest_portfolio_slots`／`backtest_revenue_filter`／
`backtest_structure_bear`／`backtest_vs_etf` 都用到 ⇒ **一開始就只留一份。**

**🚨 最重要的設計判斷：只調整個股、不調整基準，alpha 會被系統性高估。**
TAIEX 是價格指數、同樣不含股利 ⇒ 只改一邊，alpha 憑空多出整個市場的殖利率
（約 3~4%/年）。這與十五章「必須看 alpha 而非原始報酬」同一族——**量尺只改一邊。**

⇒ 所以 `exdiv` 提供**兩種**報酬，呼叫端必須知道自己在用哪一種：

| | 用途 |
|---|---|
| `pnl`（原樣） | 與**既有所有回測數字同基準** ⇒ 對照歷史結論時用這個 |
| `pnl_div`（個股加回股利） | **只能用在「兩組相減」**（市場項精確消掉）|

`P.stat()` 新增 `key='pnl'` 參數（預設 ⇒ 既有呼叫**位元級不變**，不需對帳）。

**領息條件差一天就錯：`entry_date < ex_date <= exit_date`。**
進場是在 `entry_date` 收盤成交 ⇒ 當天收盤買，價格已是除息後 ⇒ **領不到**；
出場日當天開盤就已除息 ⇒ **領得到**。`exdiv.py` 的自我測試
**把邊界兩側各造一個情境**（照 10/07「成對造情境」那條）。

**阻斷式涵蓋檢查 `require_coverage()`：** 任何一年筆數 < 門檻就 return False、
不給用 `pnl_div`——因為**「沒有股利」與「沒有資料」在數字上長得一樣**，
會讓那幾年的調整悄悄失效（陷阱41/42/45 的共同形狀）。
這是陷阱51「對帳要阻斷式、不要事後補 robustness」的延伸。

#### ★ 結果：十五章那個不利診斷解除，而且機制與預測吻合

B2−C 的除息月 vs 其他 8 月差距：**+0.12pp → +0.03pp**（雜訊帶 0.46pp 的 1/15）。
而且 **C 組（低成長＝高殖利率）被除息拖累得更多**
（股利提升 +0.32pp vs B2 的 +0.28pp；假停損率 1.67% vs 1.10%）
——正是陷阱50 預測的方向。完整數字見十五章「除息調整後」那節。

#### ⚠️ 仍然沒修的事：假停損（陷阱49 的同一族）

除息日的價格跳水會打到 10% 停損，產生一筆不該發生的停損。
實測 **1.1~1.7% 的交易**屬於這種（持有期遇 ≥2% 除息且以停損出場），
而且**高殖利率組的比率明顯更高** ⇒ 這是殘餘 +0.03pp 最可能的來源。
真正的修法是用**還原股價**跑整個回測，會改動所有既有基準，是另一個題目。
`exdiv.suspect_false_stops()` 會把這類交易列出來——**只揭露、不假裝沒事。**

#### ⏳ 還沒做：絕對 alpha 的除息調整版

需要**總報酬基準**（TWSE 發行量加權股價報酬指數，或
FinMind `TaiwanStockTotalReturnIndex`）。`exdiv.py` 刻意不猜。
做了之後，十五章所有 alpha 的絕對值都可以重新評估
——而 2026-09-24 那個「基準組 alpha -0.32%」有可能比現在更差
（陷阱50 已推論：策略偏向低殖利率的電子股，基準含高殖利率的全市場）。

---

### 53. 🚨 一次性回填留下一個「18% 的月份」，而它看起來完全正常（2026-10-17）

**⚠️ 這是陷阱42「錯資料看起來完全正常」的第三次，但來源不是程式 bug，
也不是資料本身的性質（陷阱49），而是**回填的那個時間點**。**

**起因：** 使用者問「接下來是不是要檢討月營收的問題」。九章標著的問題是
「沒接進每日更新 ⇒ 會變舊」。查了一下才發現**它不只是舊**：

```
monthly_revenue 最新營收月份：2026-09
  2026-09　 176 檔　avail_date 2026-10-11  ✅ 已過
  2026-08　 993 檔　avail_date 2026-09-11  ✅ 已過
  2026-07　 993 檔
```

`monthly_revenue` 是 **2026-10-06** 一次性回填的，而那天 9 月營收只公布了
176/993 檔（法規只要求次月 10 日前公布完）。到了 **10-11**（9月的 `avail_date`）之後，
`get_monthly_revenue()` 的 look-ahead 過濾就放行了——**開始供應那份 18% 的子集。**

#### ★ 偏誤方向已用最乾淨的方式量到（不是推論）

把那 176 檔「早公布者」拿去看**另一個完整月份**：

```
同樣是 2026-08（993 檔全部都在）：
  早公布的 176 檔　YoY 中位  +21.8%   (n=175)
  其餘    817 檔　YoY 中位  +13.3%
                          ⇒ 差 +8.5pp
```

**同一個月、完整資料、唯一的分組依據是「9月有沒有早公布」**
⇒ 那 8.5pp 不可能是月份效應，**就是選擇偏誤本身**。
陷阱50 當初寫的「偏向先公布者（業績通常較好）」——方向、量級都對上了。

#### ⚠️ 最危險的地方：它與真實情況在數字上無法區分

**「這個月只有 176 檔」與「這個月真的只有 176 家公司營收」長得一模一樣。**
九章原本的處置是「讓過期這件事看得見」（caption 印出資料截止月份），
但那**只看得到「舊」，看不到「不完整」**——2026-09 顯示在 caption 上，
看起來反而是「很新」。

#### 做的三件事

| | |
|---|---|
| ① **完整度守衛**（`database.incomplete_revenue_months()`） | 某營收月筆數 < 全市場中位 ×0.6 ⇒ **整月不供應**。**阻斷式**，不是警告 |
| ② **接進 `fetch_all()`**（`fetcher.fetch_monthly_revenue()`） | 每日重抓「當月＋前兩個月」。⚠️ **刻意不用 `MAX(date)` 水位線**——次月 1~10 日逐日累積，「抓過就跳過」會讓那個月永久停在不完整快照（陷阱45 的病根） |
| ③ **把 MOPS 實作收成一份** | 回填腳本抽出 `upsert_month()` / `write_rows()`，`fetcher` **呼叫它而非複製**。陷阱34／43 的病根就是同一邏輯多份實作 |

**★ 守衛放在存取函式而不是 UI**，所以 `github_sync` 的雲端匯出自動受保護。

**門檻 0.6 不是憑感覺：** 回填腳本本來就有 `len(rows) < 600` → 標「⚠️ 公布中，
之後要重抓」。**它早就知道這件事，只是當時只印出來、沒有擋。**
0.6 × 中位 930 ≈ 558，與那條線同一個量級。

**三個方向都實測過**（照 10/07「成對造情境」那條）：
真資料 → 只擋 2026-09（176 檔，105 個月中唯一一個）；
門檻放寬到 0.1 → 不擋（證明是門檻驅動、不是寫死）；
完整月份 → 完全不受影響。

#### ⭐ 方法論（新的一條）

**一次性回填會把「執行當天的世界」凍結進資料庫，而那個時間點本身就是一種抽樣。**

專案對「資料對不對」的檢查已經很多（陷阱41 的日期守衛、陷阱42 的重複日、
陷阱50 的涵蓋範圍），但那些問的都是**內容**。這一則問的是
**「這份資料是什麼時候抓的，那個時點有沒有讓它變得不具代表性」**。

⇒ **判斷方法：對任何一次性回填，問一句「最後那幾筆，在抓的當下是完整的嗎？」**
凡是答案為否的資料源（月營收、財報、法說會、任何有「公布期間」的東西），
**都需要一道完整度守衛**，而不是只靠「之後記得重抓」。

而且這一則與陷阱50 是同一族的兩半：
那次是「**資料表有資料 ≠ 涵蓋你的回測期間**」（看 MIN/MAX 與逐年分布），
這次是「**某個月有資料 ≠ 那個月是完整的**」（看逐月筆數 vs 中位）。
**兩個檢查都只要一行 `GROUP BY`。**

---

### 54. 🚨 懶加載的靜默失敗：39/103 檔自選股季報全缺（含台積電），而 yfinance 明明有資料（2026-10-20）

**⚠️ 這是陷阱51 那條「零結果會被印成什麼？」的第四次，而且本則裡我自己又犯了一次
「用索引假設排序」——在報告層，差一點把正確的資料報成「落後三年」。**

**起因：** 使用者問「為什麼個股華新科看不到資料？其它個股也會這樣嗎」。

**先查，結果與「沒資料」相反——華新科（2492）幾乎全滿：**

| | 筆數 | 最新 |
|---|---|---|
| `prices` | 2,137（2017-12 起）| 當天 |
| `chips` | 2,138 | 當天 |
| `fundamentals`（PE/PB/殖利率）| 114 | 前一日 |
| **`monthly_revenue`** | 105 個月 | 2026-09，**YoY +53.9%**（連四月加速）|
| `ownership` | 15.19% | 當天 |
| 雲端 `data/json/2492.json` | 131 KB | 當天 22:05 |
| **`stock_quarterly_financials`** | **0** | — ← **只有這個** |

⇒ 空的只有「💰 基本面」頁籤裡的**季度 EPS 趨勢**那一張圖。

**而「其它個股也會嗎」的答案是會，而且比例很高：**

```
stock_quarterly_financials 全市場只有 66 檔
103 檔自選股裡 39 檔完全沒有 —— 含 2330 台積電、2454 聯發科、
                               2881 富邦金、6488 環球晶、8046 南電
```

**⇒ 「連台積電都缺」就排除了「新加入的股票還沒抓」這個解釋。**

#### 根因：`app.py` 季度 EPS 區塊的懶加載（陷阱19 留下的）

```python
if IS_LOCAL and not _qf_rows and not st.session_state.get(f'_qf_fetched_{code}'):
    st.session_state[f'_qf_fetched_{code}'] = True   # ← 抓取**之前**就鎖住
    try:
        _n = _fetch_qf(code, years=4)
        ...
    except Exception:
        pass                                          # ← 失敗沒有任何痕跡
```

兩個缺陷疊加：

| | |
|---|---|
| ① 鎖設在抓取之前 | 抓失敗後，**這個 session 內永遠不會重試**。而 Streamlit App 常開著數天不重啟 |
| ② `except: pass` | 畫面只是一張空圖，**沒有任何訊息** ⇒ 使用者無從分辨「真的沒資料」與「抓失敗了」 |

**關鍵的排除步驟：先確認資料源有沒有東西，再修程式。**
本機實測（沙盒的 proxy 擋 yfinance，必須在本機跑）：

```
2492 (45, 5)    2330 (54, 6)    2454 (45, 6)    1101 (47, 6)
```

**四檔全有 ⇒ 不是資料源的問題，是補抓流程的問題。** 若少了這一步，
很可能會往「換資料源」的方向白走一趟。

#### 修正

| | |
|---|---|
| `backfill_quarterly_financials.py`（已進版控，預設試跑） | 一次補齊自選股缺的檔，**逐檔印結果、失敗明確列出** |
| `app.py` 懶加載 | 失敗時把原因寫進 `st.session_state[f'_qf_err_{code}']`，空圖下方以 caption 顯示＋附重試指令。**鎖仍然要設**（Streamlit rerun 很頻繁，不鎖會每次重抓），但失敗不再無聲 |

**實際執行結果（使用者本機，39 檔）：**

```
成功 35 檔　零結果 4 檔　例外 0 檔
```

★ **FinMind 那條路給 15 季（2022Q4~2026Q2），比 yfinance 的 5~6 季多得多**
⇒ `fetch_quarterly_financials()` 的「FinMind 優先、yfinance 備援」設計是對的，
而且 `saved > 0` 才 `return` 這個寫法讓它正確地落到備援。

#### ★ 零結果那 4 檔全部是結構性的，不是 bug

```
2881 富邦金　2882 國泰金　2891 中信金   ← 金融保險業（industry='17'）
9103 美德醫療-DR                        ← 存託憑證
```

**金融業的損益表沒有「毛利」這個科目**——銀行與保險的收入是利息淨收益／保費收入，
不走「營收 − 銷貨成本」。而 `fetch_quarterly_financials()` **兩條路都有
`if rev and gp` 的守衛** ⇒ 必然被擋掉。DR 則沒有獨立財報。

⇒ **這兩類永遠補不回來**，所以腳本與 UI 都把它們標成「⚪ 結構性」、
**不列入「待處理」的計數**——十九章那條通則：
把無解的照樣算進警告數字，使用者兩週後就會學會忽略整個警告框。

#### 🚨 我在報告層犯的「用索引假設排序」（本則最值得記的部分）

腳本第一版印出 **「最新季度分布：2023Q3　35 檔」**——35/35 檔同一個值、
而且落後三年。看起來像「yfinance 的資料很舊」，**但資料其實完全正確**
（2492 與 2330 都是 2022Q4~2026Q2 共 15 季，台積電毛利率 53%→67%、
EPS 7.98→27.25，全部合理）。

錯在這一行：

```python
rows   = get_quarterly_financials(c, quarters=12)
latest = rows[0]['period']        # ← 以為 [0] 是最新
```

而那支函式的 **docstring 第一行就寫著「升序」**。15 季取最新 12 季
（2023Q3~2026Q2），升序的 `[0]` 正好是 **2023Q3** ⇒ 35 檔全部印出同一個值。

**正解：用專門回答這件事的那支函式** `get_quarterly_financials_last_period()`
——它不受 `quarters` 截斷影響，而且它存在的理由就是這個。

| | `rows[0]` | **`last_period()`** |
|---|---|---|
| 2492 / 2330 / 1101 | 2023Q3 | **2026Q2** ✅ |

**⭐ 這一則與陷阱43（`list[-2]` 不等於前一個交易日）是同一個病根，
但它出現在「報告層」而不是計算層 ⇒ 數字全對、讀出來的結論完全錯。**
與 10/07 那條「呈現差異時不要讓讀者自己推符號」同一族。

⇒ **判斷方法極便宜：取某個序列的「最新一筆」之前，先讀那支函式的 docstring，
或印 `rows[0]` 與 `rows[-1]` 兩個一起看。** 本專案的 `database.py` read 函式
**大多回升序**（`get_prices`／`get_chips`／`get_market_margin`／
`get_quarterly_financials`…），但 `get_monthly_revenue()` 是**降序**
——所以「這個專案一律升序」這個印象本身也是錯的，每支都要確認。

#### ⚠️ 定位：這件事不影響任何評分與回測

`scorer.py` 的基本面 25% 走的是 **`fundamentals` 表（PE/PB/殖利率）**，
完全不碰 `stock_quarterly_financials`。後者只有兩個用途：
個股頁的季度 EPS 圖、以及 EPS TTM 的第二層 fallback（陷阱20）。
⇒ 39 檔缺季報期間，評分、進場門檻、十五章所有回測**都不受影響**。

#### 🚨 隔天發現第二個缺陷：同一段懶加載「只在完全沒資料時才抓」（2026-10-21 修）

**起因：** 使用者問「個股的 eps 一直都還留在 q1 或 q2，何時會更新」。
**答案是「不會自己更新」**——我 10/20 只修了「失敗沒痕跡」，沒看到條件本身也是錯的。

```python
if IS_LOCAL and not _qf_rows and not st.session_state.get(f'_qf_fetched_{code}'):
#                ^^^^^^^^^^^^ 只有「完全沒資料」才抓
```

⇒ **每檔股票永久凍結在「第一次被點進個股頁那一天」的最新季度。**
對照 `updated_at` 看得一清二楚：

```
停在 2026Q1：51 檔    有 2026Q2：50 檔     ← 差別只是當初哪一天被點到
  6~9 月抓的 → 停 Q1（Q2 半年報 8/14 才公布）
  10/20~21 抓的 → Q2
```

而 **`fetch_all()` 完全沒碰這張表**——與月營收在陷阱53 之前一模一樣。

**★ `market_tracker` 的四檔反而是對的**（它們每 session 無條件重抓一次）：
2049／2317／2308 今天 21:23 都更新成 Q2，而 **7769 停在 `2026-06-27`**
——因為那個分頁從 6/27 起沒再被打開過。⇒ **那四處的寫法沒錯，只是依賴「你有去點」。**

#### 修法：條件改成「沒資料 **或** 季度已過期」（使用者選的方案）

新增兩個模組層級 helper（`_vol20_label()` 正下方）：

| | |
|---|---|
| `_expected_last_period(today)` | 依**法定申報期限**回傳「現在應該已公布的最新季度」。Q1→5/15、Q2 半年報→8/14、Q3→11/14、Q4/年報→隔年 3/31。11 個邊界日逐一單元測試通過（含 8/13 vs 8/14、11/13 vs 11/14 這兩對）|
| `_qf_is_stale(code)` | `DB 最新季度 < 應有季度` **且** `上次抓取已超過 QF_RETRY_DAYS(7) 天` |

**★ 第二個條件是必要的，不是保險。** 資料源（FinMind／yfinance）比公司公告再慢
1~2 個月 ⇒ **法定期限剛過的那幾週，來源還沒有**。少了重試間隔，那段時間
每次點進個股頁都會白敲一次 API。
（這是陷阱44「不要留一個看起來像在補齊的迴圈」的反面：那次是假裝補得到，
這次是真的補得到但**不能一直敲**。）

**UI 另加一行：** 過期、重抓後來源仍沒有新季度時，明講
「目前最新為 2026Q2，法定上應已有 2026Q3——來源通常慢 1~2 個月，每 7 天自動重試」。
⇒ **「等來源」與「漏抓」在畫面上要分得出來**，否則又是一個靜默狀態。

#### ⏰ Q3 2026 的時間表（回答使用者的問題）

| | |
|---|---|
| **2026Q2 是目前正確的最新季** | 今天 10/21，Q3（7~9月）法定期限是 **11/14**，現在任何來源都還不會有 |
| Q3 進到 FinMind／yfinance | 公司 11 月中公告後再慢 1~2 個月 ⇒ 約 **11 月底 ~ 12 月** |
| 那 51 檔停在 Q1 的 | **是漏抓**，修正後點進個股頁會自動補上 Q2 |

#### ⭐ 方法論：「修好了」要問一句「那個條件本身對嗎」

10/20 我花了很多力氣修 `except: pass`（失敗要看得見），**但完全沒質疑
`not _qf_rows` 這個前提**——因為它看起來就是懶加載該有的樣子。
結果修完的隔天，使用者一句「何時會更新」就問出了真正的缺口。

⇒ **懶加載的條件要分兩問：「什麼時候該抓」與「失敗了怎麼辦」。**
我只答了第二問。而第一問的正確答案幾乎從來不是「沒資料才抓」
——只要那份資料會隨時間新增（財報、月營收、法說會），
**「沒資料才抓」就等於「只抓第一次」。**
這與陷阱45（`MAX(date)` 水位線看不到中間的洞）是同一族：
**都是用一個「看起來合理的條件」取代「真正該問的問題」。**

#### 沒有動的地方（刻意）

`market_tracker` 的四個固定監控股（2049 上銀／2317 鴻海／7769 鴻勁／2308 台達電）
有**完全相同的 `except Exception: pass`**。沒改的理由：那是五個天天看的分頁、
單一股票、有問題會立刻發現，不是靜默風險的主要來源；而個股頁那一處
影響全部 1,000+ 檔。**但那四處仍然是同一個 bug，日後若要動那一頁要一起修。**

#### ⭐ 方法論（兩條，第一條是舊通則的新形狀）

**(a) 「失敗必須長得跟成功不一樣」要涵蓋 UI，不只腳本。**
陷阱51 立這條規矩時講的是回填腳本的輸出。這次同一個病出現在
**Streamlit 的 try/except 裡**——而 UI 的 `except: pass` 比腳本的更危險，
因為腳本至少會印一行，UI 只是少畫一張圖。
⇒ **任何 `except Exception: pass` 包住的「自動補抓」，都要留一條使用者看得見的痕跡。**

**(b) 「看不到資料」這類回報，要先查「是哪一塊看不到」，不要先接受「沒資料」這個說法。**
本例使用者說的是「看不到資料」，而實際上 6 張表裡 5 張全滿、只有 1 張空。
若直接去修「資料抓取」，會往完全錯的方向走。
⇒ **逐表印 `COUNT(*) / MIN(date) / MAX(date)`，成本幾秒，而它直接定位問題。**

---

### 55. 🚨 回測宇宙是用「今天的掛牌清單＋今天的流動性」挑的（2026-10-21）

**⚠️ 這是 2026-09-24 那條通則（「回測宇宙的組成時間必須早於回測期間的起點」）
在**股票母體**上的版本。那次出現在自選股，這次出現在全市場宇宙本身。**
量測結果見十五章「清地基」那節（alpha 掉 0.33~0.44pp）。

#### 兩個條件都擋，而後者是決定性的

```python
def market_universe(conn, ...):
    mk = dict(conn.execute("SELECT code, market FROM stocks"))   # ← 今天的掛牌清單
    rows = conn.execute(
        "... FROM prices WHERE date>=? ... GROUP BY code HAVING n>=?",
        (UNI_SINCE, UNI_MIN_DAYS))      # ← UNI_SINCE='2025-09-01'、n>=180
```

`UNI_SINCE` 是**近一年**。所以任何在 2025-09 之前消失的股票，
`n>=180` 必然不成立 ⇒ **一律被排除，而且不是被「流動性」排除的。**

| | 檔數 |
|---|---|
`prices` 裡 2018 起的 4 碼普通股 | 2,040 |
　├ `stocks` 查得到 TWSE | 1,082 |
　├ `stocks` 查得到 TPEx | 885 |
　└ **★ `stocks` 查不到（已退場）** | **73** |
　　　其中日均成交 ≥0.5 億（會達標） | **21** |
　　　其中 2018~2026 歷史退場 | **18** |

那 18 檔：**6452 康友-KY**（2020-08 財報造假下市、日均成交 2.89 億、
639 個交易日 ⇒ 完全達標，但從未出現在任何回測裡）是唯一的全損；
其餘多為**合併換股**（2311 日月光→日月光投控、2325 矽品、2448 晶電→富采、
2456 奇力新、2888 新光金→台新新光金、2823 中壽、2809 京城銀、1704 榮化、
3682 亞太電→遠傳、5264 鎧勝-KY、3454 晶睿…）——股東有換到對價，
**所以偏誤方向不是單純「贏家才留下」**。

#### ⚠️ 連帶更正：10/07 與 10/08 的「點時間宇宙」只做對了一半

`backtest_structure_bear.py` 的 `uni_at` 雖然叫 point-in-time，
成員資格仍然是 `mk.get(r[0]) == 'TWSE'`（第 331 行）
⇒ **時間是逐月重算的，但「是不是上市」是查今天的表** ⇒ 同樣漏掉那 18 檔。
所以 10/07（續抱 +169pp）與 10/08（真D 否決）兩節的宇宙也帶著這個偏誤。
⚠️ 那兩節的**配對差值**受影響較小（偏誤是共同項），但**絕對報酬**偏高。

#### ★ 修法：上市判準改成「有 chips」，不依賴 `stocks`

`chips` 的來源是 TWSE **T86，而 T86 只收上市** ⇒ 一個不依賴「今天的狀態」
的乾淨判準。實測驗證：

```
18/18 已退場股都有 chips（2017-12 起）      ✅
對照 上櫃 6488／3324／4979 的 chips 筆數 = 0 / 0 / 0   ✅
```

| 新增（`backtest_portfolio_slots.py`） | 作用 |
|---|---|
`listed_codes(conn)` | 上市集合＝有 chips 的 4 碼普通股 |
`pit_universe(conn)` | 每月第一個交易日依「過去 130 日流動性」重算，回 (months, union) |
`pit_lookup(months)` | bisect 成 `lookup(date) -> frozenset` |
`assert_pit_has_delisted()` | **阻斷式**守衛（見下） |
`simulate(pit_at=None)` | `None` ⇒ 位元級不變；給 lookup ⇒ 只有當天在宇宙裡的才可進場 |
`cand_probe=None` | 量「單日候選 ≥ 槽位數」的比例（10/14 的便宜判準） |
`cache_dir()` | 快取目錄，可用 `TWSTOOL_CACHE` 改掉（見陷阱56 末） |

`market_universe()` **刻意保留不動**（唯一能對帳既有數字的東西），
只在 docstring 加 🚨 警語。

**★ 守衛的設計：不檢查「有幾檔」，檢查「有沒有已退場的」。**
```
點時間宇宙裡「今天的 stocks 查不到」的檔數 < 10 ⇒ sys.exit(1)
```
因為若判準悄悄退回查 `stocks`，宇宙會再次變成倖存者，而**結果看起來完全正常**
（陷阱41/42/45 的共同形狀）。硬編碼那 18 個代號會很脆；用「已退場股的檔數」
當判準則是自我描述的。**兩個方向都實測過**（照 10/07「成對造情境」那條）：
真資料 ⇒ 26 檔、放行；刻意把判準退回查 `stocks` ⇒ 0 檔、阻斷 exit 1。

#### 宇宙規模（2018-01 ~ 2026-10，106 個月）

```
逐月宇宙平均 390 檔　聯集 872 檔（現行 market_universe 是 513）
  2018 平均 192（0~304）   ← ⚠️ 價格回填邊界，見下
  2019 265　2020 328　2021 472　2022 407
  2023 408　2024 490　2025 467　2026 496
```

**⚠️ 2018 那個 192 不是 bug：全市場個股價格只回填到 2018-01-02**
（TAIEX 有 2016-10，個股沒有）⇒ 前 60 個交易日湊不滿 130 日回看窗。
**待辦：回填 2017 的全市場價格**（`MI_INDEX` 逐日，約 250 天、十幾分鐘，
與 `backfill_prices_history.py` 同一條路）即可補完整。

---

### 56. 🚨 「位元級一致」只在同一份快取內成立——DB 每天都在改寫歷史（2026-10-22）

**⚠️ 這一則要修正十五章 10/14、10/15、10/16 三處「與改版前位元級相同、
不需對帳」的說法。那些話的正確範圍是「**同一份快取內**」，
不是「同一套程式＋同一個 DB」。**

#### 發現經過：一個對帳點對不上，而分解得很乾淨

10/21 重建快取後想對帳既有數字（★10%／現行階梯 ⇒ 15,169~15,176 筆、
alpha +0.31%），結果：

| 組 | 這次 | 既有 | 差 |
|---|---|---|---|
`R65` 舊宇宙・**一律65**（不碰大盤淨值） | 28,444　**+0.18%** | 28,613　**+0.19%** | 筆數 -0.6%、**alpha 差 0.01pp** |
`R` 舊宇宙・**現行階梯**（走大盤淨值） | 15,221　**+0.24%** | 15,169~15,176　**+0.31%** | 筆數 +0.3%、**alpha 差 0.07pp** |

**alpha 的落差集中在走階梯的那一組** ⇒ 指向 `market_net`。

#### 機制：FMTQIK 每日用 UPDATE 重寫近 12 個月的 `prices.value`

```
backtest_stocks._build_market_signals() 的 Signal 8：
    vols = [p['value'] for p in tpx_win[-5:] ...]        ← 讀 TAIEX 的 value
fetcher.fetch_market_volume(months=12)：
    逐月呼叫 FMTQIK，對近 12 個月 **UPDATE ... WHERE date=?**
```

⇒ **近 12 個月的歷史 `value` 每天都可能被改寫** ⇒ S8 的量能趨勢變
⇒ 淨值變 ⇒ 階梯門檻（70/55/45）在某些日子跨界 ⇒ 交易集合變。

而這**正是陷阱27 刻意的設計**——當初為了修「同一欄位混雜 yfinance 原始值
與 FMTQIK 億元值」，必須回填歷史。所以它不是 bug，是一個**正確的設計
帶來的副作用**：歷史會變。

另一條同族的路：**智慧補齊（陷阱45）會填補近 45 天的缺漏日**
⇒ 改變那些日期的訊號與評分。這對應 R65 少掉的 169 筆（約兩個月的量級）。

#### ⇒ 能說與不能說

| | |
|---|---|
❌ **不可再說** | 「`filter=None` 時與改版前**位元級相同**，所以不需要對帳」——那只在同一份快取內成立 |
✅ 正確說法 | 「參數預設值不改變 `simulate()` 的行為 ⇒ **同一份快取**下位元級相同；但跨 session 重建的快取必然不同，**絕對數字不可並列**」 |
✅ 可以說 | **同一份快取內的比較（配對、A/B）完全有效**——偏誤是共同項 |

**⇒ 實務規則：任何要跨 session 比較的絕對數字，必須連同快取一起保存；
否則只能比「同一份快取內的兩組」。**

#### 順帶：快取放 `/tmp` 的代價終於被付了

CLAUDE.md 從 10/15 起就把「所有快取都在 `/tmp`」標成已知的結構問題。
10/21 要重用 10/16~10/18 那份 `_pf_slots_cache_market.pkl` 時，
**整個不見了**（`/tmp` 被清）⇒ 一份 20~40 分鐘的快取白建，
而且連帶失去唯一能對帳既有數字的東西。

⇒ 新增 `backtest_portfolio_slots.cache_dir()`：預設仍是 `/tmp`
（維持既有行為），可用環境變數改掉，所有讀寫快取的腳本都會把解析後的
路徑印出來。`data/cache/` 已加進 `.gitignore`。

```
export TWSTOOL_CACHE=~/台股分析工具/data/cache
```

⚠️ **建快取與跑測試必須用同一個值**，否則會「找不到快取」然後重建。

#### ⭐ 方法論

**對帳失敗時，要先用「不經過嫌疑路徑的那一組」做分解，而不是逐行讀程式。**
本次的關鍵一步是加 `R65`（一律 65 分、**不碰 `market_net`**）當第二個對帳點：
它幾乎完全對上（alpha 差 0.01pp）而 `R` 沒有 ⇒ 一次就把範圍縮到大盤淨值，
不必去猜是評分、價格還是模擬邏輯。

**⇒ 對帳點至少要兩個，而且要刻意選成「經過／不經過同一條嫌疑路徑」。**
單一對帳點只能告訴你「對不上」，兩個才能告訴你「哪裡對不上」。

---

## 十九、資料完整性檢查（2026-09-08 新增）

**為什麼做這個：** 三天內連續發現三個**靜默失敗**——陷阱40（快取沒失效，9/1 評分點消失）、陷阱41（`STOCK_DAY_ALL` 的 date 參數被忽略，補齊機制假成功）、陷阱42（上櫃快照被蓋上錯誤日期，整批重複資料）。三者的共同點：**程式不報錯、畫面看起來完全正常，全靠使用者偶然察覺**。陷阱42 更是在使用者沒發現的情況下，從 2026-05 起累積了 11 個受汙染的日期。

**設計立場（重要）：** 沒辦法保證每一支 fetcher 永遠不出事——API 會改版、參數會失效、伺服器會逾時、外部資料源的發布節奏會變。**但可以保證出事時會被看見。** 這個檢查解決的不是「哪一支壞了」，而是「壞掉的時候多久才會知道」。

### 兩種偵測（互補，缺一不可）

| 偵測 | 方法 | 抓得到什麼 |
|---|---|---|
| **缺漏日** | 以 TAIEX 的實際交易日為基準（yfinance 抓整段，全專案缺口最少），比對七張表少了哪幾天 | 陷阱39/41 那類「補齊機制失效」 |
| **重複日** | 相鄰交易日「開高低收四欄全等」的檔數比例，分市場統計，`≥80% 且檔數 ≥100` 即判定 | 陷阱42 那類**資料汙染**——缺資料檢查**完全抓不到** |

第二項是這次事件最重要的收穫：**缺資料看得出來，錯資料看起來完全正常。** 正常市場單日平盤股只有個位數，整批相同必然是寫入錯誤。

### 實作

`app.py` 兩個函式（定義在 `_market_advice()` 正上方）：

- `_data_integrity_report(days=30)`：回傳 `{'missing': [(表名, [日期...])], 'dupes': [(日期, 市場, 相同檔數, 總數)]}`。只掃最近 30 個交易日（近期問題才需要立即處理，舊缺口已知），SQL 全走 index，單次約 0.1 秒。**快取 key 帶 TAIEX 最新日期**（`_integrity_{date}_{days}`），資料一更新自動重算——遵循陷阱40 的通則。
- `_render_integrity_warning()`：**沒問題時完全不顯示**（同多殺多框、資金配置警示的設計慣例）。有問題時在側邊欄畫一行摘要，並附可展開的明細與對應的修復指令。

**顏色分級刻意反映嚴重度：** 有重複日 → 紅色（資料汙染），只有缺漏 → 橘色。

**位置：側邊欄，更新按鈕下方。** 選這裡的理由：(1) 每一頁都看得到，不像大盤分析頁要切過去；(2) 緊鄰「🔄 手動更新資料」這個動作，更新完立刻看到結果。

**僅本機（`IS_LOCAL`）：** 雲端的 DB 是每次部署重建的暫存資料，這個檢查的語意（「今天的抓取有沒有成功」）在雲端不成立。

### 實測結果（2026-09-08 首次上線，近 30 個交易日）

```
【缺漏日】
  個股收盤   : 完整 ✅        個股籌碼  : 完整 ✅
  法人排行   : 缺 2 天         融資融券  : 缺 2 天
  台指期法人 : 缺 1 天（9/7）  選擇權P/C : 缺 1 天（9/7）
  大盤本益比 : 缺 12 天  ← 最嚴重
【重複日】
  08-04 / 08-14 / 08-20 / 09-08  TPEx 各約 970~979 檔與前一交易日完全相同
```

兩個偵測都正確抓到已知問題，證明邏輯有效。

### 缺漏項目的三種分類（2026-09-08 更新）

上線當天列出的三個缺口（台指期法人、選擇權P/C、大盤本益比）已逐一驗證並處理，結果分成兩類——**這個分類本身就是本章的價值**：警告框只計數「做得到的事」，做不到的另外列，避免監控變成天天叫但無事可做。

| 分類 | 項目 | 處置 |
|---|---|---|
| ✅ 按更新即自動補齊 | 個股收盤、個股籌碼、融資融券、法人排行、台指期法人、選擇權P/C | 六支都改用交易日日曆比對，**中間的洞也補得到**（陷阱44 加了補齊、陷阱45 修好水位線） |
| ⚪ **做不到，永久缺口** | 大盤本益比 | BWIBBU_ALL 的 date 參數無效，只拿得到最新一份報表。**不影響任何評分與回測**（陷阱43 已查證），只會讓估值走勢圖有斷點 |

（`backfill_missing_days.py` 仍保留，但正常情況下不再需要——按更新按鈕就會補。它現在的用途是「補超過 45 天的舊缺口」或繞過 fetcher 直接重抓。）

`_render_integrity_warning()` 對應改成三段顯示：`_INTEGRITY_FIX` 給每一項標上該怎麼修；`_INTEGRITY_UNFIXABLE` 裡的項目**不列入警告框的計數**，只在明細裡以「⚪ 缺漏但無法補回」列出；若當下只剩無法補回的項目，整個警告框不出現，改成一行淡色 caption。

**通則：** 監控清單一定要區分「可修復」與「已知且無解」。把無解的項目照樣算進警告數字，使用者兩週後就會學會忽略整個警告框——連帶漏掉真正該處理的那幾項。**警告的價值來自它每次出現都值得行動。**

**仍未涵蓋：** `fetch_ownership()`（外資持股比例）尚未加智慧補齊，也還沒納入本章的缺漏檢查。

**通則：** 這類「保證出事會被看見」的監控，價值不在於它抓到多少問題，而在於**把偵測延遲從「數週（偶然發現）」壓到「當天」**。它不能取代修 bug，但能讓每個 bug 的傷害範圍從「累積數個月」變成「當天發現」。**任何有多條獨立資料管線的系統都該有一個。**
