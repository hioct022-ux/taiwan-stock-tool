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

from config import VERSION, VERSION_DATE, IS_LOCAL
from database import (init_db, get_prices, get_fundamentals, get_chips,
                      get_watchlist, add_watchlist, remove_watchlist,
                      update_watchlist_tag, search_stock, get_notes,
                      save_note, update_user_note, delete_note, get_last_update,
                      get_etf_holders, get_etf_last_update, get_ownership,
                      get_t86_ranking, get_t86_ranking_bottom, get_t86_last_date,
                      get_exdividend, get_exdividend_upcoming, get_exdividend_by_code)
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
    /* ── 隱藏側邊欄收起按鈕 ── */
    div[data-testid="stSidebarCollapseButton"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
        pointer-events: none !important;
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
''', unsafe_allow_html=True)

# ── 圖表顯示 helper（禁用觸控拖曳/縮放，避免 iPad 變形）──
_CHART_CONFIG = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}

def show_chart(fig, key=None):
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CONFIG, key=key)

# ── 初始化 ──────────────────────────────
init_db()

# 雲端模式初始化（定義在 module 頂層，確保 cache_resource 正常運作）
@st.cache_resource
def _init_cloud_cache(version: str):
    """每個 exported_at 版本只初始化一次（跨 session 共用）"""
    try:
        from github_sync import init_cloud_data
        init_cloud_data()
        print(f'雲端資料匯入完成（版本：{version}）')
    except Exception as _ce:
        print(f'雲端資料匯入失敗：{_ce}')
    return version

def _get_meta_version():
    try:
        import json as _json
        from config import JSON_DIR as _JDIR
        with open(os.path.join(_JDIR, 'meta.json'), encoding='utf-8') as _f:
            return _json.load(_f).get('exported_at', 'unknown')
    except Exception:
        return 'unknown'

# 雲端模式：從 JSON 匯入資料
if not IS_LOCAL:

    _init_cloud_cache(_get_meta_version())

# 本機才啟動自動排程
if IS_LOCAL:
    start_scheduler()


# ── JS：清除sidebar localStorage + 移除收起按鈕 ──
import streamlit.components.v1 as _components
_components.html("""
<script>
(function() {
    var p = window.parent;

    // 1. 移除側邊欄收起按鈕
    function removeCollapseBtn() {
        try {
            var btn = p.document.querySelector('[data-testid="stSidebarCollapseButton"]');
            if (btn) btn.remove();
        } catch(e) {}
    }

    // 2. 清除 localStorage sidebar 狀態（只做一次，避免無限 reload）
    try {
        var flag = p.sessionStorage.getItem('_sb_reset');
        if (!flag) {
            var removed = false;
            Object.keys(p.localStorage).forEach(function(k) {
                if (k.toLowerCase().includes('sidebar')) {
                    p.localStorage.removeItem(k);
                    removed = true;
                }
            });
            if (removed) {
                p.sessionStorage.setItem('_sb_reset', '1');
                p.location.reload();
                return;
            }
        }
    } catch(e) {}

    // 3. 持續監聽 DOM，每次 React re-render 後重新移除按鈕
    removeCollapseBtn();
    var n = 0;
    var t = setInterval(function() {
        removeCollapseBtn();
        if (++n > 30) clearInterval(t);
    }, 500);
    try {
        new MutationObserver(removeCollapseBtn).observe(
            p.document.body, {childList: true, subtree: true}
        );
    } catch(e) {}
})();
</script>
""", height=0)

# ── 側邊欄 ──────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(f'### 📈 台股分析工具 {VERSION}')

        # 模式標示
        if IS_LOCAL:
            st.markdown('<div style="background:#1c2030;border-radius:6px;padding:4px 10px;'
                        'font-size:12px;color:#22c55e;border:1px solid #22c55e33">'
                        '🖥️ 本機版　資料每日自動更新</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:#1c2030;border-radius:6px;padding:4px 10px;'
                        'font-size:12px;color:#f59e0b;border:1px solid #f59e0b33">'
                        '☁️ 雲端版　唯讀模式</div>', unsafe_allow_html=True)

        st.markdown('---')

        if IS_LOCAL:
            # 資料狀態
            status = get_data_status()
            color_map = {'ok':'green','pending':'orange','error':'red','holiday':'blue'}
            st.markdown(
                f'<div class="status-bar" style="background:rgba(0,0,0,0.3);'
                f'border-left:4px solid {color_map.get(status["status"],"gray")}">'
                f'{status["label"]}</div>',
                unsafe_allow_html=True
            )
            if status.get('last_time'):
                st.caption(f'🕐 上次嘗試更新：{status["last_time"]}')

            # 更新並同步一鍵按鈕（本機限定）
            if st.button('🚀 更新並同步到雲端', use_container_width=True):
                with st.status('更新並同步中...', expanded=True) as _status:
                    # Step 1: 抓資料
                    st.write('📥 步驟 1／2　抓取最新收盤資料...')
                    _fetch_ok = True
                    try:
                        from fetcher import fetch_all
                        fetch_all()
                        st.write('✅ 資料更新完成')
                    except Exception as _e:
                        st.write(f'⚠️ 抓取部分失敗：{_e}')
                        _fetch_ok = False
                    # Step 2: 同步 GitHub
                    st.write('📤 步驟 2／2　同步到 GitHub...')
                    try:
                        from github_sync import sync_via_git
                        ok, msg = sync_via_git()
                        if ok:
                            st.write(f'✅ {msg}')
                            st.write('🌐 雲端版約 1 分鐘後自動更新')
                        else:
                            st.write(f'⚠️ 同步失敗：{msg}')
                    except Exception as _e:
                        st.write(f'❌ 同步失敗：{_e}')
                    _status.update(
                        label='✅ 完成！' if _fetch_ok else '⚠️ 完成（抓取部分失敗）',
                        state='complete'
                    )
                st.rerun()

            st.markdown('---')

        else:
            # 雲端版資料時間提示
            try:
                from github_sync import load_meta_raw
                meta = load_meta_raw()
                if meta and meta.get('exported_at'):
                    st.caption(f'📅 資料更新：{meta["exported_at"]}')
            except Exception:
                pass
            st.markdown('---')

        # 大盤分析
        if st.button('📊 大盤分析', use_container_width=True):
            st.session_state['page'] = 'market'
            st.session_state.pop('current_code', None)
            st.rerun()

        # 法人排行
        if st.button('🏆 法人買超排行榜', use_container_width=True):
            st.session_state['page'] = 'ranking'
            st.session_state.pop('current_code', None)
            st.rerun()

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
                    st.session_state['page'] = 'stock'
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
                        st.session_state['page'] = 'stock'
                        st.rerun()
                with col2:
                    if IS_LOCAL and st.button('✕', key=f"del_{w['code']}"):
                        remove_watchlist(w['code'])
                        st.rerun()
        else:
            st.info('尚無自選股，搜尋後加入')

        # 新增自選股（本機限定）
        if IS_LOCAL:
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
        else:
            st.markdown('---')
            st.caption('✏️ 新增/刪除自選股請在本機操作後同步')

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

    # 布林通道（淺灰色帶）
    bb_upper_s = ind.get('bb_upper_series', [])
    bb_lower_s = ind.get('bb_lower_series', [])
    if bb_upper_s and bb_lower_s and len(dates) == len(bb_upper_s):
        # 上軌（透明線，作為 fill 的頂部）
        fig.add_trace(go.Scatter(
            x=dates, y=bb_upper_s,
            name='布林上軌',
            mode='lines',
            line=dict(color='rgba(180,180,180,0.4)', width=1),
            showlegend=True
        ), row=1, col=1)
        # 下軌（填色到上軌之間）
        fig.add_trace(go.Scatter(
            x=dates, y=bb_lower_s,
            name='布林下軌',
            mode='lines',
            line=dict(color='rgba(180,180,180,0.4)', width=1),
            fill='tonexty',
            fillcolor='rgba(160,160,160,0.12)',
            showlegend=True
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
    show_chart(fig)

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

    # 除權息提示（只顯示未來的）
    ex_records = [r for r in get_exdividend_by_code(code) if r['ex_date'] >= datetime.now().strftime('%Y-%m-%d')]
    if ex_records:
        latest = ex_records[0]
        type_label = {'息': '除息', '權': '除權', '權息': '除權息'}.get(latest['div_type'], latest['div_type'])
        st.info(f'🎁 **即將{type_label}**：{latest["ex_date"]}　'
                f'權息值 {latest["div_value"]:.2f} 元　'
                f'參考價 {latest["ref_price"]:.2f} 元')

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
            st.info(
                '**股價淨值比（PB）** 是股價除以每股帳面價值（淨值），'
                '代表你付出多少錢買 1 元的公司資產。\n\n'
                'PB=1 代表股價剛好等於帳面價值；'
                'PB<1 代表用打折的價格買資產，通常出現在景氣低迷或市場過度悲觀時；'
                'PB 越高代表市場願意付出更高的溢價，通常反映對公司未來獲利能力的期待。\n\n'
                '**注意**：高科技或輕資產公司（如台積電、軟體業）因為獲利能力強，'
                'PB 天生就偏高，不能直接與傳統製造業相比，需同產業橫向比較才有意義。'
            )
            if pb < 1:
                st.success(f'PB={pb:.2f}倍，股價低於帳面淨值，理論上具安全邊際，但需確認公司基本面無重大問題。')
            elif pb < 1.5:
                st.success(f'PB={pb:.2f}倍，評價偏低，市場溢價不高，適合重視資產保護的投資人。')
            elif pb < 3:
                st.info(f'PB={pb:.2f}倍，評價合理，在台股一般產業的正常範圍內。')
            elif pb < 5:
                st.warning(f'PB={pb:.2f}倍偏高，市場給予明顯溢價，需要持續的高獲利能力來支撐。')
            else:
                st.error(f'PB={pb:.2f}倍極高，市場期待非常強勁的成長，若獲利不如預期股價修正風險大。')# ── 頁籤三：籌碼面 ──────────────────────
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

    # ── 三大法人歷史走勢圖 ──
    if len(chips_list) >= 5:
        dates_c   = [r['date'] for r in recent65]
        f_nets    = [r.get('foreign_net', 0) for r in recent65]
        t_nets    = [r.get('trust_net',   0) for r in recent65]
        d_nets    = [r.get('dealer_net',  0) for r in recent65]

        fig_chips = go.Figure()
        fig_chips.add_trace(go.Bar(
            x=dates_c, y=f_nets, name='外資淨買賣',
            marker_color=['#22c55e' if v >= 0 else '#ef4444' for v in f_nets],
            opacity=0.8
        ))
        fig_chips.add_trace(go.Scatter(
            x=dates_c, y=t_nets, name='投信淨買賣',
            mode='lines+markers', line=dict(color='#38bdf8', width=2),
            marker=dict(size=4)
        ))
        fig_chips.add_trace(go.Scatter(
            x=dates_c, y=d_nets, name='自營商淨買賣',
            mode='lines', line=dict(color='#facc15', width=1.5, dash='dot')
        ))
        fig_chips.add_hline(y=0, line_color='#555', line_width=1)
        fig_chips.update_layout(
            title=None,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'), height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(orientation='h', y=1.0, x=0, bgcolor='rgba(0,0,0,0)'),
            xaxis=dict(gridcolor='#2a2f3e'),
            yaxis=dict(gridcolor='#2a2f3e', tickformat=',d')
        )
        st.markdown('**三大法人每日淨買賣超（張）**')
        show_chart(fig_chips)

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

    # ── 融資融券歷史走勢圖 ──
    margin_vals = [r.get('margin_balance', 0) for r in recent65]
    short_vals  = [r.get('short_balance',  0) for r in recent65]
    if any(v > 0 for v in margin_vals) or any(v > 0 for v in short_vals):
        dates_m = [r['date'] for r in recent65]
        fig_margin = make_subplots(specs=[[{'secondary_y': True}]])
        fig_margin.add_trace(go.Scatter(
            x=dates_m, y=margin_vals, name='融資餘額',
            mode='lines', fill='tozeroy',
            line=dict(color='#ef4444', width=2),
            fillcolor='rgba(239,68,68,0.15)'
        ), secondary_y=False)
        fig_margin.add_trace(go.Scatter(
            x=dates_m, y=short_vals, name='融券餘額',
            mode='lines', fill='tozeroy',
            line=dict(color='#38bdf8', width=2),
            fillcolor='rgba(56,189,248,0.15)'
        ), secondary_y=True)
        fig_margin.update_layout(
            title=None,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'), height=280,
            margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(orientation='h', y=1.0, x=0, bgcolor='rgba(0,0,0,0)'),
            xaxis=dict(gridcolor='#2a2f3e'),
        )
        st.markdown('**融資／融券餘額歷史（張）**')
        fig_margin.update_yaxes(
            title_text='融資餘額（張）', gridcolor='#2a2f3e',
            tickformat=',d', secondary_y=False)
        fig_margin.update_yaxes(
            title_text='融券餘額（張）', gridcolor='#2a2f3e',
            tickformat=',d', secondary_y=True)
        show_chart(fig_margin)
    else:
        st.caption('融資融券歷史資料不足，請先按手動更新補齊歷史資料')

    st.markdown('---')
    # ── 持股結構 + ETF 持股（同一排）──
    # 外資持股%從 DB 讀取（每日更新自 TWSE MI_QFIIS）
    _own = get_ownership(code)
    _fp  = round(_own['foreign_pct'], 1) if _own else None
    if _fp is not None:
        ownership = {
            'foreign':  _fp,
            'trust':    5,
            'dealer':   2,
            'director': 12,
            'retail':   max(0, 100 - _fp - 5 - 2 - 12),
        }
    else:
        ownership = {'foreign': 52, 'trust': 5, 'dealer': 2, 'director': 12, 'retail': 29}
    st.markdown('---')

    # ── ETF 持股 ──────────────────────────────────────────────────────────
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │  【資料來源說明 & 維護注意事項】                                         │
    # │                                                                     │
    # │  顯示優先順序：                                                        │
    # │    A. 資料庫即時資料（get_etf_holders）— 最準確，需先抓取               │
    # │    B. 下方 _ETF_FALLBACK 備援資料     — 程式碼內手動維護               │
    # │    C. 完全無資料，顯示抓取按鈕                                          │
    # │                                                                     │
    # │  關於即時抓取（情況A）：                                                │
    # │    • 曾試過 FinMind API：免費版無 ETF 成分股資料集（2026/05）           │
    # │    • 曾試過 TWSE OpenAPI / T201U：全部回傳 HTML，程式無法解析           │
    # │    • 結論：目前無法免費自動取得即時 ETF 成分股資料                       │
    # │    • 若未來 TWSE 或 FinMind 開放，可在 fetcher.py                     │
    # │      的 fetch_etf_holdings() 函式重新啟用對應策略                      │
    # │                                                                     │
    # │  關於備援資料（情況B，_ETF_FALLBACK）：                                 │
    # │    • 資料為人工整理，參考各 ETF 官方公告及公開資訊                        │
    # │    • ETF 成分股每季調整（3、6、9、12月），約 3-6 個月需更新一次           │
    # │    • 更新方式：直接修改下方 _ETF_FALLBACK 字典                          │
    # │    • 涵蓋台股市值前 50 大及常見高息/熱門股，共 40+ 支                    │
    # │    • 上次人工更新：2026/05                                             │
    # └─────────────────────────────────────────────────────────────────────┘
    # 備援資料：常見股票的 ETF 分類（資料庫沒資料時顯示）
    _ETF_FALLBACK = {
        # ── 半導體 / 科技 ──────────────────────────────
        '2330': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'00850','name':'元大臺灣ESG永續','type':'ESG型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[{'code':'00985A','name':'主動野村台灣50','type':'主動型'},{'code':'00990A','name':'主動元大AI新經濟','type':'主動型'}],'note':'台積電為台股最大市值，幾乎所有市值型與科技主題ETF第一大持股'},
        '2454': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[{'code':'00990A','name':'主動元大AI新經濟','type':'主動型'}],'note':'聯發科為IC設計龍頭，AI手機晶片題材，科技型ETF核心持股'},
        '2303': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00921','name':'兆豐台灣晶圓製造','type':'晶圓製造'}],'active':[],'note':'聯電為成熟製程晶圓廠，多支半導體主題ETF持有'},
        '3711': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'}],'active':[],'note':'日月光投控為全球最大封測廠，半導體ETF重要成分'},
        '2344': {'passive':[],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00921','name':'兆豐台灣晶圓製造','type':'晶圓製造'}],'active':[],'note':'華邦電為DRAM/NAND Flash廠，半導體記憶體主題ETF持有'},
        '2379': {'passive':[],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'瑞昱為網路/藍牙晶片龍頭，科技主題ETF常見成分'},
        '3034': {'passive':[],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'聯詠為面板驅動IC龍頭，科技高息ETF成分'},
        '2327': {'passive':[{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'國巨為被動元件龍頭，科技供應鏈ETF重要成分'},
        # ── AI / 伺服器 / 散熱 ──────────────────────────
        '2382': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'},{'code':'00935','name':'野村臺灣新科技50','type':'新科技'}],'active':[{'code':'00990A','name':'主動元大AI新經濟','type':'主動型'}],'note':'廣達為AI伺服器出貨量最大，AI伺服器/雲端主題ETF核心持股'},
        '2357': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00929','name':'復華台灣科技優息','type':'科技高息'},{'code':'00935','name':'野村臺灣新科技50','type':'新科技'}],'active':[],'note':'華碩以個人電腦/電競聞名，近年轉型AI伺服器'},
        '2376': {'passive':[],'thematic':[{'code':'00935','name':'野村臺灣新科技50','type':'新科技'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'技嘉為AI伺服器/顯示卡板卡廠，AI題材受惠'},
        '3231': {'passive':[],'thematic':[{'code':'00935','name':'野村臺灣新科技50','type':'新科技'}],'active':[],'note':'緯創為伺服器ODM廠，AI伺服器擴產受惠'},
        '6415': {'passive':[],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'矽力-KY為電源管理IC廠，AI電源題材'},
        # ── 電子零組件 / 蘋果供應鏈 ────────────────────
        '2308': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體/AI電源'},{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00935','name':'野村臺灣新科技50','type':'新科技'}],'active':[{'code':'00990A','name':'主動元大AI新經濟','type':'主動型'}],'note':'台達電為AI電源/散熱龍頭，幾乎所有科技、AI主題ETF必配'},
        '2317': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'},{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'}],'active':[],'note':'鴻海為大型藍籌股，市值型與高息型ETF均大量配置'},
        '2412': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'中華電為電信龍頭，穩定配息，高股息ETF大量布局'},
        '3008': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00881','name':'國泰台灣科技龍頭','type':'科技龍頭'}],'active':[],'note':'大立光為iPhone鏡頭龍頭，蘋果供應鏈ETF必配'},
        '2301': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'00850','name':'元大臺灣ESG永續','type':'ESG型'}],'thematic':[{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'光寶科殖利率高，高股息型ETF大量持有'},
        # ── 金融 ──────────────────────────────────────
        '2882': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'國泰金為大型金控，高股息與金融主題ETF重要持股'},
        '2881': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'}],'active':[],'note':'富邦金為大型金控，高股息ETF大量配置'},
        '2886': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00915','name':'凱基優選高股息30','type':'高息型'}],'active':[],'note':'兆豐金為官股金控，高填息率，高股息ETF最愛持股之一'},
        '2884': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'}],'active':[],'note':'玉山金以數位金融見長，高股息ETF穩定配置'},
        '2885': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00915','name':'凱基優選高股息30','type':'高息型'}],'active':[],'note':'元大金旗下有元大投信，高股息ETF穩定布局'},
        '2892': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'第一金為官股行庫，高填息、高股息ETF最常見成分股'},
        '5880': {'passive':[],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'合庫金為官股行庫，高填息特性吸引高股息ETF大量持有'},
        '2880': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'華南金為官股金控，高股息ETF穩定持有'},
        '2883': {'passive':[{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00919','name':'群益台灣精選高息','type':'高息型'}],'active':[],'note':'開發金持有中信銀，金融ETF成分'},
        '2891': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'0055','name':'元大MSCI金融','type':'金融型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'中信金為大型民營金控，高股息ETF大量配置'},
        # ── 石化 / 傳產 ────────────────────────────────
        '6505': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'台塑化為台灣最大煉油廠，高配息，高股息ETF重要成分'},
        '1301': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'台塑集團核心，高股息ETF長期持有'},
        '1303': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'南亞為台塑四寶之一，高股息ETF成分'},
        '1326': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'}],'thematic':[{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'台化為台塑四寶之一，高股息ETF成分'},
        '2002': {'passive':[{'code':'0050','name':'元大台灣50','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'}],'thematic':[{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'中鋼為台灣最大鋼鐵廠，高配息，高股息ETF長期持有'},
        # ── 光電 / 面板 ────────────────────────────────
        '2395': {'passive':[],'thematic':[{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'00878','name':'國泰永續高股息','type':'高息/ESG'}],'active':[],'note':'研華為工業電腦龍頭，ESG與高息ETF持有'},
        '2408': {'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'0050','name':'元大台灣50','type':'市值型'}],'thematic':[{'code':'00891','name':'中信關鍵半導體','type':'半導體'},{'code':'00892','name':'富邦台灣半導體','type':'半導體'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'南亞科為DRAM龍頭，半導體主題ETF必配'},
        # ── 生技 / 醫療 ────────────────────────────────
        '4958': {'passive':[],'thematic':[{'code':'00929','name':'復華台灣科技優息','type':'科技高息'}],'active':[],'note':'臻鼎-KY為軟板廠，科技ETF少量持有'},
        # ── 自選股原有資料 ─────────────────────────────
        '2049': {'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'},{'code':'006208','name':'富邦台50','type':'市值型'},{'code':'0050','name':'元大台灣50','type':'市值型'}],'thematic':[{'code':'00737','name':'國泰AI機器人','type':'AI/機器人'},{'code':'00896','name':'中信綠能及電動車','type':'工業自動化'},{'code':'00911','name':'兆豐洲際半導體','type':'半導體'}],'active':[{'code':'00985A','name':'主動野村台灣50','type':'主動型'}],'note':'上銀為精密機械/機器人龍頭，AI機器人相關主題ETF大量布局'},
        '1476': {'passive':[{'code':'00692','name':'富邦公司治理','type':'市值型'}],'thematic':[{'code':'00915','name':'凱基優選高股息30','type':'高息型'},{'code':'00919','name':'群益台灣精選高息','type':'高息型'},{'code':'00940','name':'元大台灣價值高息','type':'高息型'}],'active':[],'note':'儒鴻為紡織龍頭，殖利率穩定，高股息ETF重要成分股'},
    }

    etf_holders  = get_etf_holders(code)
    etf_last     = get_etf_last_update()
    close_price  = result['close']
    etf_fallback = _ETF_FALLBACK.get(code, {})

    # ── 兩個圓餅圖同一排 ─────────────────────────────────────────────
    col_own, col_etf = st.columns(2)

    # 左欄：持股結構
    with col_own:
        _own_title = '#### 持股結構'
        if _fp is not None:
            _own_title += f'（外資 {_fp}%，每日更新）'
        else:
            _own_title += '（估算，更新後可見真實外資%）'
        st.markdown(_own_title)
        labels = ['外資', '投信', '自營', '董監', '散戶']
        values = [ownership['foreign'], ownership['trust'],
                  ownership['dealer'], ownership['director'], ownership['retail']]
        colors = ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#6b7280']
        fig_own = go.Figure(go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            hole=0.4, textinfo='label+percent'
        ))
        fig_own.update_layout(
            paper_bgcolor='#0d0f12', font=dict(color='#e2e8f0'),
            height=280, margin=dict(l=0, r=0, t=0, b=0), showlegend=True
        )
        show_chart(fig_own)

        # ── 動態判斷文字（依真實資料）──────────────
        if _fp is not None:
            # 外資持股水位判斷
            if _fp >= 60:
                level_msg = f'外資高度持有（{_fp}%），法人長期看好，籌碼集中。'
            elif _fp >= 30:
                level_msg = f'外資持股適中（{_fp}%），有一定法人認同。'
            else:
                level_msg = f'外資持股偏低（{_fp}%），以本土資金為主，波動相對較大。'

            # 近期外資買賣超方向（從 chips_list 讀取）
            recent5_foreign = sum(r.get('foreign_net', 0) for r in chips_list[-5:]) if chips_list else 0
            recent20_foreign = sum(r.get('foreign_net', 0) for r in chips_list[-20:]) if chips_list else 0
            if recent5_foreign > 1000:
                trend_msg = f'近5日外資買超 {recent5_foreign:+,} 張，持續加碼，籌碼偏正面。'
            elif recent5_foreign > 0:
                trend_msg = f'近5日外資小幅買超 {recent5_foreign:+,} 張。'
            elif recent5_foreign > -1000:
                trend_msg = f'近5日外資小幅賣超 {recent5_foreign:+,} 張。'
            else:
                trend_msg = f'近5日外資賣超 {recent5_foreign:+,} 張，法人出脫，需留意。'

            st.caption(f'{level_msg} {trend_msg}')
            st.caption('外資%來源：TWSE MI_QFIIS 每日更新；投信/自營/董監為估算值')
        else:
            st.caption('外資持股比率尚無資料，請先按「手動更新資料」取得真實數據。')

    # 右欄：ETF 持股圓餅圖
    with col_etf:
        st.markdown('#### ETF 持股')
        if etf_holders:
            # 情況A：資料庫即時資料 → 顯示各ETF比例圓餅
            for e in etf_holders:
                e['market_value'] = round(e.get('shares',0) * close_price / 1000) if e.get('shares') and close_price else 0
            pie_data   = etf_holders[:10]
            pie_labels = [f'{e["etf_code"]} {(e["etf_name"] or e["etf_code"])[:6]}' for e in pie_data]
            pie_values = [e['weight'] for e in pie_data]
            if sum(pie_values) > 0:
                fig_ep = go.Figure(go.Pie(
                    labels=pie_labels, values=pie_values, hole=0.4,
                    textinfo='label+percent',
                    marker=dict(colors=['#38bdf8','#22c55e','#f59e0b','#a78bfa','#ef4444',
                                        '#06b6d4','#84cc16','#f97316','#8b5cf6','#ec4899'])
                ))
                fig_ep.update_layout(
                    paper_bgcolor='#0d0f12', font=dict(color='#e2e8f0', size=11),
                    height=280, margin=dict(l=0, r=0, t=0, b=0), showlegend=False
                )
                show_chart(fig_ep)
            st.caption(f'資料來源：TWSE　最後更新：{etf_last[:10] if etf_last else "未知"}')

        elif etf_fallback:
            # 情況B：備援資料 → 顯示類型分布圓餅
            etf_type_labels = ['被動型', '主題型', '主動型']
            etf_type_values = [
                len(etf_fallback.get('passive', [])),
                len(etf_fallback.get('thematic', [])),
                len(etf_fallback.get('active', []))
            ]
            if sum(etf_type_values) > 0:
                fig2 = go.Figure(go.Pie(
                    labels=etf_type_labels, values=etf_type_values,
                    marker=dict(colors=['#38bdf8','#a78bfa','#22c55e']),
                    hole=0.4, textinfo='label+value'
                ))
                fig2.update_layout(
                    paper_bgcolor='#0d0f12', font=dict(color='#e2e8f0'),
                    height=280, margin=dict(l=0, r=0, t=0, b=0), showlegend=True
                )
                show_chart(fig2)
            st.caption('資料來源：參考資料（備援）')

        else:
            # 情況C：無資料（此股票不在備援清單且資料庫無資料）
            st.caption('此股票暫無 ETF 持股資料')

    # ── 圓餅圖下方：ETF 詳細資料 ─────────────────────────────────────
    if etf_holders:
        # 情況A：詳細清單
        top = etf_holders[:20]
        st.markdown(f'**共有 {len(etf_holders)} 支 ETF 持有此股票**，以下顯示持股比例最高前 {len(top)} 支：')
        col_h = st.columns([2, 3, 1.5, 2, 2])
        col_h[0].markdown('**ETF 代號**')
        col_h[1].markdown('**ETF 名稱**')
        col_h[2].markdown('**持股比例**')
        col_h[3].markdown('**持股股數（千股）**')
        col_h[4].markdown('**估算市值（萬元）**')
        for e in top:
            w    = e.get('weight', 0)
            sh   = e.get('shares', 0)
            mv   = e.get('market_value', 0)
            cols = st.columns([2, 3, 1.5, 2, 2])
            cols[0].markdown(f'`{e["etf_code"]}`')
            cols[1].markdown(e['etf_name'] or e['etf_code'])
            bar_w = min(int(w * 3), 100) if w else 0
            cols[2].markdown(
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div style="width:{bar_w}px;height:8px;background:#38bdf8;border-radius:4px"></div>'
                f'<span>{w:.2f}%</span></div>', unsafe_allow_html=True)
            cols[3].markdown(f'{sh:,}' if sh else '—')
            cols[4].markdown(f'{mv:,}' if mv else '—')

    elif etf_fallback:
        # 情況B：ETF 卡片
        def _etf_cards(items, color):
            cols = st.columns(3)
            for i, e in enumerate(items):
                with cols[i % 3]:
                    st.markdown(
                        f'<div style="background:#1c2030;border-radius:8px;padding:6px 10px;'
                        f'border:1px solid #252a38;margin-bottom:6px">'
                        f'<div style="font-size:10px;color:#4a5568">{e["code"]}</div>'
                        f'<div style="font-size:12px;font-weight:500">{e["name"]}</div>'
                        f'<div style="font-size:10px;color:{color}">{e["type"]}</div>'
                        f'</div>', unsafe_allow_html=True)

        if etf_fallback.get('passive'):
            st.markdown('**被動型（市值／指數）**')
            _etf_cards(etf_fallback['passive'], '#38bdf8')
        if etf_fallback.get('thematic'):
            st.markdown('**主題型（AI／產業／高息）**')
            _etf_cards(etf_fallback['thematic'], '#a78bfa')
        if etf_fallback.get('active'):
            st.markdown('**主動型**')
            _etf_cards(etf_fallback['active'], '#22c55e')
        if etf_fallback.get('note'):
            st.info(f'💡 {etf_fallback["note"]}')


    # 情況C（無備援資料且資料庫無資料）已在右欄圓餅圖區域顯示提示，此處不重複

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
        placeholder='例如：法說會後外資加碼，持續觀察...',
        key=f'user_note_{code}'   # 隨股票代號變動，換股票時自動清空
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button('💾 儲存筆記', use_container_width=True):
            save_note(code, auto_note, user_note)
            st.success('筆記已儲存')

    st.markdown('---')
    st.markdown('#### 歷史筆記')

    notes = get_notes(code, limit=20)
    if notes:
        st.caption(f'顯示最近 {len(notes)} 筆（最多顯示 20 筆，資料庫無上限）')
        for n in notes:
            title = f"📅 {n['date']}　{n['auto_note'][:30]}..."
            with st.expander(title):
                st.markdown('**系統摘要：**')
                st.text(n['auto_note'])
                if n['user_note']:
                    st.markdown('**我的筆記：**')
                    st.info(n['user_note'])
                # 刪除按鈕
                if st.button('🗑️ 刪除此筆記', key=f'del_note_{n["id"]}'):
                    delete_note(n['id'])
                    st.success('已刪除')
                    st.rerun()
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
| ETF 持股分類 | 人工整理備援資料（參考用） | 每季手動更新 |

**注意**：本工具使用盤後資料，無法提供即時報價。

---

## 二之一、ETF 持股資料說明

ETF 持股欄位目前使用**人工整理的備援資料**，並非即時抓取。原因如下：

| 來源 | 狀況 |
|------|------|
| 台灣證交所（TWSE）OpenAPI | 所有端點均回傳 HTML 錯誤頁，程式無法解析（已於 2026/05 確認） |
| FinMind API（免費版） | 免費版不含 ETF 成分股資料集，無法使用 |

**目前做法**：程式內建 40+ 支常見股票的 ETF 分類資料（市值型、主題型、主動型），
涵蓋半導體、AI 伺服器、金融、石化等主要族群。

**維護週期**：ETF 成分股每年 3、6、9、12 月調整，
建議每季更新一次 `app.py` 中的 `_ETF_FALLBACK` 字典。

**未來改善方向**：若 TWSE OpenAPI 恢復正常 JSON 回傳，
或 FinMind 開放免費 ETF 資料集，可在 `fetcher.py` 的
`fetch_etf_holdings()` 函式重新啟用對應策略，即可升級為即時資料。

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

# ── 大盤走勢分析 ────────────────────────
def render_market():
    st.markdown('## 📊 大盤走勢分析（加權指數）')

    prices = get_prices('TAIEX', days=250)
    if not prices:
        st.warning('尚無大盤資料，請先按左側「🔄 手動更新資料」抓取最新數據。')
        return

    ind = calc_all(prices)

    close     = prices[-1]['close']
    date      = prices[-1]['date']
    chg       = prices[-1]['change']
    chg_pct   = prices[-1]['change_pct']
    prev      = prices[-2]['close'] if len(prices) >= 2 else close

    # ── 頂部指標列 ─────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        chg_color = '🔴' if chg < 0 else '🟢'
        chg_sign  = f'{chg:+.2f}' if chg else '0.00'
        st.metric(
            f'加權指數（{date}）',
            f'{close:,.2f}',
            delta=f'{chg_sign} ({chg_pct:+.2f}%)'
        )
    with col2:
        ma20 = ind.get('ma20')
        if ma20:
            above = close >= ma20
            st.metric('MA20（月線）', f'{ma20:,.2f}',
                      delta='站上月線 ✅' if above else '跌破月線 ❌')
        else:
            st.metric('MA20', '資料不足')
    with col3:
        rsi = ind.get('rsi')
        if rsi:
            rsi_label = ('超買區' if rsi > 70 else '超賣區' if rsi < 30 else '健康區')
            st.metric('RSI(14)', f'{rsi}', delta=rsi_label)
        else:
            st.metric('RSI(14)', '—')
    with col4:
        pos_65 = ind.get('pos_65')
        h65    = ind.get('high_65')
        l65    = ind.get('low_65')
        if pos_65 is not None:
            pos_label = '高檔區 ⚠️' if pos_65 >= 80 else '低檔區 ✅' if pos_65 <= 20 else '中段整理'
            st.metric('近3個月位置', f'{pos_65}%', delta=pos_label)
            st.caption(f'區間 {l65:,.0f} ～ {h65:,.0f}')
        else:
            st.metric('近3個月位置', '—')

    st.caption(f'資料來源：Yahoo Finance ^TWII　｜　成交量欄位代表相對量能（較大代表當日成交活絡）')

    # ── 走勢圖 ─────────────────────────────
    dates   = ind.get('dates', [])
    closes  = ind.get('closes', [])
    ma5s    = ind.get('ma5_series', [])
    ma20s   = ind.get('ma20_series', [])
    ma60s   = ind.get('ma60_series', [])
    volumes = ind.get('volumes', [])
    bb_upper_s = ind.get('bb_upper_series', [])
    bb_lower_s = ind.get('bb_lower_series', [])

    if dates:
        fig = go.Figure()

        # 指數線
        fig.add_trace(go.Scatter(
            x=dates, y=closes, name='加權指數',
            line=dict(color='#38bdf8', width=2)
        ))

        # 均線
        fig.add_trace(go.Scatter(
            x=dates, y=ma5s, name='MA5',
            line=dict(color='#f59e0b', width=1),
            connectgaps=True
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=ma20s, name='MA20',
            line=dict(color='#a78bfa', width=1),
            connectgaps=True
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=ma60s, name='MA60',
            line=dict(color='#22c55e', width=1),
            connectgaps=True
        ))

        # 布林通道（淺灰色帶）
        if bb_upper_s and bb_lower_s and len(dates) == len(bb_upper_s):
            fig.add_trace(go.Scatter(
                x=dates, y=bb_upper_s, name='布林上軌',
                mode='lines',
                line=dict(color='rgba(180,180,180,0.4)', width=1),
                showlegend=True
            ))
            fig.add_trace(go.Scatter(
                x=dates, y=bb_lower_s, name='布林下軌',
                mode='lines',
                line=dict(color='rgba(180,180,180,0.4)', width=1),
                fill='tonexty', fillcolor='rgba(160,160,160,0.12)',
                showlegend=True
            ))

        fig.update_layout(
            paper_bgcolor='#0d0f12',
            plot_bgcolor='#141720',
            font=dict(color='#e2e8f0', size=11),
            height=420,
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            xaxis=dict(showgrid=True, gridcolor='#252a38'),
            yaxis=dict(showgrid=True, gridcolor='#252a38'),
            margin=dict(l=0, r=0, t=40, b=0)
        )
        show_chart(fig)

    st.markdown('---')

    # ── 大盤綜合判斷 ─────────────────────────
    st.markdown('#### 大盤趨勢判斷')

    ma_trend  = ind.get('ma_trend')
    ma5       = ind.get('ma5')
    ma60      = ind.get('ma60')
    pos_65    = ind.get('pos_65')
    high_65   = ind.get('high_65')
    low_65    = ind.get('low_65')
    macd_dif  = ind.get('macd_dif')
    macd_def  = ind.get('macd_def')
    macd_hist = ind.get('macd_hist')
    k         = ind.get('k')
    d         = ind.get('d')

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown('**均線趨勢**')
        trend_map = {
            'bullish':  ('多頭排列 ↑', '#22c55e'),
            'bearish':  ('空頭排列 ↓', '#ef4444'),
            'sideways': ('均線糾結 →', '#f59e0b'),
        }
        t_label, t_color = trend_map.get(ma_trend, ('資料不足', '#6b7280'))
        st.markdown(f'<span style="color:{t_color};font-size:20px;font-weight:700">'
                    f'{t_label}</span>', unsafe_allow_html=True)
        if ma5:  st.metric('MA5',  f'{ma5:,.2f}')
        if ma20: st.metric('MA20', f'{ma20:,.2f}', delta=f'{close-ma20:+.2f}')
        if ma60: st.metric('MA60', f'{ma60:,.2f}')
        if ma_trend == 'bullish':
            st.success(f'MA5({ma5:,.0f}) > MA20({ma20:,.0f}) > MA60({ma60:,.0f})，'
                       f'三條均線多頭排列，大盤趨勢向上。')
        elif ma_trend == 'bearish':
            st.warning(f'均線空頭排列，短中長期趨勢均向下，操作需謹慎。')
        else:
            st.info('均線糾結，方向待確認，建議觀望為主。')

    with col_b:
        st.markdown('**動能指標**')
        if rsi:
            rsi_color = '#ef4444' if rsi > 75 else '#22c55e' if rsi < 35 else '#38bdf8'
            st.markdown(f'RSI(14)：<span style="color:{rsi_color};font-size:20px;font-weight:700">'
                        f'{rsi}</span>', unsafe_allow_html=True)
            if rsi > 75:
                st.warning(f'大盤 RSI={rsi} 偏高，短期指數已偏熱，留意回測壓力。')
            elif rsi < 35:
                st.success(f'大盤 RSI={rsi} 偏低，指數進入超賣區，可留意反彈機會。')
            else:
                st.info(f'RSI={rsi}，動能正常，大盤沒有明顯過熱或過冷。')

        if k and d:
            st.metric('KD', f'K={k} / D={d}')
            if k > d:
                st.success('KD 黃金交叉，短期大盤偏多。')
            else:
                st.warning('KD 死亡交叉，短期大盤偏空。')

        if macd_dif and macd_def:
            st.metric('MACD', f'DIF={macd_dif:+.1f}',
                      delta=f'柱={macd_hist:+.1f}' if macd_hist else None)
            if macd_dif > macd_def:
                st.success('MACD 多頭，中期趨勢向上。')
            else:
                st.warning('MACD 空頭，中期趨勢向下。')

    with col_c:
        st.markdown('**近3個月位置**')
        if pos_65 is not None:
            pos_color = '#ef4444' if pos_65 >= 80 else '#22c55e' if pos_65 <= 20 else '#f59e0b'
            st.markdown(f'近3個月位置：<span style="color:{pos_color};font-size:18px;font-weight:700">'
                        f'{pos_65}%</span>', unsafe_allow_html=True)
            st.caption(f'近3個月區間：{low_65:,.0f} ～ {high_65:,.0f}')
            if pos_65 >= 80:
                st.warning(f'指數位於近3個月高檔區（{pos_65}%），短期追高風險較大。')
            elif pos_65 <= 20:
                st.success(f'指數位於近3個月低檔區（{pos_65}%），若量能回升可留意反彈。')
            else:
                st.info(f'指數位於近3個月中段（{pos_65}%），方向待確認。')

    # ── 近5個交易日走勢簡表 ────────────────
    st.markdown('---')
    st.markdown('#### 近5個交易日')
    recent5 = prices[-5:] if len(prices) >= 5 else prices
    cols = st.columns(len(recent5))
    for i, row in enumerate(recent5):
        chg_d = row['change']
        pct_d = row['change_pct']
        color = '#22c55e' if chg_d >= 0 else '#ef4444'
        with cols[i]:
            st.markdown(
                f'<div style="text-align:center;background:#141720;border-radius:8px;'
                f'padding:8px 4px;border:1px solid #252a38">'
                f'<div style="font-size:11px;color:#8892a4">{row["date"][5:]}</div>'
                f'<div style="font-size:15px;font-weight:700">{row["close"]:,.2f}</div>'
                f'<div style="font-size:12px;color:{color}">{chg_d:+.2f} ({pct_d:+.2f}%)</div>'
                f'<div style="font-size:11px;color:#6b7280">&nbsp;</div>'
                f'</div>',
                unsafe_allow_html=True
            )


# ── 法人買超排行榜 ───────────────────────
def render_ranking():
    st.markdown('## 🏆 三大法人買賣超排行榜')

    last_date = get_t86_last_date()
    if not last_date:
        st.warning('尚無排行資料，請先按左側「🔄 手動更新資料」抓取最新數據。')
        return

    st.caption(f'資料日期：{last_date}　｜　投信含 ETF 買盤，可反映 ETF 資金動向')

    tabs = st.tabs([
        '📈 投信買超 Top15', '📉 投信賣超 Top15',
        '📈 外資買超 Top15', '📉 外資賣超 Top15',
        '📈 三大合計買超 Top15', '📉 三大合計賣超 Top15',
        '🎁 即將除權息',
    ])

    def make_table(rows, net_col, net_label, is_sell=False):
        if not rows:
            st.info('無資料')
            return
        for i, r in enumerate(rows, 1):
            net = r.get(net_col, 0)
            color = '#ff5252' if is_sell else '#00c853'
            buy_key  = net_col.replace('net', 'buy')
            sell_key = net_col.replace('net', 'sell')
            buy_val  = r.get(buy_key, 0)
            sell_val = r.get(sell_key, 0)

            c0, c1, c2, c3, c4, c5 = st.columns([0.5, 1.3, 2.8, 1.8, 1.8, 2])
            c0.markdown(f'**#{i}**')
            c1.markdown(f'`{r["code"]}`')
            c2.markdown(f'**{r["name"]}**')
            if buy_val or sell_val:
                c3.caption(f'買 {buy_val:,}')
                c4.caption(f'賣 {sell_val:,}')
            c5.markdown(
                f'<span style="color:{color};font-weight:bold">'
                f'{net_label} {net:+,} 張</span>',
                unsafe_allow_html=True
            )
        st.markdown('---')
        st.caption('💡 在左側搜尋欄輸入代碼可查看該股詳細分析')

    with tabs[0]:
        rows, _ = get_t86_ranking(last_date, sort_by='trust_net', top=15)
        st.markdown('#### 投信淨買超前 15 名（含 ETF 買盤）')
        make_table(rows, 'trust_net', '投信淨')

    with tabs[1]:
        rows, _ = get_t86_ranking_bottom(last_date, sort_by='trust_net', top=15)
        st.markdown('#### 投信淨賣超前 15 名（法人撤退訊號）')
        make_table(rows, 'trust_net', '投信淨', is_sell=True)

    with tabs[2]:
        rows, _ = get_t86_ranking(last_date, sort_by='foreign_net', top=15)
        st.markdown('#### 外資淨買超前 15 名')
        make_table(rows, 'foreign_net', '外資淨')

    with tabs[3]:
        rows, _ = get_t86_ranking_bottom(last_date, sort_by='foreign_net', top=15)
        st.markdown('#### 外資淨賣超前 15 名')
        make_table(rows, 'foreign_net', '外資淨', is_sell=True)

    with tabs[4]:
        rows, _ = get_t86_ranking(last_date, sort_by='total_net', top=15)
        st.markdown('#### 三大法人合計淨買超前 15 名')
        make_table(rows, 'total_net', '合計淨')

    with tabs[5]:
        rows, _ = get_t86_ranking_bottom(last_date, sort_by='total_net', top=15)
        st.markdown('#### 三大法人合計淨賣超前 15 名')
        make_table(rows, 'total_net', '合計淨', is_sell=True)

    with tabs[6]:
        st.markdown('#### 未來 30 天除權息公告')
        st.caption('資料來源：TWSE TWT49U，顯示今日起未來一個月內已公告的除權息預告')
        ex_rows = get_exdividend_upcoming(days=30)
        if not ex_rows:
            st.warning('目前無未來一個月內的除權息公告，請先按左側「🔄 手動更新資料」。')
        else:
            type_icon = {'息': '💰', '權': '📊', '權息': '💰📊'}
            header = st.columns([1.5, 1.2, 2.5, 1.5, 1.5, 1.5, 1])
            header[0].caption('除權息日')
            header[1].caption('代號')
            header[2].caption('名稱')
            header[3].caption('前收盤')
            header[4].caption('參考價')
            header[5].caption('權息值')
            header[6].caption('類型')
            st.markdown('---')
            for r in ex_rows:
                icon = type_icon.get(r['div_type'], '📌')
                c0,c1,c2,c3,c4,c5,c6 = st.columns([1.5, 1.2, 2.5, 1.5, 1.5, 1.5, 1])
                c0.write(r['ex_date'])
                c1.write(f"`{r['code']}`")
                c2.write(r['name'])
                c3.write(f"{r['prev_close']:.2f}")
                c4.write(f"{r['ref_price']:.2f}")
                c5.markdown(
                    f'<span style="color:#facc15;font-weight:bold">{r["div_value"]:.2f}</span>',
                    unsafe_allow_html=True)
                c6.write(f'{icon} {r["div_type"]}')
            st.markdown('---')
            st.caption('💡 在左側搜尋欄輸入代碼可查看該股詳細分析')

# ── 主程式 ──────────────────────────────
def main():
    render_sidebar()

    page = st.session_state.get('page', 'stock')

    # 大盤分析頁
    if page == 'market':
        render_market()
        return

    # 排行榜頁
    if page == 'ranking':
        render_ranking()
        return

    if 'current_code' not in st.session_state:
        st.markdown('## 📈 台股投資分析工具')
        st.info('請從左側側邊欄搜尋股票，或點選自選股清單中的股票開始分析。')
        return

    code = st.session_state['current_code']

    # 抓取資料
    prices    = get_prices(code, days=400)
    fund_data = get_fundamentals(code, days=400)
    chips_list = get_chips(code, days=65)

    # 價格或籌碼歷史不足時自動補抓（每支股票每次 session 只試一次，避免無限循環）
    need_price = len(prices) < 60
    need_chips = len(chips_list) < 20
    fetch_key  = f'_fetched_{code}'

    if IS_LOCAL and (need_price or need_chips) and not st.session_state.get(fetch_key):
        st.session_state[fetch_key] = True
        with st.status(f'正在補齊 {code} 歷史資料...', expanded=True) as _st:
            if need_price:
                st.write('📥 抓取價格歷史（約 10 秒）...')
                try:
                    from fetcher import fetch_history
                    fetch_history(code, months=3)
                    st.write('✅ 價格資料完成')
                except Exception as _e:
                    st.write(f'⚠️ 價格資料失敗：{_e}')

            if need_chips:
                st.write('📥 抓取籌碼歷史（約 30 秒）...')
                try:
                    from fetcher import fetch_chips_history
                    n = fetch_chips_history(code, months=3)
                    st.write(f'✅ 籌碼資料完成（新增 {n} 筆）')
                except Exception as _e:
                    st.write(f'⚠️ 籌碼資料失敗：{_e}')

            _st.update(label='歷史資料補齊完成', state='complete')

        prices     = get_prices(code, days=400)
        fund_data  = get_fundamentals(code, days=400)
        chips_list = get_chips(code, days=65)
    elif not IS_LOCAL and (need_price or need_chips):
        st.info('☁️ 雲端版為唯讀模式，此股票資料需在本機同步後才可查看。')

    if not prices:
        st.warning(f'無法載入 {code} 的資料，請確認股票代碼是否正確。')
        return

    # 取得股票名稱
    from database import search_stock
    results = search_stock(code)
    name = results[0]['name'] if results else code

    # 計算評分（外資持股比率從 DB 讀取真實資料）
    _own = get_ownership(code)
    _foreign_pct = round(_own['foreign_pct'], 1) if _own else 52
    ownership = {
        'foreign':  _foreign_pct,
        'trust':    5,                          # 投信：暫無每日持股%資料，預設估算
        'dealer':   2,                          # 自營：暫無每日持股%資料，預設估算
        'director': 12,                         # 董監：季報資料，暫用估算
        'retail':   max(0, 100 - _foreign_pct - 5 - 2 - 12),
    }
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
