"""
個股評分分段測試 ＋ 雜訊帶估計 —— 2026-09-24 進版控

═══ 背景 / 要驗證的問題 ═══
「65 分門檻到底有沒有用」。這是整套策略最核心、卻**最晚才被檢驗**的一條線。

歷史：
  2026-09-17 第一次測 → 五組 alpha 全距 1.26pp，雜訊帶 2.27pp → 測不出來
  2026-09-17 補完籌碼歷史後重測 → 全距縮到 0.79pp，雜訊帶 2.76pp → 還是測不出來
  2026-09-23 量到評分是「後照鏡」（與未來報酬 corr ≈ 0、與過去 +0.25）
  2026-09-23 補了 439 個交易日的全市場價格，標的數 74 → 510

這支腳本把那兩次的臨時程式**正式化**，好處是下次重跑不用重寫，
而且雜訊帶的算法固定下來、不會每次憑感覺換。

═══ 為什麼一定要算雜訊帶（本專案最重要的方法論之一）═══
做法：從基準組**重抽**與各組同樣筆數的子集數百次，看 alpha 的 5–95% 分位。
**若各組的全距比雜訊帶窄，整張表就不必解讀。**

2026-09-17 若少了這一步，會從「F 比 B 高 1.41pp」得出「挑最高分有害」
這個完全錯誤的結論。它與「必須設無條件基準」「必須看 alpha」是同一族防護：
前兩者防「量尺選錯」，這一則防「把雜訊當訊號」。

═══ 使用方式 ═══
  python3 backtest_score_bands.py            # 用自選股快取（87 檔）
  python3 backtest_score_bands.py market     # 用全市場快取（510 檔）

  兩者都要先建快取：
  python3 backtest_portfolio_slots.py cache [market]

═══ 讀這張表時必須同時講的限制 ═══
1. 樣本全在多頭（2024-07~2026-09，指數大漲）。多頭裡低分股照樣漲，
   任何「挑好股」的機制在這種環境都難以顯出差距。
2. 各區間是**不同的交易集合**，有狀態依賴（一檔被某區間持有就不會出現在別的區間），
   跨組比較本來就不嚴謹。
3. **基本面那 25% 權重，2026-05 之前是預設值 50**（BWIBBU date 參數無效，陷阱44，永久）。
   所以這張表的意義是「技術 40% + 籌碼 35% ＝ 75% 權重可驗證」。
"""
import sys, os, random, statistics as stt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pickle
import backtest_portfolio_slots as P

BANDS = [
    ('＜40（極低）',      lambda s: s < 40),
    ('40–49',            lambda s: 40 <= s < 50),
    ('50–59',            lambda s: 50 <= s < 60),
    ('60–64（差一點）',   lambda s: 60 <= s < 65),
    ('≥65（現行門檻）',   lambda s: s >= 65),
]

BOOT_N = 800          # 重抽次數


def noise_band(trades, tpx, n, reps=BOOT_N):
    """
    從基準組重抽 n 筆、算 alpha，回傳 (5%分位, 中位, 95%分位, 帶寬)。
    ⚠️ 有放回抽樣（bootstrap）——問的是「同一個母體、只是運氣不同，
       alpha 會飄多寬」，而不是「另一個母體會怎樣」。
    """
    pn = [(t['pnl'], _mkt(t, tpx)) for t in trades]
    pn = [(a, b) for a, b in pn if b is not None]
    if len(pn) < 10:
        return None
    out = []
    for _ in range(reps):
        s = [pn[random.randrange(len(pn))] for _ in range(n)]
        out.append(sum(a for a, _ in s) / n - sum(b for _, b in s) / n)
    out.sort()
    lo, mid, hi = out[int(reps * .05)], out[reps // 2], out[int(reps * .95)]
    return lo, mid, hi, hi - lo


def _mkt(t, tpx):
    a, b = tpx.get(t['entry_date']), tpx.get(t['exit_date'])
    return (b / a - 1) * 100 if a and b else None


def main():
    mkt = 'market' in sys.argv[1:]
    path = P.CACHE_MARKET if mkt else P.CACHE
    if not os.path.exists(path):
        print(f'找不到快取 {path}')
        print('請先執行：python3 backtest_portfolio_slots.py cache' + (' market' if mkt else ''))
        return
    with open(path, 'rb') as f:
        cache = pickle.load(f)
    tpx = cache['tpx_close']
    print(f'快取：{path}　{len(cache["stocks"])} 檔'
          f'（{"全市場上市普通股" if mkt else "自選股"}）')

    by_code = lambda c, d, s: (c,)

    # ── 基準組：現行階梯、不限檔數（＝現行規則的實際行為）──
    _, base_tr = P.simulate(cache, by_code, None, 'base')
    bs_ = P.stat(base_tr, tpx)
    print(f'基準（現行階梯、不限檔數）：n={bs_["n"]}　alpha {bs_["alpha"]:+.2f}%\n')

    print('=' * 88)
    print(f'{"進場評分":<18}{"筆數":>7}{"報酬":>9}{"同期大盤":>10}{"alpha":>9}{"勝率":>8}')
    print('-' * 88)
    rows = []
    for label, fn in BANDS:
        _, tr = P.simulate(cache, by_code, None, label, score_filter=fn)
        s = P.stat(tr, tpx)
        if not s:
            print(f'{label:<18}{"— 無交易":>7}')
            continue
        rows.append((label, s))
        print(f'{label:<18}{s["n"]:>7}{s["ret"]:>+8.2f}%{s["mkt"]:>+9.2f}%'
              f'{s["alpha"]:>+8.2f}%{s["win"]:>7.1f}%')
    print('=' * 88)

    if not rows:
        return
    al = [s['alpha'] for _, s in rows]
    spread = max(al) - min(al)
    ns = [s['n'] for _, s in rows]
    print(f'\n五組 alpha 全距　{spread:.2f}pp　（各組 n {min(ns)}~{max(ns)}）')

    print('\n雜訊帶（從基準組重抽，看純運氣能造成多大落差）：')
    worst = 0
    for n in sorted(set([min(ns), int(stt.median(ns)), max(ns)])):
        nb = noise_band(base_tr, tpx, n)
        if nb:
            lo, mid, hi, w = nb
            worst = max(worst, w)
            print(f'   n={n:<5} alpha 5~95% 分位 {lo:+.2f}% ~ {hi:+.2f}%　帶寬 {w:.2f}pp')

    print()
    if spread < worst:
        print(f'⇒ 全距 {spread:.2f}pp **小於**雜訊帶 {worst:.2f}pp')
        print('   → 各組無法區分。**不可解讀這張表的排序**。')
        print('   → 正確結論是「這個測試的解析度不足以驗證門檻」，')
        print('     不是「門檻無效」——沒測到差異 ≠ 證明沒有差異。')
    else:
        print(f'⇒ 全距 {spread:.2f}pp **大於**雜訊帶 {worst:.2f}pp　→ 差異開始有意義，可以往下看是哪一組。')
        print('   ⚠️ 但仍要檢查：排序是否單調？是否被單一子期間帶走？（分期間重跑一次）')

    # 勝率也一起看——2026-09-17 兩次都發現 ≥65 的勝率是五組最低
    print('\n勝率（2026-09-17 兩次都是 ≥65 最低，列出來持續追蹤）：')
    for label, s in rows:
        se = (s['win'] / 100 * (1 - s['win'] / 100) / s['n']) ** 0.5 * 100
        print(f'   {label:<18}{s["win"]:>6.1f}%　±{se:.1f}pp（二項式標準誤）')


if __name__ == '__main__':
    main()
