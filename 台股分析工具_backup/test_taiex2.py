"""
快速測試：yfinance ^TWII 能否拿到資料
執行：python3 test_taiex2.py
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/台股分析工具'))

# ── 測試 1：yfinance ──────────────────────
print('='*50)
print('測試 1：yfinance ^TWII')
try:
    import yfinance as yf
    ticker = yf.Ticker('^TWII')
    hist   = ticker.history(period='3mo', auto_adjust=True)
    if hist.empty:
        print('⚠️  yfinance 回傳空資料')
    else:
        print(f'資料筆數 = {len(hist)}')
        print(f'日期範圍：{hist.index[0].strftime("%Y-%m-%d")} ～ {hist.index[-1].strftime("%Y-%m-%d")}')
        print(f'最新收盤：{hist["Close"].iloc[-1]:.2f}')
        print(f'最新成交量：{int(hist["Volume"].iloc[-1]):,}')
        print('✅ yfinance 正常')
except ImportError:
    print('❌ yfinance 未安裝，請執行：')
    print('   pip install yfinance --break-system-packages')
except Exception as e:
    print(f'❌ 錯誤：{e}')

# ── 測試 2：透過 fetcher.fetch_taiex() ────────
print()
print('='*50)
print('測試 2：執行 fetcher.fetch_taiex()')
try:
    from fetcher import fetch_taiex
    n = fetch_taiex(months=3)
    print(f'fetch_taiex 完成，處理 {n} 筆')
except Exception as e:
    import traceback
    print(f'❌ fetch_taiex 失敗：{e}')
    traceback.print_exc()

# ── 測試 3：從 DB 讀回 ─────────────────────
print()
print('='*50)
print('測試 3：從 DB 讀取 TAIEX 資料')
try:
    from database import get_prices
    rows = get_prices('TAIEX', days=30)
    print(f'DB 中 TAIEX 筆數：{len(rows)}')
    if rows:
        print(f'最舊：{rows[0]["date"]}  收盤={rows[0]["close"]}  成交金額={rows[0]["volume"]}億')
        print(f'最新：{rows[-1]["date"]}  收盤={rows[-1]["close"]}  成交金額={rows[-1]["volume"]}億')
        print('✅ 資料正常，可以在大盤分析頁面看到圖表')
    else:
        print('❌ DB 中無 TAIEX 資料')
except Exception as e:
    print(f'❌ 讀取失敗：{e}')
