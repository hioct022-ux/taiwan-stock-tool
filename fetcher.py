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
                      save_stock_info, log_update,
                      save_futures_institutional, get_futures_institutional)

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
    # 有斜線：115/05/22（民國）或 2026/05/22（西元）
    if '/' in d:
        parts = d.split('/')
        if len(parts) == 3:
            year = int(parts[0])
            if year < 1911:   # 民國年
                year += 1911
            return f'{year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}'
    # 7碼：只有開頭是 '1' 才是民國（如 1150522）
    if len(d) == 7 and d[0] == '1':
        return f'{int(d[:3])+1911}-{d[3:5]}-{d[5:7]}'
    # 8碼西元：20260522
    if len(d) == 8:
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
def _parse_twse_csv_all(content_bytes):
    """
    解析 TWSE STOCK_DAY_ALL?date=YYYYMMDD 回傳的 CSV。
    格式（utf-8）：
      日期,證券代號,證券名稱,成交股數,成交金額,開盤價,最高價,最低價,收盤價,漲跌價差,成交筆數
      "1150624","0050","元大台灣50","235939737",...
    回傳 (list[dict], actual_date_str)
    """
    import csv, io
    text = content_bytes.decode('utf-8', errors='ignore')
    rows_out = []
    actual_date = None
    reader = csv.reader(io.StringIO(text))
    for i, row in enumerate(reader):
        if i == 0:   # 標題行
            continue
        if len(row) < 11:
            continue
        try:
            raw_date = row[0].strip().strip('"')
            date     = twse_date_to_std(raw_date)   # "1150624" → "2026-06-24"
            code     = row[1].strip().strip('"')
            open_    = clean_num(row[5])
            high     = clean_num(row[6])
            low      = clean_num(row[7])
            close    = clean_num(row[8])
            chg      = clean_num(row[9])
            vol      = clean_num(row[3])
            val      = clean_num(row[4])
            pct      = round(chg / (close - chg) * 100, 2) if (close - chg) != 0 else 0
            if code and close > 0:
                if actual_date is None:
                    actual_date = date
                rows_out.append({'code': code, 'date': date,
                                 'open': open_, 'high': high, 'low': low,
                                 'close': close, 'volume': int(vol),
                                 'value': val, 'change': chg, 'change_pct': pct})
        except Exception:
            pass
    return rows_out, actual_date


def fetch_today_prices():
    """抓取今日全市場收盤價，回傳實際資料日期（TWSE 回傳的交易日，非今天）或 None。"""
    print('抓取今日收盤價...')
    count = 0
    twse_actual_date = None   # 記錄 TWSE API 回傳的實際交易日，供上櫃使用
    today_str = datetime.now().strftime('%Y%m%d')

    # 上市
    # 優先策略：帶日期參數的 CSV 端點（最可靠，即使無日期版本返回舊資料也能取到正確日期）
    # 備援：無日期 JSON 端點（有時返回舊資料）、OpenAPI（有時延遲）
    twse_sources = [
        ('csv_with_date', f'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?date={today_str}'),
        ('json_no_date',  'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json'),
        ('openapi',       'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'),
    ]
    for src_type, twse_url in twse_sources:
        try:
            r = requests.get(twse_url, headers=HEADERS, timeout=20, verify=False)

            if src_type == 'csv_with_date':
                # CSV 格式（帶日期參數時 response=json 無效，一律返回 CSV）
                parsed_rows, actual_date = _parse_twse_csv_all(r.content)
                if not parsed_rows:
                    raise ValueError('CSV 解析結果為空')
                for row in parsed_rows:
                    save_prices(row['code'], [row])
                    count += 1
                twse_actual_date = actual_date
            else:
                resp = r.json()
                if isinstance(resp, dict) and resp.get('stat') == 'OK':
                    # 網頁端 JSON 格式
                    raw_date = resp.get('date', '')
                    date     = twse_date_to_std(raw_date)
                    rows     = resp.get('data', [])
                    for row in rows:
                        try:
                            code  = str(row[0]).strip()
                            open_ = clean_num(row[4])
                            high  = clean_num(row[5])
                            low   = clean_num(row[6])
                            close = clean_num(row[7])
                            chg   = clean_num(row[8])
                            vol   = clean_num(row[2])
                            val   = clean_num(row[3])
                            pct   = round(chg / (close - chg) * 100, 2) if (close - chg) != 0 else 0
                            if code and close > 0:
                                if twse_actual_date is None:
                                    twse_actual_date = date
                                save_prices(code, [{'date':date,'open':open_,'high':high,
                                                    'low':low,'close':close,'volume':int(vol),
                                                    'value':val,'change':chg,'change_pct':pct}])
                                count += 1
                        except Exception:
                            pass
                elif isinstance(resp, list):
                    # OpenAPI 格式
                    for s in resp:
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
                            if twse_actual_date is None:
                                twse_actual_date = date
                            save_prices(code, [{'date':date,'open':open_,'high':high,
                                                'low':low,'close':close,'volume':int(vol),
                                                'value':val,'change':chg,'change_pct':pct}])
                            count += 1
                else:
                    raise ValueError('未預期的回應格式')

            print(f'上市收盤價：{count} 筆（來源：{src_type}，實際交易日：{twse_actual_date}）')
            break   # 成功就不再嘗試備援

        except Exception as e:
            print(f'上市收盤失敗（{src_type}）：{e}，嘗試備援...')

    if count == 0:
        print('上市收盤價：所有來源均失敗')

    # 上櫃
    # 重要：TPEx API 沒有回傳日期欄位，必須沿用 TWSE 取得的實際交易日
    # 絕對不可使用 datetime.now() — 那會讓週末執行時產生錯誤日期的資料
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        otc_count = 0

        # 強制使用 TWSE 取得的實際交易日，不採用 TPEx API 回傳的日期欄位
        # 原因：TPEx API 的 Date 欄位會在盤後即時更新為今日，
        #       但 TWSE STOCK_DAY_ALL 有時會延遲更新，兩者可能出現不同日期。
        #       以 TWSE 日期為基準，確保 DB 內所有股票使用同一個交易日。
        if not twse_actual_date:
            print('上櫃收盤價：跳過（無法從 TWSE 取得實際交易日）')
        else:
            otc_date = twse_actual_date  # 永遠沿用 TWSE 實際交易日

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
                    save_prices(code, [{'date':otc_date,'open':open_,'high':high,
                                        'low':low,'close':close,'volume':int(vol),
                                        'value':val,'change':chg,'change_pct':pct}])
                    otc_count += 1
            print(f'上櫃收盤價：{otc_count} 筆（日期：{otc_date}）')
    except Exception as e:
        print(f'抓取上櫃收盤失敗：{e}')

    return twse_actual_date  # 回傳實際資料日期，None 表示失敗

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
                date_str2 = str(data2.get('date', yesterday)).strip()
                try:
                    if len(date_str2) == 7 and date_str2[0] == '1':  # 民國年 1YYMMDD
                        date_str = f'{int(date_str2[:3])+1911}-{date_str2[3:5]}-{date_str2[5:7]}'
                    elif len(date_str2) == 8 and date_str2[0] == '2':  # 西元年 YYYYMMDD
                        date_str = f'{date_str2[:4]}-{date_str2[4:6]}-{date_str2[6:8]}'
                    else:
                        date_str = datetime.now().strftime('%Y-%m-%d')
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
            

# ── 抓大盤整體融資融券 ────────────────────
def _parse_market_margin_response(data, date_std_fb):
    """解析 MI_MARGN MS 回傳，回傳 (date_str, result_dict) 或 (None, None)"""
    def parse_date_tw(s, fallback):
        s = str(s).strip()
        try:
            if len(s) == 7 and s[0] == '1':
                return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
            if len(s) == 8 and s[0] == '2':
                return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
        except Exception:
            pass
        return fallback

    if data.get('stat') != 'OK':
        return None, None

    date_str = parse_date_tw(data.get('date', ''), date_std_fb)
    tables = data.get('tables', []) or []

    margin_lots = margin_buy = margin_sell = 0
    margin_amount = 0
    short_balance = short_buy = short_sell = 0

    for tbl in tables:
        for row in tbl.get('data', []):
            if not row:
                continue
            label = str(row[0]).strip()
            vals  = [clean_num(v) for v in row[1:]]
            if len(vals) < 5:
                continue
            try:
                if label == '融資(交易單位)':
                    margin_buy   = int(vals[0])
                    margin_sell  = int(vals[1])
                    margin_lots  = int(vals[4])
                elif '融資金額' in label:
                    margin_amount = int(vals[4])
                elif label == '融券(交易單位)':
                    short_sell    = int(vals[0])
                    short_buy     = int(vals[1])
                    short_balance = int(vals[4])
            except Exception:
                pass

    margin_balance = round(margin_amount / 100000) if margin_amount > 0 else margin_lots
    if margin_balance == 0 and short_balance == 0:
        return None, None

    return date_str, {
        'margin_balance': margin_balance,
        'margin_buy':     margin_buy,
        'margin_sell':    margin_sell,
        'short_balance':  short_balance,
        'short_buy':      short_buy,
        'short_sell':     short_sell,
    }


def fetch_market_margin_history(months=3):
    """補抓大盤融資融券歷史（逐交易日查詢，較慢）"""
    from database import save_market_margin, get_market_margin_last_date
    last = get_market_margin_last_date()
    today = datetime.now()
    start = today - timedelta(days=months * 31)
    cur = start
    count = 0
    print(f'補抓大盤融資融券歷史（{months} 個月）...')
    while cur.date() <= today.date():
        if cur.weekday() < 5:
            date_yyyymmdd = cur.strftime('%Y%m%d')
            date_std = cur.strftime('%Y-%m-%d')
            if last and date_std <= last:
                cur += timedelta(days=1)
                continue
            url = (f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN'
                   f'?date={date_yyyymmdd}&selectType=MS&response=json')
            try:
                r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
                d, result = _parse_market_margin_response(r.json(), date_std)
                if d and result:
                    save_market_margin(d, result)
                    count += 1
                time.sleep(0.4)
            except Exception as e:
                print(f'  {date_std} 失敗：{e}')
        cur += timedelta(days=1)
    print(f'大盤融資融券歷史補齊：{count} 筆')
    return count


def fetch_market_margin():
    """
    抓取全市場融資融券彙總資料（MI_MARGN selectType=MS）。
    儲存到 market_margin 表。
    """
    from database import save_market_margin, get_market_margin_last_date, get_latest_price_date

    twse_date = get_latest_price_date('2330') or datetime.now().strftime('%Y-%m-%d')
    last = get_market_margin_last_date()
    if last and last >= twse_date:
        print(f'大盤融資融券已是最新（{last}），略過')
        return

    # 若歷史資料不足 60 筆，先補抓歷史
    from database import get_market_margin
    existing = get_market_margin(days=5)
    if len(existing) < 3:
        fetch_market_margin_history(months=3)
        return

    def parse_date_tw(s, fallback):
        s = str(s).strip()
        try:
            if len(s) == 7 and s[0] == '1':
                return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
            if len(s) == 8 and s[0] == '2':
                return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
        except Exception:
            pass
        return fallback

    # 最多往前找 5 天
    for days_back in range(0, 6):
        try_d = (datetime.now() - timedelta(days=days_back))
        if try_d.weekday() >= 5:
            continue
        date_yyyymmdd = try_d.strftime('%Y%m%d')
        date_std_fb   = try_d.strftime('%Y-%m-%d')

        url = (f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN'
               f'?date={date_yyyymmdd}&selectType=MS&response=json')
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            data = r.json()
        except Exception as e:
            print(f'大盤融資融券請求失敗（{date_yyyymmdd}）：{e}')
            continue

        if data.get('stat') != 'OK':
            continue

        date_str = parse_date_tw(data.get('date', ''), date_std_fb)

        # 已有此日資料就跳過
        if last and date_str <= last:
            print(f'大盤融資融券已有 {date_str}，略過')
            return

        # 解析彙總表：找包含「融資」「餘額」的 table
        tables = data.get('tables', []) or []
        # 有時候直接是 data key（非 tables）
        if not tables and data.get('data'):
            tables = [data]

        margin_balance = short_balance = 0
        margin_buy = margin_sell = short_buy = short_sell = 0

        # API 欄位：['項目','買進','賣出','現金(券)償還','前日餘額','今日餘額']
        # vals 索引：  0      1      2        3            4         5  （row[1:]）
        margin_lots = margin_buy = margin_sell = 0   # 融資（張）
        margin_amount = 0                             # 融資金額（千元）
        short_balance = short_buy = short_sell = 0   # 融券（張）

        for tbl in tables:
            for row in tbl.get('data', []):
                if not row:
                    continue
                label = str(row[0]).strip()
                vals  = [clean_num(v) for v in row[1:]]
                if len(vals) < 5:
                    continue
                try:
                    if label == '融資(交易單位)':
                        margin_buy   = int(vals[0])
                        margin_sell  = int(vals[1])
                        margin_lots  = int(vals[4])   # 今日餘額（張）
                    elif '融資金額' in label:
                        margin_amount = int(vals[4])  # 今日餘額（千元）
                    elif label == '融券(交易單位)':
                        short_sell    = int(vals[0])
                        short_buy     = int(vals[1])
                        short_balance = int(vals[4])  # 今日餘額（張）
                except Exception:
                    pass

        # margin_balance 儲存為億元（整數），融資金額仟元 ÷ 100000
        margin_balance = round(margin_amount / 100000) if margin_amount > 0 else margin_lots

        if margin_balance > 0 or short_balance > 0:
            save_market_margin(date_str, {
                'margin_balance': margin_balance,   # 億元
                'margin_buy':     margin_buy,       # 張
                'margin_sell':    margin_sell,       # 張
                'short_balance':  short_balance,    # 張
                'short_buy':      short_buy,        # 張
                'short_sell':     short_sell,       # 張
            })
            print(f'大盤融資融券儲存完成（{date_str}）：融資={margin_balance:,} 億元，融券={short_balance:,} 張')
            return
        else:
            print(f'大盤融資融券無法解析（{date_yyyymmdd}），嘗試前一天...')

    print('大盤融資融券：所有日期均無資料')


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

        # ── 找融資融券彙總表，同時取得 API 回傳的實際交易日期 ──
        def parse_date_tw(date_tw, fallback):
            try:
                s = str(date_tw).strip()
                if len(s) == 7 and s[0] == '1':   # 民國年 1YYMMDD
                    return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
                if len(s) == 8 and s[0] == '2':   # 西元年 YYYYMMDD
                    return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
            except Exception:
                pass
            return fallback

        tables = data.get('tables', [])
        margin_table = None
        for t in tables:
            if '融資融券彙總' in t.get('title', ''):
                margin_table = t
                # 修正：從 API 回傳的實際日期更新 date_str（避免週末日期錯誤）
                date_str = parse_date_tw(
                    data.get('date', today),
                    datetime.now().strftime('%Y-%m-%d')
                )
                break

        if not margin_table:
            # 往前最多找 5 天（應對連假）
            for days_back in range(1, 6):
                prev = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
                prev_std = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
                url2 = f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={prev}&selectType=ALL&response=json'
                try:
                    r2 = requests.get(url2, headers=HEADERS, timeout=15, verify=False)
                    data2 = r2.json()
                    for t in data2.get('tables', []):
                        if '融資融券彙總' in t.get('title', ''):
                            margin_table = t
                            date_str = parse_date_tw(data2.get('date', prev), prev_std)
                            break
                    if margin_table:
                        print(f'融資融券：使用 {date_str} 的資料')
                        break
                    time.sleep(0.3)
                except Exception:
                    pass

        if margin_table:
            conn_db = __import__('database').get_conn()
            c = conn_db.cursor()
            for row in margin_table.get('data', []):
                try:
                    code   = row[0].strip()
                    margin = clean_num(row[6])   # 融資今日餘額
                    short  = clean_num(row[12])  # 融券今日餘額
                    # 先嘗試更新已有的行
                    c.execute('''
                        UPDATE chips SET margin_balance=?, short_balance=?
                        WHERE code=? AND date=?
                    ''', (margin, short, code, date_str))
                    # 若那天還沒有 chips 資料，就新增一行（僅記錄融資融券）
                    if c.rowcount == 0:
                        c.execute('''
                            INSERT OR IGNORE INTO chips
                            (code, date, foreign_buy, foreign_sell, foreign_net,
                             trust_buy, trust_sell, trust_net,
                             dealer_buy, dealer_sell, dealer_net,
                             margin_balance, short_balance)
                            VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?)
                        ''', (code, date_str, margin, short))
                    count += 1
                except:
                    pass
            conn_db.commit()
            conn_db.close()
            print(f'融資融券：{count} 筆（日期：{date_str}）')
        else:
            print('融資融券資料尚未發布')
    except Exception as e:
        print(f'抓取融資融券失敗：{e}')

# ── 回填歷史融資融券資料 ─────────────────
def fetch_margin_history(max_dates=30):
    """
    找出 chips 表中融資融券全部為 0 的歷史日期，
    逐日向 MI_MARGN 補抓，最多回填 max_dates 個交易日。
    每次 fetch_all() 呼叫，會漸進補齊歷史資料。
    """
    from database import get_conn as _gc
    conn = _gc()
    # 找出「全部 margin_balance=0」的日期（代表該日從未回填過）
    rows = conn.execute('''
        SELECT date FROM chips
        GROUP BY date
        HAVING SUM(margin_balance) = 0
        ORDER BY date DESC
        LIMIT ?
    ''', (max_dates,)).fetchall()
    conn.close()

    dates_to_fill = [r[0] for r in rows if r[0]]
    if not dates_to_fill:
        print('融資融券歷史：無需回填')
        return

    print(f'融資融券歷史：回填 {len(dates_to_fill)} 個交易日...')
    filled = 0
    conn = _gc()
    c = conn.cursor()

    def parse_date_tw(s, fallback):
        try:
            s = str(s).strip()
            if len(s) == 7 and s[0] == '1':
                return f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
            if len(s) == 8 and s[0] == '2':
                return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
        except Exception:
            pass
        return fallback

    for date_std in dates_to_fill:
        date_str = date_std.replace('-', '')
        url = (f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN'
               f'?date={date_str}&selectType=ALL&response=json')
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            data = r.json()
            if data.get('stat') != 'OK':
                time.sleep(0.3)
                continue
            # 確認實際交易日期
            actual_date = parse_date_tw(data.get('date', date_str), date_std)
            if actual_date != date_std:
                time.sleep(0.3)
                continue  # 假日回傳前一交易日資料，跳過
            margin_table = None
            for t in data.get('tables', []):
                if '融資融券彙總' in t.get('title', ''):
                    margin_table = t
                    break
            if not margin_table:
                time.sleep(0.3)
                continue
            for row in margin_table.get('data', []):
                try:
                    code   = str(row[0]).strip()
                    margin = clean_num(row[6])
                    short  = clean_num(row[12])
                    c.execute('''
                        UPDATE chips SET margin_balance=?, short_balance=?
                        WHERE code=? AND date=?
                    ''', (margin, short, code, actual_date))
                except Exception:
                    pass
            conn.commit()
            filled += 1
            print(f'  回填 {actual_date} 完成')
            time.sleep(0.5)
        except Exception as e:
            print(f'  回填 {date_std} 失敗：{e}')
            time.sleep(0.3)

    conn.close()
    print(f'融資融券歷史回填完成：{filled} 個交易日')

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


def fetch_history_tpex(code, months=15):
    """補抓上櫃（TPEx）個股歷史價格，使用 yfinance（代碼格式：XXXX.TWO）"""
    print(f'抓取上櫃 {code} 歷史資料（yfinance）...')
    try:
        import yfinance as yf
        ticker = yf.Ticker(f'{code}.TWO')
        period = f'{min(months, 24)}mo'
        hist = ticker.history(period=period)
        if hist.empty:
            print(f'{code} yfinance 無資料')
            return []
        all_rows = []
        for ts, row in hist.iterrows():
            try:
                date_str = ts.strftime('%Y-%m-%d')
                close = round(float(row['Close']), 2)
                open_ = round(float(row['Open']),  2)
                high  = round(float(row['High']),  2)
                low   = round(float(row['Low']),   2)
                vol   = int(row['Volume'] / 1000)  # 股→張
                if close > 0:
                    all_rows.append({
                        'date': date_str, 'open': open_, 'high': high,
                        'low': low, 'close': close, 'volume': vol,
                        'value': 0, 'change': 0, 'change_pct': 0
                    })
            except Exception:
                pass
        if all_rows:
            save_prices(code, all_rows)
            print(f'{code} 上櫃歷史資料：{len(all_rows)} 筆')
        return all_rows
    except ImportError:
        print('yfinance 未安裝，請執行：pip install yfinance')
        return []
    except Exception as e:
        print(f'{code} yfinance 失敗：{e}')
        return []


def fetch_history_auto(code, months=15):
    """自動判斷上市/上櫃，呼叫對應的歷史補抓函數"""
    from database import get_conn
    conn = get_conn()
    row = conn.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone()
    conn.close()
    market = row[0] if row else 'TWSE'
    if market == 'TPEx':
        return fetch_history_tpex(code, months=months)
    else:
        return fetch_history(code, months=months)


def fetch_fundamentals_tpex_all():
    """
    從櫃買中心 OpenAPI 一次抓取全部上櫃股的 PE/PB/殖利率，
    只更新資料庫中已存在的上櫃股（watchlist 或 stocks 表）。
    API: https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis
    回傳欄位：SecuritiesCompanyCode, StockName, PerRatio, PbRatio, DividendYield
    """
    print('抓取上櫃基本面（批次）...')
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis'
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if r.status_code != 200 or not r.text.strip():
            print(f'上櫃基本面 API 無回應（status={r.status_code}）')
            return
        data = r.json()
        today = datetime.now().strftime('%Y-%m-%d')

        # 建立 code→資料 查找表
        tpex_map = {}
        for s in data:
            code = str(s.get('SecuritiesCompanyCode', '') or s.get('Code', '')).strip()
            if not code:
                continue
            pe  = clean_num(s.get('PerRatio')  or s.get('PEratio', ''))
            pb  = clean_num(s.get('PbRatio')   or s.get('PBratio', ''))
            div = clean_num(s.get('DividendYield', ''))
            tpex_map[code] = (pe, pb, div)

        if not tpex_map:
            print('上櫃基本面：API 回傳空資料，欄位名稱可能已更動')
            # 印出第一筆方便偵錯
            if data:
                print(f'  第一筆範例：{list(data[0].keys())}')
            return

        # 只更新 stocks 表中 market=TPEx 的股票
        from database import get_conn as _gc, save_fundamental as _sf, get_prices as _gp
        conn = _gc()
        tpex_codes = [r[0] for r in conn.execute(
            "SELECT code FROM stocks WHERE market='TPEx'"
        ).fetchall()]
        conn.close()

        count = 0
        for code in tpex_codes:
            if code not in tpex_map:
                continue
            pe, pb, div = tpex_map[code]
            prices = _gp(code, days=1)
            close  = prices[-1]['close'] if prices else 0
            eps    = round(close / pe, 2) if pe and pe > 0 and close > 0 else 0.0
            _sf(code, today, eps, pe, pb, div)
            count += 1

        print(f'上櫃基本面（批次）：更新 {count} 筆（API 共 {len(tpex_map)} 支）')
    except Exception as e:
        print(f'上櫃基本面批次抓取失敗：{e}')


def fetch_fundamentals_tpex(code):
    """
    用 yfinance 抓取上櫃個股基本面（PE、PB、殖利率）。
    yfinance ticker.info 包含 trailingPE、priceToBook、trailingAnnualDividendYield 等欄位。
    """
    print(f'抓取上櫃 {code} 基本面（yfinance）...')
    try:
        import yfinance as yf
        ticker = yf.Ticker(f'{code}.TWO')
        info = ticker.info
        if not info or info.get('regularMarketPrice') is None:
            print(f'{code} yfinance info 無資料')
            return

        pe  = info.get('trailingPE') or info.get('forwardPE') or 0.0
        pb  = info.get('priceToBook') or 0.0
        div = (info.get('trailingAnnualDividendYield') or 0.0) * 100  # 轉成百分比

        # EPS 從收盤價 ÷ PE 反推（近四季TTM）
        close = info.get('regularMarketPrice') or info.get('currentPrice') or 0.0
        eps = round(close / pe, 2) if pe and pe > 0 and close > 0 else 0.0

        today = datetime.now().strftime('%Y-%m-%d')
        save_fundamental(code, today, eps, pe, pb, div)
        print(f'{code} 基本面：EPS={eps}, PE={pe}, PB={pb}, 殖利率={div:.2f}%')
    except ImportError:
        print('yfinance 未安裝，請執行：pip install yfinance')
    except Exception as e:
        print(f'{code} yfinance 基本面失敗：{e}')


def fetch_fundamentals_auto(code):
    """自動判斷上市/上櫃，抓取對應的基本面資料"""
    from database import get_conn
    conn = get_conn()
    row = conn.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone()
    conn.close()
    market = row[0] if row else 'TWSE'
    if market == 'TPEx':
        fetch_fundamentals_tpex(code)
    else:
        # TWSE 基本面由全市場 fetch_fundamentals() 統一抓，這裡只做單股補抓
        fetch_fundamentals_tpex(code)  # 上市也可用 yfinance 補抓單股


# ── 每日完整更新流程 ─────────────────────
# ── 抓外資持股比率 ───────────────────────
def fetch_ownership():
    """從 TWSE MI_QFIIS 抓取全市場外資持股比率（每日更新）"""
    print('抓取外資持股比率...')
    count = 0
    try:
        url = ('https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS'
               '?response=json&selectType=ALLBUT0999')
        r    = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        resp = r.json()

        if resp.get('stat') != 'OK':
            print(f'外資持股比率：API 回傳非 OK（{resp.get("stat")}）')
            return

        raw_date = resp.get('date', '')          # e.g. "20260525"
        date     = twse_date_to_std(raw_date)    # → "2026-05-25"
        rows     = resp.get('data', [])
        # fields: 證券代號(0), 證券名稱(1), ISIN(2), 發行股數(3),
        #         尚可投資股數(4), 全體持有股數(5), 尚可投資比率(6),
        #         全體外資持股比率(7), ...
        from database import save_ownership
        for row in rows:
            try:
                code        = str(row[0]).strip()
                foreign_pct = float(row[7])          # 全體外資及陸資持股比率
                if code:
                    save_ownership(code, foreign_pct, date)
                    count += 1
            except (ValueError, IndexError):
                pass
        print(f'外資持股比率：{count} 筆（日期：{date}）')
    except Exception as e:
        print(f'抓取外資持股比率失敗：{e}')


def fetch_all():
    print(f'\n開始更新資料 {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('='*40)
    errors = []

    _twse_data_date = None
    try:
        _twse_data_date = fetch_today_prices()
    except Exception as e:
        errors.append(f'收盤價：{e}')

    # 如果 TWSE 回傳的不是今天的資料，記錄警告（TWSE 有時延遲發布）
    _today_str = datetime.now().strftime('%Y-%m-%d')
    if _twse_data_date and _twse_data_date != _today_str:
        print(f'⚠️  TWSE 回傳的是 {_twse_data_date} 的資料（今天是 {_today_str}），尚未發布今日資料')
        errors.append(f'TWSE 尚未發布今日({_today_str})收盤資料，目前最新為 {_twse_data_date}')

    time.sleep(1)

    try:
        fetch_fundamentals()
    except Exception as e:
        errors.append(f'基本面：{e}')

    time.sleep(1)

    try:
        fetch_fundamentals_tpex_all()
    except Exception as e:
        errors.append(f'上櫃基本面：{e}')

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

    time.sleep(1)

    # 歷史融資融券回填（每次補最多 30 個未填日期，漸進完成）
    try:
        fetch_margin_history(max_dates=30)
    except Exception as e:
        errors.append(f'融資融券歷史：{e}')

    time.sleep(1)

    try:
        fetch_ownership()
    except Exception as e:
        errors.append(f'外資持股：{e}')

    time.sleep(1)

    # ── 自選股歷史補齊（資料不足 60 天就自動補抓）──
    try:
        from database import get_watchlist, get_prices as _gp, get_chips as _gchips, get_conn as _gcc
        watchlist = get_watchlist()
        for w in watchlist:
            code = w['code']
            # 取得市場別
            _conn_w = _gcc()
            _mkt_w = (_conn_w.execute('SELECT market FROM stocks WHERE code=?', (code,)).fetchone() or [None])[0]
            _conn_w.close()

            existing = _gp(code, days=60)
            if len(existing) < 60:
                print(f'[補齊] {code} 價格歷史不足（{len(existing)} 筆），補抓中...')
                if _mkt_w == 'TPEx':
                    fetch_history_tpex(code, months=15)
                else:
                    fetch_history(code, months=3)
                time.sleep(1)

            # 上櫃股不支援 T86 籌碼，跳過
            if _mkt_w == 'TPEx':
                continue

            existing_chips = _gchips(code, days=60)
            if len(existing_chips) < 30:
                print(f'[補齊] {code} 籌碼歷史不足（{len(existing_chips)} 筆），補抓中...')
                fetch_chips_history(code, months=3)
                time.sleep(1)
    except Exception as e:
        errors.append(f'歷史補齊：{e}')

    # ── ETF 成分股（每月更新一次）──────────────
    try:
        from database import get_etf_last_update
        last_etf = get_etf_last_update()
        need_etf = True
        if last_etf:
            from datetime import datetime as _dt
            days_since = (_dt.now() - _dt.strptime(last_etf[:10], '%Y-%m-%d')).days
            need_etf = days_since >= 30
        if need_etf:
            print('ETF 成分股資料已過期，開始更新...')
            fetch_etf_holdings()
        else:
            print(f'ETF 成分股資料尚新（上次：{last_etf[:10]}），略過')
    except Exception as e:
        errors.append(f'ETF成分股：{e}')

    # ── 三大法人買賣超排行（T86）──────────────
    try:
        fetch_t86()
    except Exception as e:
        errors.append(f'T86排行：{e}')

    # ── 加權指數歷史（大盤走勢）────────────────
    try:
        fetch_taiex()
    except Exception as e:
        errors.append(f'加權指數：{e}')

    # ── 大盤融資融券彙總 ──────────────────────
    try:
        fetch_market_margin()
    except Exception as e:
        errors.append(f'大盤融資融券：{e}')

    # ── 大盤本益比 ────────────────────────────
    try:
        fetch_market_pe()
    except Exception as e:
        errors.append(f'大盤本益比：{e}')

    # ── 台指期三大法人未平倉 ──────────────────
    try:
        futures_data = get_futures_institutional(days=5)
        if len(futures_data) < 3:
            fetch_futures_institutional_history(months=3)
        else:
            fetch_futures_institutional()
    except Exception as e:
        errors.append(f'台指期未平倉：{e}')

    time.sleep(1)

    # ── 選擇權 P/C 比率 ──────────────────────
    try:
        from database import get_options_pc
        pc_data = get_options_pc(days=5)
        if len(pc_data) < 3:
            fetch_options_pc_history(months=3)
        else:
            fetch_options_pc()
    except Exception as e:
        errors.append(f'P/C比率：{e}')

    time.sleep(1)

    # ── 除權息資料（最後執行，避免被 TWSE 限流）──
    time.sleep(3)
    try:
        fetch_exdividend()
    except Exception as e:
        errors.append(f'除權息：{e}')

    if errors:
        msg = '部分失敗：' + '、'.join(errors)
        # TWSE 未發布今日資料是可預期的情況，用 PENDING 狀態而非 WARNING
        if any('尚未發布' in e for e in errors):
            non_twse_errors = [e for e in errors if '尚未發布' not in e]
            if non_twse_errors:
                log_update('WARNING', '部分失敗：' + '、'.join(non_twse_errors) + f'（TWSE 資料日期：{_twse_data_date}）')
            else:
                log_update('PENDING', f'TWSE 尚未發布今日收盤資料，目前最新為 {_twse_data_date}')
        else:
            log_update('WARNING', msg)
        print(f'\n⚠️  {msg}')
    else:
        log_update('OK', '全部更新成功')
        print('\n✅ 全部更新成功')

    print('='*40)

# ── 工具：從 BWIBBU_ALL 個股資料計算市場中位數 PE/PB/殖利率 ──
def _calc_market_pe_from_bwibbu(date_yyyymmdd):
    """
    呼叫 TWSE BWIBBU_ALL，回傳 (date_std, pe_median, pb_median, dy_median)。
    以上市個股中位數計算（排除負值、異常值、無資料）。
    回傳 None 表示失敗。
    """
    url = (f'https://www.twse.com.tw/exchangeReport/BWIBBU_ALL'
           f'?response=json&date={date_yyyymmdd}&selectType=ALL')
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        data = r.json()
    except Exception as e:
        print(f'  BWIBBU_ALL 請求失敗（{date_yyyymmdd}）：{e}')
        return None

    if data.get('stat') != 'OK':
        return None

    # 解析欄位順序：["股票代號","股票名稱","本益比","殖利率(%)","股價淨值比"]
    fields = data.get('fields', [])
    try:
        pe_idx = next(i for i, f in enumerate(fields) if '本益比' in f)
        dy_idx = next(i for i, f in enumerate(fields) if '殖利率' in f)
        pb_idx = next(i for i, f in enumerate(fields) if '淨值比' in f)
    except StopIteration:
        pe_idx, dy_idx, pb_idx = 2, 3, 4

    pes, dys, pbs = [], [], []
    for row in (data.get('data') or []):
        def safe_float(v):
            try:
                f = float(str(v).replace(',', '').strip())
                return f if f > 0 else None
            except:
                return None
        pe = safe_float(row[pe_idx]) if len(row) > pe_idx else None
        dy = safe_float(row[dy_idx]) if len(row) > dy_idx else None
        pb = safe_float(row[pb_idx]) if len(row) > pb_idx else None
        # 排除明顯異常值（PE > 200 視為極端值）
        if pe and pe <= 200:
            pes.append(pe)
        if dy:
            dys.append(dy)
        if pb and pb <= 30:
            pbs.append(pb)

    if not pes:
        return None

    pes.sort(); dys.sort(); pbs.sort()
    def median(lst):
        n = len(lst)
        return (lst[n // 2] if n % 2 else (lst[n // 2 - 1] + lst[n // 2]) / 2) if lst else None

    # API date 欄位是西元年8碼（如 20260530），直接轉換
    raw_date = str(data.get('date', '')).strip()
    if len(raw_date) == 8:
        date_std = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}'
    else:
        date_std = twse_date_to_std(raw_date) if raw_date else datetime.strptime(date_yyyymmdd, '%Y%m%d').strftime('%Y-%m-%d')

    return date_std, round(median(pes), 2), round(median(pbs), 2) if pbs else None, round(median(dys), 2) if dys else None


# ── 大盤本益比（每日更新）──────────────────
def fetch_market_pe():
    """從 TWSE BWIBBU_ALL 計算市場中位數本益比並存入 DB。"""
    from database import save_market_pe, get_market_pe_last_date
    last = get_market_pe_last_date()

    for days_back in range(0, 6):
        try_d = datetime.now() - timedelta(days=days_back)
        if try_d.weekday() >= 5:
            continue
        date_yyyymmdd = try_d.strftime('%Y%m%d')
        date_std      = try_d.strftime('%Y-%m-%d')
        if last and date_std <= last:
            print(f'大盤本益比已是最新（{last}），略過')
            return

        result = _calc_market_pe_from_bwibbu(date_yyyymmdd)
        if result:
            date_std, pe, pb, dy = result
            save_market_pe(date_std, pe, pb, dy)
            print(f'大盤本益比：{date_std} PE中位數={pe} PB={pb} 殖利率={dy}%')
            return

    print('大盤本益比：今日無資料（非交易日或 API 無回應）')


# ── 大盤本益比歷史補抓（僅抓今日，歷史靠每日累積）──
def fetch_market_pe_history(months=6):
    """BWIBBU_ALL 不支援歷史查詢，改為只儲存今日資料作為起始點。"""
    print('大盤本益比：TWSE API 不支援歷史查詢，今日資料已儲存，往後每日自動累積。')
    fetch_market_pe()
    return 1


# ── 抓即將除權息名單 ──────────────────────
def fetch_exdividend():
    """
    兩階段抓取除權息資料：
    1. TWT48U（早期預告）：120+ 筆，含所有已公告除息日的股票，is_confirmed=0
    2. TWT49U（正式確認）：最近幾天已確認的名單，is_confirmed=1，覆蓋預告資料
    """
    import re as _re
    from database import save_exdividend

    def parse_tw_date(s):
        m = _re.match(r'(\d+)年(\d+)月(\d+)日', str(s).strip())
        if m:
            return f'{int(m.group(1))+1911}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}'
        return ''

    def fetch_url(url):
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
                if resp.text.strip():
                    return resp.json()
            except Exception as e:
                print(f'  第{attempt+1}次失敗：{e}')
            time.sleep(2)
        return None

    # ── Step 1：TWT48U 早期預告 ──
    print('抓取除權息早期預告（TWT48U）...')
    data48 = fetch_url('https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json')
    rows_early = []
    if data48 and data48.get('stat') == 'OK':
        for r in data48.get('data', []):
            try:
                ex_date = parse_tw_date(r[0])
                if not ex_date:
                    continue
                code = str(r[1]).strip()
                name = str(r[2]).strip()
                div_type = str(r[3]).strip()
                # r[7] 可能是數字或 HTML「待公告」
                raw_div = str(r[7])
                div_value = clean_num(raw_div) if '<' not in raw_div else 0.0
                prev_close = float(clean_num(r[11])) if r[11] else 0.0
                if code:
                    rows_early.append({
                        'ex_date': ex_date, 'code': code, 'name': name,
                        'prev_close': prev_close, 'ref_price': 0.0,
                        'div_value': div_value, 'div_type': div_type,
                        'is_confirmed': 0,
                    })
            except Exception:
                continue
        if rows_early:
            save_exdividend(rows_early)
            print(f'除權息早期預告：{len(rows_early)} 筆')

    time.sleep(1)

    # ── Step 2：TWT49U 正式確認（覆蓋預告）──
    print('抓取除權息正式確認（TWT49U）...')
    data49 = fetch_url('https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json')
    rows_confirmed = []
    if data49 and data49.get('stat') == 'OK':
        for r in data49.get('data', []):
            try:
                ex_date    = parse_tw_date(r[0])
                if not ex_date:
                    continue
                code       = str(r[1]).strip()
                name       = str(r[2]).strip()
                prev_close = float(clean_num(r[3]))
                ref_price  = float(clean_num(r[4]))
                div_value  = float(clean_num(r[5]))
                div_type   = str(r[6]).strip()
                if code:
                    rows_confirmed.append({
                        'ex_date': ex_date, 'code': code, 'name': name,
                        'prev_close': prev_close, 'ref_price': ref_price,
                        'div_value': div_value, 'div_type': div_type,
                        'is_confirmed': 1,
                    })
            except Exception:
                continue
        if rows_confirmed:
            save_exdividend(rows_confirmed)
            print(f'除權息正式確認：{len(rows_confirmed)} 筆（已覆蓋預告）')
        else:
            print('除權息正式確認：目前無新資料')
    else:
        print('除權息正式確認：API 無回應或無資料')

# ── 抓台指期三大法人未平倉 ──────────────────
def _parse_futures_csv(raw):
    """
    解析 TAIFEX CSV（Big5 編碼）。
    raw 可以是 bytes 或已解碼的 str。
    回傳 {date: {foreign_long, ...}} dict
    """
    import csv, io
    # 強制以 Big5 解碼
    if isinstance(raw, bytes):
        text = raw.decode('big5', errors='ignore')
    else:
        # 若已是 str 但亂碼，嘗試 encode back 再解碼
        try:
            text = raw.encode('latin-1').decode('big5', errors='ignore')
        except Exception:
            text = raw

    result = {}
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # 跳過標題

    for row in reader:
        if len(row) < 15:
            continue
        # row[1]=商品名稱（臺股期貨）, row[2]=身份別
        # 只取臺股期貨（排除電子/金融期貨）
        commodity = row[1].strip()
        if '臺股' not in commodity and '台股' not in commodity:
            continue
        date     = row[0].strip().replace('/', '-')
        identity = row[2].strip()
        try:
            long_oi  = int(row[9].replace(',', '').strip())
            short_oi = int(row[11].replace(',', '').strip())
            net_oi   = int(row[13].replace(',', '').strip())
        except Exception:
            continue
        if date not in result:
            result[date] = {}
        if '外資' in identity:
            result[date].update({'foreign_long': long_oi, 'foreign_short': short_oi, 'foreign_net': net_oi})
        elif '投信' in identity:
            result[date].update({'trust_long': long_oi, 'trust_short': short_oi, 'trust_net': net_oi})
        elif '自營' in identity:
            result[date].update({'dealer_long': long_oi, 'dealer_short': short_oi, 'dealer_net': net_oi})
    return result


def fetch_futures_institutional():
    """抓取今日（或最近一交易日）台指期三大法人未平倉"""
    from database import save_futures_institutional, get_futures_institutional
    print('抓取台指期三大法人未平倉...')
    today = datetime.now().strftime('%Y/%m/%d')
    url = 'https://www.taifex.com.tw/cht/3/futContractsDateDown'
    try:
        r = requests.get(url, params={
            'down_type': '1', 'commodity_id': 'TXF',
            'queryStartDate': today, 'queryEndDate': today
        }, headers=HEADERS, timeout=15)
        parsed = _parse_futures_csv(r.content)
        if not parsed:
            # 今天可能還沒資料，試前一交易日
            prev = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
            r2 = requests.get(url, params={
                'down_type': '1', 'commodity_id': 'TXF',
                'queryStartDate': prev, 'queryEndDate': prev
            }, headers=HEADERS, timeout=15)
            parsed = _parse_futures_csv(r2.content)
        count = 0
        for date, data in parsed.items():
            if len(data) >= 6:  # 至少有外資+投信+自營
                save_futures_institutional(date, data)
                count += 1
        print(f'台指期未平倉：{count} 筆')
    except Exception as e:
        print(f'台指期未平倉失敗：{e}')


def fetch_futures_institutional_history(months=3):
    """
    補抓台指期三大法人未平倉歷史。
    TAIFEX 限制單次查詢範圍約 30 天，改為逐月分批抓取。
    """
    import calendar
    from database import save_futures_institutional
    print(f'補抓台指期未平倉歷史（{months} 個月，逐月分批）...')
    url   = 'https://www.taifex.com.tw/cht/3/futContractsDateDown'
    total = 0
    now   = datetime.now()

    # 建立月份列表（由舊到新）
    month_ranges = []
    for i in range(months - 1, -1, -1):
        # 往回 i 個月
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_start = datetime(y, m, 1)
        # 最後一個月以今天為結束，其他月份以月底為結束
        if i == 0:
            month_end = now
        else:
            last_day = calendar.monthrange(y, m)[1]
            month_end = datetime(y, m, last_day)
        month_ranges.append((month_start, month_end))

    for month_start, month_end in month_ranges:
        try:
            r = requests.get(url, params={
                'down_type': '1', 'commodity_id': 'TXF',
                'queryStartDate': month_start.strftime('%Y/%m/%d'),
                'queryEndDate':   month_end.strftime('%Y/%m/%d'),
            }, headers=HEADERS, timeout=20)
            parsed = _parse_futures_csv(r.content)
            for date, data in sorted(parsed.items()):
                if len(data) >= 6:
                    save_futures_institutional(date, data)
                    total += 1
            print(f'  {month_start.strftime("%Y/%m/%d")}～{month_end.strftime("%Y/%m/%d")}：{len(parsed)} 筆')
            time.sleep(0.5)
        except Exception as e:
            print(f'  {month_start.strftime("%Y/%m")} 失敗：{e}')

    print(f'台指期未平倉歷史：共 {total} 筆')
    return total


# ── 選擇權 P/C 比率 ───────────────────────
def _parse_pc_csv(content: bytes) -> list:
    """
    解析 TAIFEX pcRatioDown CSV（Big5），回傳 list of dict。
    實際欄位順序（以回傳資料確認）：
      日期, 賣權成交量, 買權成交量, 買賣權成交量比率%,
      賣權未平倉量, 買權未平倉量, 買賣權未平倉量比率%
    日期格式：2026/06/12（斜線分隔西元年）
    比率欄：168.35 代表 put/call OI = 1.6835
    """
    text = content.decode('big5', errors='ignore')
    rows = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.split(',')]
        if len(cols) < 7:
            continue
        raw_date = cols[0].strip()
        try:
            # 格式：2026/06/12 → 2026-06-12
            if '/' in raw_date and len(raw_date) == 10:
                date = raw_date.replace('/', '-')
            else:
                continue
            # 賣權未平倉量 = cols[4]，買權未平倉量 = cols[5]
            put_oi  = int(cols[4].replace(',', '')) if cols[4].replace(',', '').lstrip('-').isdigit() else 0
            call_oi = int(cols[5].replace(',', '')) if cols[5].replace(',', '').lstrip('-').isdigit() else 0
            # 比率欄：168.35 → pc_ratio = 1.6835
            pc_pct   = float(cols[6].replace(',', '')) if cols[6].replace(',', '') else 0.0
            pc_ratio = round(pc_pct / 100, 4)
            if call_oi > 0 and put_oi > 0:
                rows.append({'date': date, 'call_oi': call_oi,
                             'put_oi': put_oi, 'pc_ratio': pc_ratio})
        except (ValueError, IndexError):
            continue
    return rows


def fetch_options_pc():
    """抓取今日（或最近一交易日）選擇權 P/C 比率"""
    from database import save_options_pc, get_options_pc_last_date
    print('抓取選擇權 P/C 比率...')
    url   = 'https://www.taifex.com.tw/cht/3/pcRatioDown'
    today = datetime.now().strftime('%Y/%m/%d')
    try:
        r = requests.get(url, params={
            'queryStartDate': today,
            'queryEndDate':   today,
        }, headers=HEADERS, timeout=15)
        rows = _parse_pc_csv(r.content)
        if not rows:
            # 當日可能還沒資料，試前一交易日
            prev = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
            r2 = requests.get(url, params={
                'queryStartDate': prev, 'queryEndDate': prev,
            }, headers=HEADERS, timeout=15)
            rows = _parse_pc_csv(r2.content)
        count = 0
        for row in rows:
            save_options_pc(row['date'], row['call_oi'], row['put_oi'], row['pc_ratio'])
            count += 1
        print(f'P/C 比率：{count} 筆')
    except Exception as e:
        print(f'P/C 比率失敗：{e}')


def fetch_options_pc_history(months=3):
    """補抓選擇權 P/C 比率歷史（逐月分批，最多 30 天/次）"""
    import calendar
    from database import save_options_pc
    print(f'補抓 P/C 比率歷史（{months} 個月）...')
    url   = 'https://www.taifex.com.tw/cht/3/pcRatioDown'
    total = 0
    now   = datetime.now()

    month_ranges = []
    for i in range(months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_start = datetime(y, m, 1)
        month_end   = now if i == 0 else datetime(y, m, calendar.monthrange(y, m)[1])
        month_ranges.append((month_start, month_end))

    for ms, me in month_ranges:
        try:
            r = requests.get(url, params={
                'queryStartDate': ms.strftime('%Y/%m/%d'),
                'queryEndDate':   me.strftime('%Y/%m/%d'),
            }, headers=HEADERS, timeout=20)
            rows = _parse_pc_csv(r.content)
            for row in rows:
                save_options_pc(row['date'], row['call_oi'], row['put_oi'], row['pc_ratio'])
                total += 1
            print(f'  {ms.strftime("%Y/%m")}：{len(rows)} 筆')
            time.sleep(0.5)
        except Exception as e:
            print(f'  {ms.strftime("%Y/%m")} 失敗：{e}')

    print(f'P/C 比率歷史：共 {total} 筆')
    return total


# ── 抓三大法人當日買賣超排行（T86）──────────
def fetch_t86():
    """
    抓取 TWSE T86 三大法人買賣超明細（全市場，當日）。
    實際欄位順序（依診斷確認）：
      [0]證券代號  [1]證券名稱
      [2]外陸資買進  [3]外陸資賣出  [4]外陸資買賣超（不含外資自營商）
      [5]外資自營商買進  [6]外資自營商賣出  [7]外資自營商買賣超
      [8]投信買進  [9]投信賣出  [10]投信買賣超
      [11]自營商買賣超（合計）
      [12]自營商買進(自行)  [13]自營商賣出(自行)  [14]自營商買賣超(自行)
      [15]自營商買進(避險)  [16]自營商賣出(避險)  [17]自營商買賣超(避險)
      [18]三大法人買賣超合計
    單位：股數（需除以 1000 轉換為張）
    """
    from database import save_t86_ranking, get_t86_last_date, get_latest_price_date
    from datetime import timedelta

    # 取得 TWSE 最新交易日（用 2330 當基準）
    twse_date = get_latest_price_date('2330')
    if not twse_date:
        print('T86：無法取得 TWSE 日期，略過')
        return

    # 已有當日資料則略過
    last = get_t86_last_date()
    if last and last >= twse_date:
        print(f'T86 排行資料已是最新（{last}），略過')
        return

    # 從上次日期+1天逐日往後補，最多試5個交易日
    from_date = datetime.strptime(last, '%Y-%m-%d') + timedelta(days=1) if last else datetime.strptime(twse_date, '%Y-%m-%d')
    to_date   = datetime.strptime(twse_date, '%Y-%m-%d')

    # 列出需要嘗試的日期（只取週一~週五，最多5天）
    candidates = []
    d = from_date
    while d <= to_date and len(candidates) < 5:
        if d.weekday() < 5:  # 非週末
            candidates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    if not candidates:
        print('T86：無需補抓')
        return

    def shares_to_lots(val):
        return int(clean_num(val) / 1000)

    # 逐日嘗試抓取，成功儲存後繼續下一天
    any_saved = False
    for target_date in candidates:
        date_str = target_date.replace('-', '')
        url = (f'https://www.twse.com.tw/rwd/zh/fund/T86'
               f'?response=json&date={date_str}&selectType=ALL')
        print(f'抓取 T86 三大法人排行（{target_date}）...')
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            data = resp.json()
        except Exception as e:
            print(f'T86 請求失敗（{target_date}）：{e}')
            continue

        if data.get('stat') != 'OK':
            print(f'T86 回傳狀態非OK（{target_date}）：{data.get("stat")}，略過')
            continue

        rows_raw = data.get('data', [])
        if not rows_raw:
            print(f'T86 無資料（{target_date}）')
            continue

        rows = []
        for r in rows_raw:
            try:
                code = str(r[0]).strip()
                name = str(r[1]).strip()
                if not code or not code.isdigit():
                    continue
                if len(r) < 12:
                    continue
                fb    = shares_to_lots(r[2])
                fs    = shares_to_lots(r[3])
                fn    = shares_to_lots(r[4])
                tb    = shares_to_lots(r[8])
                ts    = shares_to_lots(r[9])
                tn    = shares_to_lots(r[10])
                dn    = shares_to_lots(r[11])
                total = shares_to_lots(r[18]) if len(r) > 18 else (fn + tn + dn)
                rows.append({
                    'code': code, 'name': name,
                    'foreign_buy': fb, 'foreign_sell': fs, 'foreign_net': fn,
                    'trust_buy':   tb, 'trust_sell':   ts, 'trust_net':   tn,
                    'dealer_net':  dn, 'total_net':    total,
                })
            except Exception:
                continue

        if rows:
            save_t86_ranking(target_date, rows)
            print(f'T86 排行儲存完成：{len(rows)} 筆（{target_date}）')
            any_saved = True
        else:
            print(f'T86 解析後無有效資料（{target_date}）')

    if not any_saved:
        print('T86：所有日期均無資料或請求失敗')

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
                    s = str(date_tw).strip()
                    if len(s) == 7 and s[0] == '1':   # 民國年 1YYMMDD
                        date_std = f'{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}'
                    elif len(s) == 8 and s[0] == '2':  # 西元年 YYYYMMDD
                        date_std = f'{s[:4]}-{s[4:6]}-{s[6:8]}'
                    else:
                        # 用查詢日期推算
                        date_std = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
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
# ── 抓 ETF 成分股（建立股票→ETF 反向索引）──────
def fetch_etf_holdings():
    """
    抓取所有上市 ETF 的成分股資料，建立反向索引。

    【資料來源現況 - 2026/05】
    策略1 FinMind API：
      - 免費版不含 ETF 成分股資料集（TaiwanETFHolding 不在免費清單中）
      - 若未來 FinMind 開放，修改 dataset 參數名稱即可啟用

    策略2 TWSE OpenAPI（openapi.twse.com.tw）：
      - 所有端點均回傳 HTML 錯誤頁，程式無法解析 JSON
      - TWSE 已封鎖非瀏覽器的程式存取

    策略3 TWSE T201U 逐一抓各 ETF：
      - https://www.twse.com.tw/rwd/zh/fund/T201U
      - 同樣回傳 HTML 404，無法取得 JSON 資料

    【結論】目前無免費可靠的自動抓取方式。
    ETF 持股改由 app.py 的 _ETF_FALLBACK 人工維護備援資料顯示。
    本函式保留供未來資料來源恢復時使用。
    """
    from database import save_etf_holdings
    from collections import defaultdict
    from config import FINMIND_TOKEN

    print('抓取 ETF 成分股資料...')
    total = 0

    # ── 策略 1：FinMind API（最穩定，需免費 token）─────────────────────
    if FINMIND_TOKEN:
        print('  使用 FinMind API...')
        try:
            r = requests.get(
                'https://api.finmindtrade.com/api/v4/data',
                params={
                    'dataset': 'TaiwanETFHolding',
                    'token': FINMIND_TOKEN,
                },
                headers=HEADERS,
                timeout=60,
                verify=False
            )
            resp = r.json()
            if r.status_code == 200 and resp.get('status') == 200:
                data = resp.get('data', [])
                if data:
                    print(f'  FinMind 欄位：{list(data[0].keys())}')
                    etf_map   = defaultdict(list)
                    etf_names = {}
                    for row in data:
                        etf_code = str(row.get('stock_id', '')).strip()
                        etf_name = str(row.get('etf_name', '') or row.get('stock_name', '')).strip()
                        stk_code = str(row.get('security_id', '') or row.get('etf_component', '')).strip()
                        weight   = clean_num(row.get('weight', 0) or row.get('percentage', 0))
                        shares   = int(clean_num(row.get('holding_shares', 0) or row.get('shares', 0)))
                        if etf_code and stk_code:
                            etf_map[etf_code].append({
                                'stock_code': stk_code,
                                'weight': weight,
                                'shares': shares
                            })
                            if etf_name:
                                etf_names[etf_code] = etf_name
                    for etf_code, constituents in etf_map.items():
                        save_etf_holdings(etf_code, etf_names.get(etf_code, etf_code), constituents)
                        total += len(constituents)
                    print(f'  FinMind 完成：{len(etf_map)} 支ETF，{total} 筆成分股')
                    return total
                else:
                    print(f'  FinMind 回傳空資料（status={resp.get("status")}）')
            else:
                print(f'  FinMind 失敗：status={r.status_code}，msg={str(resp)[:100]}')
        except Exception as e:
            print(f'  FinMind 例外：{e}')
    else:
        print('  未設定 FINMIND_TOKEN，跳過 FinMind')

    # ── 策略 2：TWSE OpenAPI（直接抓全部）────────────────────────────
    print('  嘗試 TWSE OpenAPI...')
    twse_session = requests.Session()
    twse_session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json, text/javascript, */*',
        'Referer': 'https://www.twse.com.tw/',
        'X-Requested-With': 'XMLHttpRequest',
    })
    twse_endpoints = [
        'https://openapi.twse.com.tw/v1/ETF/constituents',
        'https://openapi.twse.com.tw/v1/opendata/t187ap06_L',
    ]
    for url in twse_endpoints:
        try:
            r = twse_session.get(url, timeout=20, verify=False)
            if r.status_code == 200 and r.text.strip().startswith('['):
                data = r.json()
                if isinstance(data, list) and data:
                    print(f'  TWSE 取得資料：{len(data)} 筆，欄位：{list(data[0].keys())}')
                    etf_map   = defaultdict(list)
                    etf_names = {}
                    for row in data:
                        etf_code = (row.get('ETFid') or row.get('etf_code') or
                                    row.get('基金代號') or '').strip()
                        etf_name = (row.get('Ch_ETFname') or row.get('etf_name') or
                                    row.get('基金名稱') or '').strip()
                        stk_code = (row.get('Stk_code') or row.get('stock_code') or
                                    row.get('成分股代號') or '').strip()
                        weight   = clean_num(row.get('Percent') or row.get('weight') or
                                             row.get('持股比例') or 0)
                        shares   = int(clean_num(row.get('Shares') or row.get('shares') or
                                                 row.get('持股股數') or 0))
                        if etf_code and stk_code:
                            etf_map[etf_code].append({
                                'stock_code': stk_code,
                                'weight': weight,
                                'shares': shares
                            })
                            if etf_name:
                                etf_names[etf_code] = etf_name
                    for etf_code, constituents in etf_map.items():
                        save_etf_holdings(etf_code, etf_names.get(etf_code, etf_code), constituents)
                        total += len(constituents)
                    print(f'  TWSE 完成：{len(etf_map)} 支ETF，{total} 筆成分股')
                    return total
        except Exception as e:
            print(f'  TWSE {url} 失敗：{e}')

    # ── 策略 3：逐一抓各主要 ETF（TWSE T201U 端點）─────────────────────
    print('  嘗試逐一抓各主要 ETF...')
    MAJOR_ETFS = [
        ('0050',   '元大台灣50'),
        ('0051',   '元大中型100'),
        ('0052',   '富邦科技'),
        ('0053',   '元大電子'),
        ('0055',   '元大MSCI金融'),
        ('0056',   '元大高股息'),
        ('006201', '元大富櫃50'),
        ('006204', '永豐臺灣加權'),
        ('006208', '富邦台50'),
        ('00631L', '元大台灣50正2'),
        ('00636',  '國泰臺灣加權'),
        ('00642U', '元大S&P石油'),
        ('00646',  '元大S&P500'),
        ('00652',  '富邦印度'),
        ('00661',  '元大日經225'),
        ('00662',  '富邦NASDAQ'),
        ('00670L', '富邦NASDAQ正2'),
        ('00678',  '群益臺灣精選高息'),
        ('00680L', '富邦臺灣加權正2'),
        ('00690',  '兆豐藍籌30'),
        ('00692',  '富邦公司治理'),
        ('00700',  '富邦台灣優質高息'),
        ('00713',  '元大台灣高息低波'),
        ('00717',  '富邦美國特別股'),
        ('00730',  '富邦臺灣優質高息'),
        ('00731',  '復華台灣科技優息'),
        ('00878',  '國泰永續高股息'),
        ('00881',  '國泰台灣5G+'),
        ('00882',  '中信中國高股息'),
        ('00883',  '國泰中國A150'),
        ('00884',  '國泰北美科技'),
        ('00885',  '富邦越南'),
        ('00886',  '國泰美國道瓊'),
        ('00887',  '國泰美國科技'),
        ('00888',  '永豐ESG低碳高息'),
        ('00891',  '中信關鍵半導體'),
        ('00892',  '富邦台灣核心治理'),
        ('00893',  '國泰智能電動車'),
        ('00894',  '中信小資高價30'),
        ('00895',  '富邦未來車'),
        ('00896',  '中信綠能及電動車'),
        ('00900',  '富邦特選高股息30'),
        ('00901',  '永豐智能車供應鏈'),
        ('00904',  '新光臺灣半導體30'),
        ('00905',  '野村臺灣新科技50'),
        ('00907',  '永豐美國科技'),
        ('00908',  '富邦入息REITs+'),
        ('00909',  '國泰數位支付服務'),
        ('00910',  '第一金太空衛星'),
        ('00912',  '中信臺灣智慧50'),
        ('00913',  '兆豐國際-臺灣晶圓製造'),
        ('00914',  '中信智慧城市'),
        ('00915',  '凱基優選高股息30'),
        ('00916',  '國泰全球品牌50'),
        ('00917',  '中信特選金融'),
        ('00918',  '大華優利高填息30'),
        ('00919',  '群益台灣精選高息'),
        ('00920',  '富邦台灣核心半導體'),
        ('00921',  '兆豐台灣晶圓製造'),
        ('00922',  '國泰台灣領袖50'),
        ('00923',  '群益台ESG低碳50'),
        ('00924',  '第一金太空衛星'),
        ('00925',  '群益全球掌趨勢'),
        ('00927',  '群益半導體收益'),
        ('00928',  '中國信託台灣活力'),
        ('00929',  '復華台灣科技優息'),
        ('00930',  '永豐優息存股'),
        ('00932',  '兆豐永續高息等權'),
        ('00933',  '國泰台灣產業龍頭存股'),
        ('00934',  '中信成長高股息'),
        ('00935',  '野村臺灣ESG'),
        ('00936',  '台新臺灣永續高息'),
        ('00937',  '台新科技ETF'),
        ('00938',  '台新臺灣IC設計'),
        ('00939',  '統一台灣高息動能'),
        ('00940',  '元大台灣價值高息'),
    ]
    etf_map   = defaultdict(list)
    etf_names = {}
    fetched   = 0
    for etf_code, etf_name in MAJOR_ETFS:
        try:
            url = (f'https://www.twse.com.tw/rwd/zh/fund/T201U'
                   f'?response=json&progid=&strDate=&endDate=&ETFid={etf_code}')
            r = twse_session.get(url, timeout=10, verify=False)
            if r.status_code != 200:
                continue
            text = r.text.strip()
            if not text.startswith('{'):
                continue
            data = r.json()
            rows = data.get('data', [])
            fields = data.get('fields', [])
            if not rows:
                continue
            # fields: ['股票代號','股票名稱','持股股數','持股市值(元)','持股比例(%)']
            code_idx   = next((i for i,f in enumerate(fields) if '代號' in f or 'code' in f.lower()), 0)
            shares_idx = next((i for i,f in enumerate(fields) if '股數' in f or 'shares' in f.lower()), 2)
            value_idx  = next((i for i,f in enumerate(fields) if '市值' in f or 'value' in f.lower()), 3)
            pct_idx    = next((i for i,f in enumerate(fields) if '比例' in f or 'percent' in f.lower()), 4)
            for row in rows:
                stk_code = str(row[code_idx]).strip() if len(row) > code_idx else ''
                shares   = int(clean_num(row[shares_idx])) if len(row) > shares_idx else 0
                weight   = clean_num(row[pct_idx]) if len(row) > pct_idx else 0
                if stk_code:
                    etf_map[etf_code].append({
                        'stock_code': stk_code,
                        'weight': weight,
                        'shares': shares
                    })
                    etf_names[etf_code] = etf_name
            fetched += 1
            print(f'    {etf_code} {etf_name}：{len(etf_map[etf_code])} 筆')
            time.sleep(0.5)
        except Exception as e:
            print(f'    {etf_code} 失敗：{e}')
            continue

    if etf_map:
        for etf_code, constituents in etf_map.items():
            save_etf_holdings(etf_code, etf_names.get(etf_code, etf_code), constituents)
            total += len(constituents)
        print(f'  逐一抓完成：{fetched} 支ETF，{total} 筆成分股')
        return total

    print('  ⚠️  所有 ETF 資料來源均失敗')
    print('  👉 建議至 https://finmindtrade.com 免費註冊，取得 token 後')
    print('     在 config_local.py 加入：FINMIND_TOKEN = "your_token"')
    return 0


# ── 抓加權指數歷史資料（TAIEX）────────────
def fetch_taiex(months=6):
    """
    抓取台灣加權指數（TAIEX）歷史日資料，存入 prices 表（code='TAIEX'）。
    使用 yfinance 套件抓取 Yahoo Finance ^TWII，自動處理 cookie/session。
    如未安裝 yfinance，執行：pip install yfinance --break-system-packages
    """
    from database import save_prices, get_latest_price_date, save_stock_info

    save_stock_info('TAIEX', '加權指數', 'TWSE', '大盤')
    last_date = get_latest_price_date('TAIEX')
    all_rows  = []

    period = f'{months}mo' if months <= 11 else '1y'
    print(f'抓取加權指數歷史（yfinance ^TWII，{period}）...')

    try:
        import yfinance as yf
        ticker = yf.Ticker('^TWII')
        hist   = ticker.history(period=period, auto_adjust=True)

        if hist.empty:
            raise ValueError('yfinance 回傳空資料')

        prev_close = None
        for ts, row in hist.iterrows():
            date_str = ts.strftime('%Y-%m-%d')
            if last_date and date_str <= last_date:
                prev_close = float(row['Close'])
                continue
            close = round(float(row['Close']), 2)
            open_ = round(float(row['Open']),  2)
            high  = round(float(row['High']),  2)
            low   = round(float(row['Low']),   2)
            raw_v = int(row['Volume']) if row['Volume'] else 0
            # Volume 單位為股，除以 1e9 得到大約「十億股」量綱方便圖表顯示
            vol   = int(raw_v / 1_000_000) if raw_v else 0
            chg   = round(close - prev_close, 2) if prev_close else 0
            pct   = round(chg / prev_close * 100, 2) if prev_close else 0
            prev_close = float(row['Close'])
            if close > 0:
                all_rows.append({
                    'date': date_str, 'open': open_, 'high': high,
                    'low': low,  'close': close,
                    'volume': vol, 'value': float(raw_v),
                    'change': chg, 'change_pct': pct,
                })
        print(f'yfinance TAIEX：解析 {len(all_rows)} 筆')

    except ImportError:
        print('❌ yfinance 未安裝，請執行：pip install yfinance --break-system-packages')
    except Exception as e:
        print(f'yfinance TAIEX 失敗：{e}')

    if all_rows:
        seen = {}
        for row in all_rows:
            seen[row['date']] = row
        deduped = sorted(seen.values(), key=lambda x: x['date'])
        save_prices('TAIEX', deduped)
        print(f'加權指數：新增 {len(deduped)} 筆')
    else:
        print('加權指數：無新資料（請確認 yfinance 已安裝）')

    # 補正成交金額（FMTQIK，比 yfinance 準確）
    fetch_market_volume()

    return len(all_rows)


def fetch_market_volume():
    """
    從 TWSE FMTQIK 抓取每日市場成交金額，
    補正 prices 表中 TAIEX 的 value 欄位（億元）。
    yfinance 對指數成交量不可靠，改用此 API 修正。
    """
    url = 'https://www.twse.com.tw/exchangeReport/FMTQIK?response=json'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
    except Exception as e:
        print(f'FMTQIK 成交金額抓取失敗：{e}')
        return

    if data.get('stat') != 'OK':
        print('FMTQIK 無資料')
        return

    fields = data.get('fields', [])
    rows   = data.get('data', [])

    from database import get_conn
    conn = get_conn()
    updated = 0

    for row in rows:
        try:
            # 日期：民國年 115/05/29 → 2026-05-29
            date_std = twse_date_to_std(row[0])
            if not date_std or len(date_std) < 8:
                continue
            # 成交金額（元）→ 億元
            value_b = float(str(row[2]).replace(',', '')) / 1e8
            # 成交股數（股）→ 億股
            volume_b = float(str(row[1]).replace(',', '')) / 1e8

            # 更新 prices 表的 value / volume 欄位
            conn.execute(
                'UPDATE prices SET value=?, volume=? WHERE code=? AND date=?',
                (value_b, volume_b, 'TAIEX', date_std)
            )
            if conn.execute('SELECT changes()').fetchone()[0] > 0:
                updated += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    print(f'FMTQIK 成交金額補正：{updated} 筆（億元）')


if __name__ == '__main__':
    fetch_all()
