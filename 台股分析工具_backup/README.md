# 台股分析工具 — 程式說明

> 版本：v2.3　　最後更新：2026/06

---

## 專案概覽

本機（Mac）執行 Streamlit，每天自動抓取 TWSE 資料存入 SQLite，再透過 Git 把 JSON 同步到 GitHub；Streamlit Cloud 從 GitHub 讀取 JSON 並匯入暫時的 SQLite，提供唯讀的雲端瀏覽介面。

```
本機 (localhost)
  ├── SQLite (data/stock.db)  ←  每日自動抓取
  ├── JSON (data/json/)       ←  從 DB 匯出
  └── git push → GitHub repo
                  ↓
         Streamlit Cloud
           └── 啟動時從 GitHub 讀取 JSON → 匯入暫時 SQLite（唯讀）
```

---

## 檔案結構

| 檔案 | 用途 |
|------|------|
| `app.py` | Streamlit 主程式，所有頁面路由與渲染 |
| `fetcher.py` | TWSE / TPEx / yfinance / TAIFEX 資料抓取 |
| `database.py` | SQLite 讀寫封裝，所有 save_xxx / get_xxx 函式 |
| `github_sync.py` | JSON 匯出/匯入、git push、雲端載入 |
| `indicators.py` | 技術指標計算（MA / RSI / KD / MACD / 布林） |
| `scorer.py` | 個股評分引擎（基本面 + 技術面 + 籌碼面） |
| `backtest.py` | 開盤前預判訊號回測腳本（本機執行，產生準確率統計） |
| `config.py` | 公開設定（指標參數、市值係數、路徑、GitHub repo） |
| `config_local.py` | **本機專屬、不上傳 Git**（Token、IS_LOCAL=True） |
| `config_local.py.example` | 上述檔案的範本 |
| `scheduler.py` | 每日排程主程式 |
| `fetch_daily.py` | 手動執行單次抓取 |
| `run.sh` | 啟動 Streamlit（`bash run.sh` 或右鍵以終端機開啟） |
| `com.taiwan-stock.fetch.plist` | macOS launchd 自動排程設定 |

**頁面功能：**

| 頁面 | 說明 |
|------|------|
| 📊 大盤分析 | 加權指數走勢（含均線）、本益比、台指期法人未平倉、融資融券、三大法人現貨、外部市場、開盤前預判 |
| ⭐ 自選股 | 自選股清單、評分、標籤管理 |
| 🔍 個股查詢 | 任意股票查詢、技術（含均線）/基本面/籌碼分頁，籌碼下方含法人判斷 |
| 🏆 法人排行 | T86 三大法人當日買賣超排行 |
| 📅 除權息 | 未來30天除權息預告與正式公告，含殖利率試算 |
| 📝 個股筆記 | 各股票自訂筆記管理 |

---

## 本機 / 雲端模式切換

**判斷機制：** `config_local.py` 只存在本機，其中設定 `IS_LOCAL = True`。雲端沒有此檔案，`IS_LOCAL` 自動為 `False`。

**IS_LOCAL 的作用：**

| 功能 | IS_LOCAL=True（本機） | IS_LOCAL=False（雲端） |
|------|----------------------|----------------------|
| 資料抓取（fetcher） | ✅ 可執行 | ❌ 停用，避免重複呼叫 TWSE |
| 個股詳細頁自動補抓 | ✅ 自動執行 | ❌ 停用 |
| 🚀 更新並同步到雲端 按鈕 | ✅ 顯示 | ❌ 隱藏 |
| 三大法人現貨彙總來源 | chips 表（1300+ 股彙整） | chips_market_agg 表（從 JSON 匯入） |
| 資料來源 | 本機 SQLite | GitHub JSON → 暫時 SQLite |

---

## 資料同步流程（本機→雲端）

1. **本機執行** `fetch_all()` 抓取最新資料（手動或每日 16:30 自動）
2. **按下「🚀 更新並同步到雲端」**，觸發：
   - `export_to_json()` — 將 SQLite 各資料表匯出為 JSON 到 `data/json/`，含 `chips_market_agg.json`
   - `sync_via_git()` — `git add data/json && git commit && git push`
   - `meta.json` 中的 `exported_at` 時間戳記一併更新
3. **Streamlit Cloud 自動偵測** `exported_at` 變化（透過 `st.cache_resource` key），重新執行 `init_cloud_data()` 匯入最新 JSON

> ⚠️ **程式碼異動（.py 檔）須另外手動推送**，「🚀 同步到雲端」只推資料 JSON：
> ```bash
> cd ~/台股分析工具
> git add app.py database.py github_sync.py backtest.py
> git commit -m "說明更新內容"
> git push
> ```

> ⚠️ 若 git push 失敗（如 index.lock 殘留），在 Terminal 手動執行：
> ```bash
> rm -f ~/台股分析工具/.git/index.lock
> git -C ~/台股分析工具 push
> ```

---

## 雲端初始化機制

雲端版啟動時執行（`app.py` 模組頂層）：

```python
@st.cache_resource
def _init_cloud_cache(version: str):
    from github_sync import init_cloud_data
    init_cloud_data()
    return version

if not IS_LOCAL:
    _init_cloud_cache(_get_meta_version())   # version = meta.json 的 exported_at
```

`init_cloud_data()` 會：
- 從 GitHub raw URL 讀取各 JSON 檔
- **清空 chips 資料表**（`DELETE FROM chips`）後重新匯入，避免舊資料殘留
- 匯入 `market_margin.json`、`TAIEX.json`、`futures_institutional.json`、`market_pe.json`、`exdividend.json` 等大盤資料表
- 匯入 `chips_market_agg.json` 到 `chips_market_agg` 表（供雲端三大法人現貨圖使用）

> ⚠️ `st.cache_resource` 必須定義在**模組頂層**（if 區塊外），否則快取可能不作用，每次重整都重新匯入。

---

## 已知的 TWSE API 注意事項

### 上櫃股（TPEx）資料來源

| 資料類型 | 上市（TWSE） | 上櫃（TPEx） |
|----------|------------|------------|
| 歷史價格 | TWSE STOCK_DAY API | yfinance `XXXX.TWO` |
| 基本面（PE/PB/殖利率） | TWSE BWIBBU_ALL | yfinance `ticker.info` |
| 法人買賣超（籌碼） | TWSE T86 API | ❌ 暫不支援 |
| 融資融券 | TWSE MI_MARGN | ❌ 暫不支援 |

- **自動偵測**：`stocks.market` 欄位記錄 `TWSE` / `TPEx`，由 `fetch_history_auto` / `fetch_fundamentals_auto` 自動路由
- **首次查詢**：個股頁面會自動補抓不足的歷史與基本面資料（每次 session 只補一次）

### T86 法人買賣超 (`fetch_t86`)
- TWSE 在非交易日不更新，程式會從上次最後日期往後逐日查詢（最多查 5 個交易日），找到有效資料為止
- 回傳格式：`shares` 欄位為**張**（已含換算），直接存入

### 融資融券 (`fetch_chips` / `fetch_market_margin`)
- API 日期格式**混用民國年（7碼）和西元年（8碼）**，需分開判斷：
  ```python
  if len(s) == 7 and s[0] == '1':   # 民國年，如 1150528
      return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
  elif len(s) == 8 and s[0] == '2':  # 西元年，如 20260528
      return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
  ```
  > ⚠️ 舊版錯誤：不判斷長度時，西元年 `20260528` 會解析成 `2113-60-52`，導致資料庫寫入錯誤日期。

### 大盤融資融券標籤比對
- API 回傳的 row[0] 標籤要**完全比對**（`==`），不可用 `in`：
  - `融資(交易單位)` → 融資張數（今日餘額 = vals[4]）
  - `融資金額(仟元)` → 融資金額（千元），÷100000 → 億元存入
  - `融券(交易單位)` → 融券張數
  > ⚠️ 若用 `'融資' in label`，`融資金額` 會覆蓋 `融資(交易單位)` 的值

### 歷史批次抓取速率限制
- TWSE 對批次請求有速率限制，連續查詢會回傳空內容（JSON parse error）
- 解決：每筆間隔 **≥ 0.4 秒**（歷史補抓用 `time.sleep(0.4)`）
- 若補抓大量資料，建議改用 2 秒間隔以策安全

---

## 大盤融資融券歷史補抓

目前每日自動抓取當天資料，若需補抓歷史，在 Terminal 執行：

```bash
cd ~/台股分析工具
python3 -c "from fetcher import fetch_market_margin_history; fetch_market_margin_history(months=4)"
```

- 預設跳過已有的日期，不重複抓取
- 補完後記得按「🚀 更新並同步到雲端」同步到 GitHub

---

## Plotly 圖表 Touch 變形防護

iPad / 手機觸控時，Plotly 預設的 drag 行為會造成圖表變形。已在全站統一套用：

```python
_CHART_CONFIG = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}

def show_chart(fig, key=None):
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CONFIG, key=key)
```

所有 Plotly 圖表一律呼叫 `show_chart()` 取代 `st.plotly_chart()`。

---

## 本機設定（config_local.py）

```python
# config_local.py — 此檔不上傳 Git
IS_LOCAL      = True
GITHUB_TOKEN  = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
FINMIND_TOKEN = 'your_finmind_token'  # 用於 ETF 持股資料
```

---

## 自動排程（macOS launchd）

- plist 路徑：`~/Library/LaunchAgents/com.taiwan-stock.fetch.plist`
- 執行時間：每日 **16:30**（台股收盤後約 3 小時，TWSE API 確保已更新）
- 安裝指令：`bash install_autostart.sh`
- 查看 log：`cat /tmp/taiwan-stock-fetch.log`

---

## 大盤分析功能說明

### 外部市場（即時，每 15 分鐘更新）

使用 yfinance 即時抓取，分兩列顯示：

**第一列 — 股市指數（納入開盤前預判評分）：**

| 指標 | Ticker | 說明 |
|------|--------|------|
| S&P 500 | `^GSPC` | 美股大盤 |
| Nasdaq | `^IXIC` | 那斯達克 |
| 費半 SOX | `^SOX` | 費城半導體指數，台灣半導體相關性極高 |
| TSM ADR | `TSM` | 台積電美國存託憑證，領先台股台積電走勢 |
| VIX | `^VIX` | 恐慌指數，> 20 警戒，> 30 恐慌 |

**第二列 — 總經指標（僅供參考，不計入評分）：**

| 指標 | Ticker | 說明 |
|------|--------|------|
| WTI 原油 | `CL=F` | 油價大漲 → 通膨預期 → 升息壓力 |
| 黃金 | `GC=F` | 黃金大漲 → 避險情緒升溫（類似 VIX） |
| 美元指數 | `DX-Y.NYB` | 強美元 → 外資流出新興市場壓力 |

---

### 開盤前預判（Signal 1–9）

每日根據前一日資料計算 9 個訊號，累積偏多分（bull）和偏空分（bear），以 net = bear - bull 判斷方向。設計目標是**每個正常交易日都能給出有意義的方向參考**，不限於危機模式才觸發。

| 訊號 | 來源資料 | 說明 |
|------|----------|------|
| S1 TAIEX 昨日漲跌 | prices 表 | 昨日漲跌幅；±0.3% 弱訊、±1% 中訊、±2% 強訊 |
| S2 融資5日趨勢 | market_margin 表 | 5日融資餘額變化率；增加偏空（槓桿過熱），減少偏多 |
| S3 外資期貨日變化 + 5日趨勢 | futures_institutional 表 | 外資期貨**日增減口數**（非絕對口數）；±1k 弱、±3k 強 |
| S4 T86 外資現貨 | t86_ranking 表 / chips_market_agg 表 | 全市場外資現貨買賣超加總；±1萬張弱、±5萬中、±15萬強；投信±5萬輔助 |
| S5 BIAS5 / BIAS20 | prices（計算） | 5日乖離 ±2%/±5%；20日乖離 ±8% |
| S6 年線位置 | prices（計算） | 相對250日高低位置；≥90% 高估偏空，≤25% 低估偏多 |
| S7 MA多空排列 | prices（計算） | MA5 > MA20 > MA60 判多頭，反之空頭 |
| S8 成交量趨勢 | prices 表 | 近3日均量 vs 前期均量；量縮 -15% 偏空、量增 +20% 偏多 |
| S9 外部市場 | yfinance 即時 | S&P、Nasdaq、費半 SOX、TSM ADR、VIX（總經指標不計入評分） |

**評分閾值：**

| net 值 | 判斷 |
|--------|------|
| ≤ -6 | 🟢 強烈偏多 |
| -3 ~ -6 | 🟢 偏多 |
| -1 ~ -3 | 🟢 小幅偏多 |
| 0 | ⚪ 中性 |
| +1 ~ +3 | 🔴 小幅偏空 |
| +3 ~ +6 | 🔴 偏空 |
| ≥ +6 | 🔴 強烈偏空 |

> ⚠️ 外部市場訊號（S9）包含即時資料，是目前最強的先行指標，但無法回測。
> 回測結果（66天）：整體方向準確率 50%，強訊號（|net| ≥ 3）為 57%，偏多 61%，偏空 42%（在多頭趨勢下偏空訊號失效）。

---

### 大盤走勢圖

加權指數走勢（上）＋成交量柱狀圖（下）的雙子圖，含 **MA5 / MA20 / MA60 均線**（橘/紫/綠）及布林通道。成交量漲紅跌綠，圖下方附量能判斷文字（與 20 日均量比較，並判斷 5 日趨勢）。

---

### 三大法人現貨買賣超圖

顯示近 20 日外資、投信、自營商每日現貨買賣超（億元），分兩子圖：

- **上圖**：外資 / 投信 / 自營商各自的每日柱狀圖（固定顏色：外資=橘、投信=藍、自營商=紫），正值=買超、負值=賣超
- **下圖**：三大法人合計買賣超柱狀圖 + 7 日移動平均線

圖下方附法人籌碼判斷文字，以外資 5 日合計 ±500 億和 ±2,000 億為閾值判斷方向。

**本機 vs 雲端資料來源差異：**
- 本機：從 `chips` 表彙整全市場（1300+ 檔股票），使用 `get_chips_market_aggregate()`，需 `HAVING stock_count >= 500` 過濾不完整日期
- 雲端：從 `chips_market_agg` 表讀取（由本機匯出的預計算彙整值），使用 `get_chips_market_agg_from_table()`

---

### 大盤本益比

每日從 TWSE `BWIBBU_ALL` 個股資料計算**市場中位數 PE / PB / 殖利率**，排除負值與異常值（PE > 200）後取中位數。資料存入 `market_pe` 表，隨每日更新累積歷史，並繪製歷史線圖附 14 / 18 / 22 參考線。

| PE 範圍 | 評估 |
|---------|------|
| < 14 | 歷史低估區，具長期投資吸引力 |
| 14–18 | 合理估值 |
| 18–22 | 偏高，需留意獲利支撐 |
| > 22 | 高估，歷史高位，保守應對 |

---

### 台指期三大法人未平倉

資料來源：台灣期貨交易所（TAIFEX）CSV 下載，Big5 解碼。因 API 單次查詢限 30 天，以逐月分批方式補抓歷史。顯示外資 / 投信 / 自營商淨多單口數折線圖，正值偏多、負值偏空。

> ⚠️ 外資期貨絕對口數（如 -7 萬口）代表長期結構性避險部位，不等於方向性訊號。開盤前預判使用**日變化量**（±1k/±3k）而非絕對口數。

---

### 大盤融資融券

大盤融資餘額 / 融券餘額走勢圖，附近 120 日相對位置判斷。

---

## 📋 大盤籌碼總判斷說明

大盤籌碼總判斷以三個信號加總評分，反映當前市場籌碼風險：

### Signal 1 — 融資佔市值比

用當日指數估算台股總市值（`市值 = 收盤指數 × TWSE_CAP_COEF`），計算融資餘額佔比。歷史上大跌前融資都會過熱：

| 佔比 | 評估 | 分數 |
|------|------|------|
| < 0.85% | ✅ 健康，尚未過熱 | +1 |
| 0.85–1.0% | 🟡 偏高，留意變化 | 0 |
| 1.0–1.2% | ⚠️ 接近警戒（歷史高點前兆） | -1 |
| > 1.2% | ⛔ 危險（2007、2021高點水準） | -2 |

### Signal 2 — 融資5日趨勢 + 季線位置

捕捉「主力是否在出逃」的訊號：

| 狀況 | 評估 | 分數 |
|------|------|------|
| 季線以上，融資變化正常 | ✅ 多頭格局 | +1 |
| 融資單週暴增 ≥ 300億 | ⚠️ 散戶過度槓桿 | -1 |
| 融資單週暴增 ≥ 300億 且跌破季線 | ⛔ 逆勢加碼高風險 | -2 |
| 融資5日大減 ≥ 200億 且跌破季線 | ⛔ 斷頭訊號，崩盤前兆 | -2 |
| 融資5日減少 ≥ 100億 且跌破季線 | ⚠️ 籌碼鬆動 | -1 |

### Signal 3 — 券資比（融券 ÷ 融資）

代表空方保護墊厚薄，空單多表示有軋空助漲的潛力：

| 券資比 | 評估 | 分數 |
|--------|------|------|
| ≥ 10% | ✅ 空單多，反彈易軋空 | +1 |
| 5–10% | ✅ 籌碼結構健康 | +1 |
| 2.5–5% | ⚪ 中性 | 0 |
| < 2.5% | ⚠️ 軋空保護薄，多頭動能弱 | -1 |

### 總分結論

| 總分 | 結論 |
|------|------|
| ≥ +2 | 🟢 整體健康，可積極參與 |
| +1 | 🟢 偏多，留意個別警示 |
| 0 | 🟡 中性觀望，降低持股比重 |
| -1 | 🟡 偏空謹慎，保守操作，設好停損 |
| ≤ -2 | 🔴 高度警戒，建議大幅減碼，優先保本 |

### 市值校準係數維護

市值以「指數點位 × 校準係數」每日自動估算，不需固定常數，每 6～12 個月校準一次：

1. 至 [TWSE 市場資訊](https://www.twse.com.tw/zh/statistics/statisticsReport/marketInformation.html) 查最新上市總市值
2. 計算：`TWSE_CAP_COEF = 最新市值（億）÷ 當日指數收盤`
3. 更新 `config.py` 的 `TWSE_CAP_COEF` 及 `TWSE_CAP_CALIBRATED`（填今天日期）
4. 超過 `TWSE_CAP_WARN_DAYS`（預設365天）未校準，App 會自動顯示提醒

---

## 個股籌碼判斷

個股籌碼頁面圖表下方附法人籌碼判斷，以近 20 日資料計算：

| 指標 | 輕微閾值 | 明顯閾值 |
|------|---------|---------|
| 外資近5日合計買賣超 | ±1,000 張 | ±5,000 張 |
| 外資近20日合計 | ±300 張 | ±1,000 張 |
| 投信近5日合計 | ±100 張 | ±500 張 |
| 自營商近5日合計 | ±100 張 | ±300 張 |

最終依外資 5 日合計給出個股法人方向判斷（±1,000 張偏多/偏空，±5,000 張強烈多/空）。

---

## 開盤前預判回測（backtest.py）

```bash
cd ~/台股分析工具
python3 backtest.py
```

使用本機歷史資料逐日模擬 Signal 1–8（S9 外部市場因需即時資料無法回測），輸出：

- 整體準確率、有方向預判準確率、強訊號（|net| ≥ 3）準確率
- 偏多 / 偏空方向各自準確率
- 逐日明細（最後20天）

**已知限制：** 回測期間若為單邊多頭，偏空訊號會系統性失準（42%），這是趨勢性市場的必然現象，不代表訊號邏輯有誤。資料累積半年以上後，涵蓋不同市場環境，統計意義才會提高。

---

## 自行修改指南

### 想調整判斷閾值或指標參數

**改 `config.py`**，不需要動其他檔案。

| 要改的項目 | 對應變數 |
|-----------|---------|
| 均線週期（MA5 / MA20 / MA60） | `MA_SHORT` / `MA_MID` / `MA_LONG` |
| RSI 計算週期 | `RSI_PERIOD` |
| 大盤籌碼總判斷 — 融資警戒比例 | `MARGIN_RATIO_WARNING` / `MARGIN_RATIO_DANGER` |
| 市值校準係數 | `TWSE_CAP_COEF` / `TWSE_CAP_CALIBRATED` |
| 評分權重（基本面/技術面/籌碼面） | `WEIGHT_FUNDAMENTAL` / `WEIGHT_TECHNICAL` / `WEIGHT_CHIPS` |
| 每日自動抓資料時間 | `AUTO_FETCH_HOUR` / `AUTO_FETCH_MINUTE` |

---

### 想調整開盤前預判訊號閾值

**改 `app.py`** 的 `render_market()` 函式，搜尋 `Signal 1` 到 `Signal 9`，每段有清楚的閾值數字可調整。Signal 9 的外部市場評分邏輯也在此處。

---

### 想新增一個資料欄位

以「新增一個新的大盤指標」為例，需要依序改四個檔案：

**1. `database.py`**
- 在 `init_db()` 裡新增 `CREATE TABLE IF NOT EXISTS` 或 `ALTER TABLE ADD COLUMN`
- 新增對應的 `save_xxx()` 和 `get_xxx()` 函式

**2. `fetcher.py`**
- 新增 `fetch_xxx()` 函式，負責呼叫 API 並存入 DB
- 在 `fetch_all()` 末端加入呼叫

**3. `github_sync.py`**
- 在 `export_to_json()` 加入匯出新資料為 JSON
- 在 `init_cloud_data()` 加入從 JSON 匯入到雲端 DB
- 在 `init_cloud_data()` 的個股 code 迴圈 skip 名單中加入新的 JSON 檔名（避免被誤認為股票代號）

**4. `app.py`**
- 在對應的 `render_xxx()` 函式裡加入顯示邏輯

---

### 想新增一個頁面

**改 `app.py`**：

1. 新增一個 `render_新頁面()` 函式
2. 在側邊欄按鈕區加入新按鈕（搜尋 `st.sidebar` 的按鈕區塊）
3. 在 `main()` 的路由邏輯加入對應判斷

```python
# 側邊欄加按鈕
if st.sidebar.button('新頁面'):
    st.session_state['page'] = 'new_page'

# main() 路由加判斷
elif page == 'new_page':
    render_新頁面()
```

---

### 想新增一支自選股要追蹤的 API

**改 `fetcher.py`** 的 `fetch_all()` 裡自選股補抓迴圈（搜尋 `for w in watchlist`），在迴圈內加入新的資料抓取邏輯。

---

## 資料庫表格速查

| 表名 | 內容 | 主鍵 |
|------|------|------|
| `prices` | 個股及TAIEX日線價格 | (code, date) |
| `fundamentals` | 個股基本面（PE/PB/殖利率/EPS） | (code, date) |
| `chips` | 三大法人買賣超（個股） | (code, date) |
| `chips_market_agg` | 三大法人買賣超**全市場彙整**（日加總，供雲端使用） | date |
| `margin` | 個股融資融券 | (code, date) |
| `market_margin` | 大盤融資融券彙總 | date |
| `market_pe` | 大盤本益比（中位數） | date |
| `futures_institutional` | 台指期三大法人未平倉 | date |
| `exdividend` | 除權息資料 | (code, exdividend_date) |
| `stocks` | 股票基本資料（代號/名稱/市場） | code |
| `watchlist` | 自選股清單 | code |
| `t86_ranking` | 三大法人買賣超排行（單日前50名） | (date, code) |
| `etf_holdings` | ETF 成分股 | (etf_code, stock_code) |

---

## 查詢資料庫內容（Terminal）

```bash
cd ~/台股分析工具

# 查最新大盤本益比
python3 -c "from database import get_market_pe; rows=get_market_pe(5); [print(r) for r in rows]"

# 查台指期未平倉最新資料
python3 -c "from database import get_futures_institutional; rows=get_futures_institutional(5); [print(r) for r in rows]"

# 查某支股票最新價格
python3 -c "from database import get_prices; rows=get_prices('2330',5); [print(r) for r in rows]"

# 查三大法人全市場彙整（雲端用資料表）
python3 -c "from database import get_chips_market_agg_from_table; rows=get_chips_market_agg_from_table(5); [print(r) for r in rows]"

# 直接用 SQLite 瀏覽
sqlite3 data/stock.db ".tables"
sqlite3 data/stock.db "SELECT * FROM chips_market_agg ORDER BY date DESC LIMIT 10;"
```

---

## 手動補抓歷史資料

```bash
cd ~/台股分析工具

# 補抓大盤融資融券歷史（月數）
python3 -c "from fetcher import fetch_market_margin_history; fetch_market_margin_history(months=4)"

# 補抓台指期未平倉歷史（TAIFEX 每次限30天，逐月分批）
python3 -c "from fetcher import fetch_futures_institutional_history; fetch_futures_institutional_history(months=3)"

# 補抓大盤本益比（每日累積，無法補歷史，只抓今日）
python3 -c "from fetcher import fetch_market_pe; fetch_market_pe()"

# 補抓某支個股歷史價格
python3 -c "from fetcher import fetch_history; fetch_history('2330', months=6)"

# 強制重新抓今日所有資料
python3 -c "from fetcher import fetch_all; fetch_all()"

# 初始化資料庫（新增資料表後首次執行）
python3 -c "from database import init_db; init_db()"

# 執行開盤前預判回測
python3 backtest.py
```

---

## 常見問題排查

| 現象 | 原因 | 解法 |
|------|------|------|
| git push 失敗（index.lock） | 上次 git 異常中斷 | `rm .git/index.lock` 後重推 |
| 雲端顯示融資融券為 0 | chips 表有錯誤日期的舊資料 | 已修：`init_cloud_data()` 會先 DELETE FROM chips |
| 雲端資料沒更新 | `cache_resource` 沒重新觸發 | 確認 `meta.json` 的 `exported_at` 有更新 |
| 雲端新資料表沒有資料 | 程式碼異動未推送，或 JSON 未匯出 | 先 `git add *.py && git push`，再按「🚀 同步到雲端」 |
| 雲端三大法人現貨圖無資料 | `chips_market_agg.json` 未匯出或未在 skip 名單 | 確認 `github_sync.py` 有匯出此 JSON；skip 名單含 `'chips_market_agg'` |
| 三大法人現貨圖顯示幾年前資料 | chips 表舊資料（2017年起）股票數量太少未被 HAVING 過濾 | 已修：加入 `WHERE date >= date('now', '-{days*2} days')` 先過濾日期範圍 |
| 抓歷史融資融券全部失敗 | TWSE 速率限制 | 改用 2 秒間隔，每次抓 14 天以內 |
| TAIFEX 台指期抓取失敗（garbled 亂碼） | Big5 編碼問題 | 已修：用 `r.content.decode('big5', errors='ignore')` |
| TAIFEX 單次查詢 30 天以上回傳 HTML | API 限制 | 已修：`fetch_futures_institutional_history` 逐月分批 |
| 大盤本益比無歷史資料 | BWIBBU_ALL 不支援歷史查詢 | 正常，每日自動累積，無法補抓過去資料 |
| iPad 圖表變形 | Plotly drag 行為 | 已修：全站改用 `show_chart()` |
| 市值估算提示需校準 | `TWSE_CAP_CALIBRATED` 超過 365 天 | 查 TWSE 最新市值，更新 `config.py` 的 `TWSE_CAP_COEF` |
| 外部市場資料抓不到 | Yahoo Finance 連線逾時 | 15 分鐘快取，重整後自動重試；偶發性正常 |
| 開盤前預判偏空準確率偏低 | 資料累積期為多頭趨勢，逆勢訊號系統性失準 | 正常現象，累積6個月以上跨越不同市場環境後準確率會改善 |
