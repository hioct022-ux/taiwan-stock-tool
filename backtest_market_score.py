"""
大盤評分門檻階梯的鑑別度驗證（2026-09-10）

═══ 背景 / 要驗證的問題 ═══
使用者問：「大盤評分的機制好像沒有做過回測？」查證後確認**只測過一半**：

  已測：S1–S8 的 net 對隔日方向的準確率（backtest.py，有方向 51.4%、強訊號 59.5%）
  已測：「net > 0 就不進場」這個二元開關（backtest_stocks.py 策略 A vs B）
  ❌ 沒測：UI 上實際在用的**四段門檻階梯**

    大盤評分 ≥70  → 個股門檻 65 分
    大盤評分 55–69 → 個股門檻 70 分
    大盤評分 45–54 → 個股門檻 75 分
    大盤評分 <45   → 停止進場

  回測裡根本沒有這個階梯，只有一行 `if market_net.get(date) > 0: continue`。
  乘數 ×5、45/55/70/85 的級距切點也從未校準過
  （對照 S3/S4 的門檻是抓實際分布算百分位校準的，見陷阱34）。

**本腳本要回答兩個問題：**
  Q1（鑑別度）：固定門檻 65 分時，進場日的大盤評分越低，交易表現真的越差嗎？
                 → 若沒差異，整個階梯就沒有存在基礎。
  Q2（階梯有效性）：在大盤評分較低的組別裡，把門檻提高到 70/75 真的能改善嗎？
                 → 這才是階梯宣稱的作用。若無效，階梯只是裝飾，應簡化成二元閘門。

═══ 方法論防護（照 CLAUDE.md 既有教訓）═══
1. **必須看 alpha，不能看原始報酬**（停損距離校準那節的教訓）。
   大盤評分高的日子本來就是市場強的日子，只看原始報酬必然得到
   「評分越高越好」——那是同義反覆，不是鑑別度。
   扣掉同期大盤（進場日→出場日的 TAIEX 報酬）之後還有差異，才叫鑑別度。
2. **必須設無條件基準對照組**（先殺後拉那節的教訓）：全部交易不分組的數字。
3. **刻意不套大盤過濾**（market_net=None）。因為策略C本身就擋掉 net>0 的日子，
   套了之後「<45」那組永遠是空的、「45–54」也只剩 net=0 一個值——
   等於現行回測從來沒有機會測到「停止進場」這條規則。

═══ 使用方式 ═══
  python3 backtest_market_score.py            # Q1：門檻 65，依大盤評分分組
  python3 backtest_market_score.py sweep      # Q1+Q2：再跑門檻 70/75 做組內對照
  python3 backtest_market_score.py ladder     # Q3：把四段階梯真的跑進回測（最重要的一組）

⚠️ Q1 單獨看會導向錯誤結論。它是拿「所有組都用 65 分」在比，
   但現行規則本來就對不同組用不同門檻——那張表其實是「拿掉階梯會怎樣」，
   不是「現行系統的表現」。**一定要跑到 Q3 才看得出全貌。**

  ⚠️ sandbox 執行請先複製到本地暫存目錄（FUSE + SQLite 極慢），見 CLAUDE.md 十五章。
"""
import sys, os, pickle, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_stocks as bs
from database import get_prices

CACHE = '/tmp/_bms_cache.pkl'

# 現行 UI 的四段級距（app.py render_strategy 的門檻階梯）
BUCKETS = [
    ('≥70   偏多',   70, 201, 65),
    ('55–69 中性偏多', 55,  70, 70),
    ('45–54 中性',    45,  55, 75),
    ('<45   偏空',  -1,  45, None),   # None = 現行規則說「停止進場」
]


def ms_from_net(net):
    """與 app.py 完全相同的換算：ms = 50 - net×5，夾在 0–100。"""
    return max(0, min(100, 50 - net * 5))


def build_context():
    """回傳 (market_net, taiex_close_by_date, taiex_dates)。"""
    print('計算大盤訊號中（S1–S8 逐日回溯）...')
    market_net = bs._build_market_signals()
    tpx = get_prices('TAIEX', days=600)
    return market_net, {p['date']: p['close'] for p in tpx}, [p['date'] for p in tpx]


def annotate(trades, market_net, tpx_close, tpx_dates):
    """
    給每筆交易補上：
      signal_ms —— **決策日**的大盤評分。決策日直接取自交易紀錄的 `signal_date`
                   （backtest_stocks.py 2026-09-10 新增的欄位），**不從進場日回推**：
                   個股若有缺資料，它的「下一根K」未必等於 TAIEX 的下一個交易日，
                   回推會對錯日期。用決策日而非進場日，是因為進場條件在決策日
                   收盤後才判斷得出來，用進場日當天的評分等於偷看未來。
      mkt_pnl   —— 同期大盤報酬（進場日→出場日的 TAIEX 變化）
      alpha     —— pnl − mkt_pnl
    取不到對應日期的交易直接丟棄（寧可少算，不用錯誤基準硬算——陷阱43 的教訓）。
    """
    out = []
    for t in trades:
        sig_date = t.get('signal_date')
        if not sig_date or sig_date not in market_net:
            continue
        c_in  = tpx_close.get(t['entry_date'])
        c_out = tpx_close.get(t['exit_date'])
        if not c_in or not c_out:
            continue
        t = dict(t)
        t['signal_date'] = sig_date
        t['signal_ms']   = ms_from_net(market_net[sig_date])
        t['mkt_pnl']     = (c_out - c_in) / c_in * 100
        t['alpha']       = t['pnl'] - t['mkt_pnl']
        out.append(t)
    return out


def stat(trades):
    if not trades:
        return None
    pnl = [t['pnl'] for t in trades]
    return {
        'n':      len(trades),
        'win':    sum(1 for p in pnl if p > 0) / len(pnl) * 100,
        'pnl':    statistics.mean(pnl),
        'mkt':    statistics.mean(t['mkt_pnl'] for t in trades),
        'alpha':  statistics.mean(t['alpha'] for t in trades),
        'stop':   sum(1 for t in trades if '停損' in t.get('exit_reason', '')) / len(trades) * 100,
    }


def row(label, s):
    if s is None:
        return f'{label:16} {"—— 無交易 ——":>44}'
    return (f'{label:16} {s["n"]:5}  {s["win"]:5.1f}%  {s["pnl"]:+6.2f}%  '
            f'{s["mkt"]:+6.2f}%  {s["alpha"]:+6.2f}%  {s["stop"]:5.1f}%')


HEADER = f'{"分組":16} {"筆數":>5}  {"勝率":>6}  {"報酬":>7}  {"同期大盤":>7}  {"alpha":>7}  {"停損率":>6}'


def run_threshold(thr, market_net):
    """用指定的個股門檻跑一次「無大盤過濾 + 到期續抱 + 10%停損」。"""
    bs.SCORE_THRESHOLD = thr
    print(f'  執行回測（個股門檻 {thr} 分，不套大盤過濾）...')
    trades, _ = bs._run_backtest(market_net=None, renew=True)
    return trades


def run_ladder(market_net, tpx_close, tpx_dates, base65):
    """
    Q3：把 app.py 的四段階梯**真的跑進回測**，與「回測長期在驗的規則」並排比較。

    ⚠️ 必備的對照組：「完全不看大盤、一律 70 分」。
    階梯的平均門檻就落在 70 附近，沒有這個對照，看到階梯 alpha 較高會直接
    誤判成「大盤評分有效」——這是停損距離校準那節立下的規矩
    （任何「按某變數動態調整參數」的提案，都要加測「改成同等平均值的固定值」）。

    續抱門檻固定 65（與策略C 的續抱規則一致），只有進場門檻走階梯。
    """
    def ladder(d):                 # 現行 UI 規則
        m = ms_from_net(market_net.get(d, 0))
        return 65 if m >= 70 else 70 if m >= 55 else 75 if m >= 45 else None

    def ladder_no_stop(d):         # 同上，但 <45 不封鎖
        return ladder(d) or 65

    variants = [
        ('現行 UI 階梯（四段，<45停止）', ladder),
        ('階梯但 <45 不封鎖（改用65分）', ladder_no_stop),
        ('★對照：不看大盤，一律 70 分',   lambda d: 70),
    ]

    print()
    print('=' * 88)
    print('【Q3】UI 的階梯 vs 回測長期在驗的規則 —— 放在同一張表')
    print('=' * 88)
    def line(label, s):
        if s is None:
            print(f'{label:34} {"—— 無交易 ——":>40}')
            return
        print(f'{label:34} {s["n"]:5}  {s["win"]:5.1f}%  {s["pnl"]:+6.2f}%  '
              f'{s["mkt"]:+6.2f}%  {s["alpha"]:+6.2f}%  {s["stop"]:5.1f}%')

    print(f'{"規則":34} {"筆數":>5}  {"勝率":>6}  {"報酬":>7}  {"同期大盤":>7}  {"alpha":>7}  {"停損率":>6}')
    print('-' * 88)
    line('基準：不看大盤，一律 65 分', stat(base65))

    bs.SCORE_THRESHOLD = 65
    c = annotate(bs._run_backtest(market_net=market_net, renew=True)[0],
                 market_net, tpx_close, tpx_dates)
    line('策略C（回測長期在驗的）', stat(c))

    for label, fn in variants:
        bs.SCORE_THRESHOLD = 65
        tr = annotate(bs._run_backtest(market_net=None, renew=True, threshold_fn=fn)[0],
                      market_net, tpx_close, tpx_dates)
        line(label, stat(tr))

    print('-' * 88)
    print('※ 跨 run 的數字不能直接相減（有狀態依賴：一檔已被持有就無法在別的日子進場），')
    print('  只有同一個 run 內的對照才嚴謹。')


def main():
    do_sweep  = 'sweep'  in sys.argv
    do_ladder = 'ladder' in sys.argv

    if os.path.exists(CACHE):
        print(f'讀取快取 {CACHE}')
        with open(CACHE, 'rb') as f:
            market_net, tpx_close, tpx_dates, by_thr = pickle.load(f)
    else:
        market_net, tpx_close, tpx_dates = build_context()
        by_thr = {}

    thresholds = [65, 70, 75] if do_sweep else [65]
    for thr in thresholds:
        if thr not in by_thr:
            by_thr[thr] = annotate(run_threshold(thr, market_net),
                                   market_net, tpx_close, tpx_dates)
            with open(CACHE, 'wb') as f:
                pickle.dump((market_net, tpx_close, tpx_dates, by_thr), f)

    # ── 大盤評分的日期分布（先看母體，避免用個位數樣本下結論）──
    print()
    print('=' * 78)
    print('【大盤評分的歷史分布】（決策日層級，非交易層級）')
    print('=' * 78)
    all_ms = [ms_from_net(n) for n in market_net.values()]
    for label, lo, hi, _ in BUCKETS:
        n = sum(1 for m in all_ms if lo <= m < hi)
        print(f'  {label:16} {n:4} 天 ({n / max(1, len(all_ms)) * 100:4.1f}%)')
    print(f'  {"合計":16} {len(all_ms):4} 天')

    # ── Q1：固定門檻 65，依大盤評分分組 ──
    base = by_thr[65]
    print()
    print('=' * 78)
    print('【Q1】個股門檻固定 65 分，依「決策日大盤評分」分組')
    print('=' * 78)
    print(HEADER)
    print('-' * 78)
    print(row('★ 基準（全部）', stat(base)))
    print('-' * 78)
    for label, lo, hi, _ in BUCKETS:
        print(row(label, stat([t for t in base if lo <= t['signal_ms'] < hi])))

    # ── 穩健性：分期間重跑同一張表 ──
    # 若某一組的結論只由單一時段撐起來，那是巧合不是鑑別度。
    print()
    print('=' * 78)
    print('【Q1-b】分期間（確認上表不是被某個時段帶走的）—— 只看 alpha')
    print('=' * 78)
    periods = [('2025全年', '2025-01-01', '2025-12-31'),
               ('2026H1',   '2026-01-01', '2026-06-30'),
               ('2026H2起', '2026-07-01', '2099-12-31')]
    print(f'{"分組":16}' + ''.join(f'{p[0]:>14}' for p in periods))
    print('-' * 78)
    for label, lo, hi, _ in BUCKETS:
        cells = []
        for _, d0, d1 in periods:
            sub = [t for t in base
                   if lo <= t['signal_ms'] < hi and d0 <= t['signal_date'] <= d1]
            s = stat(sub)
            cells.append(f'{s["alpha"]:+7.2f}%({s["n"]:3})' if s else f'{"—":>13}')
        print(f'{label:16}' + ''.join(f'{c:>14}' for c in cells))
    print('（括號內為筆數；筆數 <20 的格子不具統計意義）')

    if do_ladder:
        run_ladder(market_net, tpx_close, tpx_dates, base)

    if not do_sweep:
        if not do_ladder:
            print()
            print('※ Q2（弱市提高門檻有沒有用）：python3 backtest_market_score.py sweep')
            print('※ Q3（把階梯真的跑進回測，最重要）：'
                  'python3 backtest_market_score.py ladder')
        return

    # ── Q2：各組內比較不同個股門檻 ──
    print()
    print('=' * 78)
    print('【Q2】各大盤評分組別內，把個股門檻提高到 70／75 有沒有改善？')
    print('=' * 78)
    for label, lo, hi, ui_thr in BUCKETS:
        print()
        print(f'▍大盤評分 {label}　（現行 UI 規則：'
              f'{"門檻 " + str(ui_thr) + " 分" if ui_thr else "停止進場"}）')
        print(HEADER)
        print('-' * 78)
        for thr in thresholds:
            sub = [t for t in by_thr[thr] if lo <= t['signal_ms'] < hi]
            mark = ' ←現行' if thr == ui_thr else ''
            print(row(f'  個股門檻 {thr}', stat(sub)) + mark)


if __name__ == '__main__':
    main()
