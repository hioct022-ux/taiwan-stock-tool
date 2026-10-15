#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exdiv.py — 除息調整的**單一份實作**（2026-10-15 新增）

════════════════════════════════════════════════════════════════════════
為什麼獨立成一個模組
════════════════════════════════════════════════════════════════════════

陷阱34／43 的病根都是「同一個邏輯三份實作、只改一兩處」
（S4 門檻在 app.py／backtest.py／backtest_stocks.py 各一份、S3 同樣）。
除息調整會被 `backtest_portfolio_slots.py`、`backtest_revenue_filter.py`、
`backtest_structure_bear.py`、`backtest_vs_etf.py` 都用到
⇒ **一開始就只留一份**，別等到不同步了才來修。

════════════════════════════════════════════════════════════════════════
🚨 最重要的一件事：只調整個股、不調整基準，alpha 會被系統性高估
════════════════════════════════════════════════════════════════════════

`prices` 存的是**未調整收盤價**（陷阱49），所以除息日股價會往下跳，
而那段跳水其實是**配到你手上的現金**——個股報酬被低估。

**但 TAIEX 也是價格指數，同樣不含股利。** 所以：

```
alpha = 個股報酬 − TAIEX 報酬
```

若只把左邊加上股利、右邊不動 ⇒ **alpha 憑空多出整個市場的殖利率**
（台股約 3~4%/年），那是假的改善。這與十五章「必須看 alpha 而非原始報酬」
是同一族的錯誤：**量尺只改一邊**。

**⇒ 本模組提供兩種報酬，呼叫端必須明白自己在用哪一種：**

| | 用途 |
|---|---|
| `pnl`（原樣，未調整） | 與**既有所有回測數字**同基準 ⇒ 要對照歷史結論時用這個 |
| `pnl_div`（個股加回股利） | **只能用在「兩組相減」的比較**，例如 B2−C、A vs B 的配對差 |

★ **為什麼「兩組相減」就安全：** 兩組用同一個基準，
`(個股A − 市場) − (個股B − 市場) = 個股A − 個股B` ⇒ **市場項精確消掉**，
基準有沒有含股利完全不影響結果。而十五章月營收那節的除息診斷
（B2−C 分「除息月 vs 其他 8 月」）正好就是這種形式 ⇒ **個股端調整就夠且正確**。

**⇒ 絕對不要拿 `pnl_div` 的絕對值去跟既有的 alpha 數字並列。**
要做「絕對 alpha 的除息調整版」，必須同時換成**總報酬基準**
（TWSE 發行量加權股價報酬指數，或 FinMind `TaiwanStockTotalReturnIndex`）
——那是另一個題目，本模組刻意不猜。

════════════════════════════════════════════════════════════════════════
領息的條件（差一天就錯）
════════════════════════════════════════════════════════════════════════

`ex_date` = 除權息**交易日**，當天開盤起股價就已扣掉股利。
進場是在 `entry_date` 的收盤成交 ⇒ 你從那天收盤起持有
⇒ **領得到的條件是 `entry_date < ex_date <= exit_date`**。

- `ex_date == entry_date`：當天收盤買，價格已經是除息後 ⇒ **領不到**
- `ex_date == exit_date`：當天收盤賣，但除息已在當天開盤發生 ⇒ **領得到**

════════════════════════════════════════════════════════════════════════
⚠️ 本模組**沒有**處理的事（必須一起講）
════════════════════════════════════════════════════════════════════════

1. **假停損**：除息日的價格跳水會打到 `stop`，產生一筆不該發生的停損。
   真正的修法是用**還原股價**跑整個回測，那會改動所有既有基準。
   本模組提供 `suspect_false_stops()` 讓呼叫端把這類交易**列出來**，
   而不是假裝沒事（陷阱51 那條「零結果會被印成什麼」的同一個立場）。
2. **權（股票股利）**：`div_value` 是「權值+息值」合計，但配股會改變股數，
   單純加回金額只是近似。台股近年以現金股利為主，誤差方向不明。
3. **稅與二代健保補充保費**：完全不計（與既有回測不含稅的立場一致）。
"""
import sys
from collections import defaultdict

from database import get_conn

# 可能是「除息造成的假停損」的判定門檻：股利佔除息前收盤的比例
FALSE_STOP_DIV_PCT = 2.0


def load_dividends(codes=None):
    """
    回傳 {code: [(ex_date, div_value, prev_close), ...]}，ex_date 升序。

    ⚠️ 只取 `div_value > 0` 的列——`exdividend` 表同時存 TWT48U 預告
    （`is_confirmed=0`）與 TWT49U 正式（=1），而 `save_exdividend()` 對正式資料
    用 INSERT OR REPLACE、對預告用 INSERT OR IGNORE
    ⇒ 同一個 (ex_date, code) 只會有一列，不需要再去重。
    """
    conn = get_conn()
    rows = conn.execute(
        'SELECT code, ex_date, div_value, prev_close FROM exdividend '
        'WHERE div_value > 0 ORDER BY code, ex_date').fetchall()
    conn.close()
    want = set(codes) if codes else None
    out = defaultdict(list)
    for code, ex_date, div_value, prev_close in rows:
        if want is not None and code not in want:
            continue
        out[code].append((ex_date, float(div_value or 0), float(prev_close or 0)))
    return dict(out)


def coverage(divs=None):
    """
    回填狀況報告，回傳 (總列數, 逐年 dict, 最早, 最晚)。
    ★ 這支存在的理由就是陷阱50 那條通則：**「資料表有資料」不等於
      「涵蓋你的回測期間」。查涵蓋範圍要看 MIN/MAX 與逐年分布，不是 COUNT(*)。**
    """
    conn = get_conn()
    n, lo, hi = conn.execute(
        'SELECT COUNT(*), MIN(ex_date), MAX(ex_date) FROM exdividend '
        'WHERE div_value > 0').fetchone()
    by_year = dict(conn.execute(
        'SELECT substr(ex_date,1,4), COUNT(*) FROM exdividend '
        'WHERE div_value > 0 GROUP BY 1 ORDER BY 1').fetchall())
    conn.close()
    return n, by_year, lo, hi


def require_coverage(start, end, min_per_year=200, verbose=True):
    """
    ★ **阻斷式**檢查（照陷阱51 對帳那條：不到門檻就擋下，不要事後補 robustness）。

    回傳 True 才可以用 `pnl_div`。任何一年的筆數 < min_per_year 就回 False
    ——那代表那一年根本沒回填，而**「沒有股利」與「沒有資料」在數字上長得一樣**，
    會讓那幾年的除息調整悄悄失效（這正是陷阱41/42/45 的共同形狀）。
    """
    n, by_year, lo, hi = coverage()
    y0, y1 = int(start[:4]), int(end[:4])
    bad = [y for y in range(y0, y1 + 1) if by_year.get(str(y), 0) < min_per_year]
    if verbose:
        print(f'除權息資料：{n:,} 列　{lo} ~ {hi}')
        print('  逐年：' + '　'.join(
            f'{y}:{by_year.get(str(y), 0)}' for y in range(y0, y1 + 1)))
    if bad:
        if verbose:
            print(f'\n🚨 這些年份的筆數 < {min_per_year}，判定為**未回填**：{bad}')
            print('   ⇒ 不可使用除息調整後的數字。請先在本機執行：')
            print('       python3 backfill_exdividend.py            （試跑）')
            print('       python3 backfill_exdividend.py --apply     （寫入）')
        return False
    if verbose:
        print(f'✅ {y0}~{y1} 每年都 ≥ {min_per_year} 筆，可以做除息調整')
    return True


def div_in_window(divs, code, entry_date, exit_date):
    """
    持有期間（`entry_date < ex_date <= exit_date`）領到的股利合計（元/股）。
    回傳 (合計, [(ex_date, div, prev_close), ...])。
    """
    lst = divs.get(code)
    if not lst:
        return 0.0, []
    hit = [r for r in lst if entry_date < r[0] <= exit_date]
    return sum(r[1] for r in hit), hit


def adjust_trades(trades, divs, inplace=True):
    """
    為每筆交易補上三個欄位（**不動既有的 `pnl`**）：

      `div`      : 持有期間領到的股利合計（元/股）
      `pnl_div`  : 除息調整後報酬 % = (出場價 + div − 進場價) / 進場價 × 100
      `div_hits` : 命中的除息事件明細，供 suspect_false_stops() 用

    ★ 刻意不覆寫 `pnl`：既有所有數字都以它為基準，覆寫等於讓
      「新舊不同源」又重演一次（陷阱34 的病根）。
    """
    out = trades if inplace else [dict(t) for t in trades]
    for t in out:
        d, hits = div_in_window(divs, t['code'], t['entry_date'], t['exit_date'])
        ep = t['entry_price']
        t['div'] = d
        t['div_hits'] = hits
        t['pnl_div'] = ((t['exit_price'] + d - ep) / ep * 100) if ep else t['pnl']
    return out


def suspect_false_stops(trades):
    """
    可能是「除息跳水打到停損」的交易（陷阱49 的同一族，本模組不修只揭露）。

    判定：`exit_reason == '停損'` 且持有期間有一筆股利 ≥ 除息前收盤的
    FALSE_STOP_DIV_PCT%。而停損距離是 10%，所以 2% 以上的除息確實可能
    把一筆「本來還撐著」的部位推過停損線。
    """
    out = []
    for t in trades:
        if t.get('exit_reason') != '停損':
            continue
        for ex_date, div, prev_close in t.get('div_hits', []):
            if prev_close > 0 and div / prev_close * 100 >= FALSE_STOP_DIV_PCT:
                out.append((t, ex_date, div / prev_close * 100))
                break
    return out


def summary_line(trades):
    """一行摘要，給各回測腳本印在表格前後。"""
    n = len(trades)
    if not n:
        return '（無交易）'
    with_div = sum(1 for t in trades if t.get('div', 0) > 0)
    raw = sum(t['pnl'] for t in trades) / n
    adj = sum(t['pnl_div'] for t in trades) / n
    fs = len(suspect_false_stops(trades))
    return (f'{n} 筆　有領到股利 {with_div} 筆（{with_div/n*100:.1f}%）　'
            f'未調整 {raw:+.2f}%　除息調整後 {adj:+.2f}%（{adj-raw:+.2f}pp）　'
            f'⚠️ 疑似除息假停損 {fs} 筆')


# ════════════════════════════════════════════════════════════════════
# 自我測試（合成資料）——照 10/07「錯誤二」的教訓：**成對造情境**
#   只造「有效果」的世界會以為方法對了，但它可能連「不該有效果」的
#   情境也給出效果。所以 ex_date 的邊界兩側都要各造一個。
# ════════════════════════════════════════════════════════════════════
def _selftest():
    divs = {'9999': [('2026-07-10', 3.0, 100.0),
                     ('2026-08-20', 1.0, 110.0)]}
    cases = [
        # (說明, entry, exit, 期望股利)
        ('完全涵蓋兩次',            '2026-07-01', '2026-09-01', 4.0),
        ('只涵蓋第一次',            '2026-07-01', '2026-08-01', 3.0),
        ('★ 進場日=除息日 → 領不到', '2026-07-10', '2026-08-01', 0.0),
        ('★ 出場日=除息日 → 領得到', '2026-07-01', '2026-07-10', 3.0),
        ('完全錯開',                '2026-09-01', '2026-10-01', 0.0),
    ]
    ok = True
    for desc, e0, e1, want in cases:
        got, _ = div_in_window(divs, '9999', e0, e1)
        mark = '✅' if abs(got - want) < 1e-9 else '❌'
        if mark == '❌':
            ok = False
        print(f'  {mark} {desc:26} {e0}~{e1}　期望 {want}　實得 {got}')

    # 報酬換算
    tr = [{'code': '9999', 'entry_date': '2026-07-01', 'exit_date': '2026-09-01',
           'entry_price': 100.0, 'exit_price': 96.0, 'pnl': -4.0,
           'exit_reason': '停損'}]
    adjust_trades(tr, divs)
    want = (96.0 + 4.0 - 100.0) / 100.0 * 100   # = 0.0
    mark = '✅' if abs(tr[0]['pnl_div'] - want) < 1e-9 else '❌'
    if mark == '❌':
        ok = False
    print(f'  {mark} 報酬換算：未調整 {tr[0]["pnl"]:+.2f}% → '
          f'調整後 {tr[0]["pnl_div"]:+.2f}%（期望 {want:+.2f}%）')

    # 假停損偵測：3.0/100 = 3% ≥ 2% ⇒ 應該被抓到
    fs = suspect_false_stops(tr)
    mark = '✅' if len(fs) == 1 else '❌'
    if mark == '❌':
        ok = False
    print(f'  {mark} 假停損偵測：抓到 {len(fs)} 筆（期望 1）')

    # ★ 反向對照：不是停損的交易不該被抓
    tr2 = [dict(tr[0], exit_reason='持滿10日')]
    fs2 = suspect_false_stops(tr2)
    mark = '✅' if len(fs2) == 0 else '❌'
    if mark == '❌':
        ok = False
    print(f'  {mark} ★反向：非停損的交易抓到 {len(fs2)} 筆（期望 0）')

    print('\n' + ('✅ 全部通過' if ok else '🚨 有測試失敗'))
    return ok


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        print('exdiv.py 自我測試（合成資料）')
        sys.exit(0 if _selftest() else 1)
    print('=' * 70)
    print('除權息資料涵蓋狀況')
    print('=' * 70)
    n, by_year, lo, hi = coverage()
    print(f'{n:,} 列　{lo} ~ {hi}')
    for y, c in sorted(by_year.items()):
        print(f'   {y}　{c:>5} 筆')
    print()
    require_coverage('2018-01-01', '2026-12-31')
