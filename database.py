# ════════════════════════════════════════
# database.py　資料庫操作
# 負責建立和管理 SQLite 資料庫
# ════════════════════════════════════════

import sqlite3
import os
import json
from datetime import datetime
from config import DB_PATH

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── 股票基本資料表 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            code        TEXT PRIMARY KEY,
            name        TEXT,
            market      TEXT,
            industry    TEXT,
            updated_at  TEXT
        )
    ''')

    # ── 每日價格資料表 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            date        TEXT,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      INTEGER,
            value       REAL,
            change      REAL,
            change_pct  REAL,
            UNIQUE(code, date)
        )
    ''')

    # ── 基本面資料表 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS fundamentals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT,
            date            TEXT,
            eps_ttm         REAL,
            pe              REAL,
            pb              REAL,
            dividend_yield  REAL,
            UNIQUE(code, date)
        )
    ''')

    # ── 籌碼面資料表 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS chips (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT,
            date            TEXT,
            foreign_buy     INTEGER,
            foreign_sell    INTEGER,
            foreign_net     INTEGER,
            trust_buy       INTEGER,
            trust_sell      INTEGER,
            trust_net       INTEGER,
            dealer_buy      INTEGER,
            dealer_sell     INTEGER,
            dealer_net      INTEGER,
            margin_balance  INTEGER,
            short_balance   INTEGER,
            UNIQUE(code, date)
        )
    ''')

    # ── 自選股清單 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE,
            name        TEXT,
            tag         TEXT,
            added_at    TEXT
        )
    ''')

    # ── 備註欄 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            date        TEXT,
            auto_note   TEXT,
            user_note   TEXT,
            created_at  TEXT
        )
    ''')

    # ── 更新紀錄 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS update_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT,
            status      TEXT,
            message     TEXT,
            updated_at  TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print('資料庫初始化完成')

# ── 價格資料 ────────────────────────────
def save_prices(code, rows):
    conn = get_conn()
    c = conn.cursor()
    for r in rows:
        try:
            c.execute('''
                INSERT OR REPLACE INTO prices
                (code, date, open, high, low, close, volume, value, change, change_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, r['date'], r['open'], r['high'], r['low'],
                  r['close'], r['volume'], r['value'], r['change'], r['change_pct']))
        except Exception as e:
            print(f'儲存價格失敗 {code} {r}: {e}')
    conn.commit()
    conn.close()

def get_prices(code, days=400):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, open, high, low, close, volume, value, change, change_pct
        FROM prices WHERE code=? ORDER BY date DESC LIMIT ?
    ''', (code, days))
    rows = c.fetchall()
    conn.close()
    cols = ['date','open','high','low','close','volume','value','change','change_pct']
    return [dict(zip(cols, r)) for r in reversed(rows)]

def get_latest_price_date(code):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT MAX(date) FROM prices WHERE code=?', (code,))
    result = c.fetchone()[0]
    conn.close()
    return result

# ── 基本面資料 ───────────────────────────
def save_fundamental(code, date, eps, pe, pb, div):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO fundamentals
        (code, date, eps_ttm, pe, pb, dividend_yield)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (code, date, eps, pe, pb, div))
    conn.commit()
    conn.close()

def get_fundamentals(code, days=400):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, eps_ttm, pe, pb, dividend_yield
        FROM fundamentals WHERE code=? ORDER BY date DESC LIMIT ?
    ''', (code, days))
    rows = c.fetchall()
    conn.close()
    cols = ['date','eps_ttm','pe','pb','dividend_yield']
    return [dict(zip(cols, r)) for r in reversed(rows)]

# ── 籌碼資料 ────────────────────────────
def save_chips(code, date, data):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO chips
        (code, date, foreign_buy, foreign_sell, foreign_net,
         trust_buy, trust_sell, trust_net,
         dealer_buy, dealer_sell, dealer_net,
         margin_balance, short_balance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (code, date,
          data.get('foreign_buy',0), data.get('foreign_sell',0), data.get('foreign_net',0),
          data.get('trust_buy',0), data.get('trust_sell',0), data.get('trust_net',0),
          data.get('dealer_buy',0), data.get('dealer_sell',0), data.get('dealer_net',0),
          data.get('margin_balance',0), data.get('short_balance',0)))
    conn.commit()
    conn.close()

def get_chips(code, days=65):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, foreign_buy, foreign_sell, foreign_net,
               trust_buy, trust_sell, trust_net,
               dealer_buy, dealer_sell, dealer_net,
               margin_balance, short_balance
        FROM chips WHERE code=? ORDER BY date DESC LIMIT ?
    ''', (code, days))
    rows = c.fetchall()
    conn.close()
    cols = ['date','foreign_buy','foreign_sell','foreign_net',
            'trust_buy','trust_sell','trust_net',
            'dealer_buy','dealer_sell','dealer_net',
            'margin_balance','short_balance']
    return [dict(zip(cols, r)) for r in reversed(rows)]

# ── 自選股 ──────────────────────────────
def get_watchlist():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT code, name, tag, added_at FROM watchlist ORDER BY added_at')
    rows = c.fetchall()
    conn.close()
    return [{'code':r[0],'name':r[1],'tag':r[2],'added_at':r[3]} for r in rows]

def add_watchlist(code, name, tag=''):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO watchlist (code, name, tag, added_at)
            VALUES (?, ?, ?, ?)
        ''', (code, name, tag, datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
    except:
        pass
    conn.close()

def remove_watchlist(code):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM watchlist WHERE code=?', (code,))
    conn.commit()
    conn.close()

def update_watchlist_tag(code, tag):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE watchlist SET tag=? WHERE code=?', (tag, code))
    conn.commit()
    conn.close()

# ── 備註 ────────────────────────────────
def save_note(code, auto_note, user_note=''):
    conn = get_conn()
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d')
    now  = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('''
        INSERT INTO notes (code, date, auto_note, user_note, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (code, date, auto_note, user_note, now))
    conn.commit()
    conn.close()

def get_notes(code, limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, auto_note, user_note, created_at
        FROM notes WHERE code=? ORDER BY created_at DESC LIMIT ?
    ''', (code, limit))
    rows = c.fetchall()
    conn.close()
    return [{'date':r[0],'auto_note':r[1],'user_note':r[2],'created_at':r[3]} for r in rows]

def update_user_note(code, date, user_note):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        UPDATE notes SET user_note=? WHERE code=? AND date=?
    ''', (user_note, code, date))
    conn.commit()
    conn.close()

# ── 更新紀錄 ────────────────────────────
def log_update(status, message):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('''
        INSERT INTO update_log (date, status, message, updated_at)
        VALUES (?, ?, ?, ?)
    ''', (datetime.now().strftime('%Y-%m-%d'), status, message, now))
    conn.commit()
    conn.close()

def get_last_update():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, status, message, updated_at
        FROM update_log ORDER BY updated_at DESC LIMIT 1
    ''')
    row = c.fetchone()
    conn.close()
    if row:
        return {'date':row[0],'status':row[1],'message':row[2],'updated_at':row[3]}
    return None

# ── 股票搜尋 ────────────────────────────
def search_stock(keyword):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT code, name, market, industry FROM stocks
        WHERE code LIKE ? OR name LIKE ?
        LIMIT 20
    ''', (f'%{keyword}%', f'%{keyword}%'))
    rows = c.fetchall()
    conn.close()
    return [{'code':r[0],'name':r[1],'market':r[2],'industry':r[3]} for r in rows]

def save_stock_info(code, name, market, industry):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('''
        INSERT OR REPLACE INTO stocks (code, name, market, industry, updated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (code, name, market, industry, now))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
