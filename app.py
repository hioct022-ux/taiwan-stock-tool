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
                      get_t86_market_aggregate, get_chips_market_aggregate,
                      get_chips_market_agg_from_table,
                      get_exdividend, get_exdividend_upcoming, get_exdividend_by_code,
                      get_market_margin, get_futures_institutional, get_market_pe,
                      get_tags, add_tag, rename_tag, delete_tag,
                      update_watchlist_tags)
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
    /* 縮小主內容區頂部留白，讓右側內容盡量往上對齊 */
    .block-container {
        padding-top: 1rem !important;
    }
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
    fig.update_xaxes(tickformat='%Y-%m-%d', hoverformat='%Y-%m-%d')
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CONFIG, key=key)

# ── 初始化 ──────────────────────────────
init_db()

# 雲端模式初始化：模組頂層直接執行，無 cache 包裝
_CLOUD_INIT_STATUS = '未執行'
if not IS_LOCAL:
    try:
        from github_sync import init_cloud_data
        init_cloud_data()
        _CLOUD_INIT_STATUS = 'OK'
    except Exception as _ce:
        _CLOUD_INIT_STATUS = f'ERROR: {_ce}'

# 本機才啟動自動排程
if IS_LOCAL:
    start_scheduler()


# ── JS：清除sidebar localStorage + 移除收起按鈕 ──
st.html("""
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
""", unsafe_allow_javascript=True)

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

            # 手動更新（只抓資料，不推 GitHub）
            if st.button('🔄 手動更新資料', use_container_width=True):
                with st.status('更新資料中...', expanded=True) as _status2:
                    try:
                        from fetcher import fetch_all
                        fetch_all()
                        _status2.update(label='✅ 資料更新完成', state='complete')
                    except Exception as _e:
                        _status2.update(label=f'⚠️ 部分失敗：{_e}', state='error')
                # 清除評分快取，讓排序使用最新資料
                st.session_state.pop('_wl_scores', None)
                st.rerun()

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
                    _sync_ok = False
                    try:
                        from github_sync import sync_via_git
                        ok, msg = sync_via_git()
                        if ok:
                            st.write(f'✅ {msg}')
                            st.write('🌐 雲端版約 1 分鐘後自動更新')
                            _sync_ok = True
                        else:
                            st.error(f'❌ 同步失敗：{msg}')
                            st.warning('雲端資料**未更新**。請至終端機確認：`cd ~/台股分析工具 && git status`')
                            _sync_ok = False
                    except Exception as _e:
                        st.error(f'❌ 同步失敗：{_e}')
                        _sync_ok = False
                    _status.update(
                        label='✅ 完成！' if (_fetch_ok and _sync_ok) else '❌ 同步失敗，雲端未更新' if not _sync_ok else '⚠️ 完成（抓取部分失敗）',
                        state='complete' if (_fetch_ok and _sync_ok) else 'error'
                    )
                st.rerun()

            st.markdown('---')

        else:
            # 雲端版診斷顯示
            try:
                import json as _jmeta
                from config import JSON_DIR as _jdir
                _meta = _jmeta.load(open(os.path.join(_jdir, 'meta.json'), encoding='utf-8'))
                st.caption(f'📅 資料同步：{_meta.get("exported_at", "—")}')
            except Exception as _me:
                st.caption(f'📅 meta.json 讀取失敗：{_me}')
            st.caption(f'🔧 init狀態：{_CLOUD_INIT_STATUS}')
            try:
                _db_date = get_latest_price_date('TAIEX')
                st.caption(f'🗄️ DB截至：{_db_date or "無資料"}')
            except Exception as _de:
                st.caption(f'🗄️ DB查詢失敗：{_de}')
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

        # 先讀取自選股和標籤（搜尋區塊也會用到）
        watchlist = get_watchlist()
        TAG_LIST  = get_tags()
        _TAG_ICONS = ['🟢','🔵','🟡','🟠','🔴','🟣','⚪','🟤']
        TAG_COLOR  = {t: _TAG_ICONS[i % len(_TAG_ICONS)] for i, t in enumerate(TAG_LIST)}

        # 股票搜尋 + 加入自選股（合併）
        st.markdown('#### 🔍 搜尋股票')
        if not IS_LOCAL:
            st.caption('☁️ 雲端版僅可查詢已同步的股票')
        keyword = st.text_input('輸入代碼或名稱', placeholder='例如：2330 或 台積電')
        if keyword:
            results = search_stock(keyword)
            if results:
                existing_codes = {w['code'] for w in watchlist}
                options = {f"{r['code']} {r['name']}": r for r in results}
                selected_label = st.selectbox('搜尋結果', list(options.keys()), label_visibility='collapsed')
                selected_stock = options[selected_label]
                already = selected_stock['code'] in existing_codes
                # 查看 / 加入自選股
                b1, b2 = st.columns(2)
                with b1:
                    if st.button('📊 查看', use_container_width=True):
                        st.session_state['current_code'] = selected_stock['code']
                        st.session_state['page'] = 'stock'
                        st.rerun()
                with b2:
                    if IS_LOCAL:
                        if already:
                            st.button('✅ 已加入', use_container_width=True, disabled=True)
                        else:
                            if st.button('⭐ 自選股', use_container_width=True):
                                st.session_state['_add_wl_stock'] = selected_stock
                                st.rerun()
                # 選標籤後確認加入
                if IS_LOCAL and not already and st.session_state.get('_add_wl_stock', {}).get('code') == selected_stock['code']:
                    add_tags_sel = st.multiselect('選擇標籤（可多選）', TAG_LIST or ['其他'], key='search_add_tag')
                    if st.button('確認加入自選股', use_container_width=True):
                        s = st.session_state.pop('_add_wl_stock')
                        add_watchlist(s['code'], s['name'], add_tags_sel)
                        st.success(f'已加入 {s["code"]} {s["name"]}')
                        st.rerun()
            else:
                st.warning('找不到符合的股票，請確認代碼是否正確')

        st.markdown('---')

        # 自選股清單
        st.markdown('#### ⭐ 自選股清單')

        if watchlist:
            # 標籤篩選
            filter_opts = ['全部'] + TAG_LIST
            sel_filter  = st.radio(
                '篩選', filter_opts, horizontal=True,
                key='watchlist_tag_filter', label_visibility='collapsed'
            )
            filtered = (watchlist if sel_filter == '全部'
                        else [w for w in watchlist if sel_filter in w.get('tags', [])])

            # 排序方式
            sort_mode = st.radio(
                '排序', ['加入順序', '評分高→低', '評分低→高'],
                horizontal=True, key='watchlist_sort', label_visibility='collapsed'
            )

            if sort_mode in ('評分高→低', '評分低→高'):
                # 雲端版每次重算（資料靜態，快取無意義）；本機版快取避免重複計算
                if not IS_LOCAL:
                    st.session_state.pop('_wl_scores', None)
                _score_cache = st.session_state.get('_wl_scores', {})
                _need_calc   = [w for w in filtered if w['code'] not in _score_cache]
                if _need_calc:
                    with st.spinner(f'計算評分中（{len(_need_calc)} 支）...'):
                        for w in _need_calc:
                            try:
                                _p   = get_prices(w['code'], days=400)
                                _f   = get_fundamentals(w['code'])
                                _c   = get_chips(w['code'], days=65)
                                _own = get_ownership(w['code'])
                                _fpct = round(_own['foreign_pct'], 1) if _own else 52
                                _ownership = {
                                    'foreign':  _fpct,
                                    'trust':    5,
                                    'dealer':   2,
                                    'director': 12,
                                    'retail':   max(0, 100 - _fpct - 5 - 2 - 12),
                                }
                                _r  = full_score(_p, _f, _c, _ownership)
                                _score_cache[w['code']] = _r['total_score'] if _r else 0
                            except:
                                _score_cache[w['code']] = 0
                    st.session_state['_wl_scores'] = _score_cache

                filtered = sorted(
                    filtered,
                    key=lambda w: _score_cache.get(w['code'], 0),
                    reverse=(sort_mode == '評分高→低')
                )


            for w in filtered:
                w_tags    = w.get('tags', [])
                tag_icons = ''.join(TAG_COLOR.get(t, '⚪') for t in w_tags) or '⚪'
                _score_str = ''
                if sort_mode in ('評分高→低', '評分低→高'):
                    _s = st.session_state.get('_wl_scores', {}).get(w['code'])
                    if _s is not None:
                        _score_str = f' {_s}分'
                if IS_LOCAL:
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        if st.button(
                            f"{tag_icons} {w['code']} {w['name']}{_score_str}",
                            key=f"watch_{w['code']}", use_container_width=True
                        ):
                            st.session_state['current_code'] = w['code']
                            st.session_state['page'] = 'stock'
                            st.rerun()
                    with col2:
                        if st.button('⋯', key=f"edit_{w['code']}", help='修改/刪除'):
                            st.session_state[f'_wl_edit_{w["code"]}'] = not st.session_state.get(f'_wl_edit_{w["code"]}', False)
                            st.rerun()
                    # 展開編輯列
                    if st.session_state.get(f'_wl_edit_{w["code"]}'):
                        new_tags_sel = st.multiselect(
                            '標籤（可多選）', TAG_LIST,
                            default=[t for t in w_tags if t in TAG_LIST],
                            key=f'tagsel_{w["code"]}'
                        )
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            if st.button('✔ 儲存', key=f'save_tag_{w["code"]}', use_container_width=True):
                                update_watchlist_tags(w['code'], new_tags_sel)
                                st.session_state.pop(f'_wl_edit_{w["code"]}', None)
                                st.rerun()
                        with bc2:
                            if st.button('🗑 刪除', key=f'del_{w["code"]}', use_container_width=True):
                                remove_watchlist(w['code'])
                                st.session_state.pop(f'_wl_edit_{w["code"]}', None)
                                st.rerun()
                else:
                    tag_icons = ''.join(TAG_COLOR.get(t, '⚪') for t in w_tags) or '⚪'
                    if st.button(
                        f"{tag_icons} {w['code']} {w['name']}{_score_str}",
                        key=f"watch_{w['code']}", use_container_width=True
                    ):
                        st.session_state['current_code'] = w['code']
                        st.session_state['page'] = 'stock'
                        st.rerun()
        else:
            st.info('尚無自選股，搜尋後加入')

        if IS_LOCAL:
            st.markdown('---')
            # 標籤管理
            with st.expander('🏷️ 管理標籤'):
                st.caption('新增標籤')
                nc1, nc2 = st.columns([3, 1])
                with nc1:
                    new_tag_name = st.text_input('標籤名稱', placeholder='例如：短線', key='new_tag_input', label_visibility='collapsed')
                with nc2:
                    if st.button('新增', key='btn_add_tag', use_container_width=True):
                        if new_tag_name.strip():
                            if add_tag(new_tag_name.strip()):
                                st.success(f'已新增「{new_tag_name.strip()}」')
                                st.rerun()
                            else:
                                st.error('標籤已存在')
                        else:
                            st.error('請輸入標籤名稱')

                if TAG_LIST:
                    st.caption('重新命名 / 刪除')
                    for t in TAG_LIST:
                        r1, r2, r3 = st.columns([3, 2, 1])
                        with r1:
                            new_name_input = st.text_input(
                                t, value=t, key=f'rename_{t}', label_visibility='collapsed'
                            )
                        with r2:
                            if st.button('改名', key=f'btn_rename_{t}', use_container_width=True):
                                if new_name_input.strip() and new_name_input.strip() != t:
                                    rename_tag(t, new_name_input.strip())
                                    st.rerun()
                        with r3:
                            if st.button('✕', key=f'btn_del_tag_{t}', help=f'刪除標籤「{t}」'):
                                delete_tag(t)
                                st.rerun()
        else:
            st.caption('✏️ 新增/刪除自選股請在本機操作後同步')

        st.markdown('---')
        if st.button('📖 程式說明', use_container_width=True):
            st.session_state['page'] = 'doc'
            st.session_state.pop('current_code', None)
            st.rerun()

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

    st.markdown(f'**{name} 近3個月走勢（65個交易日）**')

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=('', '')
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

    if avg_vol and dates:
        fig.add_trace(go.Scatter(
            x=[dates[0], dates[-1]],
            y=[avg_vol, avg_vol],
            mode='lines',
            line=dict(dash='dash', color='#f59e0b', width=1),
            showlegend=False,
            hovertemplate=f'均量：{avg_vol:,}<extra></extra>'
        ), row=2, col=1)

    fig.update_layout(
        title=None,
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

    # ── 區間相對位置（20日 / 65日 / 250日）──
    st.markdown('---')
    st.markdown('#### 📍 區間相對位置')

    pos_20  = ind.get('pos_20')
    pos_250 = ind.get('pos_250')
    h20  = ind.get('high_20');  l20  = ind.get('low_20')
    h250 = ind.get('high_250'); l250 = ind.get('low_250')

    def _pos_color(p):
        if p is None: return '#94a3b8'
        if p >= 80:   return '#ef4444'
        if p <= 20:   return '#22c55e'
        return '#f59e0b'

    def _pos_label(p):
        if p is None: return '—'
        if p >= 80:   return '高檔區 ⚠️'
        if p <= 20:   return '低檔區 ✅'
        return '中間段'

    pc1, pc2, pc3 = st.columns(3)
    for col, label, days, pos, hi, lo in [
        (pc1, '近1個月（20日）', 20,  pos_20,  h20,  l20),
        (pc2, '近3個月（65日）', 65,  pos_65,  ind.get('high_65'), ind.get('low_65')),
        (pc3, '近1年（250日）',  250, pos_250, h250, l250),
    ]:
        with col:
            color = _pos_color(pos)
            pct_str = f'{pos:.1f}%' if pos is not None else '—'
            col.markdown(
                f'**{label}**<br>'
                f'<span style="font-size:28px;font-weight:700;color:{color}">{pct_str}</span><br>'
                f'<span style="font-size:11px;color:#64748b">{_pos_label(pos)}</span>',
                unsafe_allow_html=True)
            if hi and lo:
                col.caption(f'高 {hi:,.2f}　低 {lo:,.2f}')

    st.caption('位置 % = (今日收盤 − 區間最低) ÷ (區間最高 − 區間最低) × 100　｜　≥80% 高檔、≤20% 低檔')

    # ── 乖離率（BIAS）────────────────────
    bias5  = ind.get('bias5')
    bias20 = ind.get('bias20')
    if bias5 is not None or bias20 is not None:
        st.markdown('#### 📐 乖離率（短線過熱/超賣）')
        bc1, bc2 = st.columns(2)

        def _bias_color(b):
            if b is None: return '#94a3b8'
            if b > 5:  return '#ef4444'
            if b > 2:  return '#f59e0b'
            if b < -5: return '#22c55e'
            if b < -2: return '#38bdf8'
            return '#94a3b8'

        def _bias_label(b):
            if b is None: return '—'
            if b > 5:  return '短線過熱，留意回測 ⚠️'
            if b > 2:  return '偏多偏貴，不追高'
            if b < -5: return '短線超賣，留意反彈 ✅'
            if b < -2: return '偏低偏便宜'
            return '正常貼線'

        with bc1:
            b5c = _bias_color(bias5)
            st.markdown(
                f'**BIAS5（vs MA5）**<br>'
                f'<span style="font-size:28px;font-weight:700;color:{b5c}">'
                f'{bias5:+.2f}%</span><br>'
                f'<span style="font-size:11px;color:#64748b">{_bias_label(bias5)}</span>',
                unsafe_allow_html=True)
        with bc2:
            b20c = _bias_color(bias20)
            st.markdown(
                f'**BIAS20（vs MA20）**<br>'
                f'<span style="font-size:28px;font-weight:700;color:{b20c}">'
                f'{bias20:+.2f}%</span><br>'
                f'<span style="font-size:11px;color:#64748b">{_bias_label(bias20)}</span>',
                unsafe_allow_html=True)
        st.caption('乖離率 = (收盤 − 均線) ÷ 均線 × 100　｜　BIAS5 > +5% 短線過熱、< -5% 超賣')

    if cons_days and cons_dir:
            dir_str = '上漲' if cons_dir == 'up' else '下跌'
            dir_color = '#22c55e' if cons_dir == 'up' else '#ef4444'
            st.markdown(f'連續<span style="color:{dir_color};font-weight:700">'
                        f'{cons_days}個交易日{dir_str}</span>',
                        unsafe_allow_html=True)

    # ── 今日 K 線解讀 ─────────────────────
    st.markdown('---')
    st.markdown('#### 🕯️ 今日 K 線解讀')

    _dates   = ind.get('dates', [])
    _opens   = ind.get('opens', [])
    _highs   = ind.get('highs', [])
    _lows    = ind.get('lows', [])
    _closes  = ind.get('closes', [])
    _volumes = ind.get('volumes', [])

    if _dates and len(_dates) >= 2:
        o       = _opens[-1]   if _opens   else 0
        h       = _highs[-1]   if _highs   else 0
        l       = _lows[-1]    if _lows    else 0
        c       = _closes[-1]  if _closes  else 0
        vol     = _volumes[-1] if _volumes else 0
        prev_c  = _closes[-2]  if len(_closes) >= 2 else c
        avg_vol = ind.get('avg_vol_20', 0)

    if _dates and len(_dates) >= 2 and o and h and l and c:

        if o and h and l and c:
            body        = abs(c - o)
            total_range = h - l if h > l else 0.001
            upper_wick  = h - max(o, c)
            lower_wick  = min(o, c) - l
            is_red      = c < o
            body_pct    = round(body / total_range * 100, 1) if total_range else 0
            upper_pct   = round(upper_wick / total_range * 100, 1) if total_range else 0
            lower_pct   = round(lower_wick / total_range * 100, 1) if total_range else 0
            vol_ratio   = round(vol / avg_vol, 2) if avg_vol else 0

            # ── K 線圖（近20日）＋ 均線 ＋ 數值指標並排 ──
            _kl_col, _km_col = st.columns([1, 1])
            with _kl_col:
                _n = min(20, len(_dates))
                _ma5s  = ind.get('ma5_series',  [])
                _ma20s = ind.get('ma20_series', [])
                _ma60s = ind.get('ma60_series', [])
                _fig_k = go.Figure()
                _fig_k.add_trace(go.Candlestick(
                    x=_dates[-_n:],
                    open=_opens[-_n:],  high=_highs[-_n:],
                    low=_lows[-_n:],    close=_closes[-_n:],
                    increasing_line_color='#ef4444', increasing_fillcolor='#ef4444',
                    decreasing_line_color='#22c55e', decreasing_fillcolor='#22c55e',
                    name='K線', showlegend=False,
                ))
                if _ma5s and len(_ma5s) >= _n:
                    _fig_k.add_trace(go.Scatter(
                        x=_dates[-_n:], y=_ma5s[-_n:], name='MA5',
                        line=dict(color='#f59e0b', width=1.2), connectgaps=True))
                if _ma20s and len(_ma20s) >= _n:
                    _fig_k.add_trace(go.Scatter(
                        x=_dates[-_n:], y=_ma20s[-_n:], name='MA20',
                        line=dict(color='#a78bfa', width=1.2), connectgaps=True))
                if _ma60s and len(_ma60s) >= _n:
                    _fig_k.add_trace(go.Scatter(
                        x=_dates[-_n:], y=_ma60s[-_n:], name='MA60',
                        line=dict(color='#22c55e', width=1.2), connectgaps=True))
                _fig_k.update_layout(
                    height=250, margin=dict(l=0, r=0, t=8, b=0),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02,
                                font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
                    xaxis=dict(showgrid=False, tickformat='%m/%d', tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True, gridcolor='#1e293b', tickfont=dict(size=9)),
                    xaxis_rangeslider_visible=False,
                )
                show_chart(_fig_k)
            with _km_col:
                kc1, kc2 = st.columns(2)
                kc1.metric('開盤', f'{o:.1f}')
                kc2.metric('最高', f'{h:.1f}', delta=f'+{h-o:.1f}' if h > o else None)
                kc3, kc4 = st.columns(2)
                kc3.metric('最低', f'{l:.1f}', delta=f'{l-o:.1f}' if l < o else None)
                kc4.metric('收盤', f'{c:.1f}', delta=f'{c-prev_c:+.1f}')

            # ── 下方全寬顯示指標（佔位用，後面不重複 metric）──
            st.markdown('')

            # ── 影線判斷 ──
            msgs = []

            # 上影線
            if upper_pct >= 40:
                msgs.append(('🔴', f'**長上影線**（{upper_pct:.0f}%）：高檔遇到強烈賣壓，多方攻高後被壓回，次日偏弱。'))
            elif upper_pct >= 20:
                msgs.append(('🟡', f'**中上影線**（{upper_pct:.0f}%）：高點有壓但未被完全壓制，需觀察次日能否突破。'))

            # 下影線
            if lower_pct >= 40:
                msgs.append(('🟢', f'**長下影線**（{lower_pct:.0f}%）：低點有強力買盤承接，次日偏強。'))
            elif lower_pct >= 20:
                msgs.append(('🟡', f'**中下影線**（{lower_pct:.0f}%）：低點有支撐買盤，但力道尚可觀察。'))

            # 實體判斷
            if body_pct >= 60:
                if not is_red:
                    msgs.append(('🟢', f'**大紅K實體**（{body_pct:.0f}%）：多方強勢主導全日，買氣充沛。'))
                else:
                    msgs.append(('🔴', f'**大黑K實體**（{body_pct:.0f}%）：空方強勢主導全日，賣壓沉重。'))
            elif body_pct <= 15:
                if upper_pct >= 30 and lower_pct >= 30:
                    msgs.append(('🟡', '**十字星**：多空交戰激烈，方向未定，為轉折警示訊號。'))
                else:
                    msgs.append(('🟡', '**小實體**：多空力道相當，盤整格局，方向待確認。'))

            # 量能強化判斷
            if vol_ratio >= 2.0:
                if not is_red and upper_pct < 30:
                    msgs.append(('🟢', f'**爆量收紅**（均量 {vol_ratio}倍）：主力積極進場，買盤強勁，次日延續機率高。'))
                elif not is_red and upper_pct >= 30:
                    msgs.append(('🔴', f'**爆量長上影**（均量 {vol_ratio}倍）：放量攻高後遭壓回，主力可能在出貨，**需警戒**。'))
                elif is_red:
                    msgs.append(('🔴', f'**爆量收黑**（均量 {vol_ratio}倍）：空方大量殺出，賣壓沉重，次日偏弱。'))
            elif vol_ratio >= 1.3:
                msgs.append(('🟡', f'**溫和放量**（均量 {vol_ratio}倍）：市場參與度提升，方向參考 K 線型態。'))
            elif vol_ratio <= 0.6 and vol_ratio > 0:
                msgs.append(('🟡', f'**明顯縮量**（均量 {vol_ratio}倍）：市場觀望，型態訊號可信度降低。'))

            # 次日操作提示
            scores = sum(1 for m in msgs if m[0] == '🟢') - sum(1 for m in msgs if m[0] == '🔴')
            if scores >= 2:
                verdict = '🟢 **次日偏多**：多項訊號支持，可留意開盤強弱確認後操作。'
            elif scores <= -2:
                verdict = '🔴 **次日偏空**：多項賣壓訊號，建議謹慎，可設保護停損。'
            else:
                verdict = '🟡 **次日中性**：訊號混雜，建議觀察開盤 30 分鐘量價確認方向。'

            for icon, msg in msgs:
                color = '#22c55e' if icon == '🟢' else '#ef4444' if icon == '🔴' else '#f59e0b'
                st.markdown(
                    f'<div style="padding:5px 10px;border-left:3px solid {color};margin-bottom:5px">'
                    f'{icon} {msg}</div>',
                    unsafe_allow_html=True
                )

            st.markdown(
                f'<div style="background:#1a1f2e;border-radius:8px;padding:12px 16px;margin-top:8px">'
                f'<span style="font-size:14px">{verdict}</span></div>',
                unsafe_allow_html=True
            )
            st.caption(
                f'振幅：{total_range:.1f}元　實體：{body_pct:.0f}%　'
                f'上影：{upper_pct:.0f}%　下影：{lower_pct:.0f}%　'
                f'成交量：均量 {vol_ratio} 倍　｜　僅供參考，不影響評分'
            )
    elif not (_dates and len(_dates) >= 2):
        st.info('需要至少 2 日價格資料才能顯示 K 線解讀。')


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
        # 用 DB 最新收盤價計算殖利率
        _latest_close = close  # 已從 result 取得
        _yield = round(latest['div_value'] / _latest_close * 100, 2) if _latest_close and _latest_close > 0 and latest['div_value'] > 0 else 0
        _yield_str = f'　殖利率 <span style="color:#22c55e;font-weight:700">{_yield:.2f}%</span>' if _yield > 0 else ''
        _ref_str   = f'　參考價 {latest["ref_price"]:.2f} 元' if latest.get('ref_price') and latest['ref_price'] > 0 else ''
        _status    = '✅ 正式' if latest.get('is_confirmed') else '📋 預告'
        st.markdown(
            f'<div style="background:#0f2818;border:1px solid #22c55e;border-radius:8px;padding:10px 14px">'
            f'🎁 <b>即將{type_label}</b>（{_status}）：{latest["ex_date"]}　'
            f'權息值 <b>{latest["div_value"]:.4f} 元</b>{_ref_str}{_yield_str}'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown('')

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
                st.error(f'PB={pb:.2f}倍極高，市場期待非常強勁的成長，若獲利不如預期股價修正風險大。')

    # ── 季度 EPS 歷史線圖 ────────────────────
    st.markdown('---')
    st.markdown('#### 📊 季度 EPS 趨勢')

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_quarterly_eps(code, market):
        try:
            import yfinance as yf
            suffix = '.TWO' if market == 'TPEx' else '.TW'
            ticker = yf.Ticker(f'{code}{suffix}')

            # 用 quarterly_income_stmt 的 Net Income 計算季度 EPS
            qi = ticker.quarterly_income_stmt
            if qi is None or qi.empty or 'Net Income' not in qi.index:
                return [], []

            net_income = qi.loc['Net Income'].dropna()
            if net_income.empty:
                return [], []

            info   = ticker.info
            shares = info.get('sharesOutstanding', 0)
            if not shares:
                return [], []

            # 由舊到新排序
            net_income = net_income.sort_index()
            quarters = [str(d)[:7] for d in net_income.index]  # 例：2025-06
            eps_vals  = [round(float(v) / shares, 2) for v in net_income.values]
            return quarters, eps_vals
        except Exception:
            pass
        return [], []

    # 取得市場別
    from database import get_conn as _gc_eps
    _conn_eps = _gc_eps()
    _mkt_eps = (_conn_eps.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
    _conn_eps.close()

    q_dates, q_eps = _get_quarterly_eps(code, _mkt_eps or 'TWSE')

    if q_dates and q_eps:
        # 顏色：比上季成長→綠，衰退→紅
        bar_colors = []
        for i, v in enumerate(q_eps):
            if i == 0:
                bar_colors.append('#38bdf8')
            elif v >= q_eps[i - 1]:
                bar_colors.append('#22c55e')
            else:
                bar_colors.append('#ef4444')

        fig_eps = go.Figure(go.Bar(
            x=q_dates, y=q_eps,
            marker_color=bar_colors,
            text=[f'{v:.2f}' for v in q_eps],
            textposition='outside',
            textfont=dict(size=10)
        ))
        fig_eps.update_layout(
            height=260,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=20, b=0),
            yaxis=dict(gridcolor='#1e293b', title='EPS（元）'),
            xaxis=dict(gridcolor='#1e293b'),
            font=dict(color='#94a3b8', size=11),
        )
        show_chart(fig_eps)
        # 趨勢判斷
        if len(q_eps) >= 2:
            trend = q_eps[-1] - q_eps[-2]
            if trend > 0:
                st.caption(f'✅ 最近一季 EPS {q_eps[-1]:.2f} 元，較上季成長 {trend:+.2f} 元')
            else:
                st.caption(f'⚠️ 最近一季 EPS {q_eps[-1]:.2f} 元，較上季衰退 {trend:+.2f} 元')
        st.caption('資料來源：yfinance　｜　綠色＝季增，紅色＝季減　｜　此圖僅供參考，不影響評分')
    else:
        st.info('季度 EPS 資料暫無（yfinance 尚未提供此股資料）')


# ── 頁籤三：籌碼面 ──────────────────────
def render_chips(result, code, name, chips_list, market=None):
    st.markdown('#### 三大法人')

    if not chips_list:
        if market == 'TPEx':
            st.info(
                '**上櫃股票不支援籌碼面資料。**\n\n'
                '台灣證交所（TWSE）T86 法人買賣超 API 僅涵蓋上市股；'
                '櫃買中心目前未開放對應的逐日法人買賣超歷史查詢介面，'
                '因此上櫃股（TPEx）的三大法人、融資融券資料暫無法取得。'
            )
        else:
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
    if len(chips_list) < 5:
        st.info('籌碼歷史資料不足（需至少 5 個交易日），請在本機更新資料後同步。')
    elif len(chips_list) >= 5:
        dates_c   = [r['date'] for r in recent65]
        f_nets    = [r.get('foreign_net', 0) for r in recent65]
        t_nets    = [r.get('trust_net',   0) for r in recent65]
        d_nets    = [r.get('dealer_net',  0) for r in recent65]

        fig_chips = go.Figure()
        fig_chips.add_trace(go.Bar(
            x=dates_c, y=f_nets, name='外資',
            marker_color='#f97316', opacity=0.85
        ))
        fig_chips.add_trace(go.Scatter(
            x=dates_c, y=t_nets, name='投信',
            mode='lines+markers', line=dict(color='#38bdf8', width=2),
            marker=dict(size=4)
        ))
        if any(v != 0 for v in d_nets):
            fig_chips.add_trace(go.Scatter(
                x=dates_c, y=d_nets, name='自營商',
                mode='lines', line=dict(color='#a78bfa', width=1.5, dash='dot')
            ))
        fig_chips.add_hline(y=0, line_color='#475569', line_width=1)
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

        # ── 個股籌碼判斷 ──────────────────────
        _ck_date = chips_list[-1].get('date', '')          # 資料日期
        _ck_f1   = chips_list[-1].get('foreign_net', 0)   # 最新外資
        _ck_t1   = chips_list[-1].get('trust_net',   0)   # 最新投信
        _ck_f5   = foreign_net5                            # 近5日外資累計
        _ck_t5   = trust_net5                              # 近5日投信累計

        # 外資近3日方向
        _ck_f3   = [r.get('foreign_net', 0) for r in chips_list[-3:]] if len(chips_list) >= 3 else []
        _ck_f3_buy  = sum(1 for v in _ck_f3 if v > 0)
        _ck_f3_sell = sum(1 for v in _ck_f3 if v < 0)

        _ck_msgs = []

        # 外資最新日
        if _ck_f1 >= 5000:
            _ck_msgs.append(('🟢', f'外資大量買超 **+{_ck_f1:,} 張**（{_ck_date}），主力積極布局'))
        elif _ck_f1 >= 1000:
            _ck_msgs.append(('🟢', f'外資買超 +{_ck_f1:,} 張（{_ck_date}），籌碼流入'))
        elif _ck_f1 >= 300:
            _ck_msgs.append(('🟢', f'外資小幅買超 +{_ck_f1:,} 張（{_ck_date}）'))
        elif _ck_f1 <= -5000:
            _ck_msgs.append(('🔴', f'外資大量賣超 **{_ck_f1:,} 張**（{_ck_date}），主力明顯出脫'))
        elif _ck_f1 <= -1000:
            _ck_msgs.append(('🔴', f'外資賣超 {_ck_f1:,} 張（{_ck_date}），籌碼流出'))
        elif _ck_f1 <= -300:
            _ck_msgs.append(('🟡', f'外資小幅賣超 {_ck_f1:,} 張（{_ck_date}）'))
        else:
            _ck_msgs.append(('⚪', f'外資近乎中性（{_ck_date}，{_ck_f1:+,} 張）'))

        # 外資近5日累計
        if _ck_f5 >= 3000:
            _ck_msgs.append(('🟢', f'外資近5日累計買超 +{_ck_f5:,} 張，持續布局'))
        elif _ck_f5 <= -3000:
            _ck_msgs.append(('🔴', f'外資近5日累計賣超 {_ck_f5:,} 張，持續調節'))

        # 外資連續方向
        if len(_ck_f3) == 3:
            if _ck_f3_buy == 3:
                _ck_msgs.append(('🟢', f'外資連續 3 日買超（{_ck_f3[0]:+,} / {_ck_f3[1]:+,} / {_ck_f3[2]:+,}），動能持續'))
            elif _ck_f3_sell == 3:
                _ck_msgs.append(('🔴', f'外資連續 3 日賣超（{_ck_f3[0]:+,} / {_ck_f3[1]:+,} / {_ck_f3[2]:+,}），持續出脫'))

        # 投信方向
        if _ck_t1 >= 1000:
            _ck_msgs.append(('🟢', f'投信買超 +{_ck_t1:,} 張（{_ck_date}），國內法人偏多'))
        elif _ck_t1 >= 200:
            _ck_msgs.append(('🟢', f'投信小幅買超 +{_ck_t1:,} 張（{_ck_date}）'))
        elif _ck_t1 <= -1000:
            _ck_msgs.append(('🔴', f'投信賣超 {_ck_t1:,} 張（{_ck_date}），國內法人偏空'))
        elif _ck_t1 <= -200:
            _ck_msgs.append(('🟡', f'投信小幅賣超 {_ck_t1:,} 張（{_ck_date}）'))

        # 外資+投信合計近5日
        _ck_fi5 = _ck_f5 + _ck_t5
        if _ck_fi5 >= 5000:
            _ck_msgs.append(('🟢', f'外資＋投信近5日合計買超 +{_ck_fi5:,} 張，法人共同偏多'))
        elif _ck_fi5 <= -5000:
            _ck_msgs.append(('🔴', f'外資＋投信近5日合計賣超 {_ck_fi5:,} 張，法人共同偏空'))

        # 顯示訊號
        for _ick, _imsg in _ck_msgs:
            _icolor = '#22c55e' if _ick == '🟢' else '#ef4444' if _ick == '🔴' else '#f59e0b' if _ick == '🟡' else '#475569'
            st.markdown(
                f'<div style="padding:5px 12px;border-left:3px solid {_icolor};margin-bottom:4px;font-size:13px">'
                f'{_ick} {_imsg}</div>', unsafe_allow_html=True)

        # 總結
        _ck_bull = sum(1 for m in _ck_msgs if m[0] == '🟢')
        _ck_bear = sum(1 for m in _ck_msgs if m[0] == '🔴')
        # 以外資近5日累計為主要依據
        if _ck_f5 >= 5000 or (_ck_f5 > 0 and _ck_bull > _ck_bear + 1):
            _ckv, _ckb = '#22c55e', '#0a1a0a'
            _ck_verdict = f'🟢 **籌碼偏多**：外資持續買進，法人態度積極，籌碼面有利多方。'
        elif _ck_f5 >= 1000 or _ck_bull > _ck_bear:
            _ckv, _ckb = '#4ade80', '#0a150a'
            _ck_verdict = f'🟢 **籌碼略偏多**：外資小幅淨買，法人態度偏正面。'
        elif _ck_f5 <= -5000 or (_ck_f5 < 0 and _ck_bear > _ck_bull + 1):
            _ckv, _ckb = '#ef4444', '#2d0a0a'
            _ck_verdict = f'🔴 **籌碼偏空**：外資持續賣出，法人調節明顯，籌碼面承壓。'
        elif _ck_f5 <= -1000 or _ck_bear > _ck_bull:
            _ckv, _ckb = '#f97316', '#2d1500'
            _ck_verdict = f'🟡 **籌碼略偏空**：外資小幅淨賣，法人態度偏保守。'
        else:
            _ckv, _ckb = '#94a3b8', '#1a1f2e'
            _ck_verdict = f'⚪ **籌碼中性**：外資買賣超方向不明確，靜待下一步動作。'

        st.markdown(
            f'<div style="background:{_ckb};border:2px solid {_ckv};border-radius:8px;'
            f'padding:12px 16px;margin-top:8px">'
            f'<span style="color:{_ckv};font-size:14px">{_ck_verdict}</span></div>',
            unsafe_allow_html=True)
        st.markdown('')

    st.markdown('---')
    st.markdown('#### 融資融券')

    # 取最近有融資融券資料的那筆（避免今日法人已更新但融資還未更新導致顯示0）
    margin_rows = [r for r in chips_list if r.get('margin_balance', 0) > 0]
    short_rows  = [r for r in chips_list if r.get('short_balance',  0) > 0]

    col1, col2 = st.columns(2)
    with col1:
        if margin_rows:
            margin_now  = margin_rows[-1].get('margin_balance', 0)
            margin_20   = margin_rows[-20].get('margin_balance', 0) if len(margin_rows) >= 20 else margin_rows[0].get('margin_balance', 0)
            margin_chg  = ((margin_now - margin_20) / margin_20 * 100) if margin_20 > 0 else 0
            chg_color   = '#22c55e' if margin_chg < 0 else '#ef4444'
            st.markdown('**融資餘額**')
            st.metric('目前融資餘額', f'{margin_now:,}張',
                      delta=f'{margin_chg:+.1f}% 較20個交易日前')
            st.info(f'融資是投資人向券商借錢買股票。'
                    f'融資餘額{"減少" if margin_chg < 0 else "增加"}{abs(margin_chg):.1f}%，'
                    f'{"代表借錢追高行為減少，籌碼趨穩，偏正面。" if margin_chg < 0 else "代表借錢追高行為增加，需留意斷頭風險。"}')

    with col2:
        if short_rows:
            short_now = short_rows[-1].get('short_balance', 0)
            short_20  = short_rows[-20].get('short_balance', 0) if len(short_rows) >= 20 else short_rows[0].get('short_balance', 0)
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

    ma5   = ind.get('ma5')   or 'N/A'
    ma20  = ind.get('ma20')  or 'N/A'
    ma60  = ind.get('ma60')  or 'N/A'
    rsi   = ind.get('rsi')   or 'N/A'
    k     = ind.get('k')     or 'N/A'
    d     = ind.get('d')     or 'N/A'
    macd_dif  = ind.get('macd_dif')  or 'N/A'
    macd_def  = ind.get('macd_def')  or 'N/A'
    macd_hist = ind.get('macd_hist') or 'N/A'
    bb_upper  = ind.get('bb_upper')  or 'N/A'
    bb_lower  = ind.get('bb_lower')  or 'N/A'
    vol_ratio = ind.get('vol_ratio') or 'N/A'
    pos_65    = ind.get('pos_65')    or 'N/A'
    high_65   = ind.get('high_65')
    low_65    = ind.get('low_65')
    buy_low   = ind.get('buy_low')
    buy_high  = ind.get('buy_high')
    target    = ind.get('target')
    stop_loss = ind.get('stop_loss')

    pe  = fund.get('pe')  or 0.0
    pb  = fund.get('pb')  or 0.0
    div = fund.get('dividend_yield') or 0.0
    eps = fund.get('eps_ttm') or 0.0

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
@st.cache_data(ttl=900, show_spinner=False)
def _fetch_global_markets():
    """即時抓取美股指數、VIX、台積電ADR、費半、原油、黃金、美元指數（每15分鐘快取一次）"""
    try:
        import yfinance as yf
        # 股市指數群（納入預判評分）
        equity_symbols = {
            'S&P 500': '^GSPC',
            'Nasdaq':  '^IXIC',
            '費半 SOX': '^SOX',
            'TSM ADR': 'TSM',
            'VIX':     '^VIX',
        }
        # 總經指標群（僅顯示參考，不計入評分）
        macro_symbols = {
            'WTI 原油':    'CL=F',
            '黃金':        'GC=F',
            '美元指數':    'DX-Y.NYB',
            '美債10年':    '^TNX',   # 10年期公債殖利率（值為 % 數，如 4.25 = 4.25%）
        }
        result = {}
        for name, sym in {**equity_symbols, **macro_symbols}.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period='5d')
                if not hist.empty:
                    latest = hist.iloc[-1]
                    prev   = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
                    chg_pct = (latest['Close'] - prev['Close']) / prev['Close'] * 100
                    result[name] = {
                        'close':   round(float(latest['Close']), 2),
                        'chg_pct': round(chg_pct, 2),
                        'date':    str(hist.index[-1])[:10],
                    }
            except:
                pass
        return result
    except:
        return {}


def render_market():
    st.markdown('## 📊 大盤走勢分析（加權指數）')

    # ── 外部市場警示 ─────────────────────────
    st.markdown('#### 🌐 外部市場（即時）')
    global_data = _fetch_global_markets()
    if global_data:
        vix_val = global_data.get('VIX', {}).get('close', 0)

        def _market_card(col, name, d):
            chg = d['chg_pct']
            if name == 'VIX':
                color = '#ef4444' if vix_val > 30 else '#f59e0b' if vix_val > 20 else '#22c55e'
                delta_label = f'恐慌 ⚠️' if vix_val > 30 else '警戒' if vix_val > 20 else '正常'
            elif name == '美元指數':
                # DXY 強 = 偏空新興市場，顏色邏輯反轉
                color = '#ef4444' if chg > 0.8 else '#f59e0b' if chg > 0.3 else '#22c55e' if chg < -0.3 else '#94a3b8'
                delta_label = f'{chg:+.2f}%'
            elif name == '美債10年':
                # 殖利率高 / 升息疑慮 = 偏空科技股；殖利率下行 = 偏多
                _tnx = d['close']  # 殖利率值，如 4.25 = 4.25%
                # 變動量（殖利率本身就是 %，用絕對變動 bps 較直覺）
                _tnx_abs_chg = round(_tnx * chg / 100, 3)  # 殖利率絕對變動（百分點）
                color = '#ef4444' if _tnx >= 4.5 else '#f97316' if _tnx >= 4.0 else '#22c55e' if _tnx < 3.5 else '#94a3b8'
                delta_label = f'今日變動 {_tnx_abs_chg:+.3f}%　{"殖利率偏高⚠️" if _tnx >= 4.5 else "升息疑慮" if _tnx >= 4.0 else "利率溫和"}'
            else:
                color = '#ef4444' if chg < -2 else '#f59e0b' if chg < 0 else '#22c55e'
                delta_label = f'{chg:+.2f}%'
            if name == '美債10年':
                close_str = f'{d["close"]:.2f}%'
            elif d['close'] < 10000:
                close_str = f'{d["close"]:,.2f}'
            else:
                close_str = f'{d["close"]:,.0f}'
            col.markdown(
                f'<div style="background:#141720;border:1px solid #252a38;border-radius:8px;padding:10px 14px;margin-bottom:4px">'
                f'<div style="font-size:11px;color:#8892a4;margin-bottom:2px">{name}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{color}">{close_str}</div>'
                f'<div style="font-size:11px;color:{color}">{delta_label}&nbsp;&nbsp;'
                f'<span style="color:#475569">{d["date"]}</span></div>'
                f'</div>',
                unsafe_allow_html=True)

        # 第一列：股市指數
        equity_keys = ['S&P 500', 'Nasdaq', '費半 SOX', 'TSM ADR', 'VIX']
        eq_data = [(k, global_data[k]) for k in equity_keys if k in global_data]
        if eq_data:
            st.caption('📈 股市指數')
            eq_cols = st.columns(len(eq_data))
            for i, (name, d) in enumerate(eq_data):
                _market_card(eq_cols[i], name, d)

        # 第二列：總經指標
        macro_keys = ['WTI 原油', '黃金', '美元指數', '美債10年']
        mc_data = [(k, global_data[k]) for k in macro_keys if k in global_data]
        if mc_data:
            st.caption('🌐 總經指標（參考用，不計入評分）')
            mc_cols = st.columns(len(mc_data))
            for i, (name, d) in enumerate(mc_data):
                _market_card(mc_cols[i], name, d)

        # 警示文字
        sp_chg   = global_data.get('S&P 500',  {}).get('chg_pct', 0) or 0
        nq_chg   = global_data.get('Nasdaq',   {}).get('chg_pct', 0) or 0
        sox_chg  = global_data.get('費半 SOX', {}).get('chg_pct', 0) or 0
        tsm_chg  = global_data.get('TSM ADR',  {}).get('chg_pct', 0) or 0
        oil_chg  = global_data.get('WTI 原油', {}).get('chg_pct', 0) or 0
        gold_chg = global_data.get('黃金',     {}).get('chg_pct', 0) or 0
        dxy_chg  = global_data.get('美元指數', {}).get('chg_pct', 0) or 0

        alerts = []
        if sp_chg <= -2:
            alerts.append(f'🔴 S&P 500 大跌 {sp_chg:.1f}%，台股次日開盤偏弱，留意系統性風險')
        if nq_chg <= -2:
            alerts.append(f'🔴 Nasdaq 大跌 {nq_chg:.1f}%，科技股承壓，台股電子族群注意')
        if sox_chg <= -3:
            alerts.append(f'🔴 費半指數大跌 {sox_chg:.1f}%，台灣半導體族群開盤壓力大')
        elif sox_chg <= -1.5:
            alerts.append(f'🟡 費半指數跌 {sox_chg:.1f}%，半導體族群承壓')
        if tsm_chg <= -3:
            alerts.append(f'🔴 台積電 ADR 跌 {tsm_chg:.1f}%，台積電次日開盤跟跌機率高')
        if vix_val >= 30:
            alerts.append(f'🔴 VIX={vix_val:.1f}，市場恐慌指數偏高，波動劇烈，建議降低倉位')
        elif vix_val >= 20:
            alerts.append(f'🟡 VIX={vix_val:.1f}，市場開始出現警戒情緒，操作宜保守')
        if oil_chg >= 4:
            alerts.append(f'🟡 原油大漲 {oil_chg:+.1f}%，通膨預期升溫，留意升息壓力對科技股的影響')
        elif oil_chg <= -4:
            alerts.append(f'🟡 原油大跌 {oil_chg:.1f}%，需求疑慮升溫，留意景氣方向')
        if gold_chg >= 2:
            alerts.append(f'🟡 黃金大漲 {gold_chg:+.1f}%，避險情緒升溫，留意市場不確定性')
        if dxy_chg >= 0.8:
            alerts.append(f'🟡 美元指數走強 {dxy_chg:+.2f}%，強美元對外資流入新興市場不利')
        _tnx_val = global_data.get('美債10年', {}).get('close', 0) or 0
        _tnx_chg = global_data.get('美債10年', {}).get('chg_pct', 0) or 0
        if _tnx_val >= 4.5:
            alerts.append(f'🔴 美債10年殖利率 {_tnx_val:.2f}%，處於高位，資金成本壓力大，不利科技股估值')
        elif _tnx_val >= 4.0 and _tnx_chg > 2:
            alerts.append(f'🟡 美債10年殖利率 {_tnx_val:.2f}%（持續走升），升息疑慮升溫，留意資金輪動')

        if sp_chg >= 1 and nq_chg >= 1:
            alerts.append(f'🟢 美股普漲（S&P {sp_chg:+.1f}%，Nasdaq {nq_chg:+.1f}%），台股次日開盤偏正面')
        if sox_chg >= 2:
            alerts.append(f'🟢 費半指數大漲 {sox_chg:+.1f}%，台灣半導體族群開盤偏多')

        if alerts:
            for a in alerts:
                st.markdown(a)
        else:
            st.caption('外部市場無明顯異常')

        st.caption('資料來源：Yahoo Finance｜每15分鐘更新一次｜總經指標僅供參考，不納入開盤前評分')
    else:
        st.info('外部市場資料暫時無法取得（Yahoo Finance 連線中）')

    st.markdown('---')

    # ── 開盤前預判（每日常態化）────────────────
    st.markdown('#### 🔭 開盤前預判')

    _mm   = get_market_margin(days=15)
    _fut  = get_futures_institutional(days=15)
    _tpx  = get_prices('TAIEX', days=30)
    _t86  = get_t86_market_aggregate(days=5)

    if _mm and _fut and _tpx and len(_mm) >= 2 and len(_fut) >= 2 and len(_tpx) >= 2:
        _bear_score = 0   # 空方累積分
        _bull_score = 0   # 多方累積分
        _bear_msgs  = []  # 空方訊號清單 (icon, msg)
        _bull_msgs  = []  # 多方訊號清單 (icon, msg)

        # ── 計算大盤技術指標（BIAS / 位置）────
        _ind_tpx   = calc_all(_tpx)
        _bias5_tpx = _ind_tpx.get('bias5')
        _bias20_tpx= _ind_tpx.get('bias20')
        _pos20_tpx = _ind_tpx.get('pos_20')
        _pos250_tpx= _ind_tpx.get('pos_250')
        _ma_trend  = _ind_tpx.get('ma_trend')

        # ══ Signal 1：TAIEX 昨日漲跌（每日必有訊號）══
        _tpx_now  = _tpx[-1]['close']
        _tpx_date = _tpx[-1]['date']   # 資料日期（取代「昨日」字眼）
        _tpx_prev = _tpx[-2]['close'] if len(_tpx) >= 2 else _tpx_now
        _tpx_chg  = (_tpx_now - _tpx_prev) / _tpx_prev * 100 if _tpx_prev else 0

        if _tpx_chg <= -2.0:
            _bear_score += 3
            _bear_msgs.append(('🔴', f'大盤大跌 **{_tpx_chg:.2f}%**（{_tpx_date}，收 {_tpx_now:,.2f}），空方強勢，動能偏空'))
        elif _tpx_chg <= -1.0:
            _bear_score += 2
            _bear_msgs.append(('🔴', f'大盤下跌 {_tpx_chg:.2f}%（{_tpx_date}，收 {_tpx_now:,.2f}），空方有壓'))
        elif _tpx_chg <= -0.3:
            _bear_score += 1
            _bear_msgs.append(('🟡', f'大盤小跌 {_tpx_chg:.2f}%（{_tpx_date}），短線偏弱'))
        elif _tpx_chg >= 2.0:
            _bull_score += 3
            _bull_msgs.append(('🟢', f'大盤大漲 **+{_tpx_chg:.2f}%**（{_tpx_date}，收 {_tpx_now:,.2f}），多方強勢'))
        elif _tpx_chg >= 1.0:
            _bull_score += 2
            _bull_msgs.append(('🟢', f'大盤上漲 +{_tpx_chg:.2f}%（{_tpx_date}，收 {_tpx_now:,.2f}），多方有力'))
        elif _tpx_chg >= 0.3:
            _bull_score += 1
            _bull_msgs.append(('🟢', f'大盤小漲 +{_tpx_chg:.2f}%（{_tpx_date}），短線偏強'))
        else:
            _bull_msgs.append(('⚪', f'大盤收平（{_tpx_date}，{_tpx_chg:+.2f}%，收 {_tpx_now:,.2f}），方向待確認'))

        # ══ Signal 2：融資5日趨勢（相對化）════
        _mb_now  = _mm[-1]['margin_balance']
        _mb_5ago = _mm[-min(5, len(_mm))]['margin_balance']
        _mb_chg  = _mb_now - _mb_5ago
        _mb_chg_pct = _mb_chg / _mb_5ago * 100 if _mb_5ago > 0 else 0

        if _mb_chg_pct >= 2.0:
            _bear_score += 2
            _bear_msgs.append(('🔴', f'融資5日大增 **{_mb_chg_pct:+.1f}%**（+{_mb_chg:,.0f}億）：散戶加槓桿，若行情反轉易出現斷頭賣壓'))
        elif _mb_chg_pct >= 0.5:
            _bear_score += 1
            _bear_msgs.append(('🟡', f'融資5日增加 {_mb_chg_pct:+.1f}%（+{_mb_chg:,.0f}億），槓桿微升'))
        elif _mb_chg_pct <= -2.0:
            _bull_score += 2
            _bull_msgs.append(('🟢', f'融資5日大減 {_mb_chg_pct:+.1f}%（{_mb_chg:,.0f}億）：去槓桿進行中，底部訊號'))
        elif _mb_chg_pct <= -0.5:
            _bull_score += 1
            _bull_msgs.append(('🟢', f'融資5日減少 {_mb_chg_pct:+.1f}%（{_mb_chg:,.0f}億），槓桿緩降偏多'))
        else:
            _bull_msgs.append(('⚪', f'融資餘額 {_mb_now:,.0f}億，5日變化 {_mb_chg_pct:+.1f}%，水位平穩'))

        # ══ Signal 3：外資台指期 日變化量（每日方向）══
        # 用日變化而非絕對值，因外資慣性持有大量淨空單作避險
        _f_net_now  = _fut[-1]['foreign_net']
        _f_net_prev = _fut[-2]['foreign_net'] if len(_fut) >= 2 else _f_net_now
        _f_net_5    = _fut[-min(5, len(_fut))]['foreign_net']
        _f_day_chg  = _f_net_now - _f_net_prev   # 昨日單日變化
        _f_trend    = _f_net_now - _f_net_5       # 5日趨勢

        if _f_day_chg >= 3000:
            _bull_score += 2
            _bull_msgs.append(('🟢', f'外資台指期回補 **+{_f_day_chg:,} 口**（{_tpx_date}，淨 {_f_net_now:+,} 口），期貨轉多'))
        elif _f_day_chg >= 1000:
            _bull_score += 1
            _bull_msgs.append(('🟢', f'外資台指期小幅回補 +{_f_day_chg:,} 口（{_tpx_date}，淨 {_f_net_now:+,} 口），偏多'))
        elif _f_day_chg <= -3000:
            _bear_score += 2
            _bear_msgs.append(('🔴', f'外資台指期擴空 **{_f_day_chg:,} 口**（{_tpx_date}，淨 {_f_net_now:+,} 口），期貨轉空'))
        elif _f_day_chg <= -1000:
            _bear_score += 1
            _bear_msgs.append(('🟡', f'外資台指期小幅擴空 {_f_day_chg:,} 口（{_tpx_date}，淨 {_f_net_now:+,} 口），偏空'))
        else:
            _bull_msgs.append(('⚪', f'外資台指期變化 {_f_day_chg:+,} 口（{_tpx_date}），部位平穩（淨 {_f_net_now:+,} 口）'))

        # 5日趨勢（方向動能）
        if _f_trend <= -2000:
            _bear_score += 1
            _bear_msgs.append(('🟡', f'外資期貨5日持續擴空 {_f_trend:+,} 口，空方方向動能明顯'))
        elif _f_trend >= 2000:
            _bull_score += 1
            _bull_msgs.append(('🟢', f'外資期貨5日持續回補 +{_f_trend:,} 口，多方方向動能明顯'))

        # ══ Signal 4：T86 外資現貨總買賣超（每日直接訊號）══
        if _t86 and len(_t86) >= 1:
            _t86_latest = _t86[-1]
            _t86_foreign = _t86_latest.get('foreign_net_total', 0) or 0
            _t86_trust   = _t86_latest.get('trust_net_total',   0) or 0
            _t86_date    = _t86_latest.get('date', '')

            # 外資現貨（單位：張）
            if _t86_foreign >= 150000:
                _bull_score += 3
                _bull_msgs.append(('🟢', f'外資現貨大買超 **+{_t86_foreign:,} 張**（{_t86_date}），現貨大量流入'))
            elif _t86_foreign >= 50000:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'外資現貨買超 +{_t86_foreign:,} 張（{_t86_date}），籌碼偏多'))
            elif _t86_foreign >= 10000:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'外資現貨小幅買超 +{_t86_foreign:,} 張（{_t86_date}），偏多'))
            elif _t86_foreign <= -150000:
                _bear_score += 3
                _bear_msgs.append(('🔴', f'外資現貨大賣超 **{_t86_foreign:,} 張**（{_t86_date}），現貨大量流出'))
            elif _t86_foreign <= -50000:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'外資現貨賣超 {_t86_foreign:,} 張（{_t86_date}），籌碼偏空'))
            elif _t86_foreign <= -10000:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'外資現貨小幅賣超 {_t86_foreign:,} 張（{_t86_date}），偏空'))
            else:
                _bull_msgs.append(('⚪', f'外資現貨買賣超 {_t86_foreign:+,} 張（{_t86_date}），中性'))

            # 投信方向（輔助訊號）
            if _t86_trust >= 50000:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'投信買超 +{_t86_trust:,} 張（{_t86_date}），法人偏多'))
            elif _t86_trust <= -50000:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'投信賣超 {_t86_trust:,} 張（{_t86_date}），法人調節'))

        # ══ Signal 5：大盤 BIAS5（短線偏差）══
        if _bias5_tpx is not None:
            if _bias5_tpx >= 5:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'大盤 BIAS5={_bias5_tpx:+.1f}%：短線嚴重過熱，高檔壓回機率高'))
            elif _bias5_tpx >= 2:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'大盤 BIAS5={_bias5_tpx:+.1f}%：短線偏熱，注意短線壓力'))
            elif _bias5_tpx <= -5:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'大盤 BIAS5={_bias5_tpx:+.1f}%：短線嚴重超賣，技術反彈機率高'))
            elif _bias5_tpx <= -2:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'大盤 BIAS5={_bias5_tpx:+.1f}%：短線偏超賣，留意反彈'))
            else:
                _bull_msgs.append(('⚪', f'大盤 BIAS5={_bias5_tpx:+.1f}%，短線均線附近'))

        # BIAS20（中線偏差）
        if _bias20_tpx is not None:
            if _bias20_tpx >= 8:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'大盤 BIAS20={_bias20_tpx:+.1f}%：中線過熱，均值回歸壓力'))
            elif _bias20_tpx <= -8:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'大盤 BIAS20={_bias20_tpx:+.1f}%：中線超賣，反彈動能累積'))

        # ══ Signal 6：大盤近1年位置 ══
        if _pos250_tpx is not None:
            if _pos250_tpx >= 90:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'大盤近1年位置 {_pos250_tpx:.0f}%：接近年度高點，追高風險高'))
            elif _pos250_tpx >= 75:
                _bull_msgs.append(('⚪', f'大盤近1年位置 {_pos250_tpx:.0f}%，中高檔'))
            elif _pos250_tpx <= 10:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'大盤近1年位置 {_pos250_tpx:.0f}%：接近年度低點，長線支撐強'))
            elif _pos250_tpx <= 25:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'大盤近1年位置 {_pos250_tpx:.0f}%：中低檔，長線具吸引力'))
            else:
                _bull_msgs.append(('⚪', f'大盤近1年位置 {_pos250_tpx:.0f}%，中間區間'))

        # ══ Signal 7：均線排列（MA趨勢）════
        if _ma_trend == 'bullish':
            _bull_score += 1
            _bull_msgs.append(('🟢', f'大盤均線多頭排列（MA5>MA20>MA60），中線趨勢向上'))
        elif _ma_trend == 'bearish':
            _bear_score += 1
            _bear_msgs.append(('🟡', f'大盤均線空頭排列（MA5<MA20<MA60），中線趨勢向下'))

        # ══ Signal 8：成交量趨勢 ═════════
        _vols = [p['value'] for p in _tpx[-5:] if p.get('value', 0) > 0]
        if len(_vols) >= 3:
            _vol_avg3    = sum(_vols[-3:]) / 3
            _vol_avg_pre = sum(_vols[:max(1, len(_vols)-3)]) / max(1, len(_vols)-3)
            _vol_trend   = (_vol_avg3 - _vol_avg_pre) / _vol_avg_pre * 100 if _vol_avg_pre else 0
            if _vol_trend <= -15:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'近3日成交量萎縮 {_vol_trend:.0f}%，上漲無力'))
            elif _vol_trend >= 20:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'近3日成交量放大 {_vol_trend:.0f}%，市場積極度提升'))

        # ══ Signal 9：外部市場（美股 / 費半 / TSM ADR / VIX）══
        if global_data:
            _sp_chg  = global_data.get('S&P 500',  {}).get('chg_pct', 0) or 0
            _nq_chg  = global_data.get('Nasdaq',   {}).get('chg_pct', 0) or 0
            _sox_chg = global_data.get('費半 SOX', {}).get('chg_pct', 0) or 0
            _tsm_chg = global_data.get('TSM ADR',  {}).get('chg_pct', 0) or 0
            _vix_now = global_data.get('VIX',      {}).get('close',   0) or 0

            # 美股
            if _sp_chg <= -2.5 or _nq_chg <= -2.5:
                _bear_score += 3
                _bear_msgs.append(('🔴', f'美股重挫（S&P {_sp_chg:+.1f}% / Nasdaq {_nq_chg:+.1f}%）：台股跳空開低機率極高'))
            elif _sp_chg <= -1.0:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'美股收跌（S&P {_sp_chg:+.1f}%），台股開盤偏弱'))
            elif _sp_chg >= 1.5:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'美股上漲（S&P {_sp_chg:+.1f}% / Nasdaq {_nq_chg:+.1f}%）：台股跟漲動能充足'))
            elif _sp_chg >= 0.5:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'美股小漲（S&P {_sp_chg:+.1f}%），台股開盤偏正面'))
            else:
                _bull_msgs.append(('⚪', f'美股收平（S&P {_sp_chg:+.1f}%）'))

            # 費半指數（台灣半導體權重高，單獨計分）
            if _sox_chg <= -3.0:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'費半指數大跌 {_sox_chg:.1f}%，台灣半導體族群開盤壓力大'))
            elif _sox_chg <= -1.5:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'費半指數跌 {_sox_chg:.1f}%，半導體族群承壓'))
            elif _sox_chg >= 2.5:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'費半指數大漲 {_sox_chg:+.1f}%，台灣半導體族群開盤偏多'))
            elif _sox_chg >= 1.0:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'費半指數漲 {_sox_chg:+.1f}%，半導體族群有利'))

            # 台積電 ADR
            if _tsm_chg <= -2.5:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'台積電 ADR 大跌 {_tsm_chg:.1f}%，台積電開盤跟跌壓力大'))
            elif _tsm_chg <= -1.0:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'台積電 ADR 跌 {_tsm_chg:.1f}%，台積電開盤有壓'))
            elif _tsm_chg >= 2.0:
                _bull_score += 2
                _bull_msgs.append(('🟢', f'台積電 ADR 大漲 {_tsm_chg:+.1f}%，台積電領漲機率高'))
            elif _tsm_chg >= 1.0:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'台積電 ADR 漲 {_tsm_chg:+.1f}%，台積電開盤有利'))

            # VIX 恐慌指數
            if _vix_now >= 28:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'VIX={_vix_now:.1f}，市場極度恐慌，波動風險大'))
            elif _vix_now >= 20:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'VIX={_vix_now:.1f}，市場情緒偏謹慎'))
            elif 0 < _vix_now <= 16:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'VIX={_vix_now:.1f}，市場情緒穩定，風險偏好良好'))

        # ══ Signal 10：斷頭 / 多殺多風險評估（大跌時觸發）══
        if len(_mm) >= 3:
            _ms_now      = _mm[-1].get('margin_sell', 0) or 0
            _mb_s10      = _mm[-1].get('margin_balance', 0) or 0
            _mb_d1_s10   = _mm[-2].get('margin_balance', 0) or 0
            _mb_d2_s10   = _mm[-3].get('margin_balance', 0) or 0
            _ss_buy_s10  = _mm[-1].get('short_buy', 0) or 0
            _ss_bal_s10  = _mm[-1].get('short_balance', 0) or 0

            # 融資賣出比例：昨日融資賣出 / 融資餘額
            _ms_ratio = _ms_now / _mb_s10 * 100 if _mb_s10 > 0 else 0
            # 融資餘額連續萎縮幅度
            _mb_d1_shrink = (_mb_s10 - _mb_d1_s10) / _mb_d1_s10 * 100 if _mb_d1_s10 > 0 else 0
            _mb_d2_shrink = (_mb_d1_s10 - _mb_d2_s10) / _mb_d2_s10 * 100 if _mb_d2_s10 > 0 else 0
            # 融券回補比例
            _ss_ratio = _ss_buy_s10 / _ss_bal_s10 * 100 if _ss_bal_s10 > 0 else 0

            # 條件 A/B：多殺多 / 斷頭風險（依嚴重程度取最高）
            if _tpx_chg <= -3.0 and _ms_ratio >= 5.0:
                _bear_score += 3
                _bear_msgs.append(('🔴', f'⚡ **多殺多啟動**：{_tpx_date} 跌幅 {_tpx_chg:.2f}%，'
                                   f'融資賣出比例 **{_ms_ratio:.1f}%**（正常 <2.5%），'
                                   f'強制斷頭引發恐慌拋售，今日開盤續跌風險高'))
            elif _tpx_chg <= -3.0 and _ms_ratio >= 3.5:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'⚠️ **多殺多跡象**：{_tpx_date} 跌幅 {_tpx_chg:.2f}%，'
                                   f'融資賣出比例 **{_ms_ratio:.1f}%**（異常偏高），'
                                   f'斷頭賣壓仍在釋放，注意今日開盤量能'))
            elif _tpx_chg <= -2.0 and _ms_ratio >= 3.5:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'🔻 **斷頭風險**：{_tpx_date} 跌幅 {_tpx_chg:.2f}%，'
                                   f'融資賣出比例 {_ms_ratio:.1f}%（>3.5% 警戒），'
                                   f'槓桿戶面臨維持率壓力，今日若再跌易觸發連鎖斷頭'))
            elif _tpx_chg <= -2.0 and _ms_ratio >= 2.5:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'融資賣出比例 {_ms_ratio:.1f}%（{_tpx_date} 跌 {_tpx_chg:.2f}%），'
                                   f'略偏高，注意槓桿戶是否開始被動去槓桿'))

            # 條件 C：斷頭加速（連續 2 日融資餘額萎縮 ≥ 1.5%/日，獨立評估）
            if _mb_d1_shrink <= -1.5 and _mb_d2_shrink <= -1.5:
                _bear_score += 2
                _bear_msgs.append(('🔴', f'📉 **斷頭加速**：融資餘額連續 2 日快速萎縮'
                                   f'（{_mb_d2_shrink:.1f}% → {_mb_d1_shrink:.1f}%），'
                                   f'被動斷頭持續進行，賣壓尚未出清'))
            elif _mb_d1_shrink <= -1.5:
                _bear_score += 1
                _bear_msgs.append(('🟡', f'融資餘額（{_tpx_date}）萎縮 {_mb_d1_shrink:.1f}%，'
                                   f'確認部分強制斷頭已發生，觀察今日是否延續'))

            # 條件 D：融券大量回補（空頭獲利了結 = 短線反彈支撐，獨立評估）
            if _tpx_chg <= -2.0 and _ss_ratio >= 3.0:
                _bull_score += 1
                _bull_msgs.append(('🟢', f'💡 **融券回補**：{_tpx_date} 融券回補比例 {_ss_ratio:.1f}%（>3% 偏高），'
                                   f'空頭獲利了結，可能提供短線技術性反彈支撐'))

        # ── 整理訊號清單 ──────────────────────
        _bear_real    = [(i, m) for i, m in _bear_msgs if i != '⚪']
        _bull_real    = [(i, m) for i, m in _bull_msgs if i != '⚪']
        _bull_neutral = [(i, m) for i, m in _bull_msgs if i == '⚪']

        # ── 顯示：空方訊號 ─────────────────────
        if _bear_real:
            st.markdown('**📉 空方訊號：**')
            for icon, msg in _bear_real:
                _ic = '#ef4444' if icon == '🔴' else '#f59e0b'
                st.markdown(
                    f'<div style="padding:5px 12px;border-left:3px solid {_ic};margin-bottom:4px;font-size:13px">'
                    f'{icon} {msg}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="padding:5px 12px;border-left:3px solid #475569;margin-bottom:4px;'
                'font-size:13px;color:#94a3b8">✅ 目前無空方訊號</div>', unsafe_allow_html=True)

        # ── 顯示：多方訊號 ─────────────────────
        if _bull_real or _bull_neutral:
            st.markdown('**📈 多方訊號：**')
            for icon, msg in _bull_real:
                st.markdown(
                    f'<div style="padding:5px 12px;border-left:3px solid #22c55e;margin-bottom:4px;font-size:13px">'
                    f'{icon} {msg}</div>', unsafe_allow_html=True)
            for icon, msg in _bull_neutral:
                st.markdown(
                    f'<div style="padding:5px 12px;border-left:3px solid #475569;margin-bottom:4px;'
                    f'font-size:13px;color:#94a3b8">{icon} {msg}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="padding:5px 12px;border-left:3px solid #475569;margin-bottom:4px;'
                'font-size:13px;color:#94a3b8">⚪ 目前無明顯多方訊號</div>', unsafe_allow_html=True)

        st.markdown('')

        # ── 綜合判斷（門檻降低，讓正常行情也能判斷方向）────
        _net = _bear_score - _bull_score  # 正 = 偏空，負 = 偏多

        if _net >= 6:
            _vcolor = '#ef4444'; _vbg = '#2d0a0a'
            _verdict = (f'🚨 **強烈偏空（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'多項空方訊號同時觸發，開盤下壓機率高。\n\n'
                       f'**操作建議：** 開盤觀望，不急進場；持股者酌情減碼或設停損。')
        elif _net >= 3:
            _vcolor = '#f97316'; _vbg = '#2d1500'
            _verdict = (f'⚠️ **偏空（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'空方訊號偏多，開盤偏弱可能性較高。\n\n'
                       f'**操作建議：** 降低積極度，觀察開盤量價方向，逢反彈可減碼。')
        elif _net >= 1:
            _vcolor = '#f59e0b'; _vbg = '#1a1505'
            _verdict = (f'🟡 **中性偏空（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'空方稍佔上風，方向待確認。\n\n'
                       f'**操作建議：** 保守持倉，等開盤方向明朗後再決策。')
        elif _net <= -6:
            _vcolor = '#22c55e'; _vbg = '#0a2010'
            _verdict = (f'🚀 **強烈偏多（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'多方訊號強勁，反彈或上攻條件完備。\n\n'
                       f'**操作建議：** 開盤若量能回升，可考慮積極分批布局。')
        elif _net <= -3:
            _vcolor = '#4ade80'; _vbg = '#0a1a0a'
            _verdict = (f'🟢 **偏多（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'多方訊號佔優，開盤偏正面。\n\n'
                       f'**操作建議：** 可偏多操作，注意個股選股品質。')
        elif _net <= -1:
            _vcolor = '#86efac'; _vbg = '#0a150a'
            _verdict = (f'🟩 **中性偏多（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'多方略佔優勢，觀察量能是否跟上。\n\n'
                       f'**操作建議：** 現有持股可繼續持有，小幅加碼需量能配合。')
        else:
            _vcolor = '#94a3b8'; _vbg = '#1a1f2e'
            _verdict = (f'⚪ **多空均衡（空方+{_bear_score} / 多方+{_bull_score}）**\n\n'
                       f'多空訊號相當，市場方向尚不明確。\n\n'
                       f'**操作建議：** 中性觀望，等開盤後視量價再決定方向。')

        st.markdown(
            f'<div style="background:{_vbg};border:2px solid {_vcolor};'
            f'border-radius:10px;padding:16px 18px;margin-top:10px">'
            f'<span style="color:{_vcolor};font-size:14px">{_verdict}</span>'
            f'</div>',
            unsafe_allow_html=True)

        _latest_date = _mm[-1]['date']
        st.caption(f'評估基準日：{_latest_date}　空方/多方分數為各訊號加權總計（每日常態化）　｜　僅供參考，不構成投資建議')
    else:
        st.info('資料不足，無法進行開盤前預判（需至少5日融資融券及期貨資料）')

    st.markdown('---')

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

    # ── 大盤本益比指標 ──────────────────────
    pe_data = get_market_pe(days=250)
    if pe_data:
        latest_pe = pe_data[-1]
        pe_val  = latest_pe.get('pe_ratio')
        pb_val  = latest_pe.get('pb_ratio')
        dy_val  = latest_pe.get('div_yield')
        pe_date = latest_pe.get('date', '')

        # 判斷函式
        def pe_judgment(pe):
            if pe is None:
                return '—', '#94a3b8'
            if pe < 14:
                return f'歷史低估區 ✅', '#22c55e'
            if pe < 18:
                return '合理估值', '#94a3b8'
            if pe < 22:
                return '偏高，留意風險 ⚠️', '#f59e0b'
            return '高估，泡沫風險 🔴', '#ef4444'

        def pb_judgment(pb):
            if pb is None:
                return '—', '#94a3b8'
            if pb < 1.5:
                return '淨值偏低，具支撐', '#22c55e'
            if pb < 2.2:
                return '合理', '#94a3b8'
            if pb < 3.0:
                return '偏高', '#f59e0b'
            return '高估', '#ef4444'

        pe_jdg, pe_color = pe_judgment(pe_val)
        pb_jdg, pb_color = pb_judgment(pb_val)

        pc1, pc2, pc3 = st.columns(3)
        pc1.markdown(
            f'**大盤本益比（PE）**<br>'
            f'<span style="font-size:26px;font-weight:700;color:{pe_color}">'
            f'{"%.2f" % pe_val if pe_val else "—"}</span><br>'
            f'<span style="font-size:12px;color:#64748b">{pe_jdg}　資料日期：{pe_date}</span>',
            unsafe_allow_html=True)
        pc2.markdown(
            f'**大盤股價淨值比（PB）**<br>'
            f'<span style="font-size:26px;font-weight:700;color:{pb_color}">'
            f'{"%.2f" % pb_val if pb_val else "—"}</span><br>'
            f'<span style="font-size:12px;color:#64748b">{pb_jdg}</span>',
            unsafe_allow_html=True)
        pc3.markdown(
            f'**大盤殖利率**<br>'
            f'<span style="font-size:26px;font-weight:700;color:#38bdf8">'
            f'{"%.2f" % dy_val + "%" if dy_val else "—"}</span><br>'
            f'<span style="font-size:12px;color:#64748b">整體市場配息水準</span>',
            unsafe_allow_html=True)

        st.markdown('')

        # 本益比歷史線圖
        if len(pe_data) >= 5:
            pe_dates  = [r['date']     for r in pe_data]
            pe_series = [r['pe_ratio'] for r in pe_data]
            pb_series = [r['pb_ratio'] for r in pe_data]

            fig_pe = go.Figure()
            fig_pe.add_trace(go.Scatter(
                x=pe_dates, y=pe_series, name='本益比(PE)',
                line=dict(color='#f59e0b', width=2),
                yaxis='y1'
            ))
            if any(v is not None for v in pb_series):
                fig_pe.add_trace(go.Scatter(
                    x=pe_dates, y=pb_series, name='股價淨值比(PB)',
                    line=dict(color='#a78bfa', width=1.5, dash='dot'),
                    yaxis='y2'
                ))
            # 本益比參考線
            for ref_val, ref_label, ref_color in [
                (14, 'PE 14（低估）', 'rgba(34,197,94,0.5)'),
                (18, 'PE 18（合理上緣）', 'rgba(148,163,184,0.4)'),
                (22, 'PE 22（高估）', 'rgba(239,68,68,0.4)'),
            ]:
                fig_pe.add_hline(
                    y=ref_val, line_color=ref_color, line_width=1, line_dash='dash',
                    annotation_text=ref_label,
                    annotation_position='left',
                    annotation_font_size=10,
                    annotation_font_color=ref_color,
                )
            fig_pe.update_layout(
                height=260,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation='h', y=1.12),
                yaxis=dict(title='本益比', gridcolor='#1e293b', side='left'),
                yaxis2=dict(title='PB', overlaying='y', side='right',
                            gridcolor='rgba(0,0,0,0)', showgrid=False),
                xaxis=dict(gridcolor='#1e293b'),
                font=dict(color='#94a3b8', size=11),
            )
            st.markdown('**大盤本益比 / 股價淨值比 歷史走勢**')
            show_chart(fig_pe)

        # 判斷文字
        pe_msgs = []
        if pe_val is not None:
            if pe_val < 14:
                pe_msgs.append(f'🟢 **本益比 {pe_val:.1f}x**，處於歷史低估區（< 14x），市場評價偏低，具長期投資吸引力。')
            elif pe_val < 18:
                pe_msgs.append(f'⚪ **本益比 {pe_val:.1f}x**，估值合理（14–18x），整體市場無明顯高低估。')
            elif pe_val < 22:
                pe_msgs.append(f'🟡 **本益比 {pe_val:.1f}x**，估值偏高（18–22x），需留意獲利能否支撐股價。')
            else:
                pe_msgs.append(f'🔴 **本益比 {pe_val:.1f}x**，估值偏貴（> 22x），歷史高位，建議保守應對。')
        if pb_val is not None and pb_val < 1.5:
            pe_msgs.append(f'📌 股價淨值比 {pb_val:.2f}x，接近帳面價值，下方支撐相對強。')
        if dy_val is not None and dy_val >= 4.0:
            pe_msgs.append(f'💰 大盤殖利率 {dy_val:.2f}%，高於一般定存水準，股市吸引力強。')
        for msg in pe_msgs:
            st.markdown(msg)
        st.caption(f'資料來源：TWSE BWIBBU_ALL｜資料日期：{pe_data[-1].get("date","")}｜本益比為市場中位數，14以下歷史偏低、22以上偏高')
        st.markdown('---')

    st.caption(f'資料來源：Yahoo Finance ^TWII（指數）/ TWSE FMTQIK（成交金額）　｜　指數資料日期：{date}　｜　成交金額單位：億元')

    # ── 乖離率 + 區間位置 ────────────────────
    _bias5  = ind.get('bias5')
    _bias20 = ind.get('bias20')
    _pos20  = ind.get('pos_20')
    _pos250 = ind.get('pos_250')

    def _bc(b):
        if b is None: return '#94a3b8'
        if b > 5:  return '#ef4444'
        if b > 2:  return '#f59e0b'
        if b < -5: return '#22c55e'
        if b < -2: return '#38bdf8'
        return '#94a3b8'

    def _bl(b):
        if b is None: return '—'
        if b > 5:  return '短線過熱 ⚠️'
        if b > 2:  return '偏貴，不追高'
        if b < -5: return '短線超賣 ✅'
        if b < -2: return '偏便宜'
        return '正常貼線'

    def _pc(p):
        if p is None: return '#94a3b8'
        return '#ef4444' if p >= 80 else '#22c55e' if p <= 20 else '#f59e0b'

    def _pl(p):
        if p is None: return '—'
        return '高檔區 ⚠️' if p >= 80 else '低檔區 ✅' if p <= 20 else '中間段'

    mb1, mb2, mb3, mb4 = st.columns(4)
    mb1.markdown(
        f'**BIAS5（vs MA5）**<br>'
        f'<span style="font-size:24px;font-weight:700;color:{_bc(_bias5)}">{f"{_bias5:+.2f}%" if _bias5 is not None else "—"}</span><br>'
        f'<span style="font-size:11px;color:#64748b">{_bl(_bias5)}</span>', unsafe_allow_html=True)
    mb2.markdown(
        f'**BIAS20（vs MA20）**<br>'
        f'<span style="font-size:24px;font-weight:700;color:{_bc(_bias20)}">{f"{_bias20:+.2f}%" if _bias20 is not None else "—"}</span><br>'
        f'<span style="font-size:11px;color:#64748b">{_bl(_bias20)}</span>', unsafe_allow_html=True)
    mb3.markdown(
        f'**近1個月位置（20日）**<br>'
        f'<span style="font-size:24px;font-weight:700;color:{_pc(_pos20)}">{f"{_pos20:.1f}%" if _pos20 is not None else "—"}</span><br>'
        f'<span style="font-size:11px;color:#64748b">{_pl(_pos20)}</span>', unsafe_allow_html=True)
    mb4.markdown(
        f'**近1年位置（250日）**<br>'
        f'<span style="font-size:24px;font-weight:700;color:{_pc(_pos250)}">{f"{_pos250:.1f}%" if _pos250 is not None else "—"}</span><br>'
        f'<span style="font-size:11px;color:#64748b">{_pl(_pos250)}</span>', unsafe_allow_html=True)
    st.caption('BIAS > +5% 短線過熱、< -5% 超賣　｜　位置 ≥80% 高檔、≤20% 低檔')

    # ── 各天數區間高低點與目前收盤落差 ──────────
    _hl_rows = []
    for _days, _label in [(5, '5日（週）'), (20, '20日（1個月）'), (60, '60日（3個月）'), (120, '120日（半年）'), (250, '250日（1年）')]:
        if len(prices) >= _days:
            _seg   = prices[-_days:]
            _hi    = max(p['high']  for p in _seg)
            _lo    = min(p['low']   for p in _seg)
            _d_hi  = close - _hi   # 負值 = 距高點還有 X 點
            _d_lo  = close - _lo   # 正值 = 已在低點上方 X 點
            _hl_rows.append((_label, _hi, _d_hi, _lo, _d_lo))

    if _hl_rows:
        _hi_cols = st.columns(len(_hl_rows))
        for _col, (_label, _hi, _d_hi, _lo, _d_lo) in zip(_hi_cols, _hl_rows):
            # 距高點：負值正常（還沒到）→ 灰；趨近0或正值（已在高點附近）→ 紅
            _hi_color = '#ef4444' if _d_hi >= -200 else '#f97316' if _d_hi >= -500 else '#94a3b8'
            # 距低點：正值正常（站在低點上方）→ 綠；趨近0（接近低點）→ 紅
            _lo_color = '#22c55e' if _d_lo >= 500 else '#f59e0b' if _d_lo >= 200 else '#ef4444'
            _col.markdown(
                f'<div style="background:#141720;border:1px solid #252a38;border-radius:8px;'
                f'padding:10px 12px;margin-bottom:4px">'
                f'<div style="font-size:11px;color:#8892a4;margin-bottom:4px">{_label}</div>'
                f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:2px">'
                f'最高 <b style="color:{_hi_color}">{_hi:,.0f}</b>'
                f'　<span style="color:{_hi_color};font-size:11px">{_d_hi:+,.0f}（距高點）</span></div>'
                f'<div style="font-size:12px;color:#cbd5e1">'
                f'最低 <b style="color:{_lo_color}">{_lo:,.0f}</b>'
                f'　<span style="color:{_lo_color};font-size:11px">{_d_lo:+,.0f}（距低點）</span></div>'
                f'</div>',
                unsafe_allow_html=True)
    st.caption('距高點：負值 = 目前收盤低於區間最高點的點數（越負離高點越遠）　｜　距低點：正值 = 目前收盤高於區間最低點的點數（越正離低點越遠）')
    st.markdown('')

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
        # 成交量顏色：漲紅跌綠
        vol_colors = []
        for k in range(len(dates)):
            if k == 0:
                vol_colors.append('#ef4444')
            elif closes[k] >= closes[k - 1]:
                vol_colors.append('#ef4444')
            else:
                vol_colors.append('#22c55e')

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.03
        )

        # 指數線
        fig.add_trace(go.Scatter(
            x=dates, y=closes, name='加權指數',
            line=dict(color='#38bdf8', width=2)
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
        if bb_upper_s and bb_lower_s and len(dates) == len(bb_upper_s):
            fig.add_trace(go.Scatter(
                x=dates, y=bb_upper_s, name='布林上軌',
                mode='lines',
                line=dict(color='rgba(180,180,180,0.4)', width=1),
                showlegend=True
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=dates, y=bb_lower_s, name='布林下軌',
                mode='lines',
                line=dict(color='rgba(180,180,180,0.4)', width=1),
                fill='tonexty', fillcolor='rgba(160,160,160,0.12)',
                showlegend=True
            ), row=1, col=1)

        # 成交量柱狀圖
        if volumes:
            fig.add_trace(go.Bar(
                x=dates, y=volumes,
                name='成交量',
                marker_color=vol_colors,
                opacity=0.75,
                showlegend=True
            ), row=2, col=1)

        fig.update_layout(
            paper_bgcolor='#0d0f12',
            plot_bgcolor='#141720',
            font=dict(color='#e2e8f0', size=11),
            height=520,
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            xaxis2=dict(showgrid=True, gridcolor='#252a38'),
            yaxis=dict(showgrid=True, gridcolor='#252a38'),
            yaxis2=dict(showgrid=True, gridcolor='#252a38', title='成交金額（億元）',
                        title_font=dict(size=10)),
            margin=dict(l=0, r=0, t=40, b=0),
            bargap=0.2
        )
        fig.update_xaxes(showgrid=True, gridcolor='#252a38')
        show_chart(fig)

        # ── 成交量判斷 ──────────────────────────
        # 過濾掉 0 值（yfinance 近日資料有時為 0）
        valid_vols = [(i, v) for i, v in enumerate(volumes) if v and v > 0]
        if valid_vols and len(valid_vols) >= 10:
            # 取最後一個有效量及其對應日期
            last_idx, vol_today = valid_vols[-1]
            vol_date = dates[last_idx] if last_idx < len(dates) else ''

            valid_only = [v for _, v in valid_vols]
            vol_ma5  = sum(valid_only[-5:])  / min(5,  len(valid_only))
            vol_ma20 = sum(valid_only[-20:]) / min(20, len(valid_only))
            vol_ratio20 = vol_today / vol_ma20 if vol_ma20 > 0 else 1.0

            # 近5日 vs 前5日趨勢
            recent5 = sum(valid_only[-5:])  / min(5, len(valid_only))
            prev5   = sum(valid_only[-10:-5]) / min(5, len(valid_only[-10:-5])) if len(valid_only) >= 10 else recent5
            vol_trend = (recent5 - prev5) / prev5 * 100 if prev5 > 0 else 0

            # 對應的收盤漲跌
            is_up = closes[last_idx] >= closes[last_idx - 1] if last_idx > 0 else True

            vol_msgs = []
            if vol_ratio20 >= 2.0:
                color  = '#ef4444' if is_up else '#22c55e'
                action = '放量上攻，多方積極' if is_up else '放量下殺，空方強勢'
                vol_msgs.append(f'<span style="color:{color}">🔥 **爆量**（{vol_date}，約20日均量 {vol_ratio20:.1f} 倍）：{action}，需觀察後續方向確認。</span>')
            elif vol_ratio20 >= 1.3:
                action = '量增上漲，趨勢偏多' if is_up else '量增下跌，短線偏弱'
                vol_msgs.append(f'<span style="color:#f59e0b">📈 **量能偏大**（{vol_date}，20日均量 {vol_ratio20:.1f} 倍）：{action}。</span>')
            elif vol_ratio20 <= 0.6:
                vol_msgs.append(f'<span style="color:#64748b">😴 **縮量**（{vol_date}，僅20日均量 {vol_ratio20:.1f} 倍）：市場觀望，方向不明，不宜追高殺低。</span>')
            else:
                vol_msgs.append(f'<span style="color:#94a3b8">⚪ **量能正常**（{vol_date}，20日均量 {vol_ratio20:.1f} 倍）：市場交投平穩。</span>')

            if vol_trend >= 30:
                vol_msgs.append(f'<span style="color:#22c55e">📊 近5日量能持續放大（+{vol_trend:.0f}%），市場活絡度提升，動能增強。</span>')
            elif vol_trend <= -30:
                vol_msgs.append(f'<span style="color:#64748b">📉 近5日量能持續萎縮（{vol_trend:.0f}%），動能減弱，短線整理機率較高。</span>')

            for msg in vol_msgs:
                st.markdown(msg, unsafe_allow_html=True)
            st.caption(f'資料日期：{vol_date}　成交金額：{vol_today:,.0f} 億元　5日均量：{vol_ma5:,.0f} 億　20日均量：{vol_ma20:,.0f} 億　（來源：TWSE FMTQIK）')

    # ── 大盤 K 線解讀 ─────────────────────────
    if len(prices) >= 2:
        td = prices[-1]
        yd = prices[-2]
        o, h, l, c = td.get('open',0), td.get('high',0), td.get('low',0), td.get('close',0)
        vol_td   = td.get('value', 0)   # 成交金額（億元，FMTQIK 補正後）
        avg_vol20 = sum(p.get('value',0) for p in prices[-21:-1]) / 20 if len(prices) >= 21 else 0

        if o and h and l and c:
            body        = abs(c - o)
            total_range = h - l if h > l else 0.001
            upper_wick  = h - max(o, c)
            lower_wick  = min(o, c) - l
            is_red      = c < o
            upper_pct   = round(upper_wick / total_range * 100, 1)
            lower_pct   = round(lower_wick / total_range * 100, 1)
            body_pct    = round(body / total_range * 100, 1)
            vol_ratio   = round(vol_td / avg_vol20, 2) if avg_vol20 else 0

            st.markdown('#### 🕯️ 大盤今日 K 線解讀')

            # ── K 線圖（近20日）＋ 均線 ＋ 數值並排 ──
            _mk_col, _mm_col = st.columns([1, 1])
            with _mk_col:
                _n = min(20, len(prices))
                _mk_dates  = [p['date']  for p in prices[-_n:]]
                _mk_opens  = [p['open']  for p in prices[-_n:]]
                _mk_highs  = [p['high']  for p in prices[-_n:]]
                _mk_lows   = [p['low']   for p in prices[-_n:]]
                _mk_closes = [p['close'] for p in prices[-_n:]]
                _mk_ma5  = ind.get('ma5_series',  [])
                _mk_ma20 = ind.get('ma20_series', [])
                _mk_ma60 = ind.get('ma60_series', [])
                _fig_mk = go.Figure()
                _fig_mk.add_trace(go.Candlestick(
                    x=_mk_dates,
                    open=_mk_opens, high=_mk_highs,
                    low=_mk_lows,   close=_mk_closes,
                    increasing_line_color='#ef4444', increasing_fillcolor='#ef4444',
                    decreasing_line_color='#22c55e', decreasing_fillcolor='#22c55e',
                    name='K線', showlegend=False,
                ))
                if _mk_ma5 and len(_mk_ma5) >= _n:
                    _fig_mk.add_trace(go.Scatter(
                        x=_mk_dates, y=_mk_ma5[-_n:], name='MA5',
                        line=dict(color='#f59e0b', width=1.2), connectgaps=True))
                if _mk_ma20 and len(_mk_ma20) >= _n:
                    _fig_mk.add_trace(go.Scatter(
                        x=_mk_dates, y=_mk_ma20[-_n:], name='MA20',
                        line=dict(color='#a78bfa', width=1.2), connectgaps=True))
                if _mk_ma60 and len(_mk_ma60) >= _n:
                    _fig_mk.add_trace(go.Scatter(
                        x=_mk_dates, y=_mk_ma60[-_n:], name='MA60',
                        line=dict(color='#22c55e', width=1.2), connectgaps=True))
                _fig_mk.update_layout(
                    height=250, margin=dict(l=0, r=0, t=8, b=0),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02,
                                font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
                    xaxis=dict(showgrid=False, tickformat='%m/%d', tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True, gridcolor='#1e293b', tickfont=dict(size=9)),
                    xaxis_rangeslider_visible=False,
                )
                show_chart(_fig_mk)
            with _mm_col:
                mkc1, mkc2 = st.columns(2)
                mkc1.metric('開盤', f'{o:,.2f}')
                mkc2.metric('最高', f'{h:,.2f}', delta=f'+{h-o:,.2f}' if h > o else None)
                mkc3, mkc4 = st.columns(2)
                mkc3.metric('最低', f'{l:,.2f}', delta=f'{l-o:,.2f}' if l < o else None)
                mkc4.metric('收盤', f'{c:,.2f}', delta=f'{c-yd["close"]:+.2f}')

            st.markdown('')
            k_msgs = []

            if upper_pct >= 40:
                k_msgs.append(('🔴', f'**長上影線**（{upper_pct:.0f}%）：指數攻高後遭強力壓回，市場高檔賣壓明顯，次日偏弱。'))
            elif upper_pct >= 20:
                k_msgs.append(('🟡', f'**中上影線**（{upper_pct:.0f}%）：高點有壓，多方未能完全掌控，需觀察次日能否突破。'))

            if lower_pct >= 40:
                k_msgs.append(('🟢', f'**長下影線**（{lower_pct:.0f}%）：低點有強力買盤承接，底部支撐力道強，次日偏強。'))
            elif lower_pct >= 20:
                k_msgs.append(('🟡', f'**中下影線**（{lower_pct:.0f}%）：低點有支撐，但承接力道有限，觀察量能確認。'))

            if body_pct >= 60:
                if not is_red:
                    k_msgs.append(('🟢', f'**大紅K**（實體 {body_pct:.0f}%）：多方強勢主導全日，買氣充沛。'))
                else:
                    k_msgs.append(('🔴', f'**大黑K**（實體 {body_pct:.0f}%）：空方強勢主導全日，賣壓沉重。'))
            elif body_pct <= 15:
                if upper_pct >= 25 and lower_pct >= 25:
                    k_msgs.append(('🟡', '**十字星**：多空交戰激烈，方向未定，為潛在轉折訊號。'))
                else:
                    k_msgs.append(('🟡', '**小實體**：多空力道相當，盤整格局，方向待確認。'))

            if vol_ratio >= 2.0:
                if not is_red and upper_pct < 30:
                    k_msgs.append(('🟢', f'**爆量收紅**（均量 {vol_ratio}倍）：市場資金積極進場，指數後市動能強。'))
                elif not is_red and upper_pct >= 30:
                    k_msgs.append(('🔴', f'**爆量長上影**（均量 {vol_ratio}倍）：大量攻高後被壓回，法人可能在出貨，需警戒。'))
                elif is_red:
                    k_msgs.append(('🔴', f'**爆量收黑**（均量 {vol_ratio}倍）：大量殺出，空方主導，次日偏弱。'))
            elif vol_ratio >= 1.3:
                k_msgs.append(('🟡', f'**溫和放量**（均量 {vol_ratio}倍）：市場參與度提升，方向參考 K 線型態。'))
            elif 0 < vol_ratio <= 0.6:
                k_msgs.append(('🟡', f'**明顯縮量**（均量 {vol_ratio}倍）：市場觀望，訊號可信度降低，不宜追高殺低。'))

            scores = sum(1 for m in k_msgs if m[0] == '🟢') - sum(1 for m in k_msgs if m[0] == '🔴')
            if scores >= 2:
                verdict = '🟢 **大盤次日偏多**：多項訊號支持，留意開盤量能確認方向。'
            elif scores <= -2:
                verdict = '🔴 **大盤次日偏空**：多項賣壓訊號，建議謹慎，注意季線支撐。'
            else:
                verdict = '🟡 **大盤次日中性**：訊號混雜，建議觀察開盤 30 分鐘量價確認方向。'

            for icon, msg in k_msgs:
                color = '#22c55e' if icon == '🟢' else '#ef4444' if icon == '🔴' else '#f59e0b'
                st.markdown(
                    f'<div style="padding:5px 10px;border-left:3px solid {color};margin-bottom:5px">'
                    f'{icon} {msg}</div>', unsafe_allow_html=True)

            st.markdown(
                f'<div style="background:#1a1f2e;border-radius:8px;padding:12px 16px;margin-top:8px">'
                f'<span style="font-size:14px">{verdict}</span></div>',
                unsafe_allow_html=True)
            st.caption(
                f'資料日期：{td["date"]}　振幅：{total_range:,.2f}點　'
                f'實體：{body_pct:.0f}%　上影：{upper_pct:.0f}%　下影：{lower_pct:.0f}%　'
                f'成交金額：{vol_td:,.0f} 億　均量：{avg_vol20:,.0f} 億')

    st.markdown('---')

    # ── 三大法人現貨每日買賣超 ──────────────────
    st.markdown('#### 🏦 三大法人現貨每日買賣超（張）')
    # 本機用 chips 原始表彙總；雲端從 chips_market_agg 表讀取（由 JSON 匯入）
    if IS_LOCAL:
        _chips_agg = get_chips_market_aggregate(days=20)
    else:
        _chips_agg = get_chips_market_agg_from_table(days=20)

    if not _chips_agg:
        st.info('尚無三大法人現貨資料，請按「🔄 手動更新資料」取得。')
    else:
        _ca_dates   = [r['date']        for r in _chips_agg]
        _ca_foreign = [r['foreign_net'] for r in _chips_agg]
        _ca_trust   = [r['trust_net']   for r in _chips_agg]
        _ca_dealer  = [r['dealer_net']  for r in _chips_agg]
        _ca_total   = [f + t + d for f, t, d in zip(_ca_foreign, _ca_trust, _ca_dealer)]

        # 最新一日指標列
        _ca_latest = _chips_agg[-1]
        _cac1, _cac2, _cac3, _cac4 = st.columns(4)
        def _cc(v): return '#22c55e' if v > 0 else '#ef4444' if v < 0 else '#94a3b8'
        def _cl(v): return f'+{v:,}' if v > 0 else f'{v:,}'
        _cac1.markdown(f'**外資現貨**<br><span style="font-size:20px;font-weight:700;color:{_cc(_ca_latest["foreign_net"])}">{_cl(_ca_latest["foreign_net"])}</span><br><span style="font-size:11px;color:#64748b">張　{_ca_latest["date"]}</span>', unsafe_allow_html=True)
        _cac2.markdown(f'**投信現貨**<br><span style="font-size:20px;font-weight:700;color:{_cc(_ca_latest["trust_net"])}">{_cl(_ca_latest["trust_net"])}</span><br><span style="font-size:11px;color:#64748b">張　{_ca_latest["date"]}</span>', unsafe_allow_html=True)
        _cac3.markdown(f'**自營商**<br><span style="font-size:20px;font-weight:700;color:{_cc(_ca_latest["dealer_net"])}">{_cl(_ca_latest["dealer_net"])}</span><br><span style="font-size:11px;color:#64748b">張　{_ca_latest["date"]}</span>', unsafe_allow_html=True)
        _cac4.markdown(f'**三大合計**<br><span style="font-size:20px;font-weight:700;color:{_cc(_ca_latest["foreign_net"]+_ca_latest["trust_net"]+_ca_latest["dealer_net"])}">{_cl(_ca_latest["foreign_net"]+_ca_latest["trust_net"]+_ca_latest["dealer_net"])}</span><br><span style="font-size:11px;color:#64748b">張　{_ca_latest["date"]}</span>', unsafe_allow_html=True)

        st.markdown('')

        # 柱狀圖：外資 / 投信 / 自營商（分組） + 三大合計折線
        _fig_chips = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.06, row_heights=[0.6, 0.4],
            subplot_titles=('外資 / 投信 / 自營商 日別淨買賣超', '三大合計')
        )

        # 外資（固定橘色，正負靠柱子方向區分）
        _fig_chips.add_trace(go.Bar(
            x=_ca_dates, y=_ca_foreign, name='外資',
            marker_color='#f97316', opacity=0.85
        ), row=1, col=1)
        # 投信（固定藍色）
        _fig_chips.add_trace(go.Bar(
            x=_ca_dates, y=_ca_trust, name='投信',
            marker_color='#38bdf8', opacity=0.85
        ), row=1, col=1)
        # 自營商（固定紫色）
        _fig_chips.add_trace(go.Bar(
            x=_ca_dates, y=_ca_dealer, name='自營商',
            marker_color='#a78bfa', opacity=0.75
        ), row=1, col=1)
        # 三大合計柱狀
        _fig_chips.add_trace(go.Bar(
            x=_ca_dates, y=_ca_total, name='三大合計',
            marker_color=['#22c55e' if v >= 0 else '#ef4444' for v in _ca_total],
            opacity=0.9
        ), row=2, col=1)
        # 7日移動平均線
        _ca_total_ma7 = [
            sum(_ca_total[max(0, i-6):i+1]) / len(_ca_total[max(0, i-6):i+1])
            for i in range(len(_ca_total))
        ]
        _fig_chips.add_trace(go.Scatter(
            x=_ca_dates, y=_ca_total_ma7, name='7日均線',
            line=dict(color='#f59e0b', width=1.5, dash='dot'),
            showlegend=True
        ), row=2, col=1)
        # 零基準線
        _fig_chips.add_hline(y=0, line_color='#475569', line_width=1, row=1, col=1)
        _fig_chips.add_hline(y=0, line_color='#475569', line_width=1, row=2, col=1)

        _fig_chips.update_layout(
            height=450,
            paper_bgcolor='#0d0f12', plot_bgcolor='#141720',
            font=dict(color='#e2e8f0', size=11),
            barmode='group',
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            xaxis=dict(showgrid=False, tickformat='%m/%d'),
            yaxis=dict(showgrid=True, gridcolor='#252a38', tickformat=','),
            xaxis2=dict(showgrid=False, tickformat='%m/%d'),
            yaxis2=dict(showgrid=True, gridcolor='#252a38', tickformat=','),
            margin=dict(l=0, r=0, t=40, b=0)
        )
        show_chart(_fig_chips)
        st.caption(f'資料來源：TWSE 三大法人買賣超（T86）彙總　｜　單位：張　｜　僅含上市股票、股數 ≥ 500 檔日期')

        # ── 三大法人籌碼判斷 ──────────────────
        _f_now   = _ca_foreign[-1]
        _t_now   = _ca_trust[-1]
        _d_now   = _ca_dealer[-1]
        _tot_now = _ca_total[-1]
        _ma7_now = _ca_total_ma7[-1]

        # 外資近3日趨勢（連買/連賣）
        _f_3d = _ca_foreign[-3:] if len(_ca_foreign) >= 3 else _ca_foreign
        _f_3d_buy  = sum(1 for v in _f_3d if v > 0)
        _f_3d_sell = sum(1 for v in _f_3d if v < 0)

        _chip_msgs = []
        _ca_last_date = _ca_dates[-1]  # 資料日期

        # 外資判斷
        if _f_now >= 300000:
            _chip_msgs.append(('🟢', f'外資大幅買超 **+{_f_now:,} 張**（{_ca_last_date}），主力資金大規模流入，籌碼強力偏多'))
        elif _f_now >= 100000:
            _chip_msgs.append(('🟢', f'外資買超 +{_f_now:,} 張（{_ca_last_date}），外資態度積極偏多'))
        elif _f_now >= 30000:
            _chip_msgs.append(('🟢', f'外資小幅買超 +{_f_now:,} 張（{_ca_last_date}），偏多但力道有限'))
        elif _f_now <= -300000:
            _chip_msgs.append(('🔴', f'外資大幅賣超 **{_f_now:,} 張**（{_ca_last_date}），主力資金明顯撤退，籌碼強力偏空'))
        elif _f_now <= -100000:
            _chip_msgs.append(('🔴', f'外資賣超 {_f_now:,} 張（{_ca_last_date}），外資態度偏空，需留意'))
        elif _f_now <= -30000:
            _chip_msgs.append(('🟡', f'外資小幅賣超 {_f_now:,} 張（{_ca_last_date}），態度偏保守'))
        else:
            _chip_msgs.append(('⚪', f'外資買賣超 {_f_now:+,} 張（{_ca_last_date}），方向中性'))

        # 外資連續方向
        if _f_3d_buy == 3:
            _chip_msgs.append(('🟢', f'外資連續 3 日買超，短線趨勢偏多'))
        elif _f_3d_sell == 3:
            _chip_msgs.append(('🔴', f'外資連續 3 日賣超，短線持續調節，需謹慎'))

        # 投信判斷
        if _t_now >= 80000:
            _chip_msgs.append(('🟢', f'投信大量買超 +{_t_now:,} 張（{_ca_last_date}），國內法人積極加碼'))
        elif _t_now >= 30000:
            _chip_msgs.append(('🟢', f'投信買超 +{_t_now:,} 張（{_ca_last_date}），國內法人偏多'))
        elif _t_now <= -80000:
            _chip_msgs.append(('🔴', f'投信大量賣超 {_t_now:,} 張（{_ca_last_date}），國內法人持續調節'))
        elif _t_now <= -30000:
            _chip_msgs.append(('🟡', f'投信賣超 {_t_now:,} 張（{_ca_last_date}），國內法人偏保守'))

        # 三大合計 vs 7日均線
        if _tot_now > 0 and _tot_now > _ma7_now * 1.5:
            _chip_msgs.append(('🟢', f'三大合計買超 +{_tot_now:,} 張，顯著高於 7 日均值（{_ma7_now:+,.0f}），資金積極流入'))
        elif _tot_now > 0 and _ma7_now < 0:
            _chip_msgs.append(('🟢', f'三大合計由空轉多（昨 +{_tot_now:,} 張），7 日均線仍為 {_ma7_now:+,.0f}，籌碼轉向訊號'))
        elif _tot_now < 0 and _tot_now < _ma7_now * 1.5:
            _chip_msgs.append(('🔴', f'三大合計賣超 {_tot_now:,} 張，顯著低於 7 日均值（{_ma7_now:+,.0f}），賣壓加重'))
        elif _tot_now < 0 and _ma7_now > 0:
            _chip_msgs.append(('🟡', f'三大合計由多轉空（昨 {_tot_now:,} 張），7 日均線仍為 +{_ma7_now:,.0f}，留意轉弱'))

        # 顯示
        # 三大合計規模決定最終方向（外資主導，投信為輔）
        if _tot_now >= 200000:
            _cv, _cb = '#22c55e', '#0a1a0a'
            _chip_verdict = f'🟢 **籌碼偏多**：三大法人合計大量買超 +{_tot_now:,} 張，資金面強力支撐。'
        elif _tot_now >= 50000:
            _cv, _cb = '#4ade80', '#0a150a'
            _chip_verdict = f'🟢 **籌碼略偏多**：三大法人合計買超 +{_tot_now:,} 張，資金面小幅偏正面。'
        elif _tot_now <= -200000:
            _cv, _cb = '#ef4444', '#2d0a0a'
            _chip_verdict = f'🔴 **籌碼偏空**：三大法人合計大量賣超 {_tot_now:,} 張，資金面明顯承壓。'
        elif _tot_now <= -50000:
            _cv, _cb = '#f97316', '#2d1500'
            _chip_verdict = f'🟡 **籌碼略偏空**：三大法人合計賣超 {_tot_now:,} 張，資金面小幅偏弱。'
        else:
            _cv, _cb = '#94a3b8', '#1a1f2e'
            _chip_verdict = f'⚪ **籌碼中性**：三大法人合計 {_tot_now:+,} 張，買賣方向尚不明確。'

        for icon, msg in _chip_msgs:
            if icon == '⚪':
                _ic = '#475569'
            elif icon == '🟢':
                _ic = '#22c55e'
            elif icon == '🟡':
                _ic = '#f59e0b'
            else:
                _ic = '#ef4444'
            st.markdown(
                f'<div style="padding:5px 12px;border-left:3px solid {_ic};margin-bottom:4px;font-size:13px">'
                f'{icon} {msg}</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div style="background:{_cb};border:2px solid {_cv};border-radius:8px;'
            f'padding:12px 16px;margin-top:8px">'
            f'<span style="color:{_cv};font-size:14px">{_chip_verdict}</span></div>',
            unsafe_allow_html=True)
        st.markdown('')

    st.markdown('---')

    # ── 台指期三大法人未平倉 ─────────────────
    st.markdown('#### 📊 台指期三大法人未平倉口數')
    futures_data = get_futures_institutional(days=90)

    if not futures_data:
        st.info('尚無台指期未平倉資料，請按「🔄 手動更新資料」取得。')
    else:
        latest = futures_data[-1]
        f_net  = latest['foreign_net']
        t_net  = latest['trust_net']
        d_net  = latest['dealer_net']
        total_net = f_net + t_net + d_net

        # ── 最新數值指標 ──
        c1, c2, c3, c4 = st.columns(4)
        def net_color(v): return '#22c55e' if v > 0 else '#ef4444' if v < 0 else '#94a3b8'
        def net_label(v): return f'+{v:,}' if v > 0 else f'{v:,}'

        c1.markdown(f'**外資**<br><span style="font-size:22px;font-weight:700;color:{net_color(f_net)}">{net_label(f_net)} 口</span><br><span style="font-size:11px;color:#64748b">多{latest["foreign_long"]:,} / 空{latest["foreign_short"]:,}</span>', unsafe_allow_html=True)
        c2.markdown(f'**投信**<br><span style="font-size:22px;font-weight:700;color:{net_color(t_net)}">{net_label(t_net)} 口</span><br><span style="font-size:11px;color:#64748b">多{latest["trust_long"]:,} / 空{latest["trust_short"]:,}</span>', unsafe_allow_html=True)
        c3.markdown(f'**自營商**<br><span style="font-size:22px;font-weight:700;color:{net_color(d_net)}">{net_label(d_net)} 口</span><br><span style="font-size:11px;color:#64748b">多{latest["dealer_long"]:,} / 空{latest["dealer_short"]:,}</span>', unsafe_allow_html=True)
        c4.markdown(f'**三大合計**<br><span style="font-size:22px;font-weight:700;color:{net_color(total_net)}">{net_label(total_net)} 口</span><br><span style="font-size:11px;color:#64748b">資料日期：{latest["date"]}</span>', unsafe_allow_html=True)

        # ── 趨勢折線圖 ──
        dates  = [r['date'] for r in futures_data]
        f_nets = [r['foreign_net'] for r in futures_data]
        t_nets = [r['trust_net']   for r in futures_data]
        d_nets = [r['dealer_net']  for r in futures_data]
        totals = [f + t + d for f, t, d in zip(f_nets, t_nets, d_nets)]

        fig_fut = go.Figure()
        fig_fut.add_trace(go.Scatter(x=dates, y=f_nets, name='外資', line=dict(color='#60a5fa', width=2)))
        fig_fut.add_trace(go.Scatter(x=dates, y=t_nets, name='投信', line=dict(color='#34d399', width=1.5)))
        fig_fut.add_trace(go.Scatter(x=dates, y=d_nets, name='自營商', line=dict(color='#f59e0b', width=1.5)))
        fig_fut.add_trace(go.Scatter(x=dates, y=totals, name='三大合計', line=dict(color='#e2e8f0', width=2, dash='dot')))
        fig_fut.add_hline(y=0, line_color='#475569', line_width=1)
        fig_fut.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation='h', y=1.1),
            yaxis=dict(gridcolor='#1e293b', zeroline=False),
            xaxis=dict(gridcolor='#1e293b'),
            font=dict(color='#94a3b8'),
        )
        st.markdown('**未平倉口數淨額走勢（正=偏多、負=偏空）**')
        show_chart(fig_fut)

        # ── 判斷文字 ──
        f20 = [r['foreign_net'] for r in futures_data[-20:]]
        f_trend = f_nets[-1] - f_nets[-6] if len(f_nets) >= 6 else 0

        msgs = []
        if f_net > 10000:
            msgs.append(f'🟢 **外資大幅偏多** {f_net:,} 口，期貨市場看多氣氛強烈，支撐指數上漲動能。')
        elif f_net > 0:
            msgs.append(f'🟡 **外資小幅偏多** {f_net:,} 口，多空分歧，方向未明。')
        elif f_net > -10000:
            msgs.append(f'🟡 **外資小幅偏空** {f_net:,} 口，空方略佔優勢，指數偏弱。')
        else:
            msgs.append(f'🔴 **外資大幅偏空** {f_net:,} 口，法人期貨空單沉重，需留意指數下行風險。')

        if f_trend > 5000:
            msgs.append(f'📈 外資近 5 日淨多單增加 {f_trend:+,} 口，持續加碼多單，趨勢偏多。')
        elif f_trend < -5000:
            msgs.append(f'📉 外資近 5 日淨多單減少 {f_trend:+,} 口，持續擴大空單，趨勢偏空。')

        if t_net > 20000:
            msgs.append(f'🟢 **投信期貨多單** {t_net:,} 口，投信大力做多，對後市樂觀。')
        elif t_net < 0:
            msgs.append(f'🔴 **投信期貨偏空** {t_net:,} 口，投信看空後市。')

        if total_net > 20000:
            msgs.append(f'✅ **三大法人合計偏多 {total_net:,} 口**，籌碼面整體支撐行情。')
        elif total_net < -20000:
            msgs.append(f'⚠️ **三大法人合計偏空 {total_net:,} 口**，籌碼面整體壓制行情，操作需謹慎。')

        for msg in msgs:
            st.markdown(msg)

        st.caption(f'資料來源：台灣期貨交易所 TAIFEX｜資料日期：{latest["date"]}｜正值=淨多單（看多）、負值=淨空單（看空）')

    st.markdown('---')

    # ── 大盤融資融券 ─────────────────────────
    st.markdown('#### 💰 大盤融資融券')
    mmargin = get_market_margin(days=120)

    if not mmargin:
        st.info('尚無大盤融資融券資料，更新資料後即可顯示。')
    else:
        mm_latest = mmargin[-1]
        mm_date   = mm_latest['date']
        mb_now    = mm_latest['margin_balance']
        sb_now    = mm_latest['short_balance']
        # 比較基準：20日前，若不足20筆則用最舊的一筆
        _cmp_idx  = min(20, len(mmargin) - 1)
        _cmp_days = _cmp_idx  # 實際相差幾筆
        mb_20     = mmargin[-_cmp_idx - 1]['margin_balance'] if _cmp_idx > 0 else mb_now
        sb_20     = mmargin[-_cmp_idx - 1]['short_balance']  if _cmp_idx > 0 else sb_now
        mb_chg    = (mb_now - mb_20) / mb_20 * 100 if mb_20 > 0 else 0
        sb_chg    = (sb_now - sb_20) / sb_20 * 100 if sb_20 > 0 else 0
        _cmp_label = f'較{_cmp_days}日前' if _cmp_days < 20 else '較20日前'

        # 融資使用率判斷（以近120日最高值為基準）
        mb_max    = max(r['margin_balance'] for r in mmargin)
        mb_min    = min(r['margin_balance'] for r in mmargin if r['margin_balance'] > 0)
        usage_pct = (mb_now - mb_min) / (mb_max - mb_min) * 100 if mb_max > mb_min else 50

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(f'融資餘額（{mm_date}）',
                      f'{mb_now:,} 億元',
                      delta=f'{mb_chg:+.1f}% {_cmp_label}')
        with col2:
            st.metric('融券餘額',
                      f'{sb_now:,} 張',
                      delta=f'{sb_chg:+.1f}% {_cmp_label}')
        with col3:
            if usage_pct >= 75:
                usage_label = '融資偏高 ⚠️'
                usage_color = '#ef4444'
            elif usage_pct <= 30:
                usage_label = '融資偏低 ✅'
                usage_color = '#22c55e'
            else:
                usage_label = '融資中性 →'
                usage_color = '#f59e0b'
            st.metric('近120日融資水位', f'{usage_pct:.0f}%', delta=usage_label)

        # 融資融券走勢圖
        mm_dates = [r['date'] for r in mmargin]
        mb_vals  = [r['margin_balance'] for r in mmargin]
        sb_vals  = [r['short_balance']  for r in mmargin]

        fig_mm = make_subplots(specs=[[{'secondary_y': True}]])
        fig_mm.add_trace(go.Scatter(
            x=mm_dates, y=mb_vals, name='融資餘額',
            mode='lines', fill='tozeroy',
            line=dict(color='#ef4444', width=2),
            fillcolor='rgba(239,68,68,0.15)'
        ), secondary_y=False)
        fig_mm.add_trace(go.Scatter(
            x=mm_dates, y=sb_vals, name='融券餘額',
            mode='lines',
            line=dict(color='#38bdf8', width=2),
        ), secondary_y=True)
        fig_mm.update_layout(
            paper_bgcolor='#0d0f12', plot_bgcolor='#141720',
            font=dict(color='#e2e8f0', size=11),
            height=300, margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            xaxis=dict(showgrid=True, gridcolor='#252a38'),
        )
        fig_mm.update_yaxes(title_text='融資餘額', showgrid=True, gridcolor='#252a38', secondary_y=False)
        fig_mm.update_yaxes(title_text='融券餘額', showgrid=False, secondary_y=True)
        show_chart(fig_mm)

        # 判斷說明
        if usage_pct >= 75:
            st.warning(f'⚠️ **融資偏高警訊**：目前融資餘額處於近120日高水位（{usage_pct:.0f}%），'
                       f'代表市場借錢追高行為偏積極。歷史上融資高水位往往是多頭末段訊號，'
                       f'需留意回檔風險，建議降低槓桿、謹慎追高。')
        elif usage_pct <= 30:
            st.success(f'✅ **融資偏低訊號**：目前融資餘額處於近120日低水位（{usage_pct:.0f}%），'
                       f'代表市場恐慌情緒較重、借錢追高意願低。歷史上融資低水位常是底部訊號，'
                       f'逢回可留意低接機會。')
        else:
            st.info(f'→ **融資中性**：目前融資水位在近120日中段（{usage_pct:.0f}%），'
                    f'市場情緒尚屬正常，操作上不特別偏多或偏空。')

        if mb_chg > 5:
            st.caption(f'📈 融資近20日增加 {mb_chg:.1f}%，籌碼略偏激進，留意高檔風險。')
        elif mb_chg < -5:
            st.caption(f'📉 融資近20日減少 {abs(mb_chg):.1f}%，籌碼正在清洗，可觀察是否落底。')
        st.caption(f'資料來源：TWSE MI_MARGN｜資料日期：{mm_date}')

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

    # ── 📋 大盤籌碼總判斷 ─────────────────────
    st.markdown('---')
    st.markdown('#### 📋 大盤籌碼總判斷')

    mmargin_all = get_market_margin(days=120)
    _has_data   = mmargin_all and len(mmargin_all) >= 5

    if not _has_data:
        st.info('融資融券資料不足，更新後即可顯示總判斷。')
    else:
        from config import (TWSE_CAP_COEF, TWSE_CAP_CALIBRATED,
                            TWSE_CAP_WARN_DAYS,
                            MARGIN_RATIO_WARNING, MARGIN_RATIO_DANGER)
        from datetime import datetime as _dt

        # 每日用指數估算市值（億元）
        market_cap_b     = close * TWSE_CAP_COEF            # 億元
        market_cap_t     = market_cap_b / 10000             # 兆元

        # 超過校準警告天數才提醒（預設1年）
        _days_since = (_dt.now() - _dt.strptime(TWSE_CAP_CALIBRATED, '%Y-%m-%d')).days
        if _days_since > TWSE_CAP_WARN_DAYS:
            st.warning(
                f'⚠️ 市值校準係數已 **{_days_since} 天**未更新（上次：{TWSE_CAP_CALIBRATED}）。'
                f'請查詢最新市值後更新 `config.py` 的 `TWSE_CAP_COEF`。'
                f'參考：https://www.twse.com.tw/zh/statistics/statisticsReport/marketInformation.html'
            )

        # ── Signal 1：融資佔總市值比 ──────────
        latest_mm   = mmargin_all[-1]
        mb_b        = latest_mm['margin_balance']           # 億元
        margin_ratio = mb_b / market_cap_b * 100 if market_cap_b > 0 else 0

        if margin_ratio >= MARGIN_RATIO_DANGER:
            sig1_score = -2
            sig1_color = '#ef4444'
            sig1_label = f'⛔ 融資佔市值 {margin_ratio:.2f}%，歷史警戒區（>{MARGIN_RATIO_DANGER}%），槓桿過高'
        elif margin_ratio >= MARGIN_RATIO_WARNING:
            sig1_score = -1
            sig1_color = '#f59e0b'
            sig1_label = f'⚠️ 融資佔市值 {margin_ratio:.2f}%，接近警戒線（{MARGIN_RATIO_WARNING}%），需留意'
        elif margin_ratio >= 0.85:
            sig1_score = 0
            sig1_color = '#f59e0b'
            sig1_label = f'🟡 融資佔市值 {margin_ratio:.2f}%，偏高但尚可，注意後續變化'
        else:
            sig1_score = 1
            sig1_color = '#22c55e'
            sig1_label = f'✅ 融資佔市值 {margin_ratio:.2f}%（估算市值 {market_cap_t:.1f} 兆），目前健康，尚未過熱'

        # ── Signal 2：融資5日趨勢 + 季線 ──────
        mb_5day = [r['margin_balance'] for r in mmargin_all[-6:]]
        mb_trend_5d = mb_5day[-1] - mb_5day[0] if len(mb_5day) >= 2 else 0
        mb_5d_chg_b = mb_5day[-1] - mb_5day[0]  # 億元變化

        above_ma60 = close >= ma60 if ma60 else True  # 指數在季線上

        if mb_5d_chg_b <= -200 and not above_ma60:
            sig2_score = -2
            sig2_color = '#ef4444'
            sig2_label = f'⛔ 融資5日大減 {mb_5d_chg_b:+,.0f} 億且指數跌破季線（{ma60:,.0f}），主力斷頭訊號，高度警戒'
        elif mb_5d_chg_b <= -100 and not above_ma60:
            sig2_score = -1
            sig2_color = '#f59e0b'
            sig2_label = f'⚠️ 融資5日減少 {mb_5d_chg_b:+,.0f} 億，指數跌破季線，籌碼鬆動，注意跌勢擴大'
        elif mb_5d_chg_b >= 300 and above_ma60:
            sig2_score = -1
            sig2_color = '#f59e0b'
            sig2_label = f'⚠️ 融資5日大增 {mb_5d_chg_b:+,.0f} 億（單週暴增警戒線 300 億），若指數不過前高需開始減碼'
        elif mb_5d_chg_b >= 300 and not above_ma60:
            sig2_score = -2
            sig2_color = '#ef4444'
            sig2_label = f'⛔ 融資5日大增 {mb_5d_chg_b:+,.0f} 億且指數在季線下，散戶逆勢加碼，風險極高'
        else:
            ma60_txt = f'季線（{ma60:,.0f}）上方' if above_ma60 else f'季線（{ma60:,.0f}）下方'
            sig2_score = 1 if above_ma60 else -1
            sig2_color = '#22c55e' if above_ma60 else '#f59e0b'
            sig2_label = f'{"✅" if above_ma60 else "🟡"} 融資5日變化 {mb_5d_chg_b:+,.0f} 億，指數在{ma60_txt}，{"多方格局"if above_ma60 else "注意季線壓力"}'

        # ── Signal 3：券資比 ───────────────────
        sb_b = latest_mm['short_balance']
        short_ratio = sb_b / mb_b * 100 if mb_b > 0 else 0

        if short_ratio < 2.5:
            sig3_score = -1
            sig3_color = '#f59e0b'
            sig3_label = f'⚠️ 券資比僅 {short_ratio:.1f}%（< 2.5%），軋空力道弱，多頭保護墊薄'
        elif short_ratio >= 10:
            sig3_score = 1
            sig3_color = '#22c55e'
            sig3_label = f'✅ 券資比 {short_ratio:.1f}%（高空單），若大盤反彈可能觸發軋空，上漲動能充足'
        elif short_ratio >= 5:
            sig3_score = 1
            sig3_color = '#22c55e'
            sig3_label = f'✅ 券資比 {short_ratio:.1f}%，融券尚有一定保護，市場籌碼結構健康'
        else:
            sig3_score = 0
            sig3_color = '#94a3b8'
            sig3_label = f'⚪ 券資比 {short_ratio:.1f}%，中性水位'

        # ── 總分 & 結論 ────────────────────────
        total_score = sig1_score + sig2_score + sig3_score

        if total_score >= 2:
            verdict_color = '#22c55e'
            verdict = '🟢 **整體籌碼健康，目前無警訊**：融資未過熱、趨勢穩健，可積極參與行情。'
        elif total_score == 1:
            verdict_color = '#22c55e'
            verdict = '🟢 **大致偏多，留意個別風險**：整體籌碼正常，短線可操作，但需注意前文個別警示。'
        elif total_score == 0:
            verdict_color = '#f59e0b'
            verdict = '🟡 **中性觀望**：多空訊號混雜，建議降低持股比重，等待方向明朗後再加碼。'
        elif total_score == -1:
            verdict_color = '#f59e0b'
            verdict = '🟡 **偏空謹慎**：籌碼出現部分警訊，建議持股保守，勿追高，設好停損。'
        else:
            verdict_color = '#ef4444'
            verdict = '🔴 **高度警戒，建議大幅減碼**：多個籌碼指標同時亮紅燈，系統性風險提升，優先保本。'

        # 顯示三個訊號
        st.markdown(f'<div style="padding:6px 10px;border-left:3px solid {sig1_color};margin-bottom:6px">{sig1_label}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="padding:6px 10px;border-left:3px solid {sig2_color};margin-bottom:6px">{sig2_label}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="padding:6px 10px;border-left:3px solid {sig3_color};margin-bottom:12px">{sig3_label}</div>', unsafe_allow_html=True)

        # 總結論
        st.markdown(
            f'<div style="background:#1a1f2e;border-radius:8px;padding:14px 16px;'
            f'border:1px solid {verdict_color};margin-top:4px">'
            f'<span style="color:{verdict_color};font-size:15px">{verdict}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f'融資餘額 {mb_b:,} 億　融券餘額 {sb_b:,} 億　季線 {ma60:,.0f}　'
            f'｜ 今日估算市值：{market_cap_t:.1f} 兆'
            f'（指數 {close:,.0f} × 係數 {TWSE_CAP_COEF}，校準日：{TWSE_CAP_CALIBRATED}）'
        )

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
            # 用 DB 最新收盤價補正 prev_close（比 TWSE 預告時的舊價格更準確）
            from database import get_conn as _gc_ex
            _conn_ex = _gc_ex()
            for r in ex_rows:
                _row = _conn_ex.execute(
                    'SELECT close FROM prices WHERE code=? ORDER BY date DESC LIMIT 1',
                    (r['code'],)
                ).fetchone()
                if _row and _row[0]:
                    r['prev_close'] = _row[0]
            _conn_ex.close()

            # 計算殖利率並排序
            for r in ex_rows:
                r['yield_pct'] = round(r['div_value'] / r['prev_close'] * 100, 2) if r['prev_close'] > 0 else 0.0

            sort_opt = st.radio('排序方式', ['依除權息日', '依殖利率（高→低）'],
                                horizontal=True, label_visibility='collapsed')
            if sort_opt == '依殖利率（高→低）':
                ex_rows = sorted(ex_rows, key=lambda x: x['yield_pct'], reverse=True)

            # 產生 HTML 表格（固定標題列 + 捲動視窗，本機/雲端一致）
            type_label = {'息': '💰 息', '權': '📊 權', '權息': '💰📊 權息'}
            rows_html = ''
            for r in ex_rows:
                yld = r['yield_pct']
                yld_color = '#22c55e' if yld >= 5 else '#facc15' if yld >= 3 else '#94a3b8'
                yld_str   = f'<span style="color:{yld_color};font-weight:600">{yld:.2f}%</span>' if yld > 0 else '<span style="color:#475569">—</span>'
                div_str   = f'<span style="color:#facc15;font-weight:600">{r["div_value"]:.4f}</span>' if r['div_value'] > 0 else '<span style="color:#475569">待公告</span>'
                close_str = f'{r["prev_close"]:.2f}' if r['prev_close'] > 0 else '—'
                status    = '✅ 正式' if r.get('is_confirmed') else '📋 預告'
                status_c  = '#22c55e' if r.get('is_confirmed') else '#f59e0b'
                tl        = type_label.get(r['div_type'], r['div_type'])
                rows_html += f'''<tr>
                    <td>{r["ex_date"]}</td>
                    <td style="color:#60a5fa">{r["code"]}</td>
                    <td>{r["name"]}</td>
                    <td style="text-align:right">{close_str}</td>
                    <td style="text-align:right">{div_str}</td>
                    <td style="text-align:right">{yld_str}</td>
                    <td>{tl}</td>
                    <td style="color:{status_c};font-size:12px">{status}</td>
                </tr>'''

            html_table = f'''
            <div style="border:1px solid #334155;border-radius:8px;overflow:hidden">
              <div style="overflow-y:auto;max-height:480px">
                <table style="width:100%;border-collapse:collapse;font-size:13px">
                  <thead>
                    <tr style="background:#1e293b;position:sticky;top:0;z-index:1">
                      <th style="padding:8px 10px;text-align:left;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">除權息日</th>
                      <th style="padding:8px 10px;text-align:left;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">代號</th>
                      <th style="padding:8px 10px;text-align:left;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">名稱</th>
                      <th style="padding:8px 10px;text-align:right;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">前收盤</th>
                      <th style="padding:8px 10px;text-align:right;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">權息值</th>
                      <th style="padding:8px 10px;text-align:right;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">殖利率</th>
                      <th style="padding:8px 10px;text-align:left;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">類型</th>
                      <th style="padding:8px 10px;text-align:left;color:#94a3b8;font-weight:500;border-bottom:1px solid #334155">狀態</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows_html}
                  </tbody>
                </table>
              </div>
            </div>
            '''
            st.markdown(html_table, unsafe_allow_html=True)
            st.caption('💡 殖利率 = 權息值 ÷ 前收盤價　｜　✅ 正式 = TWSE 已確認　📋 預告 = 早期公告')

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

    # 程式說明頁
    if page == 'doc':
        render_doc()
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
                    from fetcher import fetch_history_auto
                    fetch_history_auto(code, months=15)
                    st.write('✅ 價格資料完成')
                except Exception as _e:
                    st.write(f'⚠️ 價格資料失敗：{_e}')

            # 上櫃股基本面由 TWSE BWIBBU_ALL 無法覆蓋，改用 yfinance 補抓
            fund_check = get_fundamentals(code, days=400)
            if not fund_check:
                from database import get_conn as _gc2
                _mkt2 = (_gc2().execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
                _gc2().close()
                if _mkt2 == 'TPEx':
                    st.write('📥 抓取上櫃基本面（yfinance）...')
                    try:
                        from fetcher import fetch_fundamentals_tpex
                        fetch_fundamentals_tpex(code)
                        st.write('✅ 基本面資料完成')
                    except Exception as _e:
                        st.write(f'⚠️ 基本面資料失敗：{_e}')

            if need_chips:
                # 上櫃股（TPEx）T86 API 無資料，跳過籌碼歷史補抓
                from database import get_conn as _gc
                _mkt = (_gc().execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
                _gc().close()
                if _mkt == 'TPEx':
                    st.write('ℹ️ 上櫃股籌碼歷史暫不支援（TWSE T86 僅涵蓋上市股）')
                else:
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

    # 查詢市場別
    from database import get_conn as _gc_hdr
    _conn_hdr = _gc_hdr()
    _mkt_hdr = (_conn_hdr.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
    _conn_hdr.close()
    _mkt_label = '🏢 上市（TWSE）' if _mkt_hdr == 'TWSE' else '🏬 上櫃（TPEx）' if _mkt_hdr == 'TPEx' else ''

    st.markdown(f'## {icon} {name}（{code}）　{close}元　{grade}（{result["total_score"]}分）')
    if _mkt_label:
        st.caption(_mkt_label)

    # 六個頁籤（程式說明已移至左側欄）
    tabs = st.tabs(['📊 技術面', '💰 基本面', '🏦 籌碼面',
                    '⭐ 綜合評分', '📝 備註欄', '📤 匯出分析'])

    with tabs[0]:
        render_technical(result, name)
    with tabs[1]:
        render_fundamental(result, code, name)
    with tabs[2]:
        from database import get_conn as _gc_tab
        _conn_tab = _gc_tab()
        _mkt_tab = (_conn_tab.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
        _conn_tab.close()
        render_chips(result, code, name, chips_list, market=_mkt_tab)
    with tabs[3]:
        render_score(result, code, name)
    with tabs[4]:
        render_notes(result, code, name)
    with tabs[5]:
        render_export(result, code, name, chips_list)

if __name__ == '__main__':
    main()
