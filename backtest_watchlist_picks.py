#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_watchlist_picks.py — 「第一層」測試：加入自選股這個決定本身有沒有預測力

════════════════════════════════════════════════════════════════════════
背景／要驗證的問題（2026-10-06）
════════════════════════════════════════════════════════════════════════

使用者問「說要驗證選股能力，不是會在投資策略中看評分高的嗎？」——
那是**第二層**。這個系統其實是兩層漏斗：

  第一層：哪些股票進自選股（98 檔，從約 1,000 檔上市股裡挑）  ← 使用者   ❌ 從沒驗過
  第二層：對那些檔評分、挑 ≥ 門檻的                          ← 系統評分  ✅ 驗過，測不出

**要回答的問題：使用者決定「把某一檔放進自選股」這個動作，本身有沒有預測力？**

為什麼值得測：
  1. 這是系統裡唯一從未被驗證的環節。
  2. 2026-09-24 量到自選股 alpha +2.44% vs 全市場 -0.32%（差 2.76pp），
     **那個差距全部落在這一層**——但當時無法歸因，因為 87/87 檔都是
     回測期（2024-07 起）之後才加入的，是後見之明。
  3. **這次的樣本是乾淨的**：加入的決定在前、表現在後。
     這是本專案第一個沒有後見之明的測試。

事前預期（記下來供校準，專案慣例）：
  預期**測不出**（n=87、窗口 40~107 日、雜訊帶會很寬）；
  方向偏**略正**（加入清單通常是注意到開始轉強，可能吃到動能延續），
  但也可能略負（追高）。

════════════════════════════════════════════════════════════════════════
三個必要的對照（少任何一個結論都不成立）
════════════════════════════════════════════════════════════════════════

① **主要對照 ＝ 同期 513 檔等權，不是大盤。**
   2026-09-24 已證明等權 vs 市值加權在前段差 39pp（漲幅集中在台積電）。
   持少數檔等權的人，對手本來就是「平均一檔股票」，
   拿市值加權指數比 ＝ 自動判輸。市值加權只列出來當參考。

② **雜訊帶：從 513 檔宇宙隨機抽同樣檔數，而且用同一組「加入日期」。**
   ⚠️ 日期分布必須保持一致——否則會把「某幾個月市場剛好比較好」
   算成選股能力。做法：保留每一檔的 base_date，只把「哪一檔」隨機換掉。

③ **公司行為守衛**（陷阱49）。這裡算的是跨越數月的累積報酬，
   正是 0050 那個 1:4 分割出事的場景。相鄰交易日比值在 [0.65,1.5] 之外
   就把當日報酬視為 0。

════════════════════════════════════════════════════════════════════════
時點約定（會影響結論，必須寫清楚）
════════════════════════════════════════════════════════════════════════

`added_at` 帶時間，實測多為盤後（例如 '2026-05-24 20:32'）。
⇒ 當天收盤已經過去，**最早能動作的是下一個交易日**。
   所以 base_date = added_at 日期之後的**第一個交易日**，報酬自該日收盤起算。
   這與策略本身的「D 日決策 → D+1 進場」一致。

另外附一組 base = added_at 當日收盤（若當天是交易日）的結果，
看「隔日跳空」有沒有吃掉差異。

════════════════════════════════════════════════════════════════════════
已知限制（引用結果時必須一起講）
════════════════════════════════════════════════════════════════════════
1. n=87，而且各檔窗口不等長（40~107 個交易日）。
2. 樣本仍全在多頭（2026-05~10 指數上漲）。
3. `added_at` 未必等於「決定要買」——可能只是隨手加進觀察名單。
   這會讓測試偏向保守（把不打算買的也算進去）。
4. 自選股含 17 檔上櫃，而 513 檔宇宙只有上市（T86 不含上櫃）。
   ⇒ 另外跑一組「只算上市」與基準同宇宙，兩組並列。

用法：
    python3 backtest_watchlist_picks.py
"""

import sqlite3
import random
import sys
from datetime import datetime

DB = 'data/stock.db'

MIN_DAYS = 20          # 加入日之後至少要有這麼多交易日才納入
BOOT_N   = 800         # 雜訊帶重抽次數

# 宇宙定義：與 backtest_portfolio_slots.market_universe() 完全一致
UNI_MIN_TURNOVER = 5e7
UNI_SINCE        = '2025-09-01'
UNI_MIN_DAYS     = 180

# 公司行為守衛（陷阱49）
SPLIT_LO, SPLIT_HI = 0.65, 1.5


def conn():
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


def market_universe(c):
    mk = dict(c.execute('SELECT code, market FROM stocks').fetchall())
    rows = c.execute(
        'SELECT code, AVG(value) av, COUNT(*) n FROM prices '
        'WHERE date>=? AND code!=? GROUP BY code HAVING n>=?',
        (UNI_SINCE, 'TAIEX', UNI_MIN_DAYS)).fetchall()
    return sorted(r[0] for r in rows
                  if r[1] and r[1] >= UNI_MIN_TURNOVER
                  and mk.get(r[0]) == 'TWSE'
                  and len(r[0]) == 4 and r[0].isdigit()
                  and not r[0].startswith('00'))


def level_series(px, cal):
    """
    把收盤價轉成「公司行為還原後的淨值序列」，之後任兩天的報酬 = lvl[b]/lvl[a]-1。

    ⚠️ 陷阱49：DB 存未調整收盤價。相鄰交易日比值超出 [0.65,1.5] 判定為
       分割/減資等公司行為（台股 ±10%，跨一個缺口日也到不了），
       該日報酬視為 0——保守選擇：寧可少算一天真實漲跌，
       也不要留一個 -75% 的假崩盤。
    """
    lvl, out, prev = 1.0, {}, None
    for d in cal:
        p = px.get(d)
        if p is None:
            out[d] = lvl          # 缺值沿用（停止交易期間等）
            continue
        if prev is not None:
            r = p / prev
            if SPLIT_LO <= r <= SPLIT_HI:
                lvl *= r
        out[d] = lvl
        prev = p
    return out


def eqw_level(uni_lvls, cal):
    """513 檔等權、每日再平衡的指數淨值序列 ＝『隨便挑一檔』的基準。"""
    lvl, out = 1.0, {cal[0]: 1.0}
    for i in range(1, len(cal)):
        d0, d1 = cal[i - 1], cal[i]
        rs = []
        for L in uni_lvls.values():
            a, b = L.get(d0), L.get(d1)
            if a and b and a > 0:
                rs.append(b / a - 1)
        if rs:
            lvl *= 1 + sum(rs) / len(rs)
        out[d1] = lvl
    return out


def main():
    c = conn()
    cal = [r[0] for r in c.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>='2026-01-01' ORDER BY date")]
    last = cal[-1]
    ci = {d: i for i, d in enumerate(cal)}

    uni = market_universe(c)
    print(f'資料庫：{DB}')
    print(f'宇宙：{len(uni)} 檔上市普通股（日均成交 ≥ {UNI_MIN_TURNOVER/1e8:.1f} 億）')
    print(f'期間：{cal[0]} ~ {last}（{len(cal)} 個交易日）')

    # ── 價格 → 還原淨值 ──
    def load(codes):
        out = {}
        for code in codes:
            px = {r[0]: r[1] for r in c.execute(
                'SELECT date, close FROM prices WHERE code=? AND date>=?',
                (code, cal[0])) if r[1]}
            if px:
                out[code] = level_series(px, cal)
        return out

    uni_lvls = load(uni)
    eqw = eqw_level(uni_lvls, cal)
    tpx = level_series({r[0]: r[1] for r in c.execute(
        "SELECT date, close FROM prices WHERE code='TAIEX' AND date>=?", (cal[0],))}, cal)

    # ── 自選股與各自的 base_date ──
    wl = c.execute('SELECT code, name, substr(added_at,1,10) FROM watchlist').fetchall()
    mk = dict(c.execute('SELECT code, market FROM stocks').fetchall())

    picks, skipped = [], []
    for code, name, ad in wl:
        # base = added_at 之後的第一個交易日（盤後決定 → 最早隔日才能動作）
        nxt = next((d for d in cal if d > ad), None)
        same = ad if ad in ci else None
        if nxt is None or (len(cal) - ci[nxt]) < MIN_DAYS:
            skipped.append((code, name, ad))
            continue
        picks.append({'code': code, 'name': name, 'added': ad,
                      'base': nxt, 'same': same, 'mkt': mk.get(code, '?')})

    wl_lvls = load([p['code'] for p in picks])
    picks = [p for p in picks if p['code'] in wl_lvls]

    print(f'自選股：{len(wl)} 檔　→ 可用 {len(picks)} 檔'
          f'（排除 {len(skipped)} 檔：加入後不足 {MIN_DAYS} 個交易日）')
    print()

    def ret(lvls, code, b, e=last):
        L = lvls[code]
        a, z = L.get(b), L.get(e)
        return (z / a - 1) * 100 if a and z and a > 0 else None

    # ── 逐檔計算 ──
    for p in picks:
        p['ret'] = ret(wl_lvls, p['code'], p['base'])
        p['bench'] = (eqw[last] / eqw[p['base']] - 1) * 100
        p['tpx'] = (tpx[last] / tpx[p['base']] - 1) * 100
        p['alpha'] = None if p['ret'] is None else p['ret'] - p['bench']
        p['days'] = len(cal) - ci[p['base']] - 1
    picks = [p for p in picks if p['alpha'] is not None]

    def summary(sub, label):
        if not sub:
            return None
        n = len(sub)
        r = sum(x['ret'] for x in sub) / n
        b = sum(x['bench'] for x in sub) / n
        t = sum(x['tpx'] for x in sub) / n
        a = sum(x['alpha'] for x in sub) / n
        win = sum(1 for x in sub if x['alpha'] > 0) / n * 100
        print(f'{label:<26}{n:>5}{r:>+10.2f}%{b:>+10.2f}%{t:>+10.2f}%'
              f'{a:>+11.2f}%{win:>8.0f}%')
        return a

    def shape(sub, label):
        """
        ⚠️ 只看平均會漏掉最關鍵的結構：個股報酬是**右偏**的，
           少數大贏家撐起整個平均。所以必須同時看中位數、勝率、
           以及「拿掉最強幾檔之後還剩什麼」。
           （這三個都要有隨機對照才能解讀——見下方雜訊帶。）
        """
        al = sorted(x['alpha'] for x in sub)
        n = len(al)
        med = al[n // 2] if n % 2 else (al[n // 2 - 1] + al[n // 2]) / 2
        win = sum(1 for x in al if x > 0) / n * 100
        trim = sum(al[:-5]) / (n - 5) if n > 5 else float('nan')
        print(f'{label:<26}{n:>5}{sum(al)/n:>+11.2f}%{med:>+11.2f}%'
              f'{win:>8.0f}%{trim:>+13.2f}%')

    hdr = (f'{"":<26}{"檔數":>5}{"平均報酬":>10}{"★等權基準":>10}'
           f'{"加權指數":>10}{"vs等權":>11}{"勝率":>8}')
    print('=' * 92)
    print('【加入自選股之後的表現】　報酬自「加入日之後第一個交易日」收盤起算')
    print('=' * 92)
    print(hdr)
    print('-' * 92)
    a_all = summary(picks, '全部')
    a_twse = summary([p for p in picks if p['mkt'] == 'TWSE'], '　└ 只算上市（與基準同宇宙）')
    summary([p for p in picks if p['mkt'] == 'TPEx'], '　└ 只算上櫃（基準不含）')
    print()
    print('分布形狀（平均會騙人——個股報酬右偏，少數大贏家撐起全部）：')
    print(f'{"":<26}{"檔數":>5}{"平均vs等權":>11}{"★中位數":>11}{"勝率":>8}{"拿掉最強5檔":>13}')
    print('-' * 92)
    shape(picks, '全部')
    shape([p for p in picks if p['mkt'] == 'TWSE'], '　└ 只算上市')
    shape([p for p in picks if p['mkt'] == 'TPEx'], '　└ 只算上櫃')

    print()
    print('依加入月份：')
    print(hdr)
    print('-' * 92)
    for m in sorted({p['added'][:7] for p in picks}):
        summary([p for p in picks if p['added'][:7] == m], f'　{m}')

    # ── 雜訊帶：同一組 base_date，隨機換「哪一檔」 ──
    print()
    print('=' * 92)
    print(f'【雜訊帶】從 {len(uni)} 檔宇宙隨機抽，**保留同一組加入日期**，重抽 {BOOT_N} 次')
    print('=' * 92)
    print('⚠️ 日期分布必須一致，否則會把「某幾個月市場剛好比較好」算成選股能力')

    pool = [code for code in uni if code in uni_lvls]
    for label, sub in [('全部 87 檔', picks),
                       ('只算上市', [p for p in picks if p['mkt'] == 'TWSE'])]:
        if not sub:
            continue
        bases = [p['base'] for p in sub]
        rnd = random.Random(20261006)
        # ⚠️ 三個指標都要對照。只對照平均，會把「勝率只有 36%」
        #    誤讀成使用者的問題——實際上隨機抽也是 28~45%，
        #    那是**股市本身的右偏特性**（個股中位數 < 平均），不是選股的特徵。
        d_mean, d_med, d_win = [], [], []
        for _ in range(BOOT_N):
            al = []
            for b in bases:
                r = ret(uni_lvls, rnd.choice(pool), b)
                al.append(0.0 if r is None else r - (eqw[last] / eqw[b] - 1) * 100)
            al.sort()
            n2 = len(al)
            d_mean.append(sum(al) / n2)
            d_med.append(al[n2 // 2] if n2 % 2 else (al[n2 // 2 - 1] + al[n2 // 2]) / 2)
            d_win.append(sum(1 for x in al if x > 0) / n2 * 100)

        act = sorted(x['alpha'] for x in sub)
        n1 = len(act)
        a_mean = sum(act) / n1
        a_med = act[n1 // 2] if n1 % 2 else (act[n1 // 2 - 1] + act[n1 // 2]) / 2
        a_win = sum(1 for x in act if x > 0) / n1 * 100

        print()
        print(f'  ◆ {label}（n={n1}）')
        verdicts = []
        for nm, draws, a, fmt in [('平均', d_mean, a_mean, '%'),
                                  ('中位數', d_med, a_med, '%'),
                                  ('勝率', d_win, a_win, '%')]:
            draws.sort()
            lo, hi = draws[int(BOOT_N * .05)], draws[int(BOOT_N * .95)]
            if a > hi:
                v = '★ 超出帶外（正）'
            elif a < lo:
                v = '★ 超出帶外（負）'
            else:
                v = '⚪ 帶內'
            verdicts.append(v)
            print(f'    {nm:<4} 隨機 5~95%: {lo:>+7.2f}{fmt} ~ {hi:>+7.2f}{fmt}'
                  f'　你的 {a:>+7.2f}{fmt}　{v}')
        if all(v.startswith('⚪') for v in verdicts):
            print('    ⇒ **三個角度全部測不出**（不等於沒價值，是這個樣本量看不見）')

    # ── 隔日跳空的影響 ──
    same = [p for p in picks if p['same']]
    if same:
        d1 = sum(p['alpha'] for p in same) / len(same)
        d0 = 0.0
        for p in same:
            r = ret(wl_lvls, p['code'], p['same'])
            d0 += (r - (eqw[last] / eqw[p['same']] - 1) * 100) if r is not None else 0
        d0 /= len(same)
        print()
        print('=' * 92)
        print(f'【時點敏感度】{len(same)} 檔的 added_at 當天是交易日')
        print('=' * 92)
        print(f'  base = 加入日當天收盤（不可能買到，僅供對照）：vs等權 {d0:+.2f}%')
        print(f'  base = 下一個交易日收盤（本報告採用）　　　　：vs等權 {d1:+.2f}%')
        print(f'  → 隔日跳空吃掉 {d0-d1:+.2f}pp')

    # ── 最好/最差 ──
    print()
    print('=' * 92)
    print('【個別明細】vs 等權基準，前 8 / 後 8')
    print('=' * 92)
    s = sorted(picks, key=lambda x: -x['alpha'])
    for tag, rows in [('🔝 最好', s[:8]), ('🔻 最差', s[-8:])]:
        print(f'  {tag}')
        for p in rows:
            print(f'    {p["code"]:<6}{p["name"]:<8}加入 {p["added"]}　'
                  f'{p["days"]:>3}日　報酬 {p["ret"]:>+8.2f}%　'
                  f'基準 {p["bench"]:>+7.2f}%　vs {p["alpha"]:>+8.2f}%')

    print()
    print('※ 主要對照是**等權基準**（隨便挑一檔），不是加權指數——')
    print('   持少數檔等權的人，對手本來就是「平均一檔股票」（2026-09-24 已驗證差 39pp）。')
    print('※ 限制：n 偏小、各檔窗口不等長、樣本全在多頭；')
    print('   `added_at` 未必等於「決定要買」（可能只是隨手加觀察），此偏誤方向保守。')
    print('※ 已套用公司行為守衛（陷阱49）：相鄰日比值在 [0.65,1.5] 之外的當日報酬視為 0。')


if __name__ == '__main__':
    main()
