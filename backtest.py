"""
開盤前預判訊號回測腳本
用歷史資料逐日模擬訊號 → 預判方向 → 比對實際漲跌
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_prices, get_futures_institutional, get_market_margin, get_conn
from indicators import calc_all

init_db()

# ── 載入所有歷史資料 ────────────────────────────────
taiex_all = get_prices('TAIEX', days=500)
futures_all = get_futures_institutional(days=500)
margin_all = get_market_margin(days=500)

# T86 全部歷史（按日期彙總）
conn = get_conn()
t86_rows = conn.execute('''
    SELECT date,
           SUM(foreign_net) AS foreign_net_total,
           SUM(trust_net)   AS trust_net_total
    FROM t86_ranking
    GROUP BY date
    ORDER BY date
''').fetchall()
conn.close()

t86_by_date = {r[0]: {'foreign_net_total': r[1], 'trust_net_total': r[2]} for r in t86_rows}
fut_by_date  = {r['date']: r for r in futures_all}
mm_by_date   = {r['date']: r for r in margin_all}

# ── 訊號評分函式（與 app.py 邏輯一致）────────────────
def score_signals(tpx_window, fut_window, mm_window, t86_prev):
    """
    tpx_window : list of price dicts，最後一筆是「昨日」
    fut_window  : list of futures dicts（按日期升序），最後一筆是「昨日」
    mm_window   : 同上
    t86_prev    : dict or None，昨日 T86 彙總
    回傳 (bear_score, bull_score, signals_used)
    """
    bear, bull = 0, 0
    used = []

    # ── Signal 1：TAIEX 昨日漲跌 ──
    if len(tpx_window) >= 2:
        c_now  = tpx_window[-1]['close']
        c_prev = tpx_window[-2]['close']
        chg    = (c_now - c_prev) / c_prev * 100 if c_prev else 0
        if   chg <= -2.0: bear += 3; used.append(f'S1 大跌{chg:.1f}%(b+3)')
        elif chg <= -1.0: bear += 2; used.append(f'S1 跌{chg:.1f}%(b+2)')
        elif chg <= -0.3: bear += 1; used.append(f'S1 小跌{chg:.1f}%(b+1)')
        elif chg >=  2.0: bull += 3; used.append(f'S1 大漲+{chg:.1f}%(u+3)')
        elif chg >=  1.0: bull += 2; used.append(f'S1 漲+{chg:.1f}%(u+2)')
        elif chg >=  0.3: bull += 1; used.append(f'S1 小漲+{chg:.1f}%(u+1)')
        else:             used.append(f'S1 平盤{chg:.2f}%')

    # ── Signal 2：融資5日趨勢 ──
    if len(mm_window) >= 2:
        mb_now  = mm_window[-1]['margin_balance']
        mb_5ago = mm_window[-min(5, len(mm_window))]['margin_balance']
        mb_pct  = (mb_now - mb_5ago) / mb_5ago * 100 if mb_5ago else 0
        if   mb_pct >=  2.0: bear += 2; used.append(f'S2 融資+{mb_pct:.1f}%(b+2)')
        elif mb_pct >=  0.5: bear += 1; used.append(f'S2 融資+{mb_pct:.1f}%(b+1)')
        elif mb_pct <= -2.0: bull += 2; used.append(f'S2 融資{mb_pct:.1f}%(u+2)')
        elif mb_pct <= -0.5: bull += 1; used.append(f'S2 融資{mb_pct:.1f}%(u+1)')

    # ── Signal 3：外資期貨日變化 + 5日趨勢 ──
    if len(fut_window) >= 2:
        f_now   = fut_window[-1]['foreign_net']
        f_prev  = fut_window[-2]['foreign_net']
        f_5ago  = fut_window[-min(5, len(fut_window))]['foreign_net']
        f_chg   = f_now - f_prev
        f_trend = f_now - f_5ago
        if   f_chg >=  3000: bull += 2; used.append(f'S3 期回補+{f_chg:,}(u+2)')
        elif f_chg >=  1000: bull += 1; used.append(f'S3 期回補+{f_chg:,}(u+1)')
        elif f_chg <= -3000: bear += 2; used.append(f'S3 期擴空{f_chg:,}(b+2)')
        elif f_chg <= -1000: bear += 1; used.append(f'S3 期擴空{f_chg:,}(b+1)')
        if   f_trend >= 2000: bull += 1; used.append('S3 期5日多')
        elif f_trend <=-2000: bear += 1; used.append('S3 期5日空')

    # ── Signal 4：T86 外資現貨 ──
    if t86_prev:
        fg = t86_prev.get('foreign_net_total', 0) or 0
        tr = t86_prev.get('trust_net_total',   0) or 0
        if   fg >=  150000: bull += 3; used.append(f'S4 T86外資+{fg:,}(u+3)')
        elif fg >=   50000: bull += 2; used.append(f'S4 T86外資+{fg:,}(u+2)')
        elif fg >=   10000: bull += 1; used.append(f'S4 T86外資+{fg:,}(u+1)')
        elif fg <= -150000: bear += 3; used.append(f'S4 T86外資{fg:,}(b+3)')
        elif fg <=  -50000: bear += 2; used.append(f'S4 T86外資{fg:,}(b+2)')
        elif fg <=  -10000: bear += 1; used.append(f'S4 T86外資{fg:,}(b+1)')
        if tr >=  50000: bull += 1; used.append(f'S4 投信+{tr:,}(u+1)')
        elif tr <= -50000: bear += 1; used.append(f'S4 投信{tr:,}(b+1)')

    # ── Signal 5：BIAS5 / BIAS20 ──
    if len(tpx_window) >= 6:
        ind = calc_all(tpx_window)
        b5  = ind.get('bias5')
        b20 = ind.get('bias20')
        p250= ind.get('pos_250')
        mat = ind.get('ma_trend')
        if b5 is not None:
            if   b5 >=  5: bear += 2; used.append(f'S5 BIAS5={b5:.1f}%(b+2)')
            elif b5 >=  2: bear += 1; used.append(f'S5 BIAS5={b5:.1f}%(b+1)')
            elif b5 <= -5: bull += 2; used.append(f'S5 BIAS5={b5:.1f}%(u+2)')
            elif b5 <= -2: bull += 1; used.append(f'S5 BIAS5={b5:.1f}%(u+1)')
        if b20 is not None:
            if   b20 >=  8: bear += 1; used.append(f'S5 BIAS20={b20:.1f}%(b+1)')
            elif b20 <= -8: bull += 1; used.append(f'S5 BIAS20={b20:.1f}%(u+1)')
        if p250 is not None:
            if   p250 >= 90: bear += 1; used.append(f'S6 pos250={p250:.0f}%(b+1)')
            elif p250 <= 10: bull += 2; used.append(f'S6 pos250={p250:.0f}%(u+2)')
            elif p250 <= 25: bull += 1; used.append(f'S6 pos250={p250:.0f}%(u+1)')
        if mat == 'bullish': bull += 1; used.append('S7 MA多頭(u+1)')
        elif mat == 'bearish': bear += 1; used.append('S7 MA空頭(b+1)')

    # ── 成交量趨勢 ──
    if len(tpx_window) >= 5:
        vols = [p['value'] for p in tpx_window[-5:] if p.get('value', 0) > 0]
        if len(vols) >= 3:
            avg3  = sum(vols[-3:]) / 3
            avgpre = sum(vols[:max(1, len(vols)-3)]) / max(1, len(vols)-3)
            vt = (avg3 - avgpre) / avgpre * 100 if avgpre else 0
            if   vt <= -15: bear += 1; used.append(f'S8 量縮{vt:.0f}%(b+1)')
            elif vt >=  20: bull += 1; used.append(f'S8 量增{vt:.0f}%(u+1)')

    return bear, bull, used


# ── 回測主迴圈 ──────────────────────────────────────
results = []
taiex_dates = [p['date'] for p in taiex_all]

for i in range(1, len(taiex_all)):
    target = taiex_all[i]          # 今日（預測目標）
    date_today = target['date']
    date_prev  = taiex_all[i-1]['date']

    # 今日實際漲跌
    actual_chg = (target['close'] - taiex_all[i-1]['close']) / taiex_all[i-1]['close'] * 100
    actual_dir = 'up' if actual_chg > 0.1 else ('down' if actual_chg < -0.1 else 'flat')

    # 昨日之前的 TAIEX 視窗（最多 30 筆）
    tpx_win  = taiex_all[max(0, i-250):i]   # 250日：與 app.py 預判視窗一致（MA60 + 真正的250日位置）

    # 昨日及之前的期貨視窗（找 date <= date_prev）
    fut_win  = [r for r in futures_all if r['date'] <= date_prev][-15:]
    mm_win   = [r for r in margin_all  if r['date'] <= date_prev][-15:]
    t86_prev = t86_by_date.get(date_prev)

    bear, bull, used = score_signals(tpx_win, fut_win, mm_win, t86_prev)
    net = bear - bull  # 正 = 空方強，負 = 多方強

    if   net >=  1: pred = 'down'
    elif net <= -1: pred = 'up'
    else:           pred = 'neutral'

    results.append({
        'date': date_today,
        'actual_chg': actual_chg,
        'actual_dir': actual_dir,
        'bear': bear, 'bull': bull, 'net': net,
        'pred': pred,
        'signals': used,
    })


# ── 統計 ────────────────────────────────────────────
total    = len(results)
non_flat = [r for r in results if r['actual_dir'] != 'flat']
non_neu  = [r for r in results if r['pred'] != 'neutral']
correct_all = [r for r in results if r['pred'] == r['actual_dir'] and r['actual_dir'] != 'flat']
correct_nonneu = [r for r in non_neu if r['pred'] == r['actual_dir'] and r['actual_dir'] != 'flat']

# 強訊號（|net| >= 3）
strong   = [r for r in results if abs(r['net']) >= 3]
strong_correct = [r for r in strong if r['pred'] == r['actual_dir'] and r['actual_dir'] != 'flat']

# 方向分析
up_pred_correct   = [r for r in results if r['pred']=='up'   and r['actual_dir']=='up']
down_pred_correct = [r for r in results if r['pred']=='down' and r['actual_dir']=='down']
up_pred_total     = [r for r in results if r['pred']=='up'   and r['actual_dir']!='flat']
down_pred_total   = [r for r in results if r['pred']=='down' and r['actual_dir']!='flat']

print('='*60)
print('  開盤前預判訊號回測報告')
print('='*60)
print(f'回測區間：{results[0]["date"]} ～ {results[-1]["date"]}')
print(f'總交易日：{total} 天（非平盤 {len(non_flat)} 天）')
print()
print('【整體準確率（排除平盤日）】')
acc_all = len(correct_all) / len(non_flat) * 100 if non_flat else 0
print(f'  全部預判（含中性）：{len(correct_all)}/{len(non_flat)} = {acc_all:.1f}%')
print(f'  （中性算猜錯）')
print()
acc_nn = len(correct_nonneu) / max(1, sum(1 for r in non_neu if r['actual_dir']!='flat')) * 100
print(f'【排除中性後準確率（有方向的預判）】')
print(f'  有方向預判：{len(non_neu)} 天')
print(f'  其中猜對：{len(correct_nonneu)} 天 = {acc_nn:.1f}%')
print()
print('【強訊號準確率（|net| ≥ 3）】')
if strong:
    acc_s = len(strong_correct) / max(1, sum(1 for r in strong if r['actual_dir']!='flat')) * 100
    print(f'  強訊號天數：{len(strong)} 天')
    print(f'  其中猜對：{len(strong_correct)} 天 = {acc_s:.1f}%')
else:
    print('  （無強訊號資料）')
print()
print('【方向拆解】')
print(f'  預判「偏多」：{len(up_pred_total)} 天，猜對 {len(up_pred_correct)} 天 = '
      f'{len(up_pred_correct)/max(1,len(up_pred_total))*100:.1f}%')
print(f'  預判「偏空」：{len(down_pred_total)} 天，猜對 {len(down_pred_correct)} 天 = '
      f'{len(down_pred_correct)/max(1,len(down_pred_total))*100:.1f}%')
print(f'  預判「中性」：{len([r for r in results if r["pred"]=="neutral"])} 天')
print()
print('【訊號覆蓋率（哪些訊號有資料）】')
print(f'  TAIEX 技術訊號 (S1/S5/S6/S7/S8)：{total} 天')
print(f'  外資期貨 (S3)：{sum(1 for r in results if any("S3" in s for s in r["signals"]))} 天')
print(f'  市場融資 (S2)：{sum(1 for r in results if any("S2" in s for s in r["signals"]))} 天')
print(f'  T86現貨 (S4)：{sum(1 for r in results if any("S4" in s for s in r["signals"]))} 天')
print()
print('【逐日明細（最後20天）】')
print(f'{"日期":12} {"實際":>8} {"空":>4} {"多":>4} {"淨":>4} {"預判":>6} {"結果":>4}')
print('-'*55)
for r in results[-20:]:
    correct_mark = '✅' if r['pred']==r['actual_dir'] and r['actual_dir']!='flat' else (
                   '➖' if r['pred']=='neutral' or r['actual_dir']=='flat' else '❌')
    pred_label = {'up':'偏多','down':'偏空','neutral':'中性'}[r['pred']]
    print(f'{r["date"]:12} {r["actual_chg"]:+7.2f}%  {r["bear"]:3}  {r["bull"]:3}  {r["net"]:+4}  {pred_label:>4}  {correct_mark}')

print()
print('注意：外部市場（美股/ADR/VIX）因無法回測，不含在內。')
print('      T86 資料只有近期少量天數，主力訊號為 TAIEX 技術+期貨。')
