# ════════════════════════════════════════
# sector_flow.py — 類股資金流向（成交金額占比）
# ════════════════════════════════════════
#
# 獨立模組：新增/修改此頁不需更動其他任何功能
#
# 資料來源：本機 DB 的 prices + stocks（全市場上市股）
# DB 依賴：prices、stocks（industry 欄）
# github_sync 依賴：無
# IS_LOCAL 分支：**有** —— 雲端沒有全市場價格，只有自選股 JSON，算不出來
#
# app.py 只需要：
#   1. from sector_flow import render_sector_flow
#   2. 側邊欄按鈕（page='sector_flow'）
#   3. main() 路由 if page == 'sector_flow'
#
# ═══ 為什麼做這個（2026-10-04）═══
# 原本的「🔄 主題輪動」只有 4 檔 ETF，其中 3 檔是半導體相關
# （0050／00891 關鍵半導體／0056 高股息／00830 費半），
# 等於看不到航運、金融、塑化、生技、電機、汽車在幹什麼——
# 它其實是「半導體 vs 高股息」，不是類股輪動。
#
# 2026-09-23 補完全市場價格（439 個交易日、56 萬列）之後，條件變了：
#   • 510 檔流動性宇宙 **100% 都有 TWSE 產業代碼**
#   • prices 有 527 個交易日 × 約 1,077 檔上市股
#   • `value` 欄（成交金額）一直都在，但從來沒有被任何功能用過
#
# 選「成交金額占比」而不是「價格強弱」的理由：
#   占比回答的是「**資金正在流進哪裡**」，價格回答的是「**哪裡已經漲過**」。
#   在 2026-09-23 量到「評分是後照鏡」之後，前者至少是個不同的問題。
#
# ⚠️ 定位（UI caption 必須保留）：純資訊顯示，未經任何回測驗證。
#    不計入評分、不影響進場門檻、不可當作進出場理由。
#    與 🎯🔥 型態、量能水位完全相同的定位——少了這句，日後必被當訊號用。
#    本專案已六次驗證出「看起來合理的訊號實測無效」，而占比同樣是
#    「昨天的成交結果」算出來的，先驗機率不高。
#    日後若真要當規則用，必須先回測；好消息是全市場樣本讓雜訊帶降到
#    0.60pp（2026-09-24），0.6pp 以上的效果現在看得見。
# ════════════════════════════════════════

import json
import os
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go

from config import IS_LOCAL, JSON_DIR
from database import get_conn

# 雲端用的匯出檔（方案B：單一視窗 + 每類股前 N 檔）
JSON_NAME     = 'sector_flow.json'
EXPORT_WINDOW = (5, 20)      # 雲端只有這個視窗；本機仍可切換
EXPORT_TOP_N  = 20           # 每類股匯出前 N 檔成分股
EXPORT_SERIES = 60           # 占比走勢天數

_CHART_CFG = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}

# ── TWSE 產業別代碼 → 中文名（已用已知股票驗證：2330→24、2317→31、
#    2882→17、1301→03、2603→15、2412→27、3008→26、2207→12、6505→23）──
IND_NAMES = {
    '01': '水泥', '02': '食品', '03': '塑膠', '04': '紡織纖維', '05': '電機機械',
    '06': '電器電纜', '07': '化學生技醫療', '08': '玻璃陶瓷', '09': '造紙',
    '10': '鋼鐵', '11': '橡膠', '12': '汽車', '13': '電子', '14': '建材營造',
    '15': '航運', '16': '觀光餐旅', '17': '金融保險', '18': '貿易百貨',
    '19': '綜合', '20': '其他', '21': '化學', '22': '生技醫療', '23': '油電燃氣',
    '24': '半導體', '25': '電腦及週邊', '26': '光電', '27': '通信網路',
    '28': '電子零組件', '29': '電子通路', '30': '資訊服務', '31': '其他電子',
    '32': '文化創意', '33': '農業科技', '34': '電子商務', '35': '綠能環保',
    '36': '數位雲端', '37': '運動休閒', '38': '居家生活',
    '80': '管理股票', '91': '存託憑證',
}

# 視窗選項：(短窗天數, 長窗天數)
WINDOWS = {
    '近5日 vs 近20日':  (5, 20),
    '近10日 vs 近60日': (10, 60),
    '近20日 vs 近60日': (20, 60),
}

MIN_SHARE   = 0.3    # 占比低於此（兩個視窗都低）就歸進「其他小類股」，避免 33 列擠爆
FLOW_CUT    = 0.3    # 變化超過 ±這個 pp 才標示流入/流出
UP   = '#ef4444'     # 台灣慣例：資金流入＝紅
DOWN = '#22c55e'     # 流出＝綠
FLAT = '#64748b'


def _show(fig, key=None):
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG, key=key)


# ── 資料計算 ─────────────────────────────────────────────
def _latest_date():
    conn = get_conn()
    r = conn.execute("SELECT MAX(date) FROM prices WHERE code='TAIEX'").fetchone()
    conn.close()
    return r[0] if r else None


@st.cache_data(ttl=3600, show_spinner=False)
def _sector_shares(data_date, short_n, long_n):
    """
    回傳 (rows, avg_short億, avg_long億, 日期區間)。

    rows 每項：{'ind','name','s_short','s_long','delta','s_60','value_short'}

    ⚠️ 快取 key 帶 `data_date`（TAIEX 最新日期）——陷阱40 的通則：
       任何「一個 session 只算一次」的快取都必須帶資料版本，
       否則按了「🔄 手動更新資料」之後這一頁還是舊的。

    ⚠️ 分母定義（十八章通則：算占比前先確認分母）：
       **上市（TWSE）、有產業代碼、4 碼數字代號的個股成交金額合計**。
       所以占比加總 ≈ 100%，但不含上櫃、ETF、權證、TDR。
       換分母（例如含上櫃）會得到完全不同的數字，UI caption 必須寫明。
    """
    conn = get_conn()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date<=? ORDER BY date DESC LIMIT ?",
        (data_date, max(long_n, 60)))]

    def agg(days):
        if not days:
            return {}, 0.0
        q = ','.join('?' * len(days))
        rs = conn.execute(f"""
            SELECT s.industry, SUM(p.value) v
            FROM prices p JOIN stocks s ON p.code = s.code
            WHERE s.market='TWSE' AND s.industry IS NOT NULL AND s.industry!=''
              AND length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
              AND p.date IN ({q})
            GROUP BY s.industry""", days).fetchall()
        tot = sum(r[1] or 0 for r in rs)
        if tot <= 0:
            return {}, 0.0
        return ({r[0]: (r[1] or 0) / tot * 100 for r in rs},
                tot / len(days) / 1e8)

    d_s, d_l, d_60 = cal[:short_n], cal[:long_n], cal[:60]
    s_short, avg_s = agg(d_s)
    s_long,  avg_l = agg(d_l)
    s_60,    _     = agg(d_60)

    # 各類股短窗的實際成交金額（億元／日均），下鑽時要用
    val_short = {}
    if d_s:
        q = ','.join('?' * len(d_s))
        for ind, v in conn.execute(f"""
                SELECT s.industry, SUM(p.value) FROM prices p JOIN stocks s ON p.code=s.code
                WHERE s.market='TWSE' AND s.industry IS NOT NULL AND s.industry!=''
                  AND length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
                  AND p.date IN ({q}) GROUP BY s.industry""", d_s).fetchall():
            val_short[ind] = (v or 0) / len(d_s) / 1e8
    conn.close()

    rows = []
    for ind in set(s_short) | set(s_long):
        a, b = s_short.get(ind, 0.0), s_long.get(ind, 0.0)
        rows.append({
            'ind': ind, 'name': IND_NAMES.get(ind, f'代碼{ind}'),
            's_short': a, 's_long': b, 'delta': a - b,
            's_60': s_60.get(ind, 0.0), 'value_short': val_short.get(ind, 0.0),
        })
    rows.sort(key=lambda r: -r['delta'])
    span = (d_s[-1], d_s[0]) if d_s else ('', '')
    return rows, avg_s, avg_l, span


@st.cache_data(ttl=3600, show_spinner=False)
def _sector_stocks(data_date, ind, short_n, long_n):
    """某一類股的個股明細（下鑽用）。占比分母＝該類股自己，不是全市場。"""
    conn = get_conn()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date<=? ORDER BY date DESC LIMIT ?",
        (data_date, long_n))]
    d_s, d_l = cal[:short_n], cal[:long_n]

    def per_stock(days):
        q = ','.join('?' * len(days))
        return dict(conn.execute(f"""
            SELECT p.code, SUM(p.value) FROM prices p JOIN stocks s ON p.code=s.code
            WHERE s.industry=? AND s.market='TWSE' AND length(p.code)=4
              AND p.date IN ({q}) GROUP BY p.code""", [ind] + days).fetchall())

    v_s, v_l = per_stock(d_s), per_stock(d_l)
    tot_s = sum(x or 0 for x in v_s.values()) or 1
    tot_l = sum(x or 0 for x in v_l.values()) or 1
    names = dict(conn.execute("SELECT code,name FROM stocks WHERE industry=?", (ind,)).fetchall())

    # 短窗漲跌幅：短窗第一天的前一個交易日收盤 → 最新收盤
    base_i = cal.index(d_s[-1]) if d_s and d_s[-1] in cal else None
    prev_d = cal[base_i + 1] if base_i is not None and base_i + 1 < len(cal) else None
    out = []
    for code, v in sorted(v_s.items(), key=lambda kv: -(kv[1] or 0)):
        c_now = conn.execute("SELECT close FROM prices WHERE code=? AND date=?",
                             (code, d_s[0])).fetchone()
        c_pre = conn.execute("SELECT close FROM prices WHERE code=? AND date=?",
                             (code, prev_d)).fetchone() if prev_d else None
        chg = ((c_now[0] / c_pre[0] - 1) * 100
               if c_now and c_pre and c_pre[0] else None)
        out.append({
            'code': code, 'name': names.get(code, code),
            'close': c_now[0] if c_now else None,   # 最新收盤（＝短窗最後一天）
            'value': (v or 0) / len(d_s) / 1e8,
            'w_short': (v or 0) / tot_s * 100,
            'w_long': (v_l.get(code, 0) or 0) / tot_l * 100,
            'chg': chg,
        })
    conn.close()
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _sector_share_series(data_date, ind, days=60):
    """該類股「每日成交金額占比」的時間序列（下鑽用）。"""
    conn = get_conn()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date<=? ORDER BY date DESC LIMIT ?",
        (data_date, days))][::-1]
    if not cal:
        conn.close()
        return [], []
    q = ','.join('?' * len(cal))
    tot = dict(conn.execute(f"""
        SELECT p.date, SUM(p.value) FROM prices p JOIN stocks s ON p.code=s.code
        WHERE s.market='TWSE' AND s.industry IS NOT NULL AND s.industry!=''
          AND length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
          AND p.date IN ({q}) GROUP BY p.date""", cal).fetchall())
    sub = dict(conn.execute(f"""
        SELECT p.date, SUM(p.value) FROM prices p JOIN stocks s ON p.code=s.code
        WHERE s.industry=? AND s.market='TWSE' AND length(p.code)=4
          AND p.date IN ({q}) GROUP BY p.date""", [ind] + cal).fetchall())
    conn.close()
    xs, ys = [], []
    for d in cal:
        t = tot.get(d) or 0
        if t > 0:
            xs.append(d)
            ys.append((sub.get(d) or 0) / t * 100)
    return xs, ys


# ── 雲端匯出 / 讀取 ──────────────────────────────────────
def export_json(path=None):
    """
    本機把類股資金流向算好、寫成 `sector_flow.json`，供雲端唯讀使用。
    由 `github_sync.export_to_json()` 呼叫。回傳寫出的檔案路徑（或 None）。

    ⚠️ 為什麼不直接迴圈呼叫上面那些 `_sector_*()`：
       那樣每個類股各查兩次 DB，33 類 × 2 = 66 次查詢，**實測要 15 秒**，
       掛在每日「🚀 更新並同步到雲端」上會明顯變慢。
       這裡改成 **一次 GROUP BY date, industry 全抓**，再於記憶體內彙總。

    ⚠️ 新增這個 JSON 之後，`init_cloud_data()` 的個股迴圈 skip 名單
       必須加入 `'sector_flow'`（CLAUDE.md 第六章），否則會被當成股票代號解析。
    """
    short_n, long_n = EXPORT_WINDOW
    conn = get_conn()
    try:
        row = conn.execute("SELECT MAX(date) FROM prices WHERE code='TAIEX'").fetchone()
        if not row or not row[0]:
            return None
        data_date = row[0]
        cal = [r[0] for r in conn.execute(
            "SELECT date FROM prices WHERE code='TAIEX' AND date<=? ORDER BY date DESC LIMIT ?",
            (data_date, max(long_n, EXPORT_SERIES) + 1))]
        if not cal:
            return None
        win = cal[:max(long_n, EXPORT_SERIES)]
        q = ','.join('?' * len(win))

        # ── 一次抓「每日 × 產業」成交金額 ──
        per_day = {}        # date → {ind: value}
        for d, ind, v in conn.execute(f"""
                SELECT p.date, s.industry, SUM(p.value)
                FROM prices p JOIN stocks s ON p.code = s.code
                WHERE s.market='TWSE' AND s.industry IS NOT NULL AND s.industry!=''
                  AND length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
                  AND p.date IN ({q})
                GROUP BY p.date, s.industry""", win).fetchall():
            per_day.setdefault(d, {})[ind] = v or 0

        def shares(days):
            acc = {}
            for d in days:
                for ind, v in per_day.get(d, {}).items():
                    acc[ind] = acc.get(ind, 0) + v
            tot = sum(acc.values())
            if tot <= 0:
                return {}, 0.0, {}
            return ({k: v / tot * 100 for k, v in acc.items()},
                    tot / len(days) / 1e8,
                    {k: v / len(days) / 1e8 for k, v in acc.items()})

        d_s, d_l, d_60 = cal[:short_n], cal[:long_n], cal[:EXPORT_SERIES]
        s_s, avg_s, val_s = shares(d_s)
        s_l, avg_l, _     = shares(d_l)
        s_60, _, _        = shares(d_60)

        rows = []
        for ind in set(s_s) | set(s_l):
            a, b = s_s.get(ind, 0.0), s_l.get(ind, 0.0)
            rows.append({'ind': ind, 'name': IND_NAMES.get(ind, f'代碼{ind}'),
                         's_short': round(a, 3), 's_long': round(b, 3),
                         'delta': round(a - b, 3), 's_60': round(s_60.get(ind, 0.0), 3),
                         'value_short': round(val_s.get(ind, 0.0), 1)})
        rows.sort(key=lambda r: -r['delta'])

        # ── 占比走勢（由 per_day 直接組，不再查 DB）──
        series = {}
        for ind in {r['ind'] for r in rows}:
            xs, ys = [], []
            for d in reversed(d_60):
                tot = sum(per_day.get(d, {}).values())
                if tot > 0:
                    xs.append(d)
                    ys.append(round((per_day.get(d, {}).get(ind, 0)) / tot * 100, 3))
            series[ind] = {'x': xs, 'y': ys}

        # ── 成分股：兩次 GROUP BY code（短窗、長窗）+ 一次抓兩天收盤 ──
        qs, ql = ','.join('?' * len(d_s)), ','.join('?' * len(d_l))
        meta = {c: (n, i) for c, n, i in conn.execute(
            "SELECT code,name,industry FROM stocks WHERE market='TWSE' "
            "AND industry IS NOT NULL AND industry!=''").fetchall()}
        v_s = dict(conn.execute(f"""SELECT p.code, SUM(p.value) FROM prices p
            WHERE length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
              AND p.date IN ({qs}) GROUP BY p.code""", d_s).fetchall())
        v_l = dict(conn.execute(f"""SELECT p.code, SUM(p.value) FROM prices p
            WHERE length(p.code)=4 AND p.code GLOB '[0-9][0-9][0-9][0-9]'
              AND p.date IN ({ql}) GROUP BY p.code""", d_l).fetchall())
        base_i = cal.index(d_s[-1])
        prev_d = cal[base_i + 1] if base_i + 1 < len(cal) else None
        cl_now = dict(conn.execute(
            "SELECT code, close FROM prices WHERE date=?", (d_s[0],)).fetchall())
        cl_pre = dict(conn.execute(
            "SELECT code, close FROM prices WHERE date=?", (prev_d,)).fetchall()) if prev_d else {}

        by_ind = {}
        for code, v in v_s.items():
            m = meta.get(code)
            if not m:
                continue
            by_ind.setdefault(m[1], []).append((code, m[0], v or 0))
        detail = {}
        for ind, lst in by_ind.items():
            tot_s = sum(x[2] for x in lst) or 1
            tot_l = sum((v_l.get(x[0]) or 0) for x in lst) or 1
            lst.sort(key=lambda x: -x[2])
            out = []
            for code, name, v in lst[:EXPORT_TOP_N]:
                a, b = cl_now.get(code), cl_pre.get(code)
                out.append({
                    'c': code, 'n': name,
                    'p': a,
                    'v': round(v / len(d_s) / 1e8, 1),
                    'ws': round(v / tot_s * 100, 1),
                    'wl': round((v_l.get(code) or 0) / tot_l * 100, 1),
                    'g': (round((a / b - 1) * 100, 2) if a and b else None),
                })
            detail[ind] = out
    finally:
        conn.close()

    payload = {
        'date': data_date, 'window': [short_n, long_n],
        'avg_s': round(avg_s, 1), 'avg_l': round(avg_l, 1),
        'span': [d_s[-1], d_s[0]],
        'rows': rows, 'series': series, 'detail': detail,
        'top_n': EXPORT_TOP_N,
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    path = path or os.path.join(JSON_DIR, JSON_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _get_meta_version():
    """雲端用：拿 meta.json 的 exported_at 當快取版本（與 app.py 同一招）。"""
    try:
        with open(os.path.join(JSON_DIR, 'meta.json'), encoding='utf-8') as f:
            return json.load(f).get('exported_at', '')
    except Exception:
        return ''


@st.cache_data(ttl=3600, show_spinner=False)
def _cloud_payload(version):
    try:
        with open(os.path.join(JSON_DIR, JSON_NAME), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


# ── 頁面 ─────────────────────────────────────────────────
def render_sector_flow():
    st.markdown('### 💧 類股資金流向')

    # ── 資料來源：本機算 DB（可切視窗）／雲端讀 sector_flow.json（單一視窗）──
    PL = None
    if IS_LOCAL:
        data_date = _latest_date()
        if not data_date:
            st.warning('DB 裡沒有 TAIEX 價格資料，無法建立交易日日曆。請先更新資料。')
            return
        c1, c2 = st.columns([1.4, 2.6])
        with c1:
            wkey = st.selectbox('比較視窗', list(WINDOWS.keys()), index=0, key='_sf_win')
        short_n, long_n = WINDOWS[wkey]
        try:
            rows, avg_s, avg_l, span = _sector_shares(data_date, short_n, long_n)
        except Exception as e:
            st.error(f'計算失敗：{type(e).__name__}: {e}')
            return
    else:
        PL = _cloud_payload(_get_meta_version())
        if not PL:
            st.info('雲端還沒有類股資金流向的資料。請在本機按一次「🚀 更新並同步到雲端」。')
            st.caption('（這一頁的雲端版讀的是 sector_flow.json，由本機匯出。）')
            return
        data_date = PL['date']
        short_n, long_n = PL['window']
        rows = PL['rows']
        avg_s, avg_l, span = PL['avg_s'], PL['avg_l'], PL['span']
        c1, c2 = st.columns([1.4, 2.6])
        with c1:
            st.caption(f'比較視窗：近{short_n}日 vs 近{long_n}日')
            st.caption('（雲端固定此視窗；要切換請用本機版）')

    if not rows:
        st.warning('沒有可用的成交金額資料。')
        return

    with c2:
        _d = avg_s - avg_l
        st.metric(f'近{short_n}日 日均成交金額',
                  f'{avg_s:,.0f} 億',
                  f'{_d:+,.0f} 億　vs 近{long_n}日（{avg_l:,.0f} 億）')
    _src = '' if IS_LOCAL else f'　｜　雲端資料，匯出於 {PL.get("exported_at", "")}'
    st.caption(f'資料日期 {span[0]} ~ {span[1]}（最新 {data_date}）{_src}')

    # ── 主圖：占比變化（橫向長條，一眼看流入/流出）──
    big = [r for r in rows if max(r['s_short'], r['s_long']) >= MIN_SHARE]
    small = [r for r in rows if r not in big]
    if small:
        big.append({
            'ind': '_other',
            'name': f'其他小類股（{len(small)}類）',
            's_short': sum(r['s_short'] for r in small),
            's_long':  sum(r['s_long'] for r in small),
            'delta':   sum(r['delta'] for r in small),
            's_60':    sum(r['s_60'] for r in small),
            'value_short': sum(r['value_short'] for r in small),
        })
    big.sort(key=lambda r: r['delta'])        # 由小到大，最大的會在圖的最上方

    colors = [UP if r['delta'] > FLOW_CUT else (DOWN if r['delta'] < -FLOW_CUT else FLAT)
              for r in big]
    fig = go.Figure(go.Bar(
        x=[r['delta'] for r in big],
        y=[r['name'] for r in big],
        orientation='h',
        marker_color=colors,
        text=[f"{r['delta']:+.2f}pp" for r in big],
        textposition='outside',
        customdata=[[r['s_short'], r['s_long'], r['value_short']] for r in big],
        hovertemplate=('<b>%{y}</b><br>'
                       f'近{short_n}日占比：%{{customdata[0]:.2f}}%<br>'
                       f'近{long_n}日占比：%{{customdata[1]:.2f}}%<br>'
                       '變化：%{x:+.2f}pp<br>'
                       '日均成交：%{customdata[2]:,.0f} 億<extra></extra>'),
    ))
    fig.add_vline(x=0, line_width=1, line_color='#64748b')
    fig.update_layout(
        height=max(280, 26 * len(big)),
        margin=dict(l=8, r=60, t=10, b=28),
        xaxis_title=f'成交金額占比變化（近{short_n}日 − 近{long_n}日，百分點）',
        yaxis_title=None, showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    _show(fig, key='sf_bar')

    st.caption(
        f'🔴 紅＝資金流入（占比上升 ＞{FLOW_CUT}pp）　🟢 綠＝流出　灰＝變化不明顯。'
        f'　分母＝上市普通股（4碼數字、有產業代碼）當期成交金額合計，'
        f'**不含上櫃、ETF、權證、TDR**，所以占比加總約 100%。'
    )
    st.caption(
        '⚠️ 純資訊顯示，**未經任何回測驗證**：不計入評分、不影響進場門檻、'
        '請勿當作進出場理由。占比同樣是「昨天的成交結果」算出來的，'
        '與 2026-09-23 量到「評分是後照鏡」是同一個病根。'
    )

    # ── 點選類股 → 下鑽 ──
    st.markdown('---')
    st.markdown(f'#### 點類股名稱看成分股（近{short_n}日）')

    sel = st.session_state.get('_sf_sel')
    listed = sorted([r for r in big if r['ind'] != '_other'],
                    key=lambda r: -r['s_short'])
    for i in range(0, len(listed), 2):
        cols = st.columns(2)
        for col, r in zip(cols, listed[i:i + 2]):
            with col:
                a, b = st.columns([1.5, 2])
                with a:
                    if st.button(r['name'], key=f"sf_btn_{r['ind']}",
                                 use_container_width=True):
                        st.session_state['_sf_sel'] = (
                            None if sel == r['ind'] else r['ind'])
                        st.rerun()
                with b:
                    _c = UP if r['delta'] > FLOW_CUT else (
                        DOWN if r['delta'] < -FLOW_CUT else FLAT)
                    st.markdown(
                        f"<div style='padding-top:6px;font-size:0.86rem'>"
                        f"占比 <b>{r['s_short']:.2f}%</b>　"
                        f"<span style='color:{_c}'>{r['delta']:+.2f}pp</span>　"
                        f"<span style='color:#94a3b8'>{r['value_short']:,.0f}億/日</span>"
                        f"</div>", unsafe_allow_html=True)

    if not sel:
        st.caption('（還沒選。點上面任一個類股名稱展開成分股明細，再點一次收起。）')
        return

    st.markdown('---')
    _name = IND_NAMES.get(sel, sel)
    st.markdown(f'### 🔍 {_name}')

    if PL is None:
        xs, ys = _sector_share_series(data_date, sel, 60)
    else:
        _s = (PL.get('series') or {}).get(sel) or {}
        xs, ys = _s.get('x', []), _s.get('y', [])
    if xs:
        f2 = go.Figure(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='#3b82f6', width=2)))
        if len(ys) >= long_n:
            _avg = sum(ys[-long_n:]) / long_n
            f2.add_hline(y=_avg, line_dash='dash', line_color='#94a3b8',
                         annotation_text=f'近{long_n}日均 {_avg:.2f}%')
        f2.update_layout(height=220, margin=dict(l=8, r=8, t=10, b=24),
                         yaxis_title='占全市場成交金額 %', showlegend=False,
                         plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        _show(f2, key=f'sf_series_{sel}')
        st.caption('該類股每日成交金額占比（近60個交易日）。')

    if PL is None:
        try:
            det = _sector_stocks(data_date, sel, short_n, long_n)
        except Exception as e:
            st.error(f'成分股計算失敗：{type(e).__name__}: {e}')
            return
    else:
        # 雲端：欄名在 JSON 裡是縮寫（省檔案大小），這裡還原
        det = [{'code': x['c'], 'name': x['n'], 'close': x['p'], 'value': x['v'],
                'w_short': x['ws'], 'w_long': x['wl'], 'chg': x['g']}
               for x in (PL.get('detail') or {}).get(sel, [])]
    if not det:
        st.info('這個類股在近期沒有成交資料。')
        return

    _W = [1.7, 1.0, 1.2, 1.1, 1.1, 1.1]
    hdr = st.columns(_W)
    for col, t in zip(hdr, ['股票', '最新價', '日均成交(億)', '占本類股%',
                            f'vs 近{long_n}日', f'近{short_n}日漲跌']):
        col.markdown(f"<div style='font-size:0.82rem;color:#94a3b8'>{t}</div>",
                     unsafe_allow_html=True)

    for r in det[:40]:
        cols = st.columns(_W)
        cols[0].markdown(f"**{r['code']}** {r['name']}")
        # 最新價跟著漲跌上色（台灣慣例：紅漲綠跌），與側邊欄價格摘要一致
        if r['close'] is None:
            cols[1].markdown('—')
        else:
            _cp = (UP if (r['chg'] or 0) >= 0 else DOWN) if r['chg'] is not None else FLAT
            _fmt = f"{r['close']:,.2f}" if r['close'] < 50 else f"{r['close']:,.1f}"
            cols[1].markdown(f"<span style='color:{_cp};font-weight:600'>{_fmt}</span>",
                             unsafe_allow_html=True)
        cols[2].markdown(f"{r['value']:,.1f}")
        cols[3].markdown(f"{r['w_short']:.1f}%")
        _dw = r['w_short'] - r['w_long']
        _c = UP if _dw > 0 else (DOWN if _dw < 0 else FLAT)
        cols[4].markdown(f"<span style='color:{_c}'>{_dw:+.1f}pp</span>",
                         unsafe_allow_html=True)
        if r['chg'] is None:
            cols[5].markdown('—')
        else:
            _c2 = UP if r['chg'] >= 0 else DOWN
            cols[5].markdown(f"<span style='color:{_c2}'>{r['chg']:+.2f}%</span>",
                             unsafe_allow_html=True)

    if PL is not None:
        st.caption(f'（雲端版每類股只匯出日均成交金額前 {PL.get("top_n", EXPORT_TOP_N)} 檔；'
                   f'完整名單請看本機版）')
    elif len(det) > 40:
        st.caption(f'（共 {len(det)} 檔，只列日均成交金額前 40 檔）')
    st.caption(f'最新價＝ {data_date} 收盤（盤後資料）。'
               f'「占本類股%」的分母是**這個類股自己**（不是全市場），'
               f'用來看類股內部的資金集中在哪幾檔。'
               f'「vs 近{long_n}日」為正代表該檔在類股內的占比上升。')
