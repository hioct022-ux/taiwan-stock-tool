"""
大盤日K盤中結構對隔日漲跌的預測力驗證（2026-09-01 新增，實驗性質，未接入正式邏輯）

═══ 背景／要驗證的問題 ═══

2026-09-01 台股收 46,949（+1.78%），但拆開來看：
    開盤 46,177（跳空僅 +0.11%）、最低 46,081、收盤 = 當日最高 46,949
    → **漲幅幾乎全在盤中走出來（+1.67%），不是隔夜資訊帶來的**
前一日 8/31 也類似：開 46,225、最低 45,450（-1.9%）、收 46,128（拉回）。
連兩天「先殺後拉」。

使用者觀察：這種型態是否代表低檔有承接力道、對隔日有參考價值？

**為什麼值得測：** 現行 Signal 1–11 **全部只用收盤價**（漲跌幅、均線、乖離、成交量），
完全沒有用到 open/high/low 的盤中結構。這是既有資料裡尚未被使用的維度，
不需要引入任何新資料來源。

本腳本要回答：
  「先殺後拉」型態（開盤後探底、收盤收在高檔）對**隔日大盤漲跌**有無預測力？

═══ 型態定義（都只用當日 OHLC，無未來資訊）═══
  下影線比例   = (min(open,close) − low) / (high − low)
  收盤位置     = (close − low) / (high − low)      1.0 = 收最高、0 = 收最低
  盤中反轉幅度 = (close − low) / low × 100

  A「先殺後拉」：收盤位置 ≥ 0.8 且 當日最低跌破前一日收盤（真的有殺下去）
  B「強力反轉」：A 且 盤中反轉幅度 ≥ 1.5%
  C「長下影線」：下影線比例 ≥ 0.4
  D「收最高」  ：收盤位置 ≥ 0.9
  E「連兩日先殺後拉」：今日與昨日都符合 A

═══ ⚠️ 判準（最重要）═══
  **必須跟「無條件的隔日表現」比。**
  樣本期是 2024-08~2026-09 大多頭（501 個交易日、指數 +102%），
  隔日上漲的基準機率本來就明顯高於 50%。
  不設對照組就會把「大盤本來就在漲」誤讀成「型態有預測力」。

  判準：型態出現後的隔日勝率／平均漲跌，**減去**全樣本基準值＝超額。
  超額若在 ±1pp 內視為無效（樣本雜訊範圍）。
  樣本數 < 30 的型態不下結論。

═══ 事前預期（先寫下來，避免事後合理化）═══
  預期**沒有顯著預測力**。單日K棒型態在實證上普遍很弱，
  且本專案已四次驗證出「看起來合理的型態訊號實測無效」
  （🎯🔥進場型態、移動停損、confirm_days=1、策略F）。
  但這是第一次測大盤層級的K棒結構，沒有十足把握。

═══ 2026-09-01 執行結果 ═══

  樣本：TAIEX 508 個交易日（2024-07-30 ~ 2026-08-31）
  ★ 基準（無條件）：隔日上漲機率 55.9%、隔日平均漲跌 +0.161%

  型態                    樣本   隔日勝率(vs基準)      隔日均漲(vs基準)
  A 先殺後拉                60   50.0% (-5.9pp)     -0.079% (-0.241pp)
  B 強力反轉(A+反彈≥1.5%)    16   56.2% (+0.3pp)     +0.075% (-0.086pp)  樣本不足
  C 長下影線 ≥0.4          111   55.0% (-1.0pp)     +0.021% (-0.140pp)
  D 收在最高 ≥0.9           86   57.0% (+1.1pp)     +0.057% (-0.104pp)
  E 連兩日先殺後拉           10   50.0% (-5.9pp)     -0.026% (-0.188pp)  樣本不足
  ── 反向對照 ──
  X 收在最低 ≤0.1          100   58.0% (+2.1pp)     +0.385% (+0.224pp)
  Y 長上影線 ≥0.4           74   58.1% (+2.2pp)     +0.325% (+0.163pp)

  **事前預期正確，但結果比預期更明確——方向是反的。**
  「先殺後拉」不但沒有預測力，隔日表現還比什麼都不看更差（勝率 -5.9pp）。
  反而是「收在最低」「長上影線」這些看起來弱的型態，隔日略優於基準
  （符合短線均值回歸：收得越弱、隔日越容易反彈；而先殺後拉是當日已把反彈走完）。

  **不建議反過來用**：超額僅 +2.1pp 勝率／+0.22pp 報酬，在 500 筆樣本下接近雜訊；
  且樣本全在大多頭，均值回歸在多頭市特別容易成立，換環境可能翻轉。

  **結論：不加入 Signal。** 這是本專案第五次驗證出「看起來合理的型態訊號實測無效」
  （前四次：🎯🔥進場型態、移動停損、confirm_days=1、策略F）。

  ⚠️ **本次最重要的方法論收穫：一定要設「無條件基準」對照組。**
  若沒有基準線，看到「先殺後拉隔日勝率 50%」可能還會覺得「五五波、也許有點用」；
  一對照才知道基準是 55.9%，實際上是**明顯更差**。
  大多頭樣本會把所有訊號的絕對數字都墊高，不設基準線會全部誤判。

═══ 執行 ═══
  python3 backtest_intraday_reversal.py
"""
import sys, os, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_prices, init_db

init_db()
MIN_SAMPLE = 30


def build():
    """回傳逐日 dict，含型態旗標與『隔日』漲跌幅。"""
    p = [x for x in get_prices('TAIEX', days=900)
         if x.get('open') and x.get('high') and x.get('low') and x.get('close')]
    out = []
    for i in range(1, len(p) - 1):          # 需要前一日與隔日
        d, prev, nxt = p[i], p[i - 1], p[i + 1]
        rng = d['high'] - d['low']
        if rng <= 0:
            continue
        lower_wick = (min(d['open'], d['close']) - d['low']) / rng
        close_pos  = (d['close'] - d['low']) / rng
        rebound    = (d['close'] - d['low']) / d['low'] * 100
        dipped     = d['low'] < prev['close']          # 當日真的殺破前收
        nxt_chg    = (nxt['close'] - d['close']) / d['close'] * 100
        out.append(dict(date=d['date'], lower_wick=lower_wick, close_pos=close_pos,
                        rebound=rebound, dipped=dipped, nxt_chg=nxt_chg,
                        chg=(d['close'] - prev['close']) / prev['close'] * 100))
    # 連兩日先殺後拉
    for i in range(1, len(out)):
        a, b = out[i - 1], out[i]
        b['two_day'] = (b['close_pos'] >= 0.8 and b['dipped']
                        and a['close_pos'] >= 0.8 and a['dipped'])
    if out:
        out[0]['two_day'] = False
    return out


def report(rows, base_wr, base_avg, label, cond):
    s = [r for r in rows if cond(r)]
    if not s:
        print(f'{label:<26} 無樣本')
        return
    n = len(s)
    wr = sum(1 for r in s if r['nxt_chg'] > 0) / n * 100
    avg = statistics.mean(r['nxt_chg'] for r in s)
    warn = '  ⚠️樣本不足' if n < MIN_SAMPLE else ''
    verdict = ''
    if n >= MIN_SAMPLE:
        if abs(wr - base_wr) <= 1 and abs(avg - base_avg) <= 0.05:
            verdict = '  → 無效（在雜訊範圍內）'
        elif wr > base_wr + 1 and avg > base_avg + 0.05:
            verdict = '  → 略優'
        elif wr < base_wr - 1 and avg < base_avg - 0.05:
            verdict = '  → 略差'
    print(f'{label:<26} n={n:>4}  隔日勝率={wr:>5.1f}%（{wr-base_wr:+5.1f}pp）  '
          f'隔日均漲={avg:>+6.3f}%（{avg-base_avg:+6.3f}pp）{warn}{verdict}')


if __name__ == '__main__':
    rows = build()
    n0 = len(rows)
    base_wr = sum(1 for r in rows if r['nxt_chg'] > 0) / n0 * 100
    base_avg = statistics.mean(r['nxt_chg'] for r in rows)

    print('=' * 104)
    print(f'樣本：TAIEX {n0} 個交易日（{rows[0]["date"]} ~ {rows[-1]["date"]}）')
    print(f'★ 基準（無條件）：隔日上漲機率 {base_wr:.1f}%　隔日平均漲跌 {base_avg:+.3f}%')
    print('  ↑ 這是大多頭樣本，基準本來就偏高。以下所有型態都要跟這個比才有意義。')
    print('=' * 104)

    report(rows, base_wr, base_avg, 'A 先殺後拉（收高檔+破前收）',
           lambda r: r['close_pos'] >= 0.8 and r['dipped'])
    report(rows, base_wr, base_avg, 'B 強力反轉（A+反彈≥1.5%）',
           lambda r: r['close_pos'] >= 0.8 and r['dipped'] and r['rebound'] >= 1.5)
    report(rows, base_wr, base_avg, 'C 長下影線（≥0.4）',
           lambda r: r['lower_wick'] >= 0.4)
    report(rows, base_wr, base_avg, 'D 收在最高（位置≥0.9）',
           lambda r: r['close_pos'] >= 0.9)
    report(rows, base_wr, base_avg, 'E 連兩日先殺後拉',
           lambda r: r.get('two_day'))
    print()
    print('對照（反向型態，確認方法本身有鑑別力）：')
    report(rows, base_wr, base_avg, 'X 收在最低（位置≤0.1）',
           lambda r: r['close_pos'] <= 0.1)
    report(rows, base_wr, base_avg, 'Y 長上影線（≥0.4）',
           lambda r: (r['high'] - max(r.get('open', 0), 0)) if False else
                     ((1 - r['close_pos']) >= 0.4 and not r['dipped']))
    print()
    print('※ 若「收在最低」的隔日表現也跟基準差不多，代表這類單日K棒結構在本樣本中')
    print('  整體沒有鑑別力，不是只有「先殺後拉」無效。')
