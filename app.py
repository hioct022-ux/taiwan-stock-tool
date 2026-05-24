# ════════════════════════════════════════
# app.py　Streamlit 主介面
# 台股投資分析工具 v2.1
# ════════════════════════════════════════

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.expanduser('~/台股分析工具'))

from config import VERSION, VERSION_DATE
from database import (init_db, get_prices, get_fundamentals, get_chips,
                      get_watchlist, add_watchlist, remove_watchlist,
                      update_watchlist_tag, search_stock, get_notes,
                      save_note, update_user_note, get_last_update)
from indicators import calc_all
from scorer import full_score, get_grade, generate_auto_note
from scheduler import start_scheduler, get_data_status, manual_fetch

# ── 頁面設定 ────────────────────────────
st.set_page_config(
    page_title='台股投資分析工具',
    page_icon='📈',
    layout='wide',
    initial_sidebar_state='expanded'
)

# ── 自訂樣式 ────────────────────────────
st.markdown('''
<style>
    /* ── 縮小頂部空白 ── */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stAppViewContainer"] > section:first-child {
        padding-top: 0 !important;
    }
    /* ── 隱藏 Streamlit Cloud 的 GitHub / Fork 徽章（CSS 嘗試）── */
    .viewerBadge_container__r5tak,
    .viewerBadge_link__qRIco,
    [data-testid="stToolbarActions"],
    [data-testid="stDecoration"],
    #stDecoration,
    [class*="viewerBadge"],
    [class*="badge_container"],
    a[href*="github.com/streamlit"],
    a[href*="streamlit.io"] { display: none !important; }
    /* ── 隱藏頁尾 & 選單，但保留側邊欄展開按鈕 ── */
    #MainMenu  { visibility: hidden !important; }
    footer     { visibility: hidden !important; }
    header     { visibility: hidden !important; }
    /* 側邊欄收合後的展開箭頭保持可見 */
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        display: flex !important;
    }

    .main { background-color: #0d0f12; }
    /* 修正 metric 元件 */
    [data-testid="stMetric"] {
        background-color: #141720;
        border: 1px solid #252a38;
        border-radius: 10px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] { color: #8892a4 !important; }
    [data-testid="stMetricValue"] { color: #e2e8f0 !important; }
    [data-testid="stMetricDelta"] { color: #8892a4 !important; }
    /* 修正 info/success/warning/error 框 */
    [data-testid="stAlert"] {
        background-color: #1c2030 !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
    }
    .stAlert p { color: #e2e8f0 !important; }
    /* 修正 caption */
    [data-testid="stCaptionContainer"] p { color: #8892a4 !important; }
    /* 修正 expander */
    [data-testid="stExpander"] {
        background-color: #141720 !important;
        border: 1px solid #252a38 !important;
        border-radius: 10px !important;
    }
    /* 修正 text_area */
    [data-testid="stTextArea"] textarea {
        background-color: #1c2030 !important;
        color: #e2e8f0 !important;
        border: 1px solid #252a38 !important;
    }
    /* 修正 selectbox */
    [data-testid="stSelectbox"] select {
        background-color: #1c2030 !important;
        color: #e2e8f0 !important;
    }
    /* 修正 text_input */
    [data-testid="stTextInput"] input {
        background-color: #1c2030 !important;
        color: #e2e8f0 !important;
        border: 1px solid #252a38 !important;
    }
    /* 修正 tab */
    [data-testid="stTabs"] [data-baseweb="tab"] {
        background-color: #141720 !important;
        color: #8892a4 !important;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background-color: #1c2030 !important;
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8 !important;
    }
    /* 修正 dataframe */
    [data-testid="stDataFrame"] {
        background-color: #1c2030 !important;
    }
    /* 修正一般文字 */
    p, span, div { color: #e2e8f0; }
    h1, h2, h3, h4 { color: #e2e8f0 !important; }
    .status-bar { padding: 8px 16px; border-radius: 8px; margin-bottom: 16px;
                  font-size: 13px; font-weight: 500; color: #e2e8f0; }
    .grade-box { text-align: center; padding: 20px; border-radius: 12px;
                 border: 1px solid; margin-bottom: 16px;
                 background-color: transparent; color: #e2e8f0; }
    .condition-pass { color: #22c55e; font-size: 13px; margin: 4px 0; }
    .condition-fail { color: #ef4444; font-size: 13px; margin: 4px 0; }
    .condition-warn { color: #f59e0b; font-size: 13px; margin: 4px 0; }
    .note-box { background-color: #141720; border-radius: 10px;
                padding: 16px; margin: 8px 0; border-left: 3px solid #38bdf8;
                color: #e2e8f0; }
    .export-box { background-color: #141720; border-radius: 10px;
                  padding: 16px; font-family: monospace; font-size: 12px;
                  color: #e2e8f0; white-space: pre-wrap; line-height: 1.8; }
/* ── 修正框外偏淡文字 ─────────────────── */
/* 所有 widget label */
label { color: #f0f4f8 !important; }
.stTextInput  > label,
.stSelectbox  > label,
.stTextArea   > label,
.stRadio      > label,
.stCheckbox   > label,
.stSlider     > label,
.stNumberInput > label,
.stDateInput  > label,
.stMultiselect > label { color: #f0f4f8 !important; }
/* 側邊欄所有文字 */
[data-testid="stSidebar"] * { color: #f0f4f8 !important; }
[data-testid="stSidebar"] [data-testid="stMetricLabel"],
[data-testid="stSidebar"] [data-testid="stMetricDelta"] { color: #8892a4 !important; }
/* Markdown 內文 */
.stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
.stMarkdown h4, .stMarkdown h5 { color: #f0f4f8 !important; }
/* 一般文字加強 */
p, span, div, li { color: #f0f4f8; }
h1, h2, h3, h4, h5 { color: #f0f4f8 !important; }
/* Button 文字 */
[data-testid="stBaseButton-secondary"] p { color: #f0f4f8 !important; }
/* SelectBox 選項文字 */
[data-baseweb="select"] span { color: #f0f4f8 !important; }
/* Input placeholder */
input::placeholder, textarea::placeholder { color: #6b7280 !important; }
/* Alert 框內文字（補強） */
[data-testid="stAlert"] * { color: #f0f4f8 !important; }
/* Caption 保持偏淡（刻意設計） */
[data-testid="stCaptionContainer"] p { color: #8892a4 !important; }
/* st.info / st.success / st.warning 圖示旁文字 */
[data-testid="stAlertContainer"] p,
[data-testid="stAlertContainer"] span { color: #f0f4f8 !important; }
/* Expander header */
[data-testid="stExpander"] summary span { color: #f0f4f8 !important; }
/* Dataframe 文字 */
[data-testid="stDataFrame"] * { color: #f0f4f8 !important; }

</style>
<script>
(function() {
    function removeBadges() {
        // 移除所有包含 github.com 或 streamlit.io 連結的元素
        document.querySelectorAll('a').forEach(function(a) {
            var href = a.getAttribute('href') || '';
            if (href.includes('github.com') || href.includes('streamlit.io')) {
                var el = a;
                // 往上找到最外層的 badge 容器再移除
                for (var i = 0; i < 5; i++) {
                    if (el.parentElement && el.parentElement !== document.body) {
                        el = el.parentElement;
                    } else { break; }
                }
                el.style.display = 'none';
            }
        });
        // 直接移除已知 class/id
        ['stDecoration','MainMenu'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    }
    // 頁面載入後執行，並監聽 DOM 變化持續清除
    var observer = new MutationObserver(removeBadges);
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(removeBadges, 500);
    setTimeout(removeBadges, 2000);
})();
</script>
''', unsafe_allow_html=True)

# ── 初始化 ──────────────────────────────
init_db()
start_scheduler()


# ── 雲端版：從 GitHub 載入資料 ───────────
def load_from_github_to_db(code):
    """
    從 GitHub 讀取 JSON 資料並存入本機 SQLite。
    適用於 Streamlit Cloud（本機 DB 是空的）。
    """
    try:
        from github_sync import load_stock_data_raw
        from database import save_prices, save_fundamental, save_chips, save_stock_info
        data = load_stock_data_raw(code)
        if not data:
            return False
        if data.get('prices'):
            save_prices(code, data['prices'])
        if data.get('fundamentals'):
            for f in data['fundamentals']:
                save_fundamental(code, f['date'],
                                 f.get('eps_ttm', 0), f.get('pe', 0),
                                 f.get('pb', 0), f.get('dividend_yield', 0))
        if data.get('chips'):
            for c in data['chips']:
                save_chips(code, c['date'], c)
        return True
    except Exception as e:
        print(f'從 GitHub 載入 {code} 失敗：{e}')
        return False

# ── 側邊欄 ──────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(f'### 📈 台股分析工具 {VERSION}')
        st.markdown('---')

        # 資料狀態
        status = get_data_status()
        color_map = {'ok':'green','pending':'orange','error':'red','holiday':'blue'}
        st.markdown(
            f'<div class="status-bar" style="background:rgba(0,0,0,0.3);'
            f'border-left:4px solid {color_map.get(status["status"],"gray")}">'
            f'{status["label"]}</div>',
            unsafe_allow_html=True
        )

        # 手動更新按鈕（僅本機版顯示，雲端版無法連台灣交易所）
        is_cloud = os.environ.get('STREAMLIT_SHARING_MODE') or \
                   os.environ.get('IS_STREAMLIT_CLOUD') or \
                   not os.path.exists(os.path.join(os.path.dirname(__file__), 'config_local.py'))
        if not is_cloud:
            if st.button('🔄 手動更新資料', use_container_width=True):
                with st.spinner('更新中，請稍候...'):
                    t = manual_fetch()
                    t.join(timeout=60)
                st.success('更新完成！')
                st.rerun()
        else:
            st.info('📡 資料由 Mac 每日自動同步\n\n如資料過舊，請在 Mac 版手動更新', icon='ℹ️')

        st.markdown('---')

        # 股票搜尋
        st.markdown('#### 🔍 搜尋股票')
        keyword = st.text_input('輸入代碼或名稱', placeholder='例如：2330 或 台積電')
        if keyword:
            results = search_stock(keyword)
            if results:
                options = {f"{r['code']} {r['name']}": r['code'] for r in results}
                selected = st.selectbox('搜尋結果', list(options.keys()))
                if st.button('查看此股票', use_container_width=True):
                    st.session_state['current_code'] = options[selected]
                    st.rerun()
            else:
                st.warning('找不到符合的股票，請確認代碼是否正確')

        st.markdown('---')

        # 自選股清單
        st.markdown('#### ⭐ 自選股清單')
        watchlist = get_watchlist()

        if watchlist:
            for w in watchlist:
                col1, col2 = st.columns([3, 1])
                with col1:
                    tag_color = '🟢' if w['tag'] == '長期' else '🟡' if w['tag'] == '觀察中' else '⚪'
                    if st.button(
                        f"{tag_color} {w['code']} {w['name']}",
                        key=f"watch_{w['code']}",
                        use_container_width=True
                    ):
                        st.session_state['current_code'] = w['code']
                        st.rerun()
                with col2:
                    if st.button('✕', key=f"del_{w['code']}"):
                        remove_watchlist(w['code'])
                        st.rerun()
        else:
            st.info('尚無自選股，搜尋後加入')

        # 新增自選股
        st.markdown('---')
        st.markdown('#### ➕ 新增自選股')
        new_code = st.text_input('股票代碼', placeholder='例如：2330')
        new_name = st.text_input('股票名稱', placeholder='例如：台積電')
        new_tag  = st.selectbox('標籤', ['長期', '觀察中', '其他'])
        if st.button('加入自選股', use_container_width=True):
            if new_code and new_name:
                add_watchlist(new_code.strip(), new_name.strip(), new_tag)
                st.success(f'已加入 {new_code} {new_name}')
                st.rerun()
            else:
                st.error('請填入代碼和名稱')

# ── 圖表：價格走勢 ───────────────────────
def render_price_chart(ind, name):
    dates   = ind.get('dates', [])
    closes  = ind.get('closes', [])
    ma5s    = ind.get('ma5_series', [])
    ma20s   = ind.get('ma20_series', [])
    ma60s   = ind.get('ma60_series', [])
    volumes = ind.get('volumes', [])

    if not dates:
        st.warning('無法載入走勢圖，歷史資料不足')
        return

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3]
    )

    # 收盤價
    fig.add_trace(go.Scatter(
        x=dates, y=closes, name='收盤價',
        line=dict(color='#38bdf8', width=1.5)
    ), row=1, col=1)

    # 均線
    fig.add_trace(go.Scatter(
        x=dates, y=ma5s, name='MA5',
        line=dict(color='#f59e0b', width=1),
        connectgaps=True
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=ma20s, name='MA20',
        line=dict(color='#a78bfa', width=1),
        connectgaps=True
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=ma60s, name='MA60',
        line=dict(color='#22c55e', width=1),
        connectgaps=True
    ), row=1, col=1)

    # 布林通道
    bb_upper = ind.get('bb_upper')
    bb_lower = ind.get('bb_lower')
    if bb_upper and bb_lower and len(dates) >= 20:
        fig.add_trace(go.Scatter(
            x=[dates[-1]], y=[bb_upper],
            name=f'布林上軌({bb_upper})',
            mode='markers',
            marker=dict(color='#ef4444', size=8, symbol='line-ew')
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=[dates[-1]], y=[bb_lower],
            name=f'布林下軌({bb_lower})',
            mode='markers',
            marker=dict(color='#22c55e', size=8, symbol='line-ew')
        ), row=1, col=1)

    # 成交量
    avg_vol = ind.get('avg_vol_20', 0)
    colors  = ['#22c55e' if c >= (closes[i-1] if i > 0 else c) else '#ef4444'
               for i, c in enumerate(closes)]
    fig.add_trace(go.Bar(
        x=dates, y=volumes, name='成交量',
        marker_color=colors, opacity=0.6
    ), row=2, col=1)

    if avg_vol:
        fig.add_hline(
            y=avg_vol, line_dash='dash',
            line_color='#f59e0b', opacity=0.7,
            annotation_text=f'均量({avg_vol:,})',
            row=2, col=1
        )

    fig.update_layout(
        title=f'{name} 近3個月走勢（65個交易日）',
        paper_bgcolor='#0d0f12',
        plot_bgcolor='#141720',
        font=dict(color='#e2e8f0', size=11),
        height=500,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        xaxis=dict(showgrid=True, gridcolor='#252a38'),
        yaxis=dict(showgrid=True, gridcolor='#252a38'),
        xaxis2=dict(showgrid=True, gridcolor='#252a38'),
        yaxis2=dict(showgrid=True, gridcolor='#252a38'),
        margin=dict(l=0, r=0, t=40, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)

# ── 頁籤一：技術面 ──────────────────────
def render_technical(result, name):
    ind   = result['indicators']
    close = result['close']

    # 走勢圖
    render_price_chart(ind, name)

    st.markdown('---')
    st.markdown('#### 技術指標')

    col1, col2, col3 = st.columns(3)

    # 均線
    ma5  = ind.get('ma5')
    ma20 = ind.get('ma20')
    ma60 = ind.get('ma60')
    ma_trend = ind.get('ma_trend')

    with col1:
        st.markdown('**均線狀態**')
        trend_map = {
            'bullish':  ('多頭排列 ↑', '#22c55e'),
            'bearish':  ('空頭排列 ↓', '#ef4444'),
            'sideways': ('均線糾結 →', '#f59e0b')
        }
        label, color = trend_map.get(ma_trend, ('資料不足', '#6b7280'))
        st.markdown(f'<span style="color:{color};font-weight:600">{label}</span>',
                    unsafe_allow_html=True)
        if ma5:  st.metric('MA5',  f'{ma5}元',  delta=f'{close-ma5:+.2f}' if ma5 else None)
        if ma20: st.metric('MA20', f'{ma20}元', delta=f'{close-ma20:+.2f}' if ma20 else None)
        if ma60: st.metric('MA60', f'{ma60}元', delta=f'{close-ma60:+.2f}' if ma60 else None)

        # 說明文字
        if ma_trend == 'bullish':
            st.info(f'MA5({ma5}) > MA20({ma20}) > MA60({ma60})，'
                    f'三條均線由上到下排列，代表短中長期持有者都是獲利狀態，趨勢向上。'
                    f'近3個月（65個交易日）維持多頭排列是偏正面的訊號。')
        elif ma_trend == 'bearish':
            st.warning(f'MA5({ma5}) < MA20({ma20}) < MA60({ma60})，'
                       f'均線空頭排列，代表短中長期持有者都是虧損狀態，趨勢向下，建議謹慎。')
        else:
            st.warning('均線糾結，方向不明確。建議等待均線方向確立後再操作，'
                       '通常需要觀察3個交易日以上確認趨勢。')

    with col2:
        st.markdown('**動能指標**')
        rsi = ind.get('rsi')
        k   = ind.get('k')
        d   = ind.get('d')

        if rsi:
            rsi_color = '#ef4444' if rsi > 80 else '#22c55e' if rsi < 30 else '#38bdf8'
            st.markdown(f'RSI(14)：<span style="color:{rsi_color};font-size:20px;font-weight:700">'
                        f'{rsi}</span>', unsafe_allow_html=True)
            if rsi > 80:
                st.error(f'RSI={rsi} 超過80，已進入超買區間。'
                         f'根據近1年（250個交易日）歷史，RSI超過80後5個交易日內回檔機率較高，'
                         f'建議不要追買，可考慮減碼。')
            elif rsi > 70:
                st.warning(f'RSI={rsi} 介於70～80，動能偏強但接近警戒區，需留意回檔風險。')
            elif rsi >= 40:
                st.success(f'RSI={rsi} 介於40～70，動能健康，趨勢正常，不需要特別擔心。')
            elif rsi >= 30:
                st.warning(f'RSI={rsi} 介於30～40，動能偏弱，建議觀察是否持續走跌。')
            else:
                st.success(f'RSI={rsi} 低於30，已進入超賣區間。'
                           f'歷史上此位置常出現反彈機會，但需確認其他指標配合。')

        if k and d:
            st.metric('KD', f'K={k} / D={d}')
            if k > d:
                st.success(f'K值({k})在D值({d})上方，KD黃金交叉，短期偏多。')
            else:
                st.warning(f'K值({k})在D值({d})下方，KD死亡交叉，短期偏空。')

    with col3:
        st.markdown('**量價與其他**')
        vol_ratio = ind.get('vol_ratio')
        macd_dif  = ind.get('macd_dif')
        macd_def  = ind.get('macd_def')
        macd_hist = ind.get('macd_hist')
        pos_65    = ind.get('pos_65')
        cons_days = ind.get('consecutive_days')
        cons_dir  = ind.get('consecutive_dir')

        if vol_ratio:
            vol_color = '#22c55e' if vol_ratio >= 1.5 else '#ef4444' if vol_ratio < 0.8 else '#38bdf8'
            st.markdown(f'量能比：<span style="color:{vol_color};font-size:18px;font-weight:700">'
                        f'{vol_ratio}x</span>', unsafe_allow_html=True)
            avg_vol = ind.get('avg_vol_20', 0)
            last_vol = ind.get('last_vol', 0)
            if vol_ratio >= 2.0:
                st.error(f'今日成交量（{last_vol:,}張）是近20個交易日均量（{avg_vol:,}張）的'
                         f'{vol_ratio}倍，異常放量，需特別注意方向。')
            elif vol_ratio >= 1.5:
                st.success(f'今日成交量（{last_vol:,}張）是近20個交易日均量（{avg_vol:,}張）的'
                           f'{vol_ratio}倍，明顯放量，買盤積極。')
            elif vol_ratio >= 1.0:
                st.info(f'今日成交量是近20個交易日均量的{vol_ratio}倍，溫和放量，量能正常。')
            else:
                st.warning(f'今日成交量是近20個交易日均量的{vol_ratio}倍，明顯縮量，'
                           f'市場參與意願下降。')

        if macd_dif and macd_def:
            st.metric('MACD', f'DIF={macd_dif} / DEF={macd_def}',
                      delta=f'柱={macd_hist}' if macd_hist else None)
            if macd_dif > macd_def:
                st.success('MACD多頭，DIF在DEF上方，中期趨勢偏多。')
            else:
                st.warning('MACD空頭，DIF在DEF下方，中期趨勢偏空。')

        if pos_65 is not None:
            st.metric('近3個月區間位置', f'{pos_65}%')

        if cons_days and cons_dir:
            dir_str = '上漲' if cons_dir == 'up' else '下跌'
            dir_color = '#22c55e' if cons_dir == 'up' else '#ef4444'
            st.markdown(f'連續<span style="color:{dir_color};font-weight:700">'
                        f'{cons_days}個交易日{dir_str}</span>',
                        unsafe_allow_html=True)

# ── 頁籤二：基本面 ──────────────────────
def render_fundamental(result, code, name):
    fund = result['fund']
    close = result['close']

    pe  = fund.get('pe')
    pb  = fund.get('pb')
    div = fund.get('dividend_yield')
    eps = fund.get('eps_ttm')

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('**獲利能力**')

        if eps is not None:
            eps_color = '#22c55e' if eps > 10 else '#ef4444' if eps < 0 else '#38bdf8'
            st.markdown(f'EPS（近四季TTM）：'
                        f'<span style="color:{eps_color};font-size:22px;font-weight:700">'
                        f'{eps:.2f}元</span>', unsafe_allow_html=True)
            if eps < 0:
                st.error(f'EPS為負（{eps:.2f}元），公司目前處於虧損狀態，'
                         f'投資需特別謹慎，需確認虧損是否為短期或長期結構性問題。')
            elif eps < 1:
                st.warning(f'EPS僅{eps:.2f}元，獲利能力偏弱，'
                           f'建議確認公司是否有獲利改善的計畫。')
            elif eps < 5:
                st.info(f'EPS {eps:.2f}元，獲利正常，維持穩定獲利是基本要求。')
            elif eps < 15:
                st.success(f'EPS {eps:.2f}元，獲利能力良好，'
                           f'代表公司具備一定的競爭優勢。')
            else:
                st.success(f'EPS {eps:.2f}元，獲利能力極強，'
                           f'是選股的重要正面條件。')

        if pe:
            pe_color = '#22c55e' if pe < 15 else '#ef4444' if pe > 50 else '#f59e0b'
            st.markdown(f'本益比（PE）：'
                        f'<span style="color:{pe_color};font-size:22px;font-weight:700">'
                        f'{pe:.1f}倍</span>', unsafe_allow_html=True)
            st.info(f'本益比代表你花多少錢買1元的獲利。{pe:.1f}倍代表以現在股價買進，'
                    f'假設獲利不變，約需{pe:.0f}年回本。'
                    f'台股近1年整體平均本益比約15～20倍。')
            if pe < 10:
                st.success(f'本益比{pe:.1f}倍極低，評價非常便宜，但需確認獲利是否持續。')
            elif pe < 15:
                st.success(f'本益比{pe:.1f}倍偏低，評價便宜，低於台股平均水準。')
            elif pe < 20:
                st.info(f'本益比{pe:.1f}倍合理，符合台股平均水準（15～20倍）。')
            elif pe < 30:
                st.warning(f'本益比{pe:.1f}倍略高，需要較高的獲利成長來支撐評價。')
            elif pe < 50:
                st.warning(f'本益比{pe:.1f}倍偏高，市場預期高成長，若成長不如預期股價壓力大。')
            else:
                st.error(f'本益比{pe:.1f}倍極高，評價昂貴，需要非常高的獲利成長支撐，風險較高。')

    with col2:
        st.markdown('**配息與資產**')

        if div:
            div_color = '#22c55e' if div > 5 else '#f59e0b' if div > 3 else '#6b7280'
            st.markdown(f'殖利率：'
                        f'<span style="color:{div_color};font-size:22px;font-weight:700">'
                        f'{div:.2f}%</span>', unsafe_allow_html=True)
            st.info(f'殖利率代表每年可領到股息佔買入成本的比例。'
                    f'台灣銀行1年定存約1.5%，台股平均殖利率約3.2%。')
            if div > 6:
                st.success(f'殖利率{div:.2f}%極高，遠高於定存（1.5%）和市場平均（3.2%）。'
                           f'需確認公司是否有能力持續配息。')
            elif div > 5:
                st.success(f'殖利率{div:.2f}%很高，高於市場平均（3.2%），配息吸引力強。')
            elif div > 3:
                st.info(f'殖利率{div:.2f}%正常，高於定存利率，配息合理。')
            elif div > 1:
                st.warning(f'殖利率{div:.2f}%偏低，配息吸引力不高。')
            else:
                st.warning(f'殖利率{div:.2f}%極低，幾乎沒有配息吸引力，'
                           f'需以資本利得為主要報酬來源。')

        if pb:
            st.metric('股價淨值比（PB）', f'{pb:.2f}倍')
            if pb < 1:
                st.success(f'PB={pb:.2f}倍，股價低於帳面價值，理論上有安全邊際。')
            elif pb < 1.5:
                st.success(f'PB={pb:.2f}倍偏低，評價合理偏低。')
            elif pb < 3:
                st.info(f'PB={pb:.2f}倍合理，在正常範圍內。')
            elif pb < 5:
                st.warning(f'PB={pb:.2f}倍偏高，需要較強的獲利能力支撐。')
            else:
                st.error(f'PB={pb:.2f}倍極高，需要非常強的獲利能力才能支撐此評價。')# ── 頁籤三：籌碼面 ──────────────────────
def render_chips(result, code, name, chips_list):
    st.markdown('#### 三大法人')

    if not chips_list:
        st.warning('籌碼資料不足，請先更新資料')
        return

    recent5  = chips_list[-5:]  if len(chips_list) >= 5  else chips_list
    recent20 = chips_list[-20:] if len(chips_list) >= 20 else chips_list
    recent65 = chips_list[-65:] if len(chips_list) >= 65 else chips_list

    foreign_net5  = sum(r.get('foreign_net', 0) for r in recent5)
    foreign_net20 = sum(r.get('foreign_net', 0) for r in recent20)
    trust_net5    = sum(r.get('trust_net',   0) for r in recent5)
    dealer_net5   = sum(r.get('dealer_net',  0) for r in recent5)

    # 近3個月買超天數統計
    foreign_buy_days = sum(1 for r in recent65 if r.get('foreign_net', 0) > 0)
    foreign_sell_days = len(recent65) - foreign_buy_days

    col1, col2, col3 = st.columns(3)
    with col1:
        color = '#22c55e' if foreign_net5 > 0 else '#ef4444'
        st.markdown(f'**外資近5個交易日**')
        st.markdown(f'<span style="color:{color};font-size:20px;font-weight:700">'
                    f'{foreign_net5:+,}張</span>', unsafe_allow_html=True)
        st.caption(f'近20個交易日（1個月）：{foreign_net20:+,}張')
        st.caption(f'近3個月：買超{foreign_buy_days}天 / 賣超{foreign_sell_days}天')
        if foreign_net5 > 10000:
            st.success('外資大量買超，法人積極佈局，是強烈正面訊號。')
        elif foreign_net5 > 3000:
            st.success('外資買超，法人偏多，籌碼面偏正面。')
        elif foreign_net5 > 0:
            st.info('外資小幅買超，法人態度偏多但力道不強。')
        elif foreign_net5 > -3000:
            st.warning('外資小幅賣超，法人態度偏空但力道不強。')
        else:
            st.error('外資大量賣超，法人積極出脫，需特別注意。')

    with col2:
        color = '#22c55e' if trust_net5 > 0 else '#ef4444'
        st.markdown('**投信近5個交易日**')
        st.markdown(f'<span style="color:{color};font-size:20px;font-weight:700">'
                    f'{trust_net5:+,}張</span>', unsafe_allow_html=True)
        if trust_net5 > 1000:
            st.success('投信積極買超，國內法人看好。')
        elif trust_net5 > 0:
            st.info('投信小幅買超。')
        elif trust_net5 > -1000:
            st.warning('投信小幅賣超。')
        else:
            st.error('投信積極賣超，國內法人看空。')

    with col3:
        color = '#22c55e' if dealer_net5 > 0 else '#ef4444'
        st.markdown('**自營商近5個交易日**')
        st.markdown(f'<span style="color:{color};font-size:20px;font-weight:700">'
                    f'{dealer_net5:+,}張</span>', unsafe_allow_html=True)
        st.caption('自營商為短線操作，參考權重較低')

    st.markdown('---')
    st.markdown('#### 融資融券')

    col1, col2 = st.columns(2)
    with col1:
        if len(chips_list) >= 2:
            margin_now  = chips_list[-1].get('margin_balance', 0)
            margin_20   = chips_list[-20].get('margin_balance', 0) if len(chips_list) >= 20 else margin_now
            margin_chg  = ((margin_now - margin_20) / margin_20 * 100) if margin_20 > 0 else 0
            chg_color   = '#22c55e' if margin_chg < 0 else '#ef4444'
            st.markdown('**融資餘額**')
            st.metric('目前融資餘額', f'{margin_now:,}張',
                      delta=f'{margin_chg:+.1f}% 較20個交易日前')
            st.info(f'融資是投資人向券商借錢買股票。'
                    f'融資餘額{"減少" if margin_chg < 0 else "增加"}{abs(margin_chg):.1f}%，'
                    f'{"代表借錢追高行為減少，籌碼趨穩，偏正面。" if margin_chg < 0 else "代表借錢追高行為增加，需留意斷頭風險。"}')

    with col2:
        if len(chips_list) >= 2:
            short_now = chips_list[-1].get('short_balance', 0)
            short_20  = chips_list[-20].get('short_balance', 0) if len(chips_list) >= 20 else short_now
            short_chg = ((short_now - short_20) / short_20 * 100) if short_20 > 0 else 0
            st.markdown('**融券餘額**')
            st.metric('目前融券餘額', f'{short_now:,}張',
                      delta=f'{short_chg:+.1f}% 較20個交易日前')
            st.info(f'融券是投資人借股票來賣（放空）。'
                    f'融券{"增加" if short_chg > 0 else "減少"}{abs(short_chg):.1f}%，'
                    f'{"代表看空的投資人增加，需注意。" if short_chg > 0 else "代表空方回補，偏正面。"}')

    st.markdown('---')
    st.markdown('#### 持股結構（估算）')

    ownership = {
        'foreign': 52, 'trust': 5, 'dealer': 2,
        'director': 12, 'retail': 29
    }
    ETF_HOLDINGS = {
        '2049':{'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'0050','name':'元大台灣50','type':'市值型'}],'thematic':[{'code':'00737','name':'國泰AI機器人','type':'AI/機器人'},{'code':'00896','name':'中信綠能及電動車','type':'工業自動化'},{'code':'00911','name':'兆豐洲際半導體','type':'半導體'}],'active':[{'code':'00985A','name':'主動野村台灣50','type':'主動型'},{'code':'00993A','name':'主動安聯台灣','type':'主動型'}],'note':'上銀為精密機械/機器人龍頭，AI機器人相關主題ETF大量布局'},
        '2408':{'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'0050','name':'元大台灣50','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[{'code':'00982A','name':'主動群益台灣強棒','type':'主動型'},{'code':'00992A','name':'主動群益科技創新','type':'主動型'}],'note':'南亞科為DRAM龍頭，半導體主題ETF必配'},
        '2308':{'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體/AI電源'},{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00935','name':'野村臺灣新科技50','type':'新科技'}],'active':[{'code':'00985A','name':'主動野村台灣50','type':'主動型'},{'code':'00990A','name':'主動元大AI新經濟','type':'主動型'}],'note':'台達電為AI電源/散熱龍頭，幾乎所有科技、AI主題ETF必配'},
        '2301':{'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00850','name':'元大臺灣ESG永續','type':'ESG型'}],'thematic':[{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[{'code':'00993A','name':'主動安聯台灣','type':'主動型'}],'note':'光寶科殖利率高，高股息型ETF大量持有'},
        '2317':{'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'}],'active':[{'code':'00981A','name':'主動統一台股增長','type':'主動型'},{'code':'00982A','name':'主動群益台灣強棒','type':'主動型'}],'note':'鴻海為大型藍籌股，市值型與高息型ETF均大量配置'},
        '1476':{'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[{'code':'00980A','name':'主動野村臺灣優選','type':'主動型'},{'code':'00993A','name':'主動安聯台灣','type':'主動型'}],'note':'儒鴻為紡織龍頭，殖利率穩定，高股息ETF重要成分股'},
        }
    etf = ETF_HOLDINGS.get(code, {'passive':[],'thematic':[],'active':[],'note':''})
    labels = ['外資', '投信', '自營', '董監', '散戶']
    values = [ownership['foreign'], ownership['trust'],
              ownership['dealer'], ownership['director'], ownership['retail']]
    colors = ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#6b7280']

    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        st.markdown('**持股結構**')
        fig1 = go.Figure(go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            hole=0.4,
            textinfo='label+percent'
        ))
        fig1.update_layout(
            paper_bgcolor='#0d0f12',
            font=dict(color='#e2e8f0'),
            height=280,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=True
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col_pie2:
        st.markdown('**ETF 持股類型分布**')
        etf_labels = ['被動型（市值/指數）', '主題型（AI/產業/高息）', '主動型']
        etf_values = [
            len(etf.get('passive', [])),
            len(etf.get('thematic', [])),
            len(etf.get('active', []))
        ]
        etf_colors = ['#38bdf8', '#a78bfa', '#22c55e']
        if sum(etf_values) > 0:
            fig2 = go.Figure(go.Pie(
                labels=etf_labels, values=etf_values,
                marker=dict(colors=etf_colors),
                hole=0.4,
                textinfo='label+value'
            ))
            fig2.update_layout(
                paper_bgcolor='#0d0f12',
                font=dict(color='#e2e8f0'),
                height=280,
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=True
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info('此股票暫無 ETF 持股資料')

    retail = ownership['retail']
    st.info(f'散戶持股比例約{retail}%。'
            f'當散戶持股持續減少而外資同步增加時，'
            f'代表籌碼從散戶轉移到法人手中，'
            f'根據近1年（250個交易日）統計，這種情況下'
            f'未來20個交易日股價上漲機率約68%。')
    st.markdown('---')
    st.markdown('#### ETF 持股')

    

    if etf['passive']:
        st.markdown('**被動型（市值／指數型）**')
        cols = st.columns(3)
        for i, e in enumerate(etf['passive']):
            with cols[i % 3]:
                st.markdown(f'''
                <div style="background:#1c2030;border-radius:8px;padding:8px 10px;
                border:1px solid #252a38;margin-bottom:6px">
                <div style="font-size:10px;color:#4a5568">{e["code"]}</div>
                <div style="font-size:12px;font-weight:500">{e["name"]}</div>
                <div style="font-size:10px;color:#38bdf8">{e["type"]}</div>
                </div>''', unsafe_allow_html=True)

    if etf['thematic']:
        st.markdown('**主題型（AI／產業／高息）**')
        cols = st.columns(3)
        for i, e in enumerate(etf['thematic']):
            with cols[i % 3]:
                st.markdown(f'''
                <div style="background:#1c2030;border-radius:8px;padding:8px 10px;
                border:1px solid #252a38;margin-bottom:6px">
                <div style="font-size:10px;color:#4a5568">{e["code"]}</div>
                <div style="font-size:12px;font-weight:500">{e["name"]}</div>
                <div style="font-size:10px;color:#a78bfa">{e["type"]}</div>
                </div>''', unsafe_allow_html=True)

    if etf['active']:
        st.markdown('**主動型**')
        cols = st.columns(3)
        for i, e in enumerate(etf['active']):
            with cols[i % 3]:
                st.markdown(f'''
                <div style="background:#1c2030;border-radius:8px;padding:8px 10px;
                border:1px solid #252a38;margin-bottom:6px">
                <div style="font-size:10px;color:#4a5568">{e["code"]}</div>
                <div style="font-size:12px;font-weight:500">{e["name"]}</div>
                <div style="font-size:10px;color:#22c55e">{e["type"]}</div>
                </div>''', unsafe_allow_html=True)

    if etf.get('note'):
        st.info(f'💡 {etf["note"]}')

# ── 頁籤四：綜合評分 ────────────────────
def render_score(result, code, name):
    total = result['total_score']
    grade = result['grade']
    ind   = result['indicators']
    close = result['close']

    grade_colors = {
        '強力買進': '#22c55e', '偏多操作': '#86efac',
        '中性觀望': '#facc15', '偏空謹慎': '#f97316',
        '風險偏高': '#ef4444'
    }
    gc = grade_colors.get(grade, '#6b7280')

    # 總分顯示
    st.markdown(
        f'<div class="grade-box" style="border-color:{gc}">'
        f'<div style="font-size:64px;font-weight:700;color:{gc}">{total}</div>'
        f'<div style="font-size:18px;font-weight:600;color:{gc}">{grade}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # 分項評分
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('基本面（40%）', f'{result["fund_score"]}分')
        for r in result['fund_reasons'][:3]:
            st.caption(f'・{r}')
    with col2:
        st.metric('技術面（35%）', f'{result["tech_score"]}分')
        for r in result['tech_reasons'][:3]:
            st.caption(f'・{r}')
    with col3:
        st.metric('籌碼面（25%）', f'{result["chip_score"]}分')
        for r in result['chip_reasons'][:3]:
            st.caption(f'・{r}')

    st.markdown('---')
    st.markdown('#### 進出場建議')

    buy_low   = ind.get('buy_low')
    buy_high  = ind.get('buy_high')
    target    = ind.get('target')
    stop_loss = ind.get('stop_loss')
    ma20      = ind.get('ma20')
    high_65   = ind.get('high_65')
    bb_upper  = ind.get('bb_upper')

    col1, col2, col3 = st.columns(3)
    with col1:
        if buy_low and buy_high:
            potential = round((buy_high - close) / close * 100, 1) if close else 0
            st.metric('買進參考區間', f'{buy_low}～{buy_high}元')
            st.info(f'計算方式：MA20（{ma20}元）上下各1%。'
                    f'在此區間買進，風險相對較低，'
                    f'因為跌破MA20才代表趨勢改變。')
    with col2:
        if target:
            potential = round((target - close) / close * 100, 1) if close else 0
            st.metric('目標參考價', f'{target}元', delta=f'潛在+{potential}%')
            st.info(f'計算方式：近3個月最高點（{high_65}元）'
                    f'與布林上軌（{bb_upper}元）取較低者。'
                    f'到達此價位可考慮分批獲利了結。')
    with col3:
        if stop_loss:
            loss_pct = round((stop_loss - close) / close * 100, 1) if close else 0
            st.metric('停損參考價', f'{stop_loss}元', delta=f'{loss_pct}%')
            st.error(f'計算方式：買進區間下緣（{buy_low}元）× 0.92。'
                     f'跌到此價位代表原先判斷可能是錯的，'
                     f'建議出場保護資金，等待下次機會。')

    st.markdown('---')
    st.markdown('#### 買進條件')
    for c in result['buy_conditions']:
        css = 'condition-pass' if c['status'] == 'pass' else \
              'condition-fail' if c['status'] == 'fail' else 'condition-warn'
        st.markdown(f'<div class="{css}">{c["text"]}</div>',
                    unsafe_allow_html=True)

    st.markdown('#### 出場條件監控')
    for c in result['sell_conditions']:
        css = 'condition-pass' if c['status'] == 'pass' else 'condition-warn'
        st.markdown(f'<div class="{css}">{c["text"]}</div>',
                    unsafe_allow_html=True)

# ── 頁籤五：備註欄 ──────────────────────
def render_notes(result, code, name):
    fund_reasons = result.get('fund_reasons', [])
    tech_reasons = result.get('tech_reasons', [])
    chip_reasons = result.get('chip_reasons', [])
    ind  = result['indicators']
    fund = result['fund']

    # 生成自動摘要
    auto_note = generate_auto_note(
        code, name, result['close'],
        result['total_score'],
        result['fund_score'], result['tech_score'], result['chip_score'],
        fund_reasons, tech_reasons, chip_reasons,
        ind, fund
    )

    st.markdown('#### 系統自動摘要')
    st.markdown(
        f'<div class="note-box">{auto_note.replace(chr(10), "<br>")}</div>',
        unsafe_allow_html=True
    )

    st.markdown('---')
    st.markdown('#### 我的筆記')

    today = datetime.now().strftime('%Y-%m-%d')
    user_note = st.text_area(
        '在此輸入你的觀察和想法',
        height=150,
        placeholder='例如：法說會後外資加碼，持續觀察...'
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button('💾 儲存筆記', use_container_width=True):
            save_note(code, auto_note, user_note)
            st.success('筆記已儲存')

    st.markdown('---')
    st.markdown('#### 歷史筆記')

    notes = get_notes(code, limit=10)
    if notes:
        for n in notes:
            with st.expander(f"📅 {n['date']}　{n['auto_note'][:30]}..."):
                st.markdown('**系統摘要：**')
                st.text(n['auto_note'])
                if n['user_note']:
                    st.markdown('**我的筆記：**')
                    st.info(n['user_note'])
    else:
        st.info('尚無歷史筆記')

# ── 頁籤六：程式說明 ────────────────────
def render_doc():
    st.markdown(f'''
# 台股投資分析工具 {VERSION}　使用說明

**版本**：{VERSION}　**建立日期**：{VERSION_DATE}

---

## 一、這個程式是什麼？

本工具整合技術面、基本面、籌碼面三個維度，
幫助投資人客觀評估股票現況，減少情緒性決策。
所有判斷邏輯透明可查，評分規則固定且可驗證。

---

## 二、資料來源

| 資料類型 | 來源 | 更新時間 |
|---------|------|---------|
| 收盤價、成交量 | 台灣證交所（TWSE）OpenAPI | 每日收盤後約15:30 |
| PE / 殖利率 / PB | 台灣證交所（TWSE）OpenAPI | 每日收盤後 |
| 三大法人買賣超 | 台灣證交所（TWSE） | 每日收盤後 |
| 融資融券 | 台灣證交所（TWSE） | 每日收盤後 |
| 上櫃股票 | 櫃買中心（TPEx）OpenAPI | 每日收盤後 |

**注意**：本工具使用盤後資料，無法提供即時報價。

---

## 三、評分邏輯

### 權重分配
- 基本面：40%
- 技術面：35%
- 籌碼面：25%

### 評級對照
| 分數 | 評級 |
|------|------|
| 80分以上 | 強力買進 |
| 65～79分 | 偏多操作 |
| 50～64分 | 中性觀望 |
| 35～49分 | 偏空謹慎 |
| 0～34分 | 風險偏高 |

### 基本面評分項目
- 本益比（PE）：低於15倍加20分，超過50倍扣20分
- 殖利率：超過5%加15分，低於1%扣5分
- 股價淨值比（PB）：低於1倍加15分，超過5倍扣10分
- EPS：超過20元加15分，負值扣25分

### 技術面評分項目
- 均線排列：多頭排列加20分，空頭排列扣20分
- 收盤與MA20關係：站上MA20加10分，跌破MA20扣20分
- RSI(14)：40～70健康加10分，超過80扣15分，低於30加15分
- KD：黃金交叉加8分，死亡交叉扣8分
- MACD：多頭加10分，空頭扣10分
- 量能：放量加8分，縮量扣8分
- 近3個月位置：低檔加12分，高檔扣5分

### 籌碼面評分項目
- 外資近5日：大量買超加20分，大量賣超扣20分
- 外資近20日：累計買超加8分，累計賣超扣8分
- 投信近5日：買超加10分，賣超扣10分
- 融資餘額：較20日前減少10%以上加10分，增加20%以上扣10分
- 外資持股比例：超過60%加10分，低於20%扣5分

---

## 四、進出場價位計算

| 價位 | 計算方式 |
|------|---------|
| 買進參考區間 | MA20 × 0.99 ～ MA20 × 1.01 |
| 目標參考價 | 近3個月最高點與布林上軌取較低者 |
| 停損參考價 | 買進區間下緣 × 0.92（跌8%停損） |

---

## 五、技術指標說明

| 指標 | 參數 | 說明 |
|------|------|------|
| 均線 MA | 5 / 20 / 60日 | 過去N個交易日收盤價平均 |
| RSI | 14日 | 衡量近14個交易日漲跌強弱，0～100 |
| KD | 9日，平滑3 | K值快線，D值慢線，交叉判斷多空 |
| MACD | 12/26/9 | DIF與DEF差距及方向，判斷中期趨勢 |
| 布林通道 | 20日，2倍標準差 | 股價相對高低位置的統計區間 |

---

## 六、這個程式不能做什麼

- ❌ 無法預測明天漲跌
- ❌ 無法保證獲利
- ❌ 不考慮突發新聞事件（財報地雷、重大消息）
- ❌ 盤後資料，無法即時操作當日進出
- ❌ 持股結構為估算值，非精確數字

---

## 七、使用建議

1. **停損紀律比買進時機更重要**
   跌破停損價要確實執行，不要凹單，保護資金才能等待下次機會。

2. **分批買進比一次買進風險更低**
   在買進區間分2～3次買進，降低單一時間點的風險。

3. **大盤環境比個股訊號更重要**
   大盤空頭時，個股買進訊號的準確率會下降，需提高警覺。

4. **本工具是輔助，不是決策者**
   最終決策仍需結合自己的判斷，不要完全依賴評分數字。

5. **定期檢視自選股**
   建議每週至少更新並檢視一次，掌握最新動態。

---

## 八、版本紀錄

| 版本 | 日期 | 說明 |
|------|------|------|
| v2.1 | 2026/05/21 | 初始版本，七個頁籤完整功能 |
    ''')

# ── 頁籤七：匯出分析 ────────────────────
def render_export(result, code, name, chips_list):
    ind   = result['indicators']
    fund  = result['fund']
    close = result['close']
    now   = datetime.now().strftime('%Y-%m-%d %H:%M')

    ma5   = ind.get('ma5')
    ma20  = ind.get('ma20')
    ma60  = ind.get('ma60')
    rsi   = ind.get('rsi')
    k     = ind.get('k')
    d     = ind.get('d')
    macd_dif  = ind.get('macd_dif')
    macd_def  = ind.get('macd_def')
    macd_hist = ind.get('macd_hist')
    bb_upper  = ind.get('bb_upper')
    bb_lower  = ind.get('bb_lower')
    vol_ratio = ind.get('vol_ratio')
    pos_65    = ind.get('pos_65')
    high_65   = ind.get('high_65')
    low_65    = ind.get('low_65')
    buy_low   = ind.get('buy_low')
    buy_high  = ind.get('buy_high')
    target    = ind.get('target')
    stop_loss = ind.get('stop_loss')

    pe  = fund.get('pe')
    pb  = fund.get('pb')
    div = fund.get('dividend_yield')
    eps = fund.get('eps_ttm')

    recent5  = chips_list[-5:]  if len(chips_list) >= 5  else chips_list
    recent20 = chips_list[-20:] if len(chips_list) >= 20 else chips_list
    recent65 = chips_list[-65:] if len(chips_list) >= 65 else chips_list

    foreign_net5  = sum(r.get('foreign_net', 0) for r in recent5)
    foreign_net20 = sum(r.get('foreign_net', 0) for r in recent20)
    trust_net5    = sum(r.get('trust_net',   0) for r in recent5)
    margin_now    = chips_list[-1].get('margin_balance', 0) if chips_list else 0
    short_now     = chips_list[-1].get('short_balance',  0) if chips_list else 0
    foreign_buy_days = sum(1 for r in recent65 if r.get('foreign_net', 0) > 0)

    notes = get_notes(code, limit=3)
    note_str = ''
    if notes:
        for n in notes:
            if n.get('user_note'):
                note_str += f"{n['date']}　{n['user_note']}\n"

    buy_cond_str  = '\n'.join([c['text'] for c in result['buy_conditions']])
    sell_cond_str = '\n'.join([c['text'] for c in result['sell_conditions']])

    export_text = f'''====================================
台股分析資料匯出
股票：{name}（{code}）
匯出時間：{now}
====================================

【基本資料】
收盤價：{close}元
近3個月（65個交易日）區間：{low_65}～{high_65}元
目前位於近3個月區間的 {pos_65}% 位置

【基本面】
EPS（近四季TTM）：{eps:.2f}元
本益比（PE）：{pe:.1f}倍
殖利率：{div:.2f}%
股價淨值比（PB）：{pb:.2f}倍

【技術面】
MA5：{ma5}　MA20：{ma20}　MA60：{ma60}
均線排列：{"多頭排列" if ind.get("ma_trend")=="bullish" else "空頭排列" if ind.get("ma_trend")=="bearish" else "均線糾結"}
RSI(14)：{rsi}
KD：K={k} / D={d}
MACD：DIF={macd_dif} / DEF={macd_def} / 柱狀={macd_hist}
布林通道：上軌{bb_upper} / 下軌{bb_lower}
量能比：{vol_ratio}倍近20個交易日均量

【籌碼面】
外資近5個交易日：{foreign_net5:+,}張
外資近20個交易日（1個月）：{foreign_net20:+,}張
外資近3個月：買超{foreign_buy_days}天
投信近5個交易日：{trust_net5:+,}張
融資餘額：{margin_now:,}張
融券餘額：{short_now:,}張

【綜合評分】
總分：{result["total_score"]}分（{result["grade"]}）
基本面：{result["fund_score"]}分
技術面：{result["tech_score"]}分
籌碼面：{result["chip_score"]}分

【進出場建議】
買進參考區間：{buy_low}～{buy_high}元
目標參考價：{target}元
停損參考價：{stop_loss}元

【買進條件達成狀況】
{buy_cond_str}

【出場條件監控】
{sell_cond_str}

【歷史筆記】
{note_str if note_str else "（尚無筆記）"}
====================================
建議問 AI 的問題：
1. 根據以上資料，這支股票現在適合買進嗎？
2. 有什麼我可能忽略的風險？
3. 如果大盤持續下跌，這支股票的抗跌能力如何？
4. 根據技術指標，短期價格走勢可能如何？
5. 這支股票的評價（PE/PB）在歷史上是偏高還是偏低？
6. 外資籌碼的變化代表什麼含義？
===================================='''

    st.markdown('#### 一鍵匯出分析資料')
    st.info('複製以下內容，貼到任何 AI（Claude、ChatGPT、Gemini）即可進行深度分析。')
    st.markdown(
        f'<div class="export-box">{export_text}</div>',
        unsafe_allow_html=True
    )
    if st.button('📋 複製全部', use_container_width=True):
        st.code(export_text)
        st.success('請從上方程式碼區塊複製（點右上角複製按鈕）')

# ── 主程式 ──────────────────────────────
def main():
    render_sidebar()

    if 'current_code' not in st.session_state:
        st.markdown('## 📈 台股投資分析工具')
        st.info('請從左側側邊欄搜尋股票，或點選自選股清單中的股票開始分析。')
        return

    code = st.session_state['current_code']

    # 抓取資料
    prices    = get_prices(code, days=400)
    fund_data = get_fundamentals(code, days=400)
    chips_list = get_chips(code, days=65)

    if not prices:
        # 嘗試從 GitHub 載入（雲端版）
        with st.spinner(f'從 GitHub 載入 {code} 資料中...'):
            ok = load_from_github_to_db(code)
        if ok:
            prices    = get_prices(code, days=400)
            fund_data = get_fundamentals(code, days=400)
            chips_list = get_chips(code, days=65)

    if not prices:
        st.warning(f'找不到 {code} 的資料，請先在 Mac 版更新資料後，資料會自動同步到這裡。')
        if st.button('立即抓取此股票資料（僅限本機）'):
            with st.spinner('抓取中...'):
                from fetcher import fetch_history
                fetch_history(code, months=3)
            st.rerun()
        return

    # 取得股票名稱
    from database import search_stock
    results = search_stock(code)
    name = results[0]['name'] if results else code

    # 計算評分
    ownership = {'foreign': 52, 'trust': 5, 'dealer': 2,
                 'director': 12, 'retail': 29}
    result = full_score(prices, fund_data, chips_list, ownership)

    if not result:
        st.error('評分計算失敗，資料可能不足')
        return

    # 股票標題
    close = result['close']
    grade = result['grade']
    grade_colors = {
        '強力買進': '🟢', '偏多操作': '🟢',
        '中性觀望': '🟡', '偏空謹慎': '🔴', '風險偏高': '🔴'
    }
    icon = grade_colors.get(grade, '⚪')

    st.markdown(f'## {icon} {name}（{code}）　{close}元　{grade}（{result["total_score"]}分）')

    # 七個頁籤
    tabs = st.tabs(['📊 技術面', '💰 基本面', '🏦 籌碼面',
                    '⭐ 綜合評分', '📝 備註欄', '📖 程式說明', '📤 匯出分析'])

    with tabs[0]:
        render_technical(result, name)
    with tabs[1]:
        render_fundamental(result, code, name)
    with tabs[2]:
        render_chips(result, code, name, chips_list)
    with tabs[3]:
        render_score(result, code, name)
    with tabs[4]:
        render_notes(result, code, name)
    with tabs[5]:
        render_doc()
    with tabs[6]:
        render_export(result, code, name, chips_list)

if __name__ == '__main__':
    main()
