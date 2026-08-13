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

get_chips_market_aggregate(days: int = 60, min_stocks: int = 500) -> list[dict]
# 本機使用：從 chips 表彙整全市場，HAVING COUNT(*) >= min_stocks 過濾不完整日期
# 必須加 WHERE date >= date('now', '-{days*2} days') 否則會撈出 2017 年老資料
# key：date, stock_count, foreign_net, trust_net, dealer_net
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
| `{stock_code}.json` | `{'code', prices, fundamentals, chips, ownership, 'exported_at'}` |

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
- 用 `st.number_input` 讓用戶自行調整各情境 PE 與 EPS
- 計算 `val = pe × eps` 並顯示現價相對估值的漲跌幅
- 長條圖 + 紫色虛線（現價）對比三情境
- EPS ≤ 0 時不顯示估值區間（PE 法不適用）

**注意：** widget key 為 `f'pe_bear_{code}'` 等，帶入股票代號避免多股同時渲染衝突。

### _check_consolidation_pattern(prices) — 量縮整理型態掃描（2026-07 新增）

定義在模組頂層（`_CHART_CONFIG` 上方）。自選股側邊欄每支股票渲染時呼叫，符合條件者在按鈕標籤前顯示 🎯。

**三個條件同時成立才回傳 True：**
1. 今日收盤 > MA20（月線之上）
2. 近 3 日成交量均低於 20 日均量（量縮）
3. 近 3 日低點不破底（`low[1] >= low[0]` 且 `low[2] >= low[1]`）

**資料來源：** `get_prices(code, days=25)`（側邊欄渲染時已取 25 天，共用同一份資料）

**篩選入口：** 自選股清單篩選列「🎯 整理」選項，點選後只顯示符合的股票。

**注意：** 第四個條件（主力券商買超）刻意不實作，因資料來源（券商分點）不在現有系統內。

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

### render_strategy() — 投資策略頁（2026-06 新增）

路由值：`'strategy'`，側邊欄按鈕「💡 投資策略」觸發。

**功能：**
- 從 `st.session_state` 讀取 `_market_ms`、`_market_net`（需先進過大盤分析頁）
- 依大盤評分決定個股建議門檻（≥70→65分、55–69→70分、45–54→75分、<45→停止進場）
- 重用 `_wl_scores` 快取（自選股評分），列出符合門檻的個股
- 退場警示：持有中個股若評分 <45 顯示紅色警告、45–54 顯示橘色注意
- 靜態策略說明：進場條件、持有管理（10日 + 到期續抱）、資金配置

**股票列表版面（2026-07 改）：** 進場符合、退場警示、觀察中三個區塊均改為 `st.columns` + `st.button`，點選股票直接跳轉個股分析頁。button key 分別為 `strat_q_{code}`、`strat_d_{code}`、`strat_ob_{code}`（避免同一頁面 key 衝突）。

**參考停損價欄位（2026-07 新增，空頭回測後補強）：** 進場符合清單改為 4 欄 `[3,1,1.6,1.4]`（股票/評分/參考停損價/標籤）。停損價 = 最新收盤 ×0.92，紅色顯示，旁附現價。內部函式 `_latest_close_for(code)`：IS_LOCAL 走 `get_prices(code, days=1)`，雲端走 `_read_stock_json()`。caption 明確指示「買進當日立即在券商 App 預掛停損單」——因為工具是盤後資料 + 隔日才能動作，評分類退場警訊天生延遲 2–3 天，唯有價格觸發的預掛停損單能即時出場。

**大盤轉空全面減碼警報（2026-07 新增，策略 D 邏輯）：** 大盤評分卡下方，依 `_market_net` 顯示兩級警報：
- `net >= 4`：紅色警報「全面減碼或出場」，引用空頭回測數據（D 平均 -1.84% vs C -4.52%）
- `net >= 2`：橘色警報「開始減碼」，提醒確認停損單已掛
設計依據：系統性下跌時個股齊跌，個股評分警訊必然落後；大盤層級訊號比個股評分早 1–2 天，且策略 D 的空頭回測驗證了「大盤轉空即出場」的優勢。此警報不改變評分/回測邏輯，純顯示層。

**雲端可行：** 是。資料來源均為 session_state 快取，無需 IS_LOCAL 分支（停損價欄位除外，該欄位兩種模式均支援）。

**注意：** `_wl_scores` 在大盤分析或自選股頁計算後會存入 session_state；若直接進投資策略頁，此快取可能不存在，需提示用戶先進自選股頁。

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

**中途發現的資料問題（未修復，僅繞開）：** 驗證過程中發現 DB 的 `change_pct` 欄位在約 4.7%（7,095/150,332）的價格列上被誤存為 `0.0`，即使當日 `close` 實際上與前一日不同。範圍橫跨 1,496 檔股票、2025-03 至 2026-08 全時間段（非單次批次匯入造成），根本原因未查。因此波動度計算刻意不依賴 `change_pct`，改由 `close` 價格逐日反推報酬率（見下方 `indicators.py` 說明），此問題已記錄於「已知陷阱」第 35 則，尚待日後排查 `fetcher.py` 寫入路徑。

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

**通則：** 外部 API 呼叫如果用 `except Exception: return {}` 這種寬鬆的錯誤處理，會讓「額度用完」「token失效」「單純網路慢」在畫面上呈現一模一樣的「資料不見了」，難以排查。建議搭配一個診斷腳本（印出原始 HTTP 狀態碼與錯誤訊息）放在專案裡備用，遇到類似「怎麼突然不見了」的回報時可以直接請使用者執行、貼結果回來，不用臆測。

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

### 掃描功能

```bash
python3 backtest_stocks.py        # A/B/C/D 四策略比較
python3 backtest_stocks.py scan   # 持有天數掃描（3/5/7/10/15/20 日）
python3 backtest_stocks.py trail  # 移動停利掃描（None/3%/5%/8%）
```

**持有天數掃描結論：** 10 日有最佳勝率；20 日 EV 最高但多頭偏差大。採用 10 日。  
**移動停利掃描結論：** 多頭市場中移動停利均劣於無停利。不採用。

### 空頭段驗證（2026-07-28 執行，僅統計 7/14 後進場的交易）

| 策略 | 進場筆數 | 平均損益 | 停損筆數 | 備註 |
|------|---------|---------|---------|------|
| A（無過濾） | 25 | -4.91% | 9 | |
| B（大盤過濾） | 16 | -4.38% | 3 | 擋掉 18 筆（被擋交易平均虧 -4.21%），過濾有效 |
| C（現行採用） | 13 | -4.52% | 2 | |
| **D（大盤轉空提前出場）** | **25** | **-1.84%** | 5 | 20 筆靠大盤訊號提前出場（net≥+4）|

**核心發現：** 策略 D 在多頭回測墊底（51.1% 勝率，被 C 淘汰），但在空頭段大幅勝出——「大盤轉空提前出場」在多頭是錯殺、在空頭是保命。這是環境依賴的典型案例。

**待決策（樣本不足暫緩）：** 混合策略構想——多頭用 C（續抱吃波段）、大盤評分轉弱時切換 D 的提前出場邏輯。目前空頭樣本僅 2 週 / 25 筆，不足以定案。**待空頭資料累積 1–2 個月後重跑本節回測，若 D 優勢持續再實作。**

**回測執行注意（sandbox 環境）：** 直接對掛載目錄跑回測極慢（FUSE + SQLite），需先把 `*.py` + `data/stock.db` 複製到本地暫存目錄再跑。`backtest_stocks.py` 全程約 60–80 秒，若環境有單次執行時間上限，可用 wrapper 腳本逐一執行策略（`_build_market_signals()` + `_run_backtest(...)` 各策略獨立呼叫，結果 pickle 存檔後彙整）。

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

**`_position_status()` 優先序（重要）：** 停損 🔴 ＞ 大盤轉空 📉（net≥+4）＞ 到期 ⏰ ＞ 接近停損 ⚠️（≤停損×1.02）＞ 持有中 🟢。大盤轉空排在到期之前，因為空頭回測顯示大盤層級訊號比個股訊號更早也更有效。

### UI 位置

| 區塊 | 位置 | 功能 |
|------|------|------|
| 側邊欄「📌 持倉觀察」 | 自選股清單**之上** | 只顯示（旗標／天數／毛淨損益／停損價），不放操作按鈕（空間有限） |
| 進場登錄 | 投資策略頁「符合進場條件」清單第 5 欄 📌 | 點擊展開表單，代號/名稱/進場價（預設最新收盤）/股數/停損價（×0.92）預填 |
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

**續抱機制（策略 C）：** `renew_position()` 把 `entry_date` 重設為今天並 `renew_count +1`，天數重新起算 10 日。注意這會讓「進場日」欄位變成「本輪起算日」，原始進場日不保留——若未來需要完整持有期分析，要改成另存 `original_entry_date` 欄位。

**到期建議來源：** 讀 `st.session_state['_wl_scores']`（自選股頁計算的評分快取）。若使用者沒先進過自選股頁，建議文字會顯示「請先計算評分」而不是給錯誤建議。

**零股支援：** `shares` 欄位以「股」為單位（1 張 = 1000 股），表單預設 1000 但可填任意值。淨損益計算會套用 `FEE_MIN` 低消，小額零股交易的成本比例明顯較高（實測：10 股台積電來回成本約佔 0.65%，100 股約 0.49%，1000 股整張則降到 0.4% 以下）。

**毛/淨損益的用途區隔：** 毛損益（純價差）與 `backtest_stocks.py` 的回測基準同基礎，可直接對照；淨損益是實際入袋金額。歷史紀錄區兩者都顯示，避免拿淨損益去跟回測數字比較而誤判策略失效。

### 分批獨立追蹤與策略驗證（2026-07 補強）

**同股多筆（分批 / 加碼）：** 刻意**不採用先進先出或加權平均**，改為「每次進場各自一筆」。理由：策略 C 的核心是每筆各自持有 10 個交易日、各自設停損；若合併成一筆，7/20 買的到期了但 7/28 加碼的才第 3 天，無法判斷出場，停損價也只剩一個平均值，與券商實際掛的多張停損單對不起來。

- `get_positions_by_code(code, status)` 回傳該檔全部持倉；`get_position_by_code()` 只回最新一筆（保留舊呼叫相容）
- 符合清單的 📌 按鈕在已持有時顯示 `📌N`（N=已持有筆數），仍可再按 = 加碼
- 退場警示列的 📤 在多筆時預設帶出**最早一筆**（先進先出精神），其餘至持倉管理區逐筆處理

**進場評分記錄（策略驗證的關鍵）：** `entry_score`（個股評分）與 `entry_ms`（大盤評分）在按 📌 時自動由 `sc` 與 `st.session_state['_market_ms']` 帶入。沒有這兩欄就無法回答「65 分門檻有沒有用」「大盤評分高時進場是否真的較好」——這正是整套策略的核心假設。

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

**金鑰存放：** `POSITIONS_ENC_KEY` 本機存在 `config_local.py`（不上傳 Git），雲端存在 Streamlit Cloud 的 Secrets，兩邊要完全一致，否則雲端解密會直接噴例外（`_decrypt_json` 沒有 try/except，錯誤金鑰產生的 bytes 通常不是合法 JSON，`json.loads` 會丟 `JSONDecodeError`，外層 `init_cloud_data()` 的 try/except 會吞掉並印「持倉部位匯入失敗」，畫面上就是雲端持倉區塊沒有資料——排查時先確認這把金鑰兩邊有沒有貼一致）。`_get_positions_enc_key()` 統一處理「雲端讀 `st.secrets`、本機讀 `config.py`（來自 `config_local.py`）」的分支，其他程式碼不用關心來源。

**密碼關卡（`app.py` `_positions_unlocked()`）：** 本機一律回傳 `True`（自己的電腦不需要密碼）；雲端檢查 `st.session_state['_pos_unlocked']`，沒解鎖就在側邊欄畫一個密碼輸入框，`POSITIONS_PASSWORD` 沒設定時直接回傳 `False` 且不顯示任何輸入框（保守預設：沒設密碼視同還沒準備好，不會意外曝光）。呼叫端寫法：`if IS_LOCAL or _positions_unlocked():`——`IS_LOCAL` 為真時靠短路求值直接跳過函式呼叫，本機完全不受這段邏輯影響。

**資料流（`export_to_json()` → `init_cloud_data()`）：**
1. 本機 `export_to_json()`：`SYNC_POSITIONS_TO_CLOUD=True` 且 `POSITIONS_ENC_KEY` 有值時，才把 `get_positions(None)`（全部，含 holding 與 closed）加密寫入 `positions.json`，格式 `{'enc': <密文>, 'exported_at': ...}`；金鑰未設定時直接跳過匯出並印警告，不會意外寫出明文。
2. 雲端 `init_cloud_data()`：讀到 `positions.json` 後解密、呼叫 `database.import_positions(rows)` 整批覆寫雲端暫存 DB 的 `positions` 表（先 `DELETE FROM positions` 再逐筆 `INSERT`，保留原始 `id`）。
3. `positions` 已加入個股 JSON 迴圈的 skip 名單，避免被誤判成股票代號。

**`database.py` 新函式：** `import_positions(rows)`——雲端唯讀匯入專用，本機端不應呼叫（本機一律用 `add_position` 等既有 CRUD 函式）。

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

**排查：** 直接查該股當期 `close` 序列（例如 6274：257.44→256.45→251.49→259.42…），收盤價逐日確實在變動，但同期 `change`／`change_pct` 卻是字面上的 `0.0`。確認是資料寫入錯誤，不是市場真的沒有變化。

**規模：** 全表掃描後，`prices` 表約 **7,095 / 150,332 筆（4.7%）**受影響，涵蓋 **1,496 檔股票**，時間分布平均橫跨 2025-03 至 2026-08 全區間（不是單次批次匯入造成的一次性瑕疵，較可能是某條抓取路徑持續性地在特定情況下漏算）。根本原因（是哪個 `fetcher.py` 路徑、什麼條件觸發）**尚未查明**。

**目前處置（繞開，非修復）：** 任何需要「日報酬率」的新計算一律**不信任 `change_pct` 欄位**，改由 `close` 價格逐日反推：`(close_today - close_yesterday) / close_yesterday * 100`。`indicators.py` 新增的 `vol20`（見四、database.py 章節下方 indicators 說明）即採此作法，程式內有對應註解。

**尚待辦：** 這則只是記錄發現，**尚未排查 `fetcher.py` 寫入 `change`/`change_pct` 的邏輯**、也**尚未回填既有錯誤資料**。日後若有人要處理，建議：
1. 先確認受影響筆數是否還在增加（如果新抓的資料也中招，代表 bug 還活著，要優先修 `fetcher.py`；如果只在舊資料，回填一次即可）
2. 全表掃描邏輯：`SELECT code, date FROM prices WHERE change_pct = 0` 再逐筆比對前一日 `close` 是否真的相同，排除真正平盤的正常案例
3. 回填時比照陷阱 27／33 的模式寫一次性腳本，而不是手動改 DB

**通則：** 涉及「報酬率／漲跌幅」的欄位，若該欄位是**寫入時計算好存起來**（而非用時現算），要對「是否可能存在計算失敗但仍寫入預設值 0」保持警覺——0 在這類欄位常常是「正常收盤持平」與「計算錯誤」兩種情況的疊加，光看數值分不出來，只能對照原始價格資料交叉驗證。

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

**排查：** 用 `GIT_CURL_VERBOSE=1 git push` 確認連線、認證都正常（object 有成功上傳），問題出在 GitHub 收到 push 之後、處理 receive-pack 這一步。改用 `git fsck --full` 檢查本機倉庫完整性，發現兩個問題：
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
