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
            'watchlist_tags', 'options_pc'):
    continue
```
**每新增一個大盤層級的 JSON 檔，都必須加到這個 skip 名單**，否則會被誤當成股票代號解析。

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

**股票列表版面（2026-07 改）：** 進場符合、退場警示、觀察中三個區塊均改為 `st.columns([3,1,2])` + `st.button`，點選股票直接跳轉個股分析頁。button key 分別為 `strat_q_{code}`、`strat_d_{code}`、`strat_ob_{code}`（避免同一頁面 key 衝突）。

**雲端可行：** 是。資料來源均為 session_state 快取，無需 IS_LOCAL 分支。

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

Signal 11 後、訊號清單前，計算四項市場應力指標並顯示統一警告框。只要有任一指標觸發（level ≥ 1）就顯示；沒有觸發不佔版面。框的位置：多殺多警告框之後、大盤評分走勢圖之前。

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
IS_LOCAL      = True
GITHUB_TOKEN  = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'  # GitHub Personal Access Token
FINMIND_TOKEN = 'your_finmind_token'  # FinMind API，用於 ETF 成分股
```

---

## 十四、開盤前預判回測說明（backtest.py）

回測使用 Signal 1–8（S9 即時資料無法回測），逐日模擬評分。

**已知偏差：** 在單邊多頭市場，偏空訊號（BIAS 過高、位置偏高）系統性失準（約 42%），這是趨勢性市場的必然現象，訊號設計本身沒有問題。資料累積 6 個月以上、跨越不同市場環境後，統計意義才會提高。

**使用方式：** `python3 backtest.py`，輸出整體準確率、強訊號準確率（|net|≥3）、逐日明細。

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
