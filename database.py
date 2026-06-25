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
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')   # 允許多個程序同時讀寫
    conn.execute('PRAGMA busy_timeout=10000') # 等待最多 10 秒再報錯
    return conn

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

    # ── 自訂標籤表 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_tags (
            name        TEXT PRIMARY KEY,
            sort_order  INTEGER DEFAULT 0
        )
    ''')
    # 預設標籤（只在空白時插入）
    existing = c.execute('SELECT COUNT(*) FROM watchlist_tags').fetchone()[0]
    if existing == 0:
        for i, t in enumerate(['長期', '觀察中', '其他']):
            c.execute('INSERT OR IGNORE INTO watchlist_tags (name, sort_order) VALUES (?,?)', (t, i))

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

    # ── ETF 成分股 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS etf_holdings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_code    TEXT,
            etf_name    TEXT,
            stock_code  TEXT,
            weight      REAL,
            shares      INTEGER,
            updated_at  TEXT,
            UNIQUE(etf_code, stock_code)
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

    # ── 外資持股比率（每日更新，來自 TWSE MI_QFIIS）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS ownership (
            code            TEXT PRIMARY KEY,
            foreign_pct     REAL,
            date            TEXT,
            updated_at      TEXT
        )
    ''')

    # ── 除權息資料 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS exdividend (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ex_date      TEXT,
            code         TEXT,
            name         TEXT,
            prev_close   REAL,
            ref_price    REAL,
            div_value    REAL,
            div_type     TEXT,
            is_confirmed INTEGER DEFAULT 0,
            UNIQUE(ex_date, code)
        )
    ''')

    # ── 三大法人當日買賣超排行（T86）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS t86_ranking (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT,
            code            TEXT,
            name            TEXT,
            foreign_buy     INTEGER,
            foreign_sell    INTEGER,
            foreign_net     INTEGER,
            trust_buy       INTEGER,
            trust_sell      INTEGER,
            trust_net       INTEGER,
            dealer_net      INTEGER,
            total_net       INTEGER,
            UNIQUE(date, code)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS market_margin (
            date             TEXT PRIMARY KEY,
            margin_balance   INTEGER DEFAULT 0,
            margin_buy       INTEGER DEFAULT 0,
            margin_sell      INTEGER DEFAULT 0,
            short_balance    INTEGER DEFAULT 0,
            short_buy        INTEGER DEFAULT 0,
            short_sell       INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS futures_institutional (
            date           TEXT PRIMARY KEY,
            foreign_long   INTEGER DEFAULT 0,
            foreign_short  INTEGER DEFAULT 0,
            foreign_net    INTEGER DEFAULT 0,
            trust_long     INTEGER DEFAULT 0,
            trust_short    INTEGER DEFAULT 0,
            trust_net      INTEGER DEFAULT 0,
            dealer_long    INTEGER DEFAULT 0,
            dealer_short   INTEGER DEFAULT 0,
            dealer_net     INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS market_pe (
            date     TEXT PRIMARY KEY,
            pe_ratio REAL,
            pb_ratio REAL,
            div_yield REAL
        )
    ''')

    # ── 三大法人現貨每日市場彙總（供雲端使用）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS chips_market_agg (
            date         TEXT PRIMARY KEY,
            foreign_net  INTEGER,
            trust_net    INTEGER,
            dealer_net   INTEGER
        )
    ''')

    # ── 選擇權 P/C 比率 ──
    c.execute('''
        CREATE TABLE IF NOT EXISTS options_pc_ratio (
            date      TEXT PRIMARY KEY,
            call_oi   INTEGER DEFAULT 0,
            put_oi    INTEGER DEFAULT 0,
            pc_ratio  REAL
        )
    ''')

    # ── 個股業務分部營收（AI Server 占比等，手動輸入）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_segment_revenue (
            code        TEXT NOT NULL,
            period      TEXT NOT NULL,   -- 'YYYYQN'
            segment     TEXT NOT NULL,   -- e.g. 'ai_server'
            revenue_pct REAL,            -- % 占總營收
            revenue_abs REAL,            -- 絕對金額（千元，可 NULL）
            note        TEXT,
            updated_at  TEXT,
            PRIMARY KEY (code, period, segment)
        )
    ''')

    # ── 個股季度財報（毛利率等，market_tracker 用）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_quarterly_financials (
            code             TEXT NOT NULL,
            period           TEXT NOT NULL,   -- 'YYYYQN' 例如 '2026Q1'
            revenue          REAL,            -- 營業收入（千元）
            gross_profit     REAL,            -- 毛利（千元）
            gross_margin     REAL,            -- 毛利率（%，e.g. 38.5）
            operating_income REAL,            -- 營業利益（千元）
            net_income       REAL,            -- 稅後淨利（千元）
            updated_at       TEXT,
            PRIMARY KEY (code, period)
        )
    ''')

    # ── DRAM 現貨與合約價（市場追蹤用）──
    c.execute('''
        CREATE TABLE IF NOT EXISTS dram_prices (
            date           TEXT PRIMARY KEY,
            spot_price     REAL,           -- DDR4 16Gb 3200 Session Average（美元）
            spot_chg_pct   REAL,           -- 當日漲跌幅（%）
            contract_price REAL            -- 季度合約價，手動輸入（美元），可為 NULL
        )
    ''')

    # ── 欄位 migration（舊版 DB 相容）──
    migrations = [
        'ALTER TABLE exdividend ADD COLUMN is_confirmed INTEGER DEFAULT 0',
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # 欄位已存在，忽略

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
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days * 2)).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT date, foreign_buy, foreign_sell, foreign_net,
               trust_buy, trust_sell, trust_net,
               dealer_buy, dealer_sell, dealer_net,
               margin_balance, short_balance
        FROM chips WHERE code=? AND date >= ?
        ORDER BY date DESC LIMIT ?
    ''', (code, cutoff, days))
    rows = c.fetchall()
    conn.close()
    cols = ['date','foreign_buy','foreign_sell','foreign_net',
            'trust_buy','trust_sell','trust_net',
            'dealer_buy','dealer_sell','dealer_net',
            'margin_balance','short_balance']
    return [dict(zip(cols, r)) for r in reversed(rows)]

# ── 自選股 ──────────────────────────────
def _tags_to_str(tags):
    """list → 逗號分隔字串"""
    if isinstance(tags, list):
        return ','.join(t.strip() for t in tags if t.strip())
    return str(tags) if tags else ''

def _str_to_tags(s):
    """逗號分隔字串 → list（去空白）"""
    if not s:
        return []
    return [t.strip() for t in s.split(',') if t.strip()]

def get_watchlist():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT code, name, tag, added_at FROM watchlist ORDER BY added_at')
    rows = c.fetchall()
    conn.close()
    return [{'code':r[0],'name':r[1],'tags':_str_to_tags(r[2]),'added_at':r[3]} for r in rows]

def add_watchlist(code, name, tags=None):
    """tags 可為 list 或單一字串"""
    conn = get_conn()
    c = conn.cursor()
    tag_str = _tags_to_str(tags) if tags else ''
    try:
        c.execute('''
            INSERT INTO watchlist (code, name, tag, added_at)
            VALUES (?, ?, ?, ?)
        ''', (code, name, tag_str, datetime.now().strftime('%Y-%m-%d %H:%M')))
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
    """向下相容：單一標籤字串"""
    update_watchlist_tags(code, [tag] if tag else [])

def update_watchlist_tags(code, tags):
    """更新多標籤，tags 為 list"""
    conn = get_conn()
    conn.execute('UPDATE watchlist SET tag=? WHERE code=?', (_tags_to_str(tags), code))
    conn.commit()
    conn.close()

# ── 自訂標籤管理 ─────────────────────────
def get_tags():
    """取得所有自訂標籤（依 sort_order 排序）"""
    conn = get_conn()
    rows = conn.execute('SELECT name FROM watchlist_tags ORDER BY sort_order, name').fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_tag(name):
    """新增標籤"""
    name = name.strip()
    if not name:
        return False
    conn = get_conn()
    try:
        max_order = conn.execute('SELECT MAX(sort_order) FROM watchlist_tags').fetchone()[0] or 0
        conn.execute('INSERT INTO watchlist_tags (name, sort_order) VALUES (?,?)', (name, max_order + 1))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def rename_tag(old_name, new_name):
    """重新命名標籤，同步更新所有自選股中包含該標籤的欄位"""
    new_name = new_name.strip()
    if not new_name or old_name == new_name:
        return False
    conn = get_conn()
    try:
        conn.execute('UPDATE watchlist_tags SET name=? WHERE name=?', (new_name, old_name))
        # 逐筆更新含有 old_name 的自選股
        rows = conn.execute('SELECT code, tag FROM watchlist').fetchall()
        for code, tag_str in rows:
            tags = _str_to_tags(tag_str)
            if old_name in tags:
                new_tags = [new_name if t == old_name else t for t in tags]
                conn.execute('UPDATE watchlist SET tag=? WHERE code=?',
                             (_tags_to_str(new_tags), code))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def delete_tag(name):
    """刪除標籤，同步從所有自選股移除該標籤"""
    conn = get_conn()
    try:
        conn.execute('DELETE FROM watchlist_tags WHERE name=?', (name,))
        # 逐筆移除含有 name 的自選股標籤
        rows = conn.execute('SELECT code, tag FROM watchlist').fetchall()
        for code, tag_str in rows:
            tags = _str_to_tags(tag_str)
            if name in tags:
                new_tags = [t for t in tags if t != name]
                conn.execute('UPDATE watchlist SET tag=? WHERE code=?',
                             (_tags_to_str(new_tags), code))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def reorder_tags(names):
    """依照傳入的 list 順序更新 sort_order"""
    conn = get_conn()
    for i, name in enumerate(names):
        conn.execute('UPDATE watchlist_tags SET sort_order=? WHERE name=?', (i, name))
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
        SELECT id, date, auto_note, user_note, created_at
        FROM notes WHERE code=? ORDER BY created_at DESC LIMIT ?
    ''', (code, limit))
    rows = c.fetchall()
    conn.close()
    return [{'id':r[0],'date':r[1],'auto_note':r[2],'user_note':r[3],'created_at':r[4]} for r in rows]

def delete_note(note_id):
    """刪除指定 id 的筆記"""
    conn = get_conn()
    conn.execute('DELETE FROM notes WHERE id=?', (note_id,))
    conn.commit()
    conn.close()

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

def save_etf_holdings(etf_code, etf_name, constituents):
    """存入某 ETF 的成分股清單（先刪舊資料再寫入）"""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('DELETE FROM etf_holdings WHERE etf_code=?', (etf_code,))
    for item in constituents:
        try:
            c.execute('''
                INSERT OR REPLACE INTO etf_holdings
                (etf_code, etf_name, stock_code, weight, shares, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (etf_code, etf_name,
                  item.get('stock_code', ''),
                  item.get('weight', 0.0),
                  item.get('shares', 0),
                  now))
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_etf_holders(stock_code):
    """查詢持有某股票的所有 ETF，依持股比例排序"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT etf_code, etf_name, weight, shares, updated_at
        FROM etf_holdings
        WHERE stock_code=?
        ORDER BY weight DESC
    ''', (stock_code,))
    rows = c.fetchall()
    conn.close()
    return [{'etf_code': r[0], 'etf_name': r[1],
             'weight': r[2], 'shares': r[3],
             'updated_at': r[4]} for r in rows]

def get_etf_last_update():
    """取得 ETF 成分股最後更新時間"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT MAX(updated_at) FROM etf_holdings')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_ownership(code, foreign_pct, date):
    """儲存外資持股比率（來自 TWSE MI_QFIIS，每日更新）"""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('''
        INSERT OR REPLACE INTO ownership (code, foreign_pct, date, updated_at)
        VALUES (?, ?, ?, ?)
    ''', (code, foreign_pct, date, now))
    conn.commit()
    conn.close()

def get_ownership(code):
    """取得個股外資持股比率，回傳 dict 或 None"""
    conn = get_conn()
    row = conn.execute(
        'SELECT foreign_pct, date FROM ownership WHERE code=?', (code,)
    ).fetchone()
    conn.close()
    if row:
        return {'foreign_pct': row[0], 'date': row[1]}
    return None

# ── 三大法人排行 ─────────────────────────
def save_t86_ranking(date, rows):
    """批次儲存 T86 當日三大法人明細（先刪當日舊資料再寫入）"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM t86_ranking WHERE date=?', (date,))
    for r in rows:
        try:
            c.execute('''
                INSERT OR REPLACE INTO t86_ranking
                (date, code, name, foreign_buy, foreign_sell, foreign_net,
                 trust_buy, trust_sell, trust_net, dealer_net, total_net)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (date, r['code'], r['name'],
                  r.get('foreign_buy', 0), r.get('foreign_sell', 0), r.get('foreign_net', 0),
                  r.get('trust_buy', 0), r.get('trust_sell', 0), r.get('trust_net', 0),
                  r.get('dealer_net', 0), r.get('total_net', 0)))
        except Exception as e:
            print(f'儲存T86失敗 {r}: {e}')
    conn.commit()
    conn.close()

def get_t86_ranking(date=None, sort_by='trust_net', top=15):
    """取得某日三大法人排行，sort_by 可為 trust_net / foreign_net / total_net"""
    conn = get_conn()
    c = conn.cursor()
    if not date:
        row = conn.execute('SELECT MAX(date) FROM t86_ranking').fetchone()
        date = row[0] if row and row[0] else None
    if not date:
        conn.close()
        return [], None
    valid_cols = {'trust_net', 'foreign_net', 'total_net', 'dealer_net'}
    col = sort_by if sort_by in valid_cols else 'trust_net'
    c.execute(f'''
        SELECT code, name, foreign_buy, foreign_sell, foreign_net,
               trust_buy, trust_sell, trust_net, dealer_net, total_net
        FROM t86_ranking WHERE date=?
        ORDER BY {col} DESC LIMIT ?
    ''', (date, top))
    rows = c.fetchall()
    conn.close()
    cols = ['code', 'name', 'foreign_buy', 'foreign_sell', 'foreign_net',
            'trust_buy', 'trust_sell', 'trust_net', 'dealer_net', 'total_net']
    return [dict(zip(cols, r)) for r in rows], date

def get_t86_ranking_bottom(date=None, sort_by='trust_net', top=15):
    """取得賣超排行（最小值在前），sort_by 同 get_t86_ranking"""
    conn = get_conn()
    c = conn.cursor()
    if not date:
        row = conn.execute('SELECT MAX(date) FROM t86_ranking').fetchone()
        date = row[0] if row and row[0] else None
    if not date:
        conn.close()
        return [], None
    valid_cols = {'trust_net', 'foreign_net', 'total_net', 'dealer_net'}
    col = sort_by if sort_by in valid_cols else 'trust_net'
    c.execute(f'''
        SELECT code, name, foreign_buy, foreign_sell, foreign_net,
               trust_buy, trust_sell, trust_net, dealer_net, total_net
        FROM t86_ranking WHERE date=?
        ORDER BY {col} ASC LIMIT ?
    ''', (date, top))
    rows = c.fetchall()
    conn.close()
    cols = ['code', 'name', 'foreign_buy', 'foreign_sell', 'foreign_net',
            'trust_buy', 'trust_sell', 'trust_net', 'dealer_net', 'total_net']
    return [dict(zip(cols, r)) for r in rows], date

def get_t86_last_date():
    """取得 T86 資料最後日期"""
    conn = get_conn()
    row = conn.execute('SELECT MAX(date) FROM t86_ranking').fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def save_chips_market_agg(rows):
    """儲存三大法人現貨市場彙總（供雲端匯入使用）"""
    conn = get_conn()
    for r in rows:
        conn.execute('''
            INSERT OR REPLACE INTO chips_market_agg (date, foreign_net, trust_net, dealer_net)
            VALUES (?, ?, ?, ?)
        ''', (r['date'], r.get('foreign_net', 0), r.get('trust_net', 0), r.get('dealer_net', 0)))
    conn.commit()
    conn.close()

def get_chips_market_agg_from_table(days=30):
    """從 chips_market_agg 表讀取（雲端使用），依日期升序"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, foreign_net, trust_net, dealer_net
        FROM chips_market_agg
        ORDER BY date DESC LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'foreign_net', 'trust_net', 'dealer_net']
    return list(reversed([dict(zip(cols, r)) for r in rows]))

def get_chips_market_aggregate(days=60, min_stocks=500):
    """
    從 chips 表彙總全市場三大法人每日淨買賣超（張）。
    只取 stock_count >= min_stocks 的日期，確保是全市場資料而非少數自選股。
    回傳依日期升序的 list of dict。
    """
    conn = get_conn()
    rows = conn.execute('''
        SELECT date,
               COUNT(*)          AS stock_count,
               SUM(foreign_net)  AS foreign_net,
               SUM(trust_net)    AS trust_net,
               SUM(dealer_net)   AS dealer_net
        FROM chips
        WHERE date >= date('now', ? || ' days')
        GROUP BY date
        HAVING stock_count >= ?
        ORDER BY date DESC LIMIT ?
    ''', (f'-{days*2}', min_stocks, days)).fetchall()
    conn.close()
    cols = ['date', 'stock_count', 'foreign_net', 'trust_net', 'dealer_net']
    return list(reversed([dict(zip(cols, r)) for r in rows]))

def get_t86_market_aggregate(days=10):
    """取得 T86 全市場外資/投信/合計淨買賣超（每日彙總），依日期升序"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT date,
               SUM(foreign_net) AS foreign_net_total,
               SUM(trust_net)   AS trust_net_total,
               SUM(total_net)   AS total_net_total
        FROM t86_ranking
        GROUP BY date
        ORDER BY date DESC LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'foreign_net_total', 'trust_net_total', 'total_net_total']
    return list(reversed([dict(zip(cols, r)) for r in rows]))

# ── 大盤融資融券 ────────────────────────
def save_market_margin(date, data):
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO market_margin
        (date, margin_balance, margin_buy, margin_sell,
         short_balance, short_buy, short_sell)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date,
          data.get('margin_balance', 0), data.get('margin_buy', 0), data.get('margin_sell', 0),
          data.get('short_balance', 0),  data.get('short_buy', 0),  data.get('short_sell', 0)))
    conn.commit()
    conn.close()

def get_market_margin(days=120):
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, margin_balance, margin_buy, margin_sell,
               short_balance, short_buy, short_sell
        FROM market_margin ORDER BY date DESC LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'margin_balance', 'margin_buy', 'margin_sell',
            'short_balance', 'short_buy', 'short_sell']
    return [dict(zip(cols, r)) for r in reversed(rows)]

def get_market_margin_last_date():
    conn = get_conn()
    row = conn.execute('SELECT MAX(date) FROM market_margin').fetchone()
    conn.close()
    return row[0] if row and row[0] else None

# ── 選擇權 P/C 比率 ─────────────────────
def save_options_pc(date: str, call_oi: int, put_oi: int, pc_ratio: float) -> None:
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO options_pc_ratio (date, call_oi, put_oi, pc_ratio)
        VALUES (?, ?, ?, ?)
    ''', (date, call_oi, put_oi, round(pc_ratio, 4)))
    conn.commit()
    conn.close()

def get_options_pc(days: int = 60) -> list:
    """回傳近 days 筆，升序。key：date, call_oi, put_oi, pc_ratio"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, call_oi, put_oi, pc_ratio
        FROM options_pc_ratio
        ORDER BY date DESC
        LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'call_oi', 'put_oi', 'pc_ratio']
    return [dict(zip(cols, r)) for r in reversed(rows)]

def get_options_pc_last_date() -> str | None:
    conn = get_conn()
    row = conn.execute(
        'SELECT date FROM options_pc_ratio ORDER BY date DESC LIMIT 1'
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── 大盤本益比 ───────────────────────────
def save_market_pe(date, pe_ratio, pb_ratio=None, div_yield=None):
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO market_pe (date, pe_ratio, pb_ratio, div_yield)
        VALUES (?, ?, ?, ?)
    ''', (date, pe_ratio, pb_ratio, div_yield))
    conn.commit()
    conn.close()

def get_market_pe(days=250):
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, pe_ratio, pb_ratio, div_yield
        FROM market_pe ORDER BY date DESC LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'pe_ratio', 'pb_ratio', 'div_yield']
    return [dict(zip(cols, r)) for r in reversed(rows)]

def get_market_pe_last_date():
    conn = get_conn()
    row = conn.execute('SELECT MAX(date) FROM market_pe').fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ── DRAM 現貨與合約價 ──────────────────────
def save_dram_price(date: str, spot_price: float, spot_chg_pct: float,
                    contract_price: float = None) -> None:
    """儲存 DDR4 16Gb 3200 現貨價（自動抓取）及合約價（手動輸入，可 None）。"""
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO dram_prices (date, spot_price, spot_chg_pct, contract_price)
        VALUES (?, ?, ?, ?)
    ''', (date, round(spot_price, 3), round(spot_chg_pct, 2),
          round(contract_price, 3) if contract_price is not None else None))
    conn.commit()
    conn.close()

def get_dram_prices(days: int = 120) -> list:
    """回傳近 days 筆，升序。key：date, spot_price, spot_chg_pct, contract_price"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, spot_price, spot_chg_pct, contract_price
        FROM dram_prices
        ORDER BY date DESC
        LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'spot_price', 'spot_chg_pct', 'contract_price']
    return [dict(zip(cols, r)) for r in reversed(rows)]

def get_dram_price_last_date() -> str | None:
    conn = get_conn()
    row = conn.execute('SELECT MAX(date) FROM dram_prices').fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ── 個股季度財報（毛利率追蹤用）──────────────
def save_quarterly_financials(code: str, period: str, revenue: float,
                               gross_profit: float, gross_margin: float,
                               operating_income: float = None,
                               net_income: float = None) -> None:
    """
    儲存個股季度財報資料。
    period 格式：'2026Q1'（年＋季）
    金額單位：千元（yfinance 原始單位）
    gross_margin：百分比，例如 38.5
    """
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO stock_quarterly_financials
            (code, period, revenue, gross_profit, gross_margin,
             operating_income, net_income, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (code, period, revenue, gross_profit, round(gross_margin, 2),
          operating_income, net_income, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def get_quarterly_financials(code: str, quarters: int = 12) -> list:
    """
    回傳個股近 quarters 季的財報資料，升序。
    key：period, revenue, gross_profit, gross_margin, operating_income, net_income
    """
    conn = get_conn()
    rows = conn.execute('''
        SELECT period, revenue, gross_profit, gross_margin,
               operating_income, net_income
        FROM stock_quarterly_financials
        WHERE code = ?
        ORDER BY period DESC
        LIMIT ?
    ''', (code, quarters)).fetchall()
    conn.close()
    cols = ['period', 'revenue', 'gross_profit', 'gross_margin',
            'operating_income', 'net_income']
    return [dict(zip(cols, r)) for r in reversed(rows)]


def get_quarterly_financials_last_period(code: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        'SELECT MAX(period) FROM stock_quarterly_financials WHERE code=?', (code,)
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ── 個股業務分部營收 ────────────────────────
def save_segment_revenue(code: str, period: str, segment: str,
                          revenue_pct: float, revenue_abs: float = None,
                          note: str = '') -> None:
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO stock_segment_revenue
            (code, period, segment, revenue_pct, revenue_abs, note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (code, period, segment, round(revenue_pct, 1), revenue_abs, note,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def get_segment_revenue(code: str, segment: str, quarters: int = 12) -> list:
    """回傳指定業務分部的歷史占比，升序。key：period, revenue_pct, revenue_abs, note"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT period, revenue_pct, revenue_abs, note
        FROM stock_segment_revenue
        WHERE code=? AND segment=?
        ORDER BY period DESC LIMIT ?
    ''', (code, segment, quarters)).fetchall()
    conn.close()
    cols = ['period', 'revenue_pct', 'revenue_abs', 'note']
    return [dict(zip(cols, r)) for r in reversed(rows)]


# ── 除權息資料 ──────────────────────────
def save_exdividend(rows):
    """
    批次存入除權息資料。
    is_confirmed=1（TWT49U 正式）時無條件覆蓋；
    is_confirmed=0（TWT48U 早期預告）時若已有正式資料則跳過。
    同時執行 ALTER TABLE 補欄位（舊版 DB 相容）。
    """
    conn = get_conn()
    c = conn.cursor()
    # 舊版 DB 相容：補 is_confirmed 欄位
    try:
        c.execute('ALTER TABLE exdividend ADD COLUMN is_confirmed INTEGER DEFAULT 0')
        conn.commit()
    except Exception:
        pass  # 欄位已存在，忽略

    for r in rows:
        try:
            is_confirmed = 1 if r.get('is_confirmed') else 0
            if is_confirmed:
                # 正式資料：直接 INSERT OR REPLACE（覆蓋預告）
                c.execute('''
                    INSERT OR REPLACE INTO exdividend
                    (ex_date, code, name, prev_close, ref_price, div_value, div_type, is_confirmed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ''', (r['ex_date'], r['code'], r['name'],
                      r.get('prev_close', 0), r.get('ref_price', 0),
                      r.get('div_value', 0), r.get('div_type', '')))
            else:
                # 早期預告：僅在無資料時才插入，有正式資料則跳過
                c.execute('''
                    INSERT OR IGNORE INTO exdividend
                    (ex_date, code, name, prev_close, ref_price, div_value, div_type, is_confirmed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ''', (r['ex_date'], r['code'], r['name'],
                      r.get('prev_close', 0), r.get('ref_price', 0),
                      r.get('div_value', 0), r.get('div_type', '')))
                # 若已存在且仍是預告，更新內容（名稱/股息可能更新）
                c.execute('''
                    UPDATE exdividend
                    SET name=?, prev_close=?, div_value=?, div_type=?
                    WHERE ex_date=? AND code=? AND is_confirmed=0
                ''', (r['name'], r.get('prev_close', 0),
                      r.get('div_value', 0), r.get('div_type', ''),
                      r['ex_date'], r['code']))
        except Exception as e:
            print(f'儲存除權息失敗：{e}')
    conn.commit()
    conn.close()

def get_exdividend(days=30):
    """取得最近 N 天的除權息清單，依除權息日降序"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT ex_date, code, name, prev_close, ref_price, div_value, div_type
        FROM exdividend
        WHERE ex_date >= date('now', ?)
        ORDER BY ex_date DESC
    ''', (f'-{days} days',))
    rows = c.fetchall()
    conn.close()
    cols = ['ex_date', 'code', 'name', 'prev_close', 'ref_price', 'div_value', 'div_type']
    return [dict(zip(cols, r)) for r in rows]

def get_exdividend_upcoming(days=30):
    """取得今天起未來 N 天的除權息清單，依除權息日升序"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT ex_date, code, name, prev_close, ref_price, div_value, div_type,
               COALESCE(is_confirmed, 0) as is_confirmed
        FROM exdividend
        WHERE ex_date >= date('now')
          AND ex_date <= date('now', ?)
        ORDER BY ex_date ASC
    ''', (f'+{days} days',))
    rows = c.fetchall()
    conn.close()
    cols = ['ex_date', 'code', 'name', 'prev_close', 'ref_price', 'div_value', 'div_type', 'is_confirmed']
    return [dict(zip(cols, r)) for r in rows]

def get_exdividend_by_code(code):
    """查詢特定股票的除權息紀錄（近一年）"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT ex_date, prev_close, ref_price, div_value, div_type
        FROM exdividend
        WHERE code=? AND ex_date >= date('now', '-365 days')
        ORDER BY ex_date DESC
    ''', (code,))
    rows = c.fetchall()
    conn.close()
    cols = ['ex_date', 'prev_close', 'ref_price', 'div_value', 'div_type']
    return [dict(zip(cols, r)) for r in rows]

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

def save_futures_institutional(date, data):
    """儲存三大法人台指期未平倉口數"""
    conn = get_conn()
    conn.execute('''
        INSERT OR REPLACE INTO futures_institutional
        (date, foreign_long, foreign_short, foreign_net,
         trust_long, trust_short, trust_net,
         dealer_long, dealer_short, dealer_net)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date,
          data.get('foreign_long', 0), data.get('foreign_short', 0), data.get('foreign_net', 0),
          data.get('trust_long', 0),   data.get('trust_short', 0),   data.get('trust_net', 0),
          data.get('dealer_long', 0),  data.get('dealer_short', 0),  data.get('dealer_net', 0)))
    conn.commit()
    conn.close()

def get_futures_institutional(days=90):
    """取得最近 N 天的三大法人台指期未平倉，依日期升序"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT date, foreign_long, foreign_short, foreign_net,
               trust_long, trust_short, trust_net,
               dealer_long, dealer_short, dealer_net
        FROM futures_institutional
        ORDER BY date DESC LIMIT ?
    ''', (days,)).fetchall()
    conn.close()
    cols = ['date', 'foreign_long', 'foreign_short', 'foreign_net',
            'trust_long', 'trust_short', 'trust_net',
            'dealer_long', 'dealer_short', 'dealer_net']
    return list(reversed([dict(zip(cols, r)) for r in rows]))

if __name__ == '__main__':
    init_db()
