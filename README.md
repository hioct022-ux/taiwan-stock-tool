# 台股分析工具 — 程式說明

> 版本：v2.1　　最後更新：2026/05

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
| `fetcher.py` | TWSE API 資料抓取（個股、大盤、融資融券、籌碼） |
| `database.py` | SQLite 讀寫封裝 |
| `github_sync.py` | JSON 匯出/匯入、git push、雲端載入 |
| `config.py` | 公開設定（指標參數、路徑、GitHub repo 名稱） |
| `config_local.py` | **本機專屬、不上傳 Git**（Token、IS_LOCAL=True） |
| `config_local.py.example` | 上述檔案的範本 |
| `scheduler.py` | 每日排程主程式 |
| `fetch_daily.py` | 手動執行單次抓取 |
| `run.sh` | 啟動 Streamlit |
| `com.taiwan-stock.fetch.plist` | macOS launchd 自動排程設定 |

---

## 本機 / 雲端模式切換

**判斷機制：** `config_local.py` 只存在本機，其中設定 `IS_LOCAL = True`。雲端沒有此檔案，`IS_LOCAL` 自動為 `False`。

**IS_LOCAL 的作用：**

| 功能 | IS_LOCAL=True（本機） | IS_LOCAL=False（雲端） |
|------|----------------------|----------------------|
| 資料抓取（fetcher） | ✅ 可執行 | ❌ 停用，避免重複呼叫 TWSE |
| 個股詳細頁自動補抓 | ✅ 自動執行 | ❌ 停用 |
| 🚀 更新並同步到雲端 按鈕 | ✅ 顯示 | ❌ 隱藏 |
| 資料來源 | 本機 SQLite | GitHub JSON → 暫時 SQLite |

---

## 資料同步流程（本機→雲端）

1. **本機執行** `fetch_all()` 抓取最新資料（手動或每日 16:30 自動）
2. **按下「🚀 更新並同步到雲端」**，觸發：
   - `export_to_json()` — 將 SQLite 各資料表匯出為 JSON 到 `data/json/`
   - `sync_via_git()` — `git add data/json && git commit && git push`
   - `meta.json` 中的 `exported_at` 時間戳記一併更新
3. **Streamlit Cloud 自動偵測** `exported_at` 變化（透過 `st.cache_resource` key），重新執行 `init_cloud_data()` 匯入最新 JSON

> ⚠️ 若 git push 失敗（如 index.lock 殘留），在 Terminal 手動執行：
> ```bash
> rm -f /Users/chenbingyang/台股分析工具/.git/index.lock
> git -C /Users/chenbingyang/台股分析工具 push
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
- **清空 chips 資料表**（`DELETE FROM chips`）後重新匯入，避免日期解析錯誤殘留的舊資料導致顯示異常
- 匯入 `market_margin.json`、`taiex_daily.json` 等大盤資料表

> ⚠️ `st.cache_resource` 必須定義在**模組頂層**（if 區塊外），否則快取可能不作用，每次重整都重新匯入。

---

## 已知的 TWSE API 注意事項

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
  > ⚠️ 舊版錯誤：`int(date_str[:3]) + 1911` 不判斷長度，西元年 `20260528` 會解析成 `2113-60-52`，導致資料庫寫入錯誤日期。

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
cd /Users/chenbingyang/台股分析工具
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

## 常見問題排查

| 現象 | 原因 | 解法 |
|------|------|------|
| git push 失敗（index.lock） | 上次 git 異常中斷 | `rm .git/index.lock` 後重推 |
| 雲端顯示融資融券為 0 | chips 表有 `2113-xx-xx` 錯誤日期的舊資料 | 已修：`init_cloud_data()` 會先 DELETE FROM chips |
| 雲端資料沒更新 | `cache_resource` 沒重新觸發 | 確認 `meta.json` 的 `exported_at` 有更新 |
| 抓歷史融資融券全部失敗 | TWSE 速率限制 | 改用 2 秒間隔，每次抓 14 天以內 |
| iPad 圖表變形 | Plotly drag 行為 | 已修：全站改用 `show_chart()` |
