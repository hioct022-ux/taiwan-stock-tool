# ════════════════════════════════════════
# theme_rotation.py — 主題輪動分析頁
# ════════════════════════════════════════
#
# 獨立模組：新增/修改此頁不需更動其他任何功能
#
# 資料來源：yfinance（外部 API，雲端本機均可用）
# 快取策略：@st.cache_data(ttl=900)，15 分鐘
# DB 依賴：無
# github_sync 依賴：無
# IS_LOCAL 分支：無（不需要）
#
# app.py 只需要：
#   1. from theme_rotation import render_theme_rotation
#   2. 側邊欄按鈕（page='theme_rotation'）
#   3. main() 路由 elif page == 'theme_rotation'
# ════════════════════════════════════════

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ── 主題定義（要新增主題只改這裡）───────────────────────
THEMES = {
    '台灣寬基': {
        'ticker':       '0050.TW',
        'label':        '0050 元大台灣50',
        'color':        '#94a3b8',
        'is_benchmark': True,
    },
    '台灣半導體': {
        'ticker':       '00891.TW',
        'label':        '00891 中信關鍵半導體',
        'color':        '#f97316',
        'is_benchmark': False,
    },
    '高股息': {
        'ticker':       '0056.TW',
        'label':        '0056 元大高股息',
        'color':        '#3b82f6',
        'is_benchmark': False,
    },
    '費城半導體（美）': {
        'ticker':       '00830.TW',
        'label':        '00830 國泰費城半導體',
        'color':        '#a855f7',
        'is_benchmark': False,
    },
}

BENCHMARK_KEY = '台灣寬基'

_CHART_CFG = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': False}

_PERIOD_MAP = {
    '1個月':  21,
    '3個月':  63,
    '6個月': 126,
    '1年':   252,
}


# ── 圖表輔助 ─────────────────────────────────────────────
def _show(fig, key=None):
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG, key=key)


# ── 資料抓取 ─────────────────────────────────────────────
@st.cache_data(ttl=900)
def _fetch() -> pd.DataFrame:
    """
    下載所有主題 ETF 近 1 年日收盤。
    回傳寬表 DataFrame，columns = ticker，index = date。
    任一 ticker 失敗不影響其他。
    """
    try:
        import yfinance as yf
        tickers = [v['ticker'] for v in THEMES.values()]
        raw = yf.download(tickers, period='1y', auto_adjust=True,
                          progress=False, threads=True)
        # yfinance 多 ticker 回傳 MultiIndex；單 ticker 回傳普通 columns
        if isinstance(raw.columns, pd.MultiIndex):
            df = raw['Close']
        else:
            df = raw[['Close']] if 'Close' in raw.columns else raw
            # 若只有一個 ticker 的 fallback
            if len(tickers) == 1:
                df.columns = tickers
        return df.dropna(how='all')
    except Exception as e:
        st.error(f'yfinance 下載失敗：{e}')
        return pd.DataFrame()


# ── 計算：RS Line ────────────────────────────────────────
def _calc_rs_lines(df: pd.DataFrame, n_days: int) -> dict:
    """
    各主題相對強度折線，區間起點標準化為 100。
    回傳 {theme_name: pd.Series(index=date, values=RS)}
    """
    bench_ticker = THEMES[BENCHMARK_KEY]['ticker']
    if bench_ticker not in df.columns:
        return {}

    data = df.iloc[-n_days:] if len(df) >= n_days else df
    result = {}
    for theme, info in THEMES.items():
        if info['is_benchmark']:
            continue
        t = info['ticker']
        if t not in data.columns:
            continue
        valid = data[[t, bench_ticker]].dropna()
        if len(valid) < 5:
            continue
        rs = valid[t] / valid[bench_ticker]
        rs_norm = rs / rs.iloc[0] * 100
        result[theme] = rs_norm
    return result


# ── 計算：RRG ────────────────────────────────────────────
def _calc_rrg(df: pd.DataFrame) -> list:
    """
    JdK RS-Ratio & RS-Momentum（簡化版）：
      RS_Ratio   = (price/bench) / SMA52(price/bench) * 100
      RS_Momentum = RS_Ratio / SMA10(RS_Ratio) * 100

    回傳最近 8 個週資料點（可顯示移動尾跡）：
    [
      {
        'theme': str,
        'label': str,
        'color': str,
        'points': [{'ratio': float, 'moment': float, 'date': str}, ...],  # 舊→新
      },
      ...
    ]
    """
    bench_ticker = THEMES[BENCHMARK_KEY]['ticker']
    if bench_ticker not in df.columns:
        return []

    result = []
    for theme, info in THEMES.items():
        if info['is_benchmark']:
            continue
        t = info['ticker']
        if t not in df.columns:
            continue
        valid = df[[t, bench_ticker]].dropna()
        if len(valid) < 60:   # 至少 60 個交易日才能算
            continue

        rs          = valid[t] / valid[bench_ticker]
        rs_ratio    = rs / rs.rolling(52).mean() * 100
        rs_momentum = rs_ratio / rs_ratio.rolling(10).mean() * 100

        combined = pd.DataFrame({
            'ratio':  rs_ratio,
            'moment': rs_momentum,
        }).dropna()

        # 週取樣（取每週最後一個交易日）
        weekly = combined.resample('W').last().dropna()
        trail  = weekly.iloc[-8:]   # 最近 8 週

        if trail.empty:
            continue

        points = [
            {
                'ratio':  float(row['ratio']),
                'moment': float(row['moment']),
                'date':   f'{idx.year}年{idx.month}月{idx.day}日',
            }
            for idx, row in trail.iterrows()
        ]
        result.append({
            'theme':  theme,
            'label':  info['label'],
            'color':  info['color'],
            'points': points,
        })
    return result


def _quadrant(ratio: float, moment: float) -> tuple:
    """回傳 (象限名稱, 顏色)"""
    if ratio >= 100 and moment >= 100:
        return '領先',   '#22c55e'
    if ratio >= 100 and moment < 100:
        return '轉弱', '#f59e0b'
    if ratio < 100  and moment < 100:
        return '落後',   '#ef4444'
    return                  '改善', '#3b82f6'


# ── 主渲染函式 ───────────────────────────────────────────
def render_theme_rotation():
    st.markdown('## 🔄 主題輪動')
    st.caption('資料來源：yfinance｜快取 15 分鐘｜基準：0050（元大台灣50）')

    # 1. 抓資料
    with st.spinner('載入 ETF 資料中...'):
        df = _fetch()

    if df.empty:
        st.warning('目前無法取得 ETF 資料，請確認網路連線後重試。')
        return

    bench_ticker = THEMES[BENCHMARK_KEY]['ticker']
    if bench_ticker not in df.columns:
        st.warning('基準 ETF（0050）資料缺失，無法計算相對強度。')
        return

    non_bench = [k for k, v in THEMES.items()
                 if not v['is_benchmark'] and v['ticker'] in df.columns]
    if not non_bench:
        st.warning('主題 ETF 資料皆缺失。')
        return

    # 2. 時間區間
    sel_period = st.radio(
        '顯示區間（RS 折線圖）',
        list(_PERIOD_MAP.keys()),
        index=2,
        horizontal=True,
        key='tr_period',
    )
    n_days = _PERIOD_MAP[sel_period]

    st.markdown('---')

    # ── Chart 1：RS 趨勢折線圖 ──────────────────────────
    st.markdown('#### 📈 相對強度趨勢（RS Line）')
    st.caption('各主題 ETF 相對於 0050 的表現，區間起點 = 100，高於 100 代表跑贏大盤')

    rs_lines = _calc_rs_lines(df, n_days)

    if rs_lines:
        fig_rs = go.Figure()

        # 基準線
        fig_rs.add_hline(
            y=100, line_dash='dot', line_color='#475569',
            annotation_text='大盤基準（0050）',
            annotation_position='bottom right',
            annotation_font=dict(color='#64748b', size=10),
        )

        for theme, series in rs_lines.items():
            info   = THEMES[theme]
            latest = series.iloc[-1]
            diff   = latest - 100
            sign   = '+' if diff >= 0 else ''
            fig_rs.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                name=f'{theme}（{sign}{diff:.1f}）',
                line=dict(color=info['color'], width=2),
                hovertemplate=(
                    f'<b>{theme}</b><br>'
                    '%{x|%Y-%m-%d}<br>'
                    'RS：%{y:.1f}<extra></extra>'
                ),
            ))

        fig_rs.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'),
            hovermode='x unified',
            legend=dict(orientation='h', y=-0.22, font=dict(size=11)),
            yaxis=dict(gridcolor='#1e293b', title='RS（100 = 大盤）'),
            xaxis=dict(gridcolor='#1e293b'),
            height=330,
            margin=dict(t=10, b=70, l=55, r=20),
        )
        _show(fig_rs, key='tr_rs_line')
    else:
        st.info('RS 資料不足，請稍後再試。')

    st.markdown('---')

    # ── Chart 2：RRG 四象限 ─────────────────────────────
    st.markdown('#### 🧭 RRG 主題輪動圖')
    st.caption(
        'X 軸：RS Ratio（相對強度）｜Y 軸：RS Momentum（動能）｜'
        '虛線尾跡 = 近 8 週軌跡，方向顯示輪動趨勢'
    )

    rrg_items = _calc_rrg(df)

    if rrg_items:
        # 自動決定顯示範圍
        all_ratios  = [p['ratio']  for item in rrg_items for p in item['points']]
        all_moments = [p['moment'] for item in rrg_items for p in item['points']]
        pad = 1.5
        xmin = min(min(all_ratios)  - pad, 96)
        xmax = max(max(all_ratios)  + pad, 104)
        ymin = min(min(all_moments) - pad, 96)
        ymax = max(max(all_moments) + pad, 104)

        fig_rrg = go.Figure()

        # 四象限背景
        for (x0, x1, y0, y1, col) in [
            (100, xmax, 100, ymax, 'rgba(34,197,94,0.07)'),   # Leading（右上）
            (100, xmax, ymin, 100, 'rgba(245,158,11,0.07)'),  # Weakening（右下）
            (xmin, 100, ymin, 100, 'rgba(239,68,68,0.07)'),   # Lagging（左下）
            (xmin, 100, 100, ymax, 'rgba(59,130,246,0.07)'),  # Improving（左上）
        ]:
            fig_rrg.add_shape(
                type='rect', x0=x0, x1=x1, y0=y0, y1=y1,
                fillcolor=col, line_width=0, layer='below',
            )

        # 象限標籤
        for (label, xpos, ypos, col) in [
            ('領先 ↗', xmax - 1.2, ymax - 0.6, '#22c55e'),
            ('轉弱 ↘', xmax - 1.2, ymin + 0.6, '#f59e0b'),
            ('落後 ↙', xmin + 1.2, ymin + 0.6, '#ef4444'),
            ('改善 ↖', xmin + 1.2, ymax - 0.6, '#3b82f6'),
        ]:
            fig_rrg.add_annotation(
                x=xpos, y=ypos, text=label,
                font=dict(color=col, size=11),
                showarrow=False,
            )

        # 各主題：尾跡線 + 當前點
        for item in rrg_items:
            pts = item['points']
            if not pts:
                continue
            xs  = [p['ratio']  for p in pts]
            ys  = [p['moment'] for p in pts]
            col = item['color']
            quadrant, _ = _quadrant(xs[-1], ys[-1])

            # 尾跡（虛線，淡色）
            if len(pts) > 1:
                fig_rrg.add_trace(go.Scatter(
                    x=xs[:-1], y=ys[:-1],
                    mode='lines',
                    line=dict(color=col, width=1.5, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip',
                ))
                # 尾跡小點
                fig_rrg.add_trace(go.Scatter(
                    x=xs[:-1], y=ys[:-1],
                    mode='markers',
                    marker=dict(size=5, color=col, opacity=0.4),
                    showlegend=False,
                    hoverinfo='skip',
                ))

            # 當前點（大點 + 標籤）
            hover_lines = [
                f'<b>{item["theme"]}</b>',
                f'日期：{pts[-1]["date"]}',
                f'RS Ratio：{xs[-1]:.2f}',
                f'RS Momentum：{ys[-1]:.2f}',
                f'象限：<b>{quadrant}</b>',
            ]
            fig_rrg.add_trace(go.Scatter(
                x=[xs[-1]], y=[ys[-1]],
                mode='markers+text',
                marker=dict(
                    size=18, color=col,
                    line=dict(color='white', width=2),
                ),
                text=[item['theme']],
                textposition='top center',
                textfont=dict(size=11, color='#e2e8f0'),
                name=f'{item["theme"]}（{quadrant}）',
                hovertemplate='<br>'.join(hover_lines) + '<extra></extra>',
            ))

        # 中心線
        fig_rrg.add_hline(y=100, line_color='#334155', line_width=1)
        fig_rrg.add_vline(x=100, line_color='#334155', line_width=1)

        fig_rrg.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(15,20,35,1)',
            font=dict(color='#e2e8f0'),
            showlegend=True,
            legend=dict(orientation='h', y=-0.22, font=dict(size=11)),
            xaxis=dict(
                range=[xmin, xmax], gridcolor='#1e293b', zeroline=False,
                title='RS Ratio（相對強度）',
            ),
            yaxis=dict(
                range=[ymin, ymax], gridcolor='#1e293b', zeroline=False,
                title='RS Momentum（動能）',
            ),
            height=460,
            margin=dict(t=10, b=80, l=65, r=20),
        )
        _show(fig_rrg, key='tr_rrg')
    else:
        st.info('RRG 資料不足（需要至少 60 個交易日），請稍後再試。')

    # ── 文字摘要 ─────────────────────────────────────────
    st.markdown('---')
    st.markdown('#### 📋 現況摘要')

    rs_now = _calc_rs_lines(df, n_days)

    _q_emoji = {
        '領先': '🟢',
        '改善': '🔵',
        '轉弱': '🟡',
        '落後': '🔴',
    }

    if rrg_items:
        for item in rrg_items:
            pts = item['points']
            if not pts:
                continue
            ratio   = pts[-1]['ratio']
            moment  = pts[-1]['moment']
            quadrant, q_col = _quadrant(ratio, moment)
            emoji   = _q_emoji.get(quadrant, '⚪')

            rs_series = rs_now.get(item['theme'])
            rs_str = ''
            if rs_series is not None and not rs_series.empty:
                diff = rs_series.iloc[-1] - 100
                sign = '+' if diff >= 0 else ''
                rs_str = f'，{sel_period}相對強度 **{sign}{diff:.1f}%**'

            st.markdown(
                f'{emoji} **{item["theme"]}**（{item["label"]}）'
                f'　{quadrant}{rs_str}'
            )
    else:
        for theme in non_bench:
            rs_series = rs_now.get(theme)
            if rs_series is None or rs_series.empty:
                continue
            diff = rs_series.iloc[-1] - 100
            sign = '+' if diff >= 0 else ''
            st.markdown(
                f'⚪ **{theme}**（{THEMES[theme]["label"]}）'
                f'　{sel_period}相對強度 {sign}{diff:.1f}%'
            )

    st.caption(
        'RRG 說明：🟢 **領先** = 強勢延續　🟡 **轉弱** = 強勢但動能衰退　'
        '🔵 **改善** = 弱勢但動能回升（輪動進場訊號）　🔴 **落後** = 持續弱勢'
    )
