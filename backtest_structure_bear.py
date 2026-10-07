#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_structure_bear.py — 「回檔小」這項優勢，在真正的空頭年還成立嗎？

════════════════════════════════════════════════════════════════════════
要驗證的問題（2026-10-07）
════════════════════════════════════════════════════════════════════════

**「10% 停損 ＋ 10 日持有週期 ＋ 5 檔上限」這組結構，
  在真正的空頭年能不能壓低最大回檔？而且是哪一個要素在作用？**

為什麼這一題優先於月營收：

  2026-10-05 的資金曲線比較量到，**「回檔小」是整個系統目前唯一站得住腳的性質**：

  | 2026-05 起（107 天） | 報酬 | 最大回檔 |
  |---|---|---|
  | 策略 5檔（評分） | +29.80% | **-9.59%** |
  | 策略 5檔（代號） | +13.83% | **-9.27%** ← 報酬一半，回檔一樣小 |
  | 買進持有 0050 | +28.12% | -15.88% |

  **「代號」那條是決定性證據：回檔小來自結構，不是選股。**

  但當時明文寫著「⚠️ 該優勢目前是推論，不是實測」——因為
  **樣本期間（2024-07~2026-10）指數 +124%，完全沒有空頭**。
  而「回檔小」真正重要的時候正是空頭。

  2026-10-06/07 回填 2018 起的歷史之後，第一次有：
      2018  年報酬 -9.2%   最大回檔 -15.8%
      2020  年報酬 +21.8%  最大回檔 -28.7%（COVID，V 轉）
      2022  年報酬 -22.6%  最大回檔 -31.6%（完整空頭年）

════════════════════════════════════════════════════════════════════════
⚠️ 為什麼刻意**不用評分**（這不是偷懶，是必要的）
════════════════════════════════════════════════════════════════════════

實查 2018~2024 的資料涵蓋：

    prices                 ✅ 完整（每年 239~246 交易日）
    chips                  ❌ 0 天
    fundamentals           ❌ 0 天（全部從 2026-05）
    market_margin          ❌ 0 天（2026-05 才有）
    futures_institutional  ❌ 0 天（2026-03 才有）

⇒ **個股評分在那段會退化成 `0.40×技術面 + 30`**
  （要達總分 65 需技術面 ≥87.5——9/17「回測期一半以上只有技術面」那個問題的極端版）
⇒ **大盤評分 S1–S8 的 S3／S4／S10 全缺，階梯根本算不出來**

所以任何依賴評分的 2018 回測都會是假的。
**而這一題本來就不該用評分**——10/05 的「代號」對照已經證明回檔小不依賴選股。
測結構本身就好，而結構只需要價格。

════════════════════════════════════════════════════════════════════════
🚨 第一版（2026-10-07 上午）兩個錯誤，已修正——記錄下來因為第一個很危險
════════════════════════════════════════════════════════════════════════

**錯誤一：核心表的符號標籤寫反了，會讓結論完全顛倒。**

原本寫「負值 = 回檔更小（更好）」，但**回檔本身是負數**：

    2022:  (a) 買進持有 -28.15%    (d) 兩者 -39.07%
           d − base = -39.07 − (-28.15) = **-10.9pp**

那個 -10.9pp 代表「(d) 的回檔比 (a) **深了** 10.9pp」＝**更糟**，不是更好。

⇒ 已改為顯示 `|回檔| 的差`（**正值 = 更深 = 更糟**）並加 ✅/❌ 標記，
  不再讓讀者自己推符號。
⇒ **通則：呈現「差異」時，若原始量本身帶符號，一定要改成絕對值差或直接標 ✅/❌。**
  這與陷阱30（相對日期用字寫死）同一族——**都是顯示層的語意錯誤，數字算對了但讀出來是反的。**

**錯誤二：把 (d) 標成「＝現行結構」，但它漏了兩個要素。**

| 現行策略（策略C） | 第一版的 (d) |
|---|---|
| 到期時評分 ≥65 **就續抱**（不換股） | ❌ **無條件**每 10 日換掉 |
| 評分門檻 + 大盤階梯 ⇒ 有時**空手** | ❌ 永遠滿倉 96% |

證據：**換手 1,103 次**（8 年 2,127 日 ÷ 10 日 × 5 檔 ≈ 1,060）。實際策略因續抱遠低於此。

⇒ (d) 改名「無條件換倉＋停損（⚠️ 不是現行策略）」，
  並**新增 (e)(f)：到期時若仍獲利就續抱**（純價格、不需評分的續抱代理）。

════════════════════════════════════════════════════════════════════════
🚨 第二版的結果推翻了原本的預期——所以有第三版（2026-10-07 下午）
════════════════════════════════════════════════════════════════════════

第二版（六組）量到兩件事：

**① 續抱的價值巨大，而且是算術不是統計：**

    (d) 無條件換倉+停損   換手 1,103 次   純成本拖累 -64.7%   全期 -36.62%
    (e) 續抱代理+停損     換手    64 次   純成本拖累  -5.9%   全期 +50.36%

**② 但「回檔小」在真正的空頭年失效：**

    (e) 在 9 年裡有 7 年回檔比買進持有淺 —— 但失手的兩年正好是
    **2018（❌+2.9pp）與 2022（❌+1.3pp），也就是唯二的負報酬空頭年**。
    2020 有保護（✅-5.0pp），但那是 **V 轉**：停損出場後市場很快回升。

**③ 而第二版有一個致命的設定限制，它就是 ② 的直接原因：**

    六組**全部永遠滿倉（在場內 96%）**——一有空位就立刻從宇宙補滿。
    ⇒ 持續下跌中：停損出場 → 立刻補滿 → 再被停損 → **反覆被巴**。
    ⇒ 在這個設定下，空頭沒有保護是**必然的**，不是實測結果。

    而**現行策略在大盤評分 `<45` 時會停止進場**——那正是唯一能產生
    「空手」的機制，也正是 2018~2024 算不出來的部分（S3/S4/S10 全缺）。

⇒ **第三版加入「純價格的空手代理」：指數跌破 MA60 就不補新倉。**
  MA60 只需要 TAIEX 收盤 ⇒ 2018 起完全算得出來。

**順便一次回答懸了很久的 C vs D。** 十五章記著「策略D 在多頭是錯殺、
在空頭是保命」，但**空頭證據只有 2026-07 那兩週一個樣本**，而 2026-08 那次
重跑還確認「那週根本不是大盤轉空」⇒ 那個條件從來沒被滿足過。
現在用 2018／2022 兩個真空頭年測：

    'block' = 不補新倉，已持有的照既有規則管理  ⇒ **策略C 的空手代理**
    'exit'  = 不補新倉**且立即出清全部部位**     ⇒ **策略D 的代理**

**MA 長度加測 MA20 當 robustness**——照本專案的規矩，選一個參數就要確認
結論不是靠那個特定數字撐起來的（停損校準那節立的對照原則）。

════════════════════════════════════════════════════════════════════════
設計：九組共用同一個進場邏輯，只差三個維度
════════════════════════════════════════════════════════════════════════

|                                    | 到期規則 | 停損 | 大盤空手 |
|------------------------------------|---------|-----|---------|
| (a) 買進持有 5 檔                   | 無       | ❌  | —       |
| (b) 無條件 10 日換倉                | 無條件   | ❌  | —       |
| (c) 只有 10% 停損                   | 無       | ✅  | —       |
| (d) 無條件換倉＋停損 ⚠️不是現行策略   | 無條件   | ✅  | —       |
| **(e) 續抱代理＋停損**              | **獲利就續抱、虧損才換** | ✅ | — |
| (f) 續抱代理、無停損                | 同上     | ❌  | —       |
| **(g) (e)＋MA60 不補新倉**          | 同上     | ✅  | **block（≈策略C）** |
| **(h) (e)＋MA60 出清**              | 同上     | ✅  | **exit（≈策略D）**  |
| (i) (e)＋MA20 不補新倉（robustness） | 同上     | ✅  | block（MA20）|

**只差這三個維度 ⇒ 差異可以乾淨歸因。** 五組關鍵對照：
  • (c) vs (a) → **停損**單獨的效果
  • (b) vs (a) → **無條件換倉**單獨的效果
  • (e) vs (d) → **「續抱」值多少**（第二版的核心問題，已答：巨大）
  • **(g) vs (e) → 「空手」值多少**（第三版的核心問題）
  • **(h) vs (g) → 空頭時該出清還是只停買**（＝策略D vs 策略C）

**為什麼要測續抱：** 第一版量到 (b)/(d) 八年虧 37~50%，而交易成本只解釋
其中 −64.6%（1,103 次 × 0.094%／次），**剩下的差額來自「系統性砍掉正在漲的那幾檔」**。
而 2026-10-07 同日量到：**87 檔自選股裡 5 檔（6%）決定了整體結果**。
⇒ 在報酬極度集中的市場裡，無條件輪動是結構性的破壞，
  而**續抱正是在修這件事**——它可能不是錦上添花，是讓這個結構不致毀滅的關鍵。

**排序鍵用真隨機、跑 `N_SEED` 條取 5~95% 分位。**
2026-10-05 的兩個教訓：
  • 一條資金曲線只是一個樣本（實測帶寬 20~143pp）
  • **「依股票代號」不是中性對照**——槽位競爭下它會持續把槽位給小代號股票，
    而台股 1xxx 是水泥食品塑膠紡織、28xx 金融 ⇒ 偷偷變成「偏重傳產」的策略

**point-in-time 宇宙**（每月重算，只用 t 之前的資訊）——2026-09-24 的教訓：
回測宇宙的組成時間必須早於回測期間的起點。

**公司行為守衛（陷阱49）：** 相鄰交易日比值在 [0.7,1.3] 之外者，
該日報酬視為 0%、且不觸發停損——不讓假崩盤穿過去造成假停損。

════════════════════════════════════════════════════════════════════════
⚠️ 限制（引用結果時必須一起講）
════════════════════════════════════════════════════════════════════════

1. **除權息無法調整**（陷阱50：`exdividend` 只有 2026 年、DB 存未調整收盤價）。
   除息造成的下跌會進入所有策略的回檔計算，**程度相似**
   ⇒ 對「回檔比較」影響較小，但會讓**所有**策略的報酬被系統性低估。
   買進持有被低估得最多（持有期最長）。
2. 這裡測的是**結構**，不是現行完整策略（後者還有大盤階梯與評分門檻，
   而那兩者在 2018~2024 算不出來）。
3. 只有上市普通股、日均成交 ≥0.5 億。
4. 滿倉 5 檔等權、每日再平衡、現金不計息；成本買 0.0855%／賣 0.3855%。

用法：
    python3 backtest_structure_bear.py
    python3 backtest_structure_bear.py 8        # 指定隨機條數（預設 20）
"""

import sqlite3
import statistics as st
import sys
from array import array
from collections import defaultdict
from math import isnan, nan

DB = 'data/stock.db'
START = '2018-01-01'

SLOTS      = 5          # 同時持股上限
HOLD_DAYS  = 10         # 持有週期（交易日）
STOP_RATIO = 0.90       # 10% 停損
N_SEED     = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 20

# 成本（與 config.py / backtest_vs_etf.py 一致）
C_BUY  = 0.001425 * 0.6                 # 0.0855%
C_SELL = 0.001425 * 0.6 + 0.003         # 0.3855%

# point-in-time 宇宙
PIT_LOOKBACK = 130
PIT_MIN_DAYS = 60
PIT_MIN_TURNOVER = 5e7

CA_LO, CA_HI = 0.7, 1.3                 # 公司行為守衛（陷阱49）

BEAR_YEARS = (2018, 2020, 2022)


def main():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    cal = [r[0] for r in c.execute(
        "SELECT date FROM prices WHERE code='TAIEX' AND date>=? ORDER BY date", (START,))]
    ci = {d: i for i, d in enumerate(cal)}
    n = len(cal)
    print(f'結構測試（不依賴評分——2018~2024 只有價格，見檔頭說明）')
    print(f'期間 {cal[0]} ~ {cal[-1]}　{n} 個交易日')

    mk = dict(c.execute('SELECT code,market FROM stocks').fetchall())

    # ── 大盤空手濾網（第三版新增）────────────────────────────────
    # 純價格：指數收盤 ≥ MAn 才允許補新倉。只需要 TAIEX close ⇒ 2018 起算得出來。
    # 這是「大盤評分 <45 停止進場」的代理——那條規則需要 S3/S4/S10，2018~2024 全缺。
    # ⚠️ 用「當日收盤後」的 MA 決定「當日收盤進場」：這是 look-ahead-free 的，
    #    因為收盤價在收盤時已知，而進場執行在收盤（與其餘各組一致）。
    tpx_close = [nan] * n
    for d, cl in c.execute(
            "SELECT date,close FROM prices WHERE code='TAIEX' AND date>=? AND close>0",
            (START,)):
        if d in ci:
            tpx_close[ci[d]] = cl

    def ma_ok_series(win):
        """ok[i] = 第 i 個交易日允許補新倉。資料不足（前 win 日）一律允許。"""
        ok = [True] * n
        for i in range(n):
            if i < win - 1:
                continue
            seg = [v for v in tpx_close[i - win + 1:i + 1] if not isnan(v)]
            if len(seg) < win * 0.8 or isnan(tpx_close[i]):
                continue
            ok[i] = tpx_close[i] >= sum(seg) / len(seg)
        return ok

    MA_OK = {60: ma_ok_series(60), 20: ma_ok_series(20)}
    for w, s in MA_OK.items():
        print(f'  MA{w} 濾網：允許進場 {sum(s)/n*100:.0f}% 的交易日'
              f'（空手期 {n - sum(s)} 天）')

    # ── 載入價格（array('d') + nan，1.9M 筆約 15MB）──
    print('載入全市場價格…', end='', flush=True)
    close, low = {}, {}
    for code, d, cl, lo in c.execute(
            'SELECT code,date,close,low FROM prices WHERE code!=? AND date>=? AND close>0',
            ('TAIEX', START)):
        i = ci.get(d)
        if i is None:
            continue
        if code not in close:
            close[code] = array('d', [nan]) * n
            low[code] = array('d', [nan]) * n
        close[code][i] = cl
        low[code][i] = lo if lo and lo > 0 else cl
    print(f' {len(close)} 檔')

    # ── 公司行為（陷阱49）──
    ca = defaultdict(set)
    for code, arr in close.items():
        prev_i = None
        for i in range(n):
            if isnan(arr[i]):
                continue
            if prev_i is not None and i - prev_i <= 2:
                r = arr[i] / arr[prev_i]
                if r < CA_LO or r > CA_HI:
                    ca[code].add(i)
            prev_i = i
    print(f'公司行為事件 {sum(len(v) for v in ca.values())} 個 / {len(ca)} 檔')

    # ── point-in-time 宇宙：每月第一個交易日重算 ──
    print('計算 point-in-time 宇宙…', end='', flush=True)
    uni_at = [None] * n       # 每個交易日對應的宇宙（list）
    cur = None
    for i, d in enumerate(cal):
        if i == 0 or d[:7] != cal[i - 1][:7]:        # 換月
            lo_d = cal[max(0, i - PIT_LOOKBACK)]
            rows = c.execute(
                'SELECT code,COUNT(*) k,AVG(value) av FROM prices '
                'WHERE date>=? AND date<? AND code!=? GROUP BY code HAVING k>=? AND av>=?',
                (lo_d, d, 'TAIEX', PIT_MIN_DAYS, PIT_MIN_TURNOVER)).fetchall()
            cur = sorted(r[0] for r in rows
                         if r[0] in close and mk.get(r[0]) == 'TWSE'
                         and len(r[0]) == 4 and r[0].isdigit()
                         and not r[0].startswith('00'))
        uni_at[i] = cur
    print(f' 平均 {st.mean([len(u) for u in uni_at]):.0f} 檔/月')

    # ── TAIEX / 0050 基準 ──
    def bench_curve(code, pay_fee=True):
        arr = {}
        for d, cl in c.execute(
                'SELECT date,close FROM prices WHERE code=? AND date>=? AND close>0',
                (code, START)):
            if d in ci:
                arr[ci[d]] = cl
        ks = sorted(arr)
        if not ks:
            return None
        cur_lv = 1.0 - (C_BUY if pay_fee else 0)
        out = [1.0] + [nan] * n
        prev = None
        for i in range(n):
            if i in arr:
                if prev is not None:
                    r = arr[i] / arr[prev]
                    if CA_LO <= r <= CA_HI:      # 公司行為就跳過（陷阱49）
                        cur_lv *= r
                prev = i
            out[i + 1] = cur_lv
        return out

    # ══════════════════════════════════════════════════════════
    def simulate(seed, expiry_mode, use_stop, mkt=None):
        """
        回傳 (淨值曲線 len=n+1, 在場內比例, 換手次數)

        九組共用這個進場邏輯，只差 expiry_mode / use_stop / mkt ⇒ 差異可乾淨歸因。

        mkt: None               不看大盤，永遠補滿（第二版的行為）
             ('block', win)     指數 < MAwin 時不補新倉，已持有的照既有規則管理
                                ⇒ **策略C 的空手代理**（C 明文「不因大盤轉弱出場」）
             ('exit',  win)     指數 < MAwin 時不補新倉**且立即出清全部部位**
                                ⇒ **策略D 的代理**

        expiry_mode:
          'none'  不因到期出場
          'all'   滿 HOLD_DAYS 無條件換股
          'hold'  ★ 滿 HOLD_DAYS 時「仍獲利就續抱、虧損才換」
                  —— 純價格的續抱代理（現行策略是「評分 ≥65 就續抱」，
                     但 2018~2024 算不出評分，見檔頭）
                  續抱時**只重設計時起點，不動 entry_px 與 stop**
                  —— 與實際的 renew_position() 一致（陷阱47：entry_price 從不隨續抱改變）
        """
        import random
        rnd = random.Random(seed)
        pref = {}                      # 每檔一個固定隨機偏好（與「代號」同性質但無產業結構）

        eq = [1.0] + [nan] * n
        lv = 1.0
        held = {}                      # code → {'entry_i','entry_px','stop'}
        invested_days = 0.0
        turns = 0

        for i in range(n):
            # ① 當日報酬（前一交易日 → 今日），只對已持有的部位
            if i > 0 and held:
                rs = []
                for code, p in list(held.items()):
                    a, b = close[code][i - 1], close[code][i]
                    if isnan(a) or isnan(b):
                        rs.append(0.0)
                        continue
                    if i in ca[code]:            # 公司行為日：報酬視為 0（陷阱49）
                        rs.append(0.0)
                        continue
                    rs.append(b / a - 1)
                # 空格是現金、報酬 0
                lv *= 1 + sum(rs) / SLOTS
            invested_days += len(held) / SLOTS

            mkt_ok = True if mkt is None else MA_OK[mkt[1]][i]

            # ②a 策略D 代理：大盤轉空就出清（在個股規則之前）
            if mkt is not None and mkt[0] == 'exit' and not mkt_ok and held:
                for code in list(held):
                    lv *= 1 - C_SELL / SLOTS
                    del held[code]
                    turns += 1

            # ② 出場判定（當日收盤後）
            for code, p in list(held.items()):
                px = close[code][i]
                if isnan(px):
                    continue
                hit_stop = (use_stop and i not in ca[code]
                            and low[code][i] <= p['stop'])
                due = (expiry_mode != 'none'
                       and (i - p['entry_i']) >= HOLD_DAYS)
                expired = False
                if due:
                    if expiry_mode == 'all':
                        expired = True
                    else:                        # 'hold'：仍獲利就續抱
                        if px > p['entry_px']:
                            p['entry_i'] = i     # 只重設計時，不動 entry_px / stop
                        else:
                            expired = True
                if hit_stop or expired:
                    # 停損以停損價計（而非收盤），其餘以收盤
                    exit_px = p['stop'] if hit_stop else px
                    # 已在 ① 以收盤計入，停損差額另外調整
                    if hit_stop and px > 0:
                        lv *= 1 + (exit_px / px - 1) / SLOTS
                    lv *= 1 - C_SELL / SLOTS
                    del held[code]
                    turns += 1

            # ③ 進場：有空位就從宇宙按隨機偏好挑
            if len(held) < SLOTS and i < n - 1 and mkt_ok:
                uni = uni_at[i]
                for code in uni:
                    if code not in pref:
                        pref[code] = rnd.random()
                cand = sorted((code for code in uni
                               if code not in held and not isnan(close[code][i])),
                              key=lambda x: pref[x])
                for code in cand:
                    if len(held) >= SLOTS:
                        break
                    px = close[code][i]
                    held[code] = {'entry_i': i, 'entry_px': px,
                                  'stop': px * STOP_RATIO}
                    lv *= 1 - C_BUY / SLOTS
            eq[i + 1] = lv
        return eq, invested_days / n * 100, turns

    # ══════════════════════════════════════════════════════════
    def metrics(eq, i0, i1):
        """i0..i1 為 cal 的索引區間（含）。eq[k] = cal[k-1] 收盤後。"""
        s = eq[i0:i1 + 2]
        s = [x for x in s if not isnan(x)]
        if len(s) < 3:
            return None
        ret = (s[-1] / s[0] - 1) * 100
        peak = s[0]
        dd = 0.0
        for v in s:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
        rets = [s[k] / s[k - 1] - 1 for k in range(1, len(s)) if s[k - 1]]
        vol = st.stdev(rets) * 100 if len(rets) > 2 else 0
        return {'ret': ret, 'mdd': dd * 100, 'vol': vol}

    PERIODS = [('全期間 2018-2026', 2018, 2026)]
    for y in range(2018, 2027):
        PERIODS.append((f'{y}' + ('　★ 空頭' if y in BEAR_YEARS else ''), y, y))

    def idx_range(y0, y1):
        a = next((i for i, d in enumerate(cal) if d >= f'{y0}-01-01'), 0)
        b = next((i - 1 for i, d in enumerate(cal) if d > f'{y1}-12-31'), n - 1)
        return a, b

    RULES = [
        ('(a) 買進持有 5 檔',          'none', False, None),
        ('(b) 無條件10日換倉',          'all',  False, None),
        ('(c) 只有 10% 停損',          'none', True,  None),
        ('(d) 無條件換倉+停損 ⚠️非現行', 'all',  True,  None),
        ('(e) ★續抱代理+停損',          'hold', True,  None),
        ('(f) 續抱代理、無停損',         'hold', False, None),
        ('(g) ★(e)+MA60停買 ≈策略C',    'hold', True,  ('block', 60)),
        ('(h) ★(e)+MA60出清 ≈策略D',    'hold', True,  ('exit',  60)),
        ('(i) (e)+MA20停買 robustness', 'hold', True,  ('block', 20)),
    ]
    MAIN = '(e) ★續抱代理+停損'

    print(f'\n跑 {N_SEED} 條隨機排序 × {len(RULES)} 組規則…', end='', flush=True)
    runs = {}
    for label, ue, us, mk_ in RULES:
        runs[label] = [simulate(sd, ue, us, mk_) for sd in range(N_SEED)]
        print(f' {label[:3]}', end='', flush=True)
    print(' 完成')

    b50 = bench_curve('0050')
    btx = bench_curve('TAIEX', pay_fee=False)

    for pname, y0, y1 in PERIODS:
        i0, i1 = idx_range(y0, y1)
        if i1 - i0 < 30:
            continue
        print()
        print('=' * 92)
        print(f'【{pname}】　{cal[i0]} ~ {cal[i1]}（{i1-i0+1} 個交易日）')
        print('=' * 92)
        print(f'  {"":<24}{"報酬(中位)":>12}{"★最大回檔(中位)":>16}'
              f'{"報酬/回檔":>11}{"在場內":>8}{"換手":>7}')
        print('  ' + '-' * 88)
        for label, *_ in RULES:
            ms = [metrics(eq, i0, i1) for eq, _, _ in runs[label]]
            ms = [m for m in ms if m]
            if not ms:
                continue
            rets = sorted(m['ret'] for m in ms)
            dds = sorted(m['mdd'] for m in ms)
            med_r = rets[len(rets) // 2]
            med_d = dds[len(dds) // 2]
            inv = st.mean([iv for _, iv, _ in runs[label]])
            tn = st.mean([t for _, _, t in runs[label]])
            rr = med_r / abs(med_d) if med_d else float('nan')
            print(f'  {label:<24}{med_r:>+11.2f}%{med_d:>+15.2f}%'
                  f'{rr:>11.2f}{inv:>7.0f}%{tn:>7.0f}')
            print(f'  {"　└ 5~95% 分位":<24}'
                  f'{rets[int(len(rets)*.05)]:>+7.1f}~{rets[int(len(rets)*.95)]:>+6.1f}%'
                  f'{dds[int(len(dds)*.05)]:>+8.1f}~{dds[int(len(dds)*.95)]:>+5.1f}%')
        for nm, cv in (('買進持有 0050', b50), ('加權指數（參考）', btx)):
            if cv:
                m = metrics(cv, i0, i1)
                if m:
                    rr = m['ret'] / abs(m['mdd']) if m['mdd'] else float('nan')
                    print(f'  {nm:<24}{m["ret"]:>+11.2f}%{m["mdd"]:>+15.2f}%'
                          f'{rr:>11.2f}{100:>7}%{"—":>7}')

    # ── 關鍵對照：空頭年 vs 多頭年 ──
    # ⚠️ 2026-10-07 修正：第一版顯示 `d − base`，而回檔本身是負數
    #    ⇒ 「-10.9pp」實際代表回檔更深（更糟），但標籤寫成「更好」，結論完全顛倒。
    #    改為顯示 |回檔| 的差：**正值 = 更深 = 更糟**，並直接標 ✅/❌。
    def med_mdd(label, y):
        i0, i1 = idx_range(y, y)
        ms = [metrics(eq, i0, i1) for eq, _, _ in runs[label]]
        ds = sorted(abs(m['mdd']) for m in ms if m)
        return ds[len(ds) // 2] if ds else None

    def med_ret(label, y):
        i0, i1 = idx_range(y, y)
        ms = [metrics(eq, i0, i1) for eq, _, _ in runs[label]]
        rs = sorted(m['ret'] for m in ms if m)
        return rs[len(rs) // 2] if rs else None

    yrs = [y for y in range(2018, 2027) if idx_range(y, y)[1] - idx_range(y, y)[0] >= 30]
    hdr = ''.join(f'{str(y)+("★" if y in BEAR_YEARS else ""):>10}' for y in yrs)

    print()
    print('=' * 100)
    print('【★ 核心問題一】回檔比「買進持有」深了幾 pp？（**正值 = 更深 = 更糟**）')
    print('=' * 100)
    print(f'  {"":<26}{hdr}')
    print('  ' + '-' * 96)
    base = {y: med_mdd('(a) 買進持有 5 檔', y) for y in yrs}
    for label, *_ in RULES[1:]:
        line = f'  {label:<26}'
        for y in yrs:
            d = med_mdd(label, y)
            diff = d - base[y]
            line += f'{("✅" if diff < 0 else "❌")}{diff:>+7.1f}'
        print(line)
    print(f'  {"(a) 買進持有的回檔":<26}'
          + ''.join(f'{-base[y]:>10.1f}' for y in yrs))
    print(f'\n  ✅ = 回檔比買進持有淺（結構有保護）　❌ = 更深（結構沒幫上忙）')
    print(f'  ★ = 空頭年 {BEAR_YEARS}')

    print()
    print('=' * 100)
    print('【★ 核心問題二】報酬（中位），看結構的代價')
    print('=' * 100)
    print(f'  {"":<26}{hdr}')
    print('  ' + '-' * 96)
    for label, *_ in RULES:
        line = f'  {label:<26}'
        for y in yrs:
            line += f'{med_ret(label, y):>+9.1f}%'
        print(line)

    print()
    print('=' * 100)
    print('【★ 核心問題三】「續抱」值多少？(e) vs (d)——兩者唯一差異是到期時獲利要不要換股')
    print('=' * 100)
    i0, i1 = idx_range(2018, 2026)
    for label in ('(d) 無條件換倉+停損 ⚠️非現行', '(e) ★續抱代理+停損'):
        ms = [metrics(eq, i0, i1) for eq, _, _ in runs[label]]
        rs = sorted(m['ret'] for m in ms if m)
        ds = sorted(m['mdd'] for m in ms if m)
        tn = st.mean([t for _, _, t in runs[label]])
        print(f'  {label:<26}全期報酬 {rs[len(rs)//2]:>+9.2f}%　'
              f'回檔 {ds[len(ds)//2]:>+7.2f}%　換手 {tn:>6.0f} 次')
    print()
    print('  交易成本的量化（單邊 買0.0855%／賣0.3855%，÷5檔）：')
    for label in ('(b) 無條件10日換倉', '(d) 無條件換倉+停損 ⚠️非現行',
                  '(e) ★續抱代理+停損'):
        tn = st.mean([t for _, _, t in runs[label]])
        drag = ((1 - C_SELL / SLOTS) ** tn) * ((1 - C_BUY / SLOTS) ** (tn + SLOTS))
        print(f'    {label:<26}換手 {tn:>6.0f} 次 ⇒ 純成本拖累 {(drag-1)*100:>+7.1f}%')
    print("""
  ⚠️ 若 (e) 明顯優於 (d)，代表「續抱」不是錦上添花，而是讓 10 日週期
     不致毀滅的關鍵——因為同日量到「87 檔自選股裡 5 檔決定整體結果」，
     而無條件輪動會系統性砍掉那幾檔。""".rstrip())

    # ══════════════════════════════════════════════════════════
    # 【核心問題四】第三版的主題：空頭保護是不是來自「空手」？
    # ══════════════════════════════════════════════════════════
    CASH = [MAIN,
            '(g) ★(e)+MA60停買 ≈策略C',
            '(h) ★(e)+MA60出清 ≈策略D',
            '(i) (e)+MA20停買 robustness']

    def med3(label, y0, y1):
        i0, i1 = idx_range(y0, y1)
        ms = [m for m in (metrics(eq, i0, i1) for eq, _, _ in runs[label]) if m]
        rs = sorted(m['ret'] for m in ms)
        ds = sorted(abs(m['mdd']) for m in ms)
        return rs[len(rs) // 2], ds[len(ds) // 2]

    print()
    print('=' * 100)
    print('【★ 核心問題四】空頭保護是不是來自「空手」？(g)(h)(i) vs (e)')
    print('=' * 100)
    print('  三組與 (e) 的唯一差異：指數跌破 MA 時的行為。其餘規則完全相同。')
    print()
    print(f'  {"":<28}{"全期報酬":>11}{"全期|回檔|":>12}'
          f'{"2018★":>10}{"2020★":>10}{"2022★":>10}{"在場內":>8}{"換手":>7}')
    print('  ' + '-' * 96)
    for label in CASH + ['(a) 買進持有 5 檔']:
        r_all, d_all = med3(label, 2018, 2026)
        cells = ''.join(f'{med3(label, y, y)[0]:>+9.1f}%' for y in BEAR_YEARS)
        inv = st.mean([iv for _, iv, _ in runs[label]])
        tn = st.mean([t for _, _, t in runs[label]])
        print(f'  {label:<28}{r_all:>+10.2f}%{d_all:>11.2f}%{cells}'
              f'{inv:>7.0f}%{tn:>7.0f}')
    print()
    print('  ★ 空頭年的回檔（|回檔|，越小越好）：')
    print(f'    {"":<28}' + ''.join(f'{str(y)+"★":>12}' for y in BEAR_YEARS))
    for label in CASH + ['(a) 買進持有 5 檔']:
        print(f'    {label:<28}'
              + ''.join(f'{med3(label, y, y)[1]:>11.1f}%' for y in BEAR_YEARS))
    print("""
  怎麼讀這張表：
    • (g) vs (e) → **「空手」單獨值多少**。若 (g) 在 2018／2022 的回檔明顯
      小於 (e)，就證實上一版「空頭沒保護」是**滿倉設定造成的**，
      而現行策略的 `<45 停止進場` 確實是空頭保護的來源。
    • (h) vs (g) → **策略D vs 策略C**。十五章至今只有 2026-07 那兩週一個
      空頭樣本（而 2026-08 重跑還確認那週其實不是大盤轉空）⇒ 這是第一次
      用真空頭年比。(h) 若在空頭年大勝但全期大輸，就重現「多頭錯殺、
      空頭保命」那個環境依賴，而且這次有 9 年可看代價有多大。
    • (i) vs (g) → **MA 長度換成 20 結論還成立嗎**。若 MA20 結果相反，
      代表 (g) 的優勢是靠 60 這個特定數字，不可採用。
  ⚠️ MA60 只是「大盤評分 <45」的**代理**，兩者不等價。這裡能回答的是
     「空手這件事有沒有用」，不是「現行那條大盤規則的刻度對不對」。""".rstrip())

    # ══════════════════════════════════════════════════════════
    # 【核心問題五】配對比較——第三版跑 6 條時，報酬完全讀不出來
    #
    # ⚠️ 6 條時的全期報酬 5~95% 分位帶寬是 182pp（g）／499pp（h），
    #    所以「(g) +85% 贏 (h) +33%」那句話當時**不能說**。
    #
    # ★ 但那是「比較兩組獨立分位」的做法，而這裡有更有力的選項：
    #   **同一個 seed 在所有規則之間用的是同一組隨機偏好 `pref`**
    #   （`simulate()` 的 `random.Random(seed)` 只決定排序鍵，與規則無關）
    #   ⇒ runs[A][s] 與 runs[B][s] 面對**完全相同的選股順序**，
    #     差額只來自規則本身 ⇒ **配對比較可以消掉共同的運氣成分。**
    #
    #   這與 2026-09-17 立的「比較多組前先算雜訊帶」不衝突，是它的強化版：
    #   雜訊帶防的是「把抽樣雜訊當訊號」，而配對設計是**直接把那個雜訊消掉**。
    #   判準改用符號檢定（k/N 條站在同一邊）——不依賴分布假設。
    # ══════════════════════════════════════════════════════════
    from math import comb

    TIE_EPS = 1e-9

    def sign_test(diffs, better_is_negative):
        """
        配對符號檢定。回傳 (中位差, A較佳條數, 有效N, 平手數, p, 標記)

        ⚠️ **平手必須排除，不能算成輸**（2026-10-07 合成資料測試抓到的 bug）：
        第一版把 `x > 0` 當成「A 輸」，於是 Δ 恰為 0 的情況（MA20 與 MA60
        在合成資料上完全相同）變成 0/20、p=0.000，**把「沒有差異」印成
        「顯著更差」**。這與同日那個符號標籤錯誤同一族——數字算對了，
        但讀出來的結論是錯的。標準符號檢定本來就是丟掉平手、只數有向的配對。
        """
        med = st.median(diffs) if diffs else 0.0
        eff = [x for x in diffs if abs(x) > TIE_EPS]
        ties = len(diffs) - len(eff)
        nn = len(eff)
        if nn == 0:
            return med, 0, 0, ties, 1.0, '⚪'
        k = sum(1 for x in eff if (x < 0) == better_is_negative)   # A 較佳
        kk = max(k, nn - k)
        p = min(1.0, 2 * sum(comb(nn, j) for j in range(kk, nn + 1)) / 2 ** nn)
        if p >= 0.05:
            mark = '⚪'
        else:
            mark = '✅' if k > nn - k else '❌'
        return med, k, nn, ties, p, mark

    PAIRS = [
        ('(e) ★續抱代理+停損',          '(d) 無條件換倉+停損 ⚠️非現行', '續抱值多少'),
        ('(g) ★(e)+MA60停買 ≈策略C',    '(e) ★續抱代理+停損',          'MA60停買值多少'),
        ('(h) ★(e)+MA60出清 ≈策略D',    '(e) ★續抱代理+停損',          'MA60出清值多少'),
        ('(h) ★(e)+MA60出清 ≈策略D',    '(g) ★(e)+MA60停買 ≈策略C',    '★出清 vs 只停買（D vs C）'),
        ('(i) (e)+MA20停買 robustness', '(g) ★(e)+MA60停買 ≈策略C',    'MA20 vs MA60（robustness）'),
        ('(e) ★續抱代理+停損',          '(a) 買進持有 5 檔',            '整套結構 vs 買進持有'),
    ]

    def paired(a, b, y0, y1):
        i0, i1 = idx_range(y0, y1)
        dr, dd = [], []
        for s in range(N_SEED):
            ma = metrics(runs[a][s][0], i0, i1)
            mb = metrics(runs[b][s][0], i0, i1)
            if not ma or not mb:
                continue
            dr.append(ma['ret'] - mb['ret'])              # 正值 = A 報酬較高（較佳）
            dd.append(abs(ma['mdd']) - abs(mb['mdd']))    # 負值 = A 回檔較淺（較佳）
        if not dr:
            return None
        return (sign_test(dr, better_is_negative=False),
                sign_test(dd, better_is_negative=True))

    print()
    print('=' * 104)
    print(f'【★ 核心問題五】配對比較（同一 seed 同一組排序，{N_SEED} 條）'
          f'——把共同的運氣成分消掉')
    print('=' * 104)
    print('  ✅ = A 較佳且 p<0.05　❌ = A 較差且 p<0.05　⚪ = 分不出來（含平手）')
    for y0, y1, pname in [(2018, 2026, '全期間 2018-2026'),
                          (2018, 2018, '2018★ 空頭'),
                          (2020, 2020, '2020★ 空頭（V 轉）'),
                          (2022, 2022, '2022★ 空頭（完整空頭年）')]:
        print(f'\n  ── {pname} ──')
        print(f'  {"A vs B":<34}{"Δ報酬":>12}{"A較佳":>9}{"p":>7}  '
              f'{"Δ|回檔|":>10}{"A較佳":>9}{"p":>7}')
        print('  ' + '-' * 100)
        for a, b, desc in PAIRS:
            r = paired(a, b, y0, y1)
            if not r:
                continue
            (mr, kr, nr, tr, pr, sr), (md, kd, nd, td, pd, sd) = r
            print(f'  {desc:<34}{mr:>+11.2f}%{sr}{f"{kr}/{nr}":>7}{pr:>7.3f}  '
                  f'{md:>+9.2f}%{sd}{f"{kd}/{nd}":>7}{pd:>7.3f}'
                  + (f'  平手{max(tr,td)}' if max(tr, td) else ''))
    print("""
  怎麼讀：
    Δ報酬  = A − B，**正值 = A 報酬較高**
    Δ|回檔| = |A回檔| − |B回檔|，**負值 = A 回檔較淺（較好）**
    「A較佳」= A 勝的條數 / 有向配對數（**平手已排除，不算輸**）
    p = 雙尾符號檢定。20 條時需 ≥15/20 才到 p<0.05；
        **6 條時即使 6/6 全勝也只有 p=0.031、5/6 是 p=0.22
        ⇒ 這就是上一版報酬讀不出來的原因，不是帶寬的問題而是條數不夠。**
  ⚠️ 配對設計消掉的是「抽到哪些股票」的運氣，消不掉
     「這 9 年剛好是什麼行情」——樣本仍只有一條歷史路徑。
     ⇒ p<0.05 的意思是「在這段歷史上，這條規則的方向是穩定的」，
       **不是**「換一段歷史也會成立」。""".rstrip())

    print()
    print('=' * 92)
    print('【限制】')
    print('=' * 92)
    print("""
  1. 🚨 **除權息無法調整**（陷阱50）。除息下跌會進入所有策略的回檔計算、程度相似
     ⇒ 對「回檔比較」影響較小，但**所有報酬都被系統性低估**，
       買進持有被低估最多（持有期最長）。
  2. 這裡測的是**結構**，不是現行完整策略——後者還有大盤階梯與評分門檻，
     而那兩者在 2018~2024 算不出來（chips／fundamentals／market_margin 全缺）。
  3. 排序鍵是**真隨機**，所以這些數字不含任何選股效果。
     那是刻意的：10/05 已證明回檔小不依賴選股，這裡要隔離的就是結構本身。
  4. 5 檔等權、每日再平衡、現金不計息。(a)~(f) 永遠滿倉；(g)~(i) 會空手。
  5. ⚠️ **MA60／MA20 是「大盤評分 <45」的代理，不等價。** 代理回答的是
     「空手這個動作有沒有用」，不是「現行那條規則的刻度對不對」。
     要驗後者，必須等 2018~2024 的 chips／market_margin／futures 補齊
     （fundamentals 永久補不回來，陷阱44）。""".rstrip())
    c.close()


if __name__ == '__main__':
    main()
