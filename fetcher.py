# ════════════════════════════════════════
# fetcher.py　資料抓取
# 負責從 TWSE / TPEx 抓取所有資料
# ════════════════════════════════════════

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import time
from datetime import datetime, timedelta
from database import (save_prices, save_fundamental, save_chips,
                      save_stock_info, log_update)

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# ── 工具函式 ────────────────────────────
def clean_num(s):
    if not s or s in ('--', '-', '', 'X', '除息', '除權', '除權息', '停止交易'):
        return 0.0
    try:
        return float(str(s).replace(',', '').replace('+', '').strip())
    except:
        return 0.0

def twse_date_to_std(d):
    d = str(d).strip()
    # 有斜線：115/05/22
    if '/' in d:
        parts = d.split('/')
        if len(parts) == 3:
            return f'{int(parts[0])+1911}-{parts[1]}-{parts[2]}'
    # 無斜線8碼：1150522 或 20260522
    if len(d) == 7:
        # 民國7碼：1150522
        return f'{int(d[:3])+1911}-{d[3:5]}-{d[5:7]}'
    if len(d) == 8:
        # 西元8碼：20260522
        return f'{d[:4]}-{d[4:6]}-{d[6:8]}'
    return d

# ── 抓全市場股票清單 ─────────────────────
def fetch_stock_list():
    print('抓取股票清單...')
    results = []

    # 上市
    try:
        url = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        for s in data:
            code = s.get('公司代號','').strip()
            name = s.get('公司簡稱','').strip()
            industry = s.get('產業別','').strip()
            if code and name:
                save_stock_info(code, name, 'TWSE', industry)
                results.append({'code':code,'name':name,'market':'TWSE'})
        print(f'上市股票：{len(results)} 筆')
    except Exception as e:
        print(f'抓取上市清單失敗：{e}')

    # 上櫃
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        otc_count = 0
        for s in data:
            code = s.get('SecuritiesCompanyCode','').strip()
            name = s.get('CompanyName','').strip()
            if code and name:
                save_stock_info(code, name, 'TPEx', '')
                otc_count += 1
        print(f'上櫃股票：{otc_count} 筆')
    except Exception as e:
        print(f'抓取上櫃清單失敗：{e}')

    return results

# ── 抓當日全市場收盤價 ───────────────────
def fetch_today_prices():
    print('抓取今日收盤價...')
    count = 0

    # 上市
    try:
        url = 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        for s in data:
            code  = s.get('Code','').strip()
            date  = twse_date_to_std(s.get('Date',''))
            close = clean_num(s.get('ClosingPrice',''))
            open_ = clean_num(s.get('OpeningPrice',''))
            high  = clean_num(s.get('HighestPrice',''))
            low   = clean_num(s.get('LowestPrice',''))
            vol   = clean_num(s.get('TradeVolume',''))
            val   = clean_num(s.get('TradeValue',''))
            chg   = clean_num(s.get('Change',''))
            pct   = round(chg / (close - chg) * 100, 2) if (close - chg) != 0 else 0
            if code and close > 0:
                save_prices(code, [{'date':date,'open':open_,'high':high,
                                    'low':low,'close':close,'volume':int(vol),
                                    'value':val,'change':chg,'change_pct':pct}])
                count += 1
        print(f'上市收盤價：{count} 筆')
    except Exception as e:
        print(f'抓取上市收盤失敗：{e}')

    # 上櫃
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        otc_count = 0
        today = datetime.now().strftime('%Y-%m-%d')
        for s in data:
            code  = s.get('SecuritiesCompanyCode','').strip()
            close = clean_num(s.get('Close',''))
            open_ = clean_num(s.get('Open',''))
            high  = clean_num(s.get('High',''))
            low   = clean_num(s.get('Low',''))
            vol   = clean_num(s.get('TradeVolume',''))
            val   = clean_num(s.get('TradeValue',''))
            chg   = clean_num(s.get('Change',''))
            pct   = round(chg / (close - chg) * 100, 2) if (close - chg) != 0 else 0
            if code and close > 0:
                save_prices(code, [{'date':today,'open':open_,'high':high,
                                    'low':low,'close':close,'volume':int(vol),
                                    'value':val,'change':chg,'change_pct':pct}])
                otc_count += 1
        print(f'上櫃收盤價：{otc_count} 筆')
    except Exception as e:
        print(f'抓取上櫃收盤失敗：{e}')

# ── 抓基本面（PE / 殖利率 / PB）─────────
def fetch_fundamentals():
    print('抓取基本面資料...')
    count = 0
    try:
        url = 'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        today = datetime.now().strftime('%Y-%m-%d')
        for s in data:
            code = s.get('Code','').strip()
            pe   = clean_num(s.get('PEratio',''))
            pb   = clean_num(s.get('PBratio',''))
            div  = clean_num(s.get('DividendYield',''))
            if code:
                # EPS 從收盤價 ÷ PE 反推（近四季TTM估算）
                from database import get_prices as _gp
                _prices = _gp(code, days=1)
                _close = _prices[-1]['close'] if _prices else 0
                eps = round(_close / pe, 2) if pe and pe > 0 and _close > 0 else 0.0
                save_fundamental(code, today, eps, pe, pb, div)
                count += 1
        print(f'基本面資料：{count} 筆')
    except Exception as e:
        print(f'抓取基本面失敗：{e}')

# ── 抓三大法人 ───────────────────────────
def fetch_chips():
    print('抓取三大法人資料...')
    count = 0
    try:
        today = datetime.now().strftime('%Y%m%d')
        url = f'https://www.twse.com.tw/rwd/zh/fund/T86?date={today}&selectType=ALLBUT0999&response=json'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        date_str = datetime.now().strftime('%Y-%m-%d')

        if data.get('stat') == 'OK':
            for row in data.get('data', []):
                try:
                    code = row[0].strip()
                    chips = {
                        'foreign_buy':  round(clean_num(row[2]) / 1000),
                        'foreign_sell': round(clean_num(row[3]) / 1000),
                        'foreign_net':  round(clean_num(row[4]) / 1000),
                        'trust_buy':    round(clean_num(row[11]) / 1000),
                        'trust_sell':   round(clean_num(row[12]) / 1000),
                        'trust_net':    round(clean_num(row[13]) / 1000),
                        'dealer_buy':   round(clean_num(row[5]) / 1000),
                        'dealer_sell':  round(clean_num(row[6]) / 1000),
                        'dealer_net':   round(clean_num(row[7]) / 1000),
                        'margin_balance': 0,
                        'short_balance':  0,
                    }
                    save_chips(code, date_str, chips)
                    count += 1
                except:
                    pass
            print(f'三大法人：{count} 筆')
        else:
            # 今日資料未發布，嘗試抓前一個交易日
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            url2 = f'https://www.twse.com.tw/rwd/zh/fund/T86?date={yesterday}&selectType=ALLBUT0999&response=json'
            r2 = requests.get(url2, headers=HEADERS, timeout=15)
            data2 = r2.json()
            if data2.get('stat') == 'OK':
                # 取得實際日期
                date_str2 = data2.get('date', yesterday)
                try:
                    y = int(date_str2[:3]) + 1911
                    m = date_str2[3:5]
                    d = date_str2[5:7]
                    date_str = f'{y}-{m}-{d}'
                except:
                    date_str = datetime.now().strftime('%Y-%m-%d')
                for row in data2.get('data', []):
                    try:
                        code = row[0].strip()
                        chips = {
                            'foreign_buy':  round(clean_num(row[2]) / 1000),
                            'foreign_sell': round(clean_num(row[3]) / 1000),
                            'foreign_net':  round(clean_num(row[4]) / 1000),
                            'trust_buy':    round(clean_num(row[11]) / 1000),
                            'trust_sell':   round(clean_num(row[12]) / 1000),
                            'trust_net':    round(clean_num(row[13]) / 1000),
                            'dealer_buy':   round(clean_num(row[5]) / 1000),
                            'dealer_sell':  round(clean_num(row[6]) / 1000),
                            'dealer_net':   round(clean_num(row[7]) / 1000),
                            'margin_balance': 0,
                            'short_balance':  0,
                        }
                        save_chips(code, date_str, chips)
                        count += 1
                    except:
                        pass
                print(f'三大法人（前一交易日）：{count} 筆')
            else:
                print('三大法人資料尚未發布')
    except Exception as e:
        print(f'抓取三大法人失敗：{e}')
            

# ── 抓融資融券 ───────────────────────────
def fetch_margin():
    print('抓取融資融券資料...')
    count = 0
    try:
        today = datetime.now().strftime('%Y%m%d')
        url = f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={today}&selectType=ALL&response=json'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        date_str = datetime.now().strftime('%Y-%m-%d')

        # 找融資融券彙總表（第二個 table）
        tables = data.get('tables', [])
        margin_table = None
        for t in tables:
            if '融資融券彙總' in t.get('title', ''):
                margin_table = t
                break

        if not margin_table:
            # 嘗試前一個交易日
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            url2 = f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={yesterday}&selectType=ALL&response=json'
            r2 = requests.get(url2, headers=HEADERS, timeout=15, verify=False)
            data2 = r2.json()
            tables2 = data2.get('tables', [])
            for t in tables2:
                if '融資融券彙總' in t.get('title', ''):
                    margin_table = t
                    # 取得實際日期
                    date_tw = data2.get('date', yesterday)
                    try:
                        y = int(date_tw[:3]) + 1911
                        m = date_tw[3:5]
                        d = date_tw[5:7]
                        date_str = f'{y}-{m}-{d}'
                    except:
                        pass
                    break

        if margin_table:
            for row in margin_table.get('data', []):
                try:
                    code   = row[0].strip()
                    margin = clean_num(row[6])   # 融資今日餘額
                    short  = clean_num(row[12])  # 融券今日餘額
                    conn_db = __import__('database').get_conn()
                    c = conn_db.cursor()
                    c.execute('''
                        UPDATE chips SET margin_balance=?, short_balance=?
                        WHERE code=? AND date=?
                    ''', (margin, short, code, date_str))
                    conn_db.commit()
                    conn_db.close()
                    count += 1
                except:
                    pass
            print(f'融資融券：{count} 筆')
        else:
            print('融資融券資料尚未發布')
    except Exception as e:
        print(f'抓取融資融券失敗：{e}')

# ── 抓個股歷史資料（補齊歷史）───────────
def fetch_history(code, months=3):
    print(f'抓取 {code} 歷史資料...')
    all_rows = []
    today = datetime.now()

    for i in range(months - 1, -1, -1):
        d = datetime(today.year, today.month, 1) - timedelta(days=i*30)
        date_str = d.strftime('%Y%m%d')
        try:
            url = f'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={date_str}&stockNo={code}&response=json'
            r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            data = r.json()
            if data.get('stat') == 'OK':
                for row in data.get('data', []):
                    try:
                        date  = twse_date_to_std(row[0])
                        vol   = clean_num(row[1])
                        val   = clean_num(row[2])
                        open_ = clean_num(row[3])
                        high  = clean_num(row[4])
                        low   = clean_num(row[5])
                        close = clean_num(row[6])
                        chg   = clean_num(row[7])
                        pct   = round(chg / (close - chg) * 100, 2) if (close - chg) != 0 else 0
                        if close > 0:
                            all_rows.append({
                                'date':date,'open':open_,'high':high,
                                'low':low,'close':close,'volume':int(vol),
                                'value':val,'change':chg,'change_pct':pct
                            })
                    except:
                        pass
            time.sleep(0.5)
        except Exception as e:
            print(f'抓取歷史失敗 {code} {date_str}：{e}')

    if all_rows:
        save_prices(code, all_rows)
        print(f'{code} 歷史資料：{len(all_rows)} 筆')
    return all_rows

# ── 每日完整更新流程 ─────────────────────
def fetch_all():
    print(f'\n開始更新資料 {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('='*40)
    errors = []

    try:
        fetch_today_prices()
    except Exception as e:
        errors.append(f'收盤價：{e}')

    time.sleep(1)

    try:
        fetch_fundamentals()
    except Exception as e:
        errors.append(f'基本面：{e}')

    time.sleep(1)

    try:
        fetch_chips()
    except Exception as e:
        errors.append(f'三大法人：{e}')

    time.sleep(1)

    try:
        fetch_margin()
    except Exception as e:
        errors.append(f'融資融券：{e}')

    if errors:
        msg = '部分失敗：' + '、'.join(errors)
        log_update('WARNING', msg)
        print(f'\n⚠️  {msg}')
    else:
        log_update('OK', '全部更新成功')
        print('\n✅ 全部更新成功')

    print('='*40)
# ── 抓個股歷史籌碼資料 ───────────────────
def fetch_chips_history(code, months=3):
    """
    修正版：T86 API 每次只回傳單一交易日資料，
    必須逐個平日（週一到週五）分別查詢，才能取得完整歷史。
    加入已存在日期的跳過邏輯，避免重複抓取。
    """
    print(f'抓取 {code} 歷史籌碼資料...')
    today = datetime.now()
    count = 0

    # 計算起始日期（N個月前的月初）
    start_d = datetime(today.year, today.month, 1) - timedelta(days=(months - 1) * 30)
    start_date = datetime(start_d.year, start_d.month, 1)

    # 查詢 DB 已有的日期，避免重複抓取
    try:
        from database import get_conn as _get_conn
        _conn = _get_conn()
        _c = _conn.cursor()
        _c.execute('SELECT date FROM chips WHERE code=?', (code,))
        existing_dates = {r[0] for r in _c.fetchall()}
        _conn.close()
    except Exception:
        existing_dates = set()

    # 產生所有平日（週一到週五）的查詢清單
    dates_to_query = []
    cur = start_date
    while cur.date() <= today.date():
        if cur.weekday() < 5:  # 週一到週五
            if cur.strftime('%Y-%m-%d') not in existing_dates:
                dates_to_query.append(cur.strftime('%Y%m%d'))
        cur += timedelta(days=1)

    if not dates_to_query:
        print(f'{code} 歷史籌碼已是最新，共 {len(existing_dates)} 筆')
        return len(existing_dates)

    print(f'  需補齊 {len(dates_to_query)} 個交易日（已有 {len(existing_dates)} 筆）...')

    seen_dates = set()  # 同一實際交易日只存一次
    for date_str in dates_to_query:
        try:
            url = (f'https://www.twse.com.tw/rwd/zh/fund/T86'
                   f'?date={date_str}&selectType=ALLBUT0999&response=json')
            r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            data = r.json()

            if data.get('stat') == 'OK':
                # 取得 API 回傳的實際交易日期（民國年7碼，如 1150522）
                date_tw = data.get('date', '')
                try:
                    if len(date_tw) == 7:
                        date_std = (f'{int(date_tw[:3])+1911}'
                                    f'-{date_tw[3:5]}-{date_tw[5:7]}')
                    else:
                        # 防呆：格式不符時用查詢日期推算
                        date_std = (f'{date_str[:4]}-{date_str[4:6]}'
                                    f'-{date_str[6:8]}')
                except Exception:
                    date_std = today.strftime('%Y-%m-%d')

                # 同一實際交易日跳過（假日前後 API 可能回傳同一天資料）
                if date_std in seen_dates or date_std in existing_dates:
                    time.sleep(0.3)
                    continue
                seen_dates.add(date_std)

                for row in data.get('data', []):
                    try:
                        if row[0].strip() != code:
                            continue
                        chips = {
                            'foreign_buy':  round(clean_num(row[2])  / 1000),
                            'foreign_sell': round(clean_num(row[3])  / 1000),
                            'foreign_net':  round(clean_num(row[4])  / 1000),
                            'trust_buy':    round(clean_num(row[11]) / 1000),
                            'trust_sell':   round(clean_num(row[12]) / 1000),
                            'trust_net':    round(clean_num(row[13]) / 1000),
                            'dealer_buy':   round(clean_num(row[5])  / 1000),
                            'dealer_sell':  round(clean_num(row[6])  / 1000),
                            'dealer_net':   round(clean_num(row[7])  / 1000),
                            'margin_balance': 0,
                            'short_balance':  0,
                        }
                        save_chips(code, date_std, chips)
                        count += 1
                    except Exception:
                        pass
            # 非交易日 API 回傳 stat != OK，直接跳過即可
            time.sleep(0.5)
        except Exception as e:
            print(f'抓取籌碼歷史失敗 {code} {date_str}：{e}')

    total = len(existing_dates) + count
    print(f'{code} 歷史籌碼資料：新增 {count} 筆（合計 {total} 筆）')
    return count
if __name__ == '__main__':
    fetch_all()
