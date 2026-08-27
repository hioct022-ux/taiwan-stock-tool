"""
一次性回填 TAIEX 兩年歷史（年線 MA240 需要 240+ 交易日）。
執行：python3 backfill_taiex_history.py
執行後可刪除此檔案。之後每日更新只會抓新資料，歷史不會消失。
注意：舊資料的 value（成交金額）為 yfinance 原始值，僅供均線計算用（均線只用 close），
     成交量圖有 <50000 過濾防護，不受影響。
"""
from fetcher import fetch_taiex
from database import get_conn

fetch_taiex(months=24, force=True)

conn = get_conn()
row = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM prices WHERE code='TAIEX'").fetchone()
conn.close()
print(f'\nTAIEX 歷史：共 {row[0]} 個交易日（{row[1]} ～ {row[2]}）')
print('≥240 日即可計算年線' if row[0] >= 240 else f'⚠️ 仍不足 240 日（差 {240 - row[0]} 日），年線無法計算')
