# ════════════════════════════════════════
# config.py　設定檔
# 所有可調整的參數都在這裡
# 程式其他部分不需要修改，只改這裡就好
# ════════════════════════════════════════

import os

# ── 資料庫設定 ──────────────────────────
# 使用 config.py 所在目錄為基準，本機和雲端（Streamlit Cloud）都相容
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'stock.db')
JSON_DIR = os.path.join(BASE_DIR, 'data', 'json')

# ── GitHub 設定 ──────────────────────────
# Token 從本機 config_local.py 讀取（安全，不會上傳到 GitHub）
# 請依照說明建立 config_local.py，不要直接填在這裡
try:
    from config_local import GITHUB_TOKEN as _GH_TOKEN
    GITHUB_TOKEN = _GH_TOKEN
except ImportError:
    GITHUB_TOKEN = ''

# ── FinMind API Token ─────────────────────
# 免費註冊取得：https://finmindtrade.com/analysis/#/Authsign/register
# 用於抓取 ETF 成分股資料
# 請在 config_local.py 加入：FINMIND_TOKEN = "your_token"
try:
    from config_local import FINMIND_TOKEN as _FM_TOKEN
    FINMIND_TOKEN = _FM_TOKEN
except ImportError:
    FINMIND_TOKEN = ''

GITHUB_REPO   = 'hioct022-ux/taiwan-stock-tool'
GITHUB_BRANCH = 'main'

# ── 自動排程設定 ─────────────────────────
# 每天幾點自動抓資料（24小時制）
# 台股收盤 13:30，TWSE API 實際更新時間約 16:00～16:30
# 設定 16:30 確保資料已發布，避免抓到前一交易日資料
AUTO_FETCH_HOUR   = 16
AUTO_FETCH_MINUTE = 30

# ── 資料設定 ────────────────────────────
# 歷史資料保留天數
HISTORY_DAYS = 400        # 約1.5年，足夠計算所有指標

# 技術指標參數
MA_SHORT  = 5             # 短期均線
MA_MID    = 20            # 中期均線
MA_LONG   = 60            # 長期均線
RSI_PERIOD = 14
KD_PERIOD  = 9
MACD_FAST  = 12
MACD_SLOW  = 26
MACD_SIGNAL = 9
BBAND_PERIOD = 20
BBAND_STD    = 2

# ── 評分權重 ────────────────────────────
WEIGHT_FUNDAMENTAL = 0.40   # 基本面 40%
WEIGHT_TECHNICAL   = 0.35   # 技術面 35%
WEIGHT_CHIPS       = 0.25   # 籌碼面 25%

# ── 進出場參數 ──────────────────────────
STOP_LOSS_RATIO  = 0.92     # 停損：買進價 × 0.92（跌8%停損）
TARGET_LOOKBACK  = 65       # 目標價參考近65個交易日（約3個月）

# ── 評分等級 ────────────────────────────
GRADE = {
    80: '強力買進',
    65: '偏多操作',
    50: '中性觀望',
    35: '偏空謹慎',
     0: '風險偏高',
}

# ── 資料過期警告天數 ─────────────────────
DATA_EXPIRE_DAYS = 3        # 超過3個交易日未更新顯示警告

# ── 版本資訊 ────────────────────────────
VERSION = 'v2.1'
VERSION_DATE = '2026/05/21'
VERSION_NOTE = '初始版本'

