# ════════════════════════════════════════
# scorer.py　綜合評分與說明文字生成
# 負責計算評分、生成說明文字、進出場建議
# ════════════════════════════════════════

from config import (WEIGHT_FUNDAMENTAL, WEIGHT_TECHNICAL, WEIGHT_CHIPS,
                    STOP_LOSS_RATIO, GRADE)

# ── 評級判斷 ────────────────────────────
def get_grade(score):
    for threshold in sorted(GRADE.keys(), reverse=True):
        if score >= threshold:
            return GRADE[threshold]
    return GRADE[0]

# ── 基本面評分 ───────────────────────────
def score_fundamental(fund):
    score = 50
    reasons = []

    pe  = fund.get('pe')
    pb  = fund.get('pb')
    div = fund.get('dividend_yield')
    eps = fund.get('eps_ttm')

    # PE 評分
    if pe and pe > 0:
        if pe < 10:
            score += 25
            reasons.append(f'本益比{pe:.1f}倍極低（低於10倍），評價非常便宜')
        elif pe < 15:
            score += 20
            reasons.append(f'本益比{pe:.1f}倍偏低（10～15倍），評價便宜')
        elif pe < 20:
            score += 10
            reasons.append(f'本益比{pe:.1f}倍合理（15～20倍），符合台股平均')
        elif pe < 30:
            score += 5
            reasons.append(f'本益比{pe:.1f}倍略高（20～30倍），尚在可接受範圍')
        elif pe < 50:
            score -= 10
            reasons.append(f'本益比{pe:.1f}倍偏高（30～50倍），需確認獲利成長支撐')
        else:
            score -= 20
            reasons.append(f'本益比{pe:.1f}倍極高（超過50倍），評價昂貴需謹慎')

    # 殖利率評分
    if div and div > 0:
        if div > 6:
            score += 20
            reasons.append(f'殖利率{div:.2f}%極高（超過6%），遠高於定存利率')
        elif div > 5:
            score += 15
            reasons.append(f'殖利率{div:.2f}%很高（5～6%），高於市場平均3.2%')
        elif div > 3:
            score += 8
            reasons.append(f'殖利率{div:.2f}%正常（3～5%），高於定存利率')
        elif div > 1:
            score += 3
            reasons.append(f'殖利率{div:.2f}%偏低（1～3%），接近定存水準')
        else:
            score -= 5
            reasons.append(f'殖利率{div:.2f}%極低（低於1%），配息吸引力不足')

    # PB 評分
    if pb and pb > 0:
        if pb < 1:
            score += 15
            reasons.append(f'股價淨值比{pb:.2f}倍低於1，股價低於帳面價值')
        elif pb < 1.5:
            score += 10
            reasons.append(f'股價淨值比{pb:.2f}倍偏低（低於1.5倍），評價合理偏低')
        elif pb < 3:
            score += 5
            reasons.append(f'股價淨值比{pb:.2f}倍合理（1.5～3倍）')
        elif pb < 5:
            score -= 5
            reasons.append(f'股價淨值比{pb:.2f}倍偏高（3～5倍）')
        else:
            score -= 10
            reasons.append(f'股價淨值比{pb:.2f}倍極高（超過5倍），需高獲利支撐')

    # EPS 評分
    if eps is not None:
        if eps < 0:
            score -= 25
            reasons.append(f'EPS為負（{eps:.2f}元），公司目前虧損')
        elif eps < 1:
            score -= 10
            reasons.append(f'EPS僅{eps:.2f}元，獲利能力偏弱')
        elif eps < 5:
            score += 3
            reasons.append(f'EPS {eps:.2f}元，獲利正常')
        elif eps < 15:
            score += 8
            reasons.append(f'EPS {eps:.2f}元，獲利能力良好')
        elif eps < 30:
            score += 12
            reasons.append(f'EPS {eps:.2f}元，獲利能力強')
        else:
            score += 15
            reasons.append(f'EPS {eps:.2f}元，獲利能力極強')

    score = max(0, min(100, score))
    return score, reasons

# ── 技術面評分 ───────────────────────────
def score_technical(ind, close):
    score = 50
    reasons = []

    ma5  = ind.get('ma5')
    ma20 = ind.get('ma20')
    ma60 = ind.get('ma60')
    rsi  = ind.get('rsi')
    k    = ind.get('k')
    d    = ind.get('d')
    macd_dif  = ind.get('macd_dif')
    macd_def  = ind.get('macd_def')
    macd_hist = ind.get('macd_hist')
    vol_ratio = ind.get('vol_ratio')
    ma_trend  = ind.get('ma_trend')
    pos_65    = ind.get('pos_65')

    # 均線排列評分
    if ma_trend == 'bullish':
        score += 20
        reasons.append(f'均線多頭排列（MA5={ma5} > MA20={ma20} > MA60={ma60}），趨勢向上')
    elif ma_trend == 'bearish':
        score -= 20
        reasons.append(f'均線空頭排列（MA5={ma5} < MA20={ma20} < MA60={ma60}），趨勢向下')
    else:
        reasons.append(f'均線糾結，方向不明確，建議觀望')

    # 收盤價與均線關係
    if ma20 and close:
        if close > ma20 * 1.05:
            score += 5
            reasons.append(f'收盤價（{close}）站在MA20（{ma20}）上方5%以上，短期偏強')
        elif close > ma20:
            score += 10
            reasons.append(f'收盤價（{close}）站在MA20（{ma20}）上方，短期趨勢正面')
        elif close > ma20 * 0.95:
            score -= 10
            reasons.append(f'收盤價（{close}）跌破MA20（{ma20}），需觀察能否回到均線上方')
        else:
            score -= 20
            reasons.append(f'收盤價（{close}）大幅低於MA20（{ma20}），趨勢偏弱')

    # RSI 評分
    if rsi:
        if rsi > 80:
            score -= 15
            reasons.append(f'RSI(14)={rsi}，超過80已超買，近期回檔機率較高')
        elif rsi > 70:
            score -= 5
            reasons.append(f'RSI(14)={rsi}，介於70～80，動能偏強但接近警戒區')
        elif rsi >= 40:
            score += 10
            reasons.append(f'RSI(14)={rsi}，介於40～70，動能健康')
        elif rsi >= 30:
            score += 5
            reasons.append(f'RSI(14)={rsi}，介於30～40，動能偏弱但尚未超賣')
        else:
            score += 15
            reasons.append(f'RSI(14)={rsi}，低於30已超賣，歷史上常出現反彈機會')

    # KD 評分
    if k and d:
        if k > 80 and k > d:
            score -= 10
            reasons.append(f'KD：K={k} D={d}，高檔黃金交叉，短期超買需注意')
        elif k < 20 and k < d:
            score += 10
            reasons.append(f'KD：K={k} D={d}，低檔死亡交叉，可能出現反彈')
        elif k > d:
            score += 8
            reasons.append(f'KD：K={k} D={d}，K值在D值上方，短期偏多')
        else:
            score -= 8
            reasons.append(f'KD：K={k} D={d}，K值在D值下方，短期偏空')

    # MACD 評分
    if macd_dif and macd_def and macd_hist:
        if macd_dif > macd_def and macd_hist > 0:
            score += 10
            reasons.append(f'MACD：DIF={macd_dif} > DEF={macd_def}，柱狀正值，多頭訊號')
        elif macd_dif < macd_def and macd_hist < 0:
            score -= 10
            reasons.append(f'MACD：DIF={macd_dif} < DEF={macd_def}，柱狀負值，空頭訊號')
        else:
            reasons.append(f'MACD：DIF={macd_dif}，DEF={macd_def}，方向待確認')

    # 量能評分
    if vol_ratio:
        if vol_ratio > 2.0:
            score += 10
            reasons.append(f'今日成交量是近20個交易日均量的{vol_ratio}倍，明顯異常放量')
        elif vol_ratio > 1.5:
            score += 8
            reasons.append(f'今日成交量是近20個交易日均量的{vol_ratio}倍，明顯放量')
        elif vol_ratio > 1.0:
            score += 5
            reasons.append(f'今日成交量是近20個交易日均量的{vol_ratio}倍，溫和放量')
        elif vol_ratio > 0.8:
            reasons.append(f'今日成交量是近20個交易日均量的{vol_ratio}倍，量能正常')
        else:
            score -= 8
            reasons.append(f'今日成交量是近20個交易日均量的{vol_ratio}倍，明顯縮量')

    # 近3個月位置評分
    if pos_65 is not None:
        if pos_65 > 80:
            score -= 5
            reasons.append(f'目前股價位於近3個月（65個交易日）區間的{pos_65}%，接近高點')
        elif pos_65 > 50:
            score += 5
            reasons.append(f'目前股價位於近3個月（65個交易日）區間的{pos_65}%，中間偏高')
        elif pos_65 > 20:
            score += 8
            reasons.append(f'目前股價位於近3個月（65個交易日）區間的{pos_65}%，中間偏低')
        else:
            score += 12
            reasons.append(f'目前股價位於近3個月（65個交易日）區間的{pos_65}%，接近低點')

    score = max(0, min(100, score))
    return score, reasons

# ── 籌碼面評分 ───────────────────────────
def score_chips(chips_list, ownership):
    score = 50
    reasons = []

    if not chips_list:
        return score, ['籌碼資料不足，無法評分']

    # 近5日三大法人
    recent5  = chips_list[-5:]  if len(chips_list) >= 5  else chips_list
    recent20 = chips_list[-20:] if len(chips_list) >= 20 else chips_list

    foreign_net5  = sum(r.get('foreign_net', 0) for r in recent5)
    foreign_net20 = sum(r.get('foreign_net', 0) for r in recent20)
    trust_net5    = sum(r.get('trust_net',   0) for r in recent5)

    # 外資近5日
    if foreign_net5 > 10000:
        score += 20
        reasons.append(f'外資近5個交易日大量買超（+{foreign_net5:,}張），法人積極佈局')
    elif foreign_net5 > 3000:
        score += 12
        reasons.append(f'外資近5個交易日買超（+{foreign_net5:,}張），法人偏多')
    elif foreign_net5 > 0:
        score += 5
        reasons.append(f'外資近5個交易日小幅買超（+{foreign_net5:,}張）')
    elif foreign_net5 > -3000:
        score -= 5
        reasons.append(f'外資近5個交易日小幅賣超（{foreign_net5:,}張）')
    elif foreign_net5 > -10000:
        score -= 12
        reasons.append(f'外資近5個交易日賣超（{foreign_net5:,}張），法人偏空')
    else:
        score -= 20
        reasons.append(f'外資近5個交易日大量賣超（{foreign_net5:,}張），法人積極出脫')

    # 外資近20日
    if foreign_net20 > 0:
        score += 8
        reasons.append(f'外資近20個交易日（1個月）累計買超（+{foreign_net20:,}張），持續偏多')
    else:
        score -= 8
        reasons.append(f'外資近20個交易日（1個月）累計賣超（{foreign_net20:,}張），持續偏空')

    # 投信近5日
    if trust_net5 > 1000:
        score += 10
        reasons.append(f'投信近5個交易日買超（+{trust_net5:,}張），投信看好')
    elif trust_net5 > 0:
        score += 5
        reasons.append(f'投信近5個交易日小幅買超（+{trust_net5:,}張）')
    elif trust_net5 < -1000:
        score -= 10
        reasons.append(f'投信近5個交易日賣超（{trust_net5:,}張），投信看空')
    else:
        score -= 3
        reasons.append(f'投信近5個交易日小幅賣超（{trust_net5:,}張）')

    # 融資餘額變化
    if len(chips_list) >= 20:
        margin_now  = chips_list[-1].get('margin_balance', 0)
        margin_20   = chips_list[-20].get('margin_balance', 0)
        if margin_20 > 0:
            margin_chg = (margin_now - margin_20) / margin_20 * 100
            if margin_chg < -10:
                score += 10
                reasons.append(f'融資餘額較20個交易日前減少{abs(margin_chg):.1f}%，籌碼趨穩')
            elif margin_chg < 0:
                score += 5
                reasons.append(f'融資餘額較20個交易日前小幅減少{abs(margin_chg):.1f}%，偏正面')
            elif margin_chg > 20:
                score -= 10
                reasons.append(f'融資餘額較20個交易日前大增{margin_chg:.1f}%，借錢追高風險提高')
            elif margin_chg > 5:
                score -= 5
                reasons.append(f'融資餘額較20個交易日前增加{margin_chg:.1f}%，需留意')

    # 外資持股比例
    foreign_pct = ownership.get('foreign', 0)
    if foreign_pct > 60:
        score += 10
        reasons.append(f'外資持股比例{foreign_pct}%極高，法人高度認可')
    elif foreign_pct > 40:
        score += 6
        reasons.append(f'外資持股比例{foreign_pct}%，法人持股比例正常偏高')
    elif foreign_pct > 20:
        score += 3
        reasons.append(f'外資持股比例{foreign_pct}%，法人持股正常')
    else:
        score -= 5
        reasons.append(f'外資持股比例{foreign_pct}%偏低，法人關注度不高')

    score = max(0, min(100, score))
    return score, reasons

# ── 綜合評分 ────────────────────────────
def calc_total_score(fund_score, tech_score, chip_score):
    total = round(
        fund_score * WEIGHT_FUNDAMENTAL +
        tech_score * WEIGHT_TECHNICAL   +
        chip_score * WEIGHT_CHIPS
    )
    return max(0, min(100, total))

# ── 買賣條件判斷 ─────────────────────────
def check_conditions(ind, chips_list, close, market_chg_5d=None):
    buy_conditions  = []
    sell_conditions = []

    ma20      = ind.get('ma20')
    rsi       = ind.get('rsi')
    vol_ratio = ind.get('vol_ratio')
    buy_low   = ind.get('buy_low')
    buy_high  = ind.get('buy_high')
    stop_loss = ind.get('stop_loss')

    # ── 買進條件 ────────────────────────
    # 條件1：價格在買進區間
    if buy_low and buy_high and close:
        if buy_low <= close <= buy_high:
            buy_conditions.append({
                'status': 'pass',
                'text': f'✅ 條件1：股價（{close}元）在買進參考區間（{buy_low}～{buy_high}元）內'
            })
        elif close < buy_low:
            buy_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 條件1：股價（{close}元）低於買進區間（{buy_low}元以下），可能繼續下跌，建議觀察'
            })
        else:
            buy_conditions.append({
                'status': 'fail',
                'text': f'❌ 條件1：股價（{close}元）高於買進區間（{buy_high}元以上），追高風險較高'
            })

    # 條件2：量能
    if vol_ratio:
        if vol_ratio >= 1.0:
            buy_conditions.append({
                'status': 'pass',
                'text': f'✅ 條件2：今日成交量（{vol_ratio}倍近20個交易日均量）有足夠買盤支撐'
            })
        else:
            buy_conditions.append({
                'status': 'fail',
                'text': f'❌ 條件2：今日成交量（{vol_ratio}倍近20個交易日均量）偏低，買盤不積極'
            })

    # 條件3：RSI
    if rsi:
        if 40 <= rsi <= 70:
            buy_conditions.append({
                'status': 'pass',
                'text': f'✅ 條件3：RSI(14)={rsi}，介於40～70健康區間，動能正常非超買'
            })
        elif rsi > 70:
            buy_conditions.append({
                'status': 'fail',
                'text': f'❌ 條件3：RSI(14)={rsi}，超過70已偏高，追買風險較大'
            })
        else:
            buy_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 條件3：RSI(14)={rsi}，低於40動能偏弱，建議等待回穩'
            })

    # 條件4：大盤
    if market_chg_5d is not None:
        if market_chg_5d >= -3:
            buy_conditions.append({
                'status': 'pass',
                'text': f'✅ 條件4：加權指數近5個交易日變化{market_chg_5d:+.1f}%，大盤環境尚可'
            })
        else:
            buy_conditions.append({
                'status': 'fail',
                'text': f'❌ 條件4：加權指數近5個交易日下跌{abs(market_chg_5d):.1f}%（超過3%警戒線），大盤偏弱'
            })

    # ── 出場條件 ────────────────────────
    # 條件1：跌破MA20
    if ma20 and close:
        days_below = 0
        if close < ma20:
            days_below = 1
        if days_below > 0:
            sell_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 出場條件1：收盤價（{close}元）已跌破MA20（{ma20}元），需觀察是否連續3個交易日收盤低於MA20'
            })
        else:
            sell_conditions.append({
                'status': 'pass',
                'text': f'✅ 出場條件1：收盤價（{close}元）在MA20（{ma20}元）上方，尚未觸發'
            })

    # 條件2：RSI超買
    if rsi:
        if rsi > 80:
            sell_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 出場條件2：RSI(14)={rsi}已超過80，短期漲幅過快，考慮減碼'
            })
        else:
            sell_conditions.append({
                'status': 'pass',
                'text': f'✅ 出場條件2：RSI(14)={rsi}未超過80，尚未觸發'
            })

    # 條件3：外資連續大量賣超
    if chips_list and len(chips_list) >= 5:
        recent5_net = [r.get('foreign_net', 0) for r in chips_list[-5:]]
        consecutive_sell = all(n < 0 for n in recent5_net)
        total_sell5 = sum(recent5_net)
        if consecutive_sell and abs(total_sell5) > 30000:
            sell_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 出場條件3：外資連續5個交易日賣超且合計超過3萬張（{total_sell5:,}張），法人明顯撤退'
            })
        else:
            sell_conditions.append({
                'status': 'pass',
                'text': f'✅ 出場條件3：外資未連續5個交易日大量賣超，尚未觸發'
            })

    # 條件4：跌破停損價
    if stop_loss and close:
        if close <= stop_loss:
            sell_conditions.append({
                'status': 'warn',
                'text': f'⚠️ 出場條件4：股價（{close}元）已跌破停損價（{stop_loss}元），建議執行停損保護資金'
            })
        else:
            sell_conditions.append({
                'status': 'pass',
                'text': f'✅ 出場條件4：股價（{close}元）未跌破停損價（{stop_loss}元），尚未觸發'
            })

    return buy_conditions, sell_conditions

# ── 自動生成備註摘要 ─────────────────────
def generate_auto_note(code, name, close, total_score,
                        fund_score, tech_score, chip_score,
                        fund_reasons, tech_reasons, chip_reasons,
                        ind, fund):
    grade = get_grade(total_score)
    ma20  = ind.get('ma20')
    rsi   = ind.get('rsi')
    buy_low  = ind.get('buy_low')
    buy_high = ind.get('buy_high')
    target   = ind.get('target')
    stop     = ind.get('stop_loss')
    pe  = fund.get('pe')
    div = fund.get('dividend_yield')
    eps = fund.get('eps_ttm')

    lines = []
    lines.append(f'【{name}（{code}）綜合評分：{total_score}分 / {grade}】')
    lines.append('')

    # 評分原因摘要
    lines.append('評分原因：')
    lines.append(f'・基本面{fund_score}分：' + (fund_reasons[0] if fund_reasons else '資料不足'))
    lines.append(f'・技術面{tech_score}分：' + (tech_reasons[0] if tech_reasons else '資料不足'))
    lines.append(f'・籌碼面{chip_score}分：' + (chip_reasons[0] if chip_reasons else '資料不足'))
    lines.append('')

    # 主要數字
    lines.append('主要指標：')
    if pe:    lines.append(f'・本益比：{pe:.1f}倍')
    if div:   lines.append(f'・殖利率：{div:.2f}%')
    if eps:   lines.append(f'・EPS(TTM)：{eps:.2f}元')
    if rsi:   lines.append(f'・RSI(14)：{rsi}')
    if ma20:  lines.append(f'・MA20：{ma20}元，目前收盤{close}元（{"上方" if close > ma20 else "下方"}）')
    lines.append('')

    # 建議價位
    lines.append('建議價位：')
    if buy_low and buy_high:
        lines.append(f'・買進參考區間：{buy_low}～{buy_high}元')
    if target:
        lines.append(f'・目標參考價：{target}元')
    if stop:
        lines.append(f'・停損參考價：{stop}元')
    lines.append('')

    # 主要風險
    risk = []
    if pe and pe > 30:
        risk.append(f'本益比{pe:.1f}倍偏高，若獲利不如預期評價面臨修正壓力')
    if rsi and rsi > 70:
        risk.append(f'RSI={rsi}偏高，短期回檔機率增加')
    if close and ma20 and close < ma20:
        risk.append(f'股價跌破MA20（{ma20}元），短期趨勢轉弱')
    if risk:
        lines.append('主要風險：')
        for r in risk:
            lines.append(f'・{r}')

    return '\n'.join(lines)

# ── 完整評分流程 ─────────────────────────
def full_score(prices, fund_data, chips_list, ownership,
               market_chg_5d=None):
    from indicators import calc_all

    if not prices:
        return None

    ind   = calc_all(prices)
    close = prices[-1]['close'] if prices else 0

    # 取最新基本面
    fund = fund_data[-1] if fund_data else {}

    # 評分
    fund_score, fund_reasons = score_fundamental(fund)
    tech_score, tech_reasons = score_technical(ind, close)
    chip_score, chip_reasons = score_chips(chips_list, ownership)
    total = calc_total_score(fund_score, tech_score, chip_score)
    grade = get_grade(total)

    # 買賣條件
    buy_cond, sell_cond = check_conditions(
        ind, chips_list, close, market_chg_5d
    )

    return {
        'close':        close,
        'indicators':   ind,
        'fund':         fund,
        'fund_score':   fund_score,
        'tech_score':   tech_score,
        'chip_score':   chip_score,
        'total_score':  total,
        'grade':        grade,
        'fund_reasons': fund_reasons,
        'tech_reasons': tech_reasons,
        'chip_reasons': chip_reasons,
        'buy_conditions':  buy_cond,
        'sell_conditions': sell_cond,
    }


if __name__ == '__main__':
    print('scorer.py 載入成功')
