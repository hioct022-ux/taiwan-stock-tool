# ════════════════════════════════════════
# github_sync.py　GitHub 備份
# 負責將資料備份到 GitHub
# ════════════════════════════════════════

import os
import json
import requests as _req
from datetime import datetime
from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, JSON_DIR


# ── 從公開 repo 直接讀取（不需要 Token）───
def load_raw(path):
    """從 GitHub raw URL 讀取檔案，適用於公開 repo，雲端版使用。"""
    if not GITHUB_REPO:
        return None
    try:
        url = (f'https://raw.githubusercontent.com/'
               f'{GITHUB_REPO}/{GITHUB_BRANCH}/{path}')
        r = _req.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def load_stock_data_raw(code):
    """從 GitHub 讀取個股完整資料（不需要 Token）"""
    return load_raw(f'data/json/{code}.json')


def load_watchlist_raw():
    """從 GitHub 讀取自選股清單（不需要 Token）"""
    return load_raw('data/json/watchlist.json') or []

def load_stocks_raw():
    """從 GitHub 讀取全市場股票清單（不需要 Token）"""
    return load_raw('data/json/stocks.json') or []


def load_meta_raw():
    """從 GitHub 讀取更新狀態（不需要 Token）"""
    return load_raw('data/json/meta.json')

# ── 檢查是否設定 GitHub ──────────────────
def is_github_configured():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    # GitHub token 只能包含 ASCII 字元（ghp_xxx 格式）
    # 若含有非 ASCII 字元（例如中文佔位符），視為未設定
    try:
        GITHUB_TOKEN.encode('ascii')
    except (UnicodeEncodeError, AttributeError):
        return False
    # token 長度至少 20 碼（正式 token 長度約 40 碼）
    if len(GITHUB_TOKEN) < 20:
        return False
    return True

# ── 匯出資料為 JSON ──────────────────────
def export_to_json(code=None):
    from database import (get_prices, get_fundamentals,
                          get_chips, get_watchlist, get_last_update,
                          get_conn)

    os.makedirs(JSON_DIR, exist_ok=True)

    # 匯出全市場股票清單（供雲端版搜尋用）
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT code, name, market, industry FROM stocks ORDER BY code')
        rows = c.fetchall()
        conn.close()
        if rows:
            stocks_list = [{'code': r[0], 'name': r[1],
                            'market': r[2], 'industry': r[3]} for r in rows]
            with open(os.path.join(JSON_DIR, 'stocks.json'), 'w', encoding='utf-8') as f:
                json.dump(stocks_list, f, ensure_ascii=False)
            print(f'匯出股票清單：{len(stocks_list)} 支')
    except Exception as e:
        print(f'匯出股票清單失敗：{e}')

    # 匯出更新紀錄
    last = get_last_update()
    meta = {
        'last_update': last.get('updated_at','') if last else '',
        'last_date':   last.get('date','')       if last else '',
        'status':      last.get('status','')     if last else '',
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    with open(os.path.join(JSON_DIR, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 匯出自選股（保護：清單是空的就不覆蓋，避免意外清空 GitHub 上的記錄）
    watchlist = get_watchlist()
    wl_path = os.path.join(JSON_DIR, 'watchlist.json')
    if watchlist:
        with open(wl_path, 'w', encoding='utf-8') as f:
            json.dump(watchlist, f, ensure_ascii=False, indent=2)
    else:
        print('⚠️  自選股清單是空的，跳過覆蓋 watchlist.json（保留 GitHub 上的版本）')

    # 匯出自訂標籤
    try:
        from database import get_tags
        tags = get_tags()
        if tags:
            with open(os.path.join(JSON_DIR, 'watchlist_tags.json'), 'w', encoding='utf-8') as f:
                json.dump(tags, f, ensure_ascii=False, indent=2)
            print(f'匯出自訂標籤：{len(tags)} 個')
    except Exception as e:
        print(f'匯出自訂標籤失敗：{e}')

    # 匯出個股資料
    if code:
        codes = [code]
    else:
        codes = [w['code'] for w in watchlist]

    for c in codes:
        try:
            from database import get_ownership as _get_own
            _own_row = _get_own(c)
            stock_data = {
                'code':         c,
                'prices':       get_prices(c, days=400),
                'fundamentals': get_fundamentals(c, days=400),
                'chips':        get_chips(c, days=65),
                'ownership':    _own_row,          # {'foreign_pct': float, 'date': str} 或 None
                'exported_at':  datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            path = os.path.join(JSON_DIR, f'{c}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(stock_data, f, ensure_ascii=False, indent=2)
            print(f'匯出 {c} 完成')
        except Exception as e:
            print(f'匯出 {c} 失敗：{e}')

    # ── 匯出大盤融資融券 ──────────────────────
    try:
        from database import get_market_margin
        mm_rows = get_market_margin(days=120)
        if mm_rows:
            with open(os.path.join(JSON_DIR, 'market_margin.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': mm_rows, 'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出大盤融資融券：{len(mm_rows)} 筆')
    except Exception as e:
        print(f'匯出大盤融資融券失敗：{e}')

    # ── 匯出大盤（TAIEX）資料 ─────────────────
    try:
        taiex_prices = get_prices('TAIEX', days=250)
        if taiex_prices:
            with open(os.path.join(JSON_DIR, 'TAIEX.json'), 'w', encoding='utf-8') as f:
                json.dump({'prices': taiex_prices,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出大盤 TAIEX：{len(taiex_prices)} 筆')
    except Exception as e:
        print(f'匯出大盤失敗：{e}')

    # ── 匯出三大法人排行（T86）─────────────────
    try:
        from database import get_t86_ranking, get_t86_last_date
        t86_date = get_t86_last_date()
        if t86_date:
            rows_trust,   _ = get_t86_ranking(t86_date, sort_by='trust_net',   top=15)
            rows_foreign, _ = get_t86_ranking(t86_date, sort_by='foreign_net', top=15)
            rows_total,   _ = get_t86_ranking(t86_date, sort_by='total_net',   top=15)
            from database import get_t86_ranking_bottom
            rows_trust_s,   _ = get_t86_ranking_bottom(t86_date, sort_by='trust_net',   top=15)
            rows_foreign_s, _ = get_t86_ranking_bottom(t86_date, sort_by='foreign_net', top=15)
            rows_total_s,   _ = get_t86_ranking_bottom(t86_date, sort_by='total_net',   top=15)
            t86_data = {
                'date': t86_date,
                'trust_top':    rows_trust,
                'trust_bot':    rows_trust_s,
                'foreign_top':  rows_foreign,
                'foreign_bot':  rows_foreign_s,
                'total_top':    rows_total,
                'total_bot':    rows_total_s,
                'exported_at':  datetime.now().strftime('%Y-%m-%d %H:%M'),
            }
            with open(os.path.join(JSON_DIR, 't86.json'), 'w', encoding='utf-8') as f:
                json.dump(t86_data, f, ensure_ascii=False)
            print(f'匯出法人排行（T86）：{t86_date}')
    except Exception as e:
        print(f'匯出法人排行失敗：{e}')

    # ── 匯出即將除權息 ─────────────────────────
    try:
        from database import get_exdividend_upcoming
        ex_rows = get_exdividend_upcoming(days=45)
        if ex_rows:
            with open(os.path.join(JSON_DIR, 'exdividend.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': ex_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出除權息：{len(ex_rows)} 筆')
    except Exception as e:
        print(f'匯出除權息失敗：{e}')

    try:
        from database import get_futures_institutional
        fut_rows = get_futures_institutional(days=120)
        if fut_rows:
            with open(os.path.join(JSON_DIR, 'futures_institutional.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': fut_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出台指期未平倉：{len(fut_rows)} 筆')
    except Exception as e:
        print(f'匯出台指期未平倉失敗：{e}')

    try:
        from database import get_market_pe
        pe_rows = get_market_pe(days=250)
        if pe_rows:
            with open(os.path.join(JSON_DIR, 'market_pe.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': pe_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出大盤本益比：{len(pe_rows)} 筆')
    except Exception as e:
        print(f'匯出大盤本益比失敗：{e}')

    try:
        from database import get_chips_market_aggregate
        agg_rows = get_chips_market_aggregate(days=30)
        if agg_rows:
            with open(os.path.join(JSON_DIR, 'chips_market_agg.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': agg_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出三大法人現貨彙總：{len(agg_rows)} 天')
    except Exception as e:
        print(f'匯出三大法人現貨彙總失敗：{e}')

    try:
        from database import get_options_pc
        pc_rows = get_options_pc(days=120)
        if pc_rows:
            with open(os.path.join(JSON_DIR, 'options_pc.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': pc_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出 P/C 比率：{len(pc_rows)} 天')
    except Exception as e:
        print(f'匯出 P/C 比率失敗：{e}')

    # ── 匯出 DRAM 現貨價格 ─────────────────────
    try:
        from database import get_dram_prices
        dram_rows = get_dram_prices(days=365)
        if dram_rows:
            with open(os.path.join(JSON_DIR, 'dram_prices.json'), 'w', encoding='utf-8') as f:
                json.dump({'rows': dram_rows,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出 DRAM 現貨價格：{len(dram_rows)} 筆')
    except Exception as e:
        print(f'匯出 DRAM 現貨價格失敗：{e}')

    # ── 匯出個股季度財報（2317/2049/南亞科等監控股）──
    try:
        from database import get_quarterly_financials
        import sqlite3 as _sql3, os as _os2
        # 從 DB 抓所有有財報資料的 code
        from database import get_conn as _gc2
        _c2 = _gc2()
        _qf_codes = [r[0] for r in _c2.execute(
            'SELECT DISTINCT code FROM stock_quarterly_financials').fetchall()]
        _c2.close()
        qf_data = {}
        for _qc in _qf_codes:
            _rows = get_quarterly_financials(_qc, quarters=16)
            if _rows:
                qf_data[_qc] = _rows
        if qf_data:
            with open(os.path.join(JSON_DIR, 'quarterly_financials.json'), 'w', encoding='utf-8') as f:
                json.dump({'data': qf_data,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出季度財報：{len(qf_data)} 支股票')
    except Exception as e:
        print(f'匯出季度財報失敗：{e}')

    # ── 匯出個股業務分部營收（AI Server 占比等）──
    try:
        from database import get_conn as _gc3
        _c3 = _gc3()
        _sr_rows = _c3.execute(
            'SELECT code, period, segment, revenue_pct, revenue_abs, note FROM stock_segment_revenue'
        ).fetchall()
        _c3.close()
        sr_data = {}
        for r in _sr_rows:
            _code, _period, _segment, _pct, _abs, _note = r
            if _code not in sr_data:
                sr_data[_code] = []
            sr_data[_code].append({'period': _period, 'segment': _segment,
                                    'revenue_pct': _pct, 'revenue_abs': _abs, 'note': _note})
        if sr_data:
            with open(os.path.join(JSON_DIR, 'segment_revenue.json'), 'w', encoding='utf-8') as f:
                json.dump({'data': sr_data,
                           'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                          f, ensure_ascii=False)
            print(f'匯出業務分部營收：{len(sr_data)} 支股票')
    except Exception as e:
        print(f'匯出業務分部營收失敗：{e}')

    print(f'JSON 匯出完成，路徑：{JSON_DIR}')

# ── 使用 git CLI 推送（推薦，不需要 Token）──
def sync_via_git(code=None):
    """
    匯出 JSON 後用 git add / commit / push 推送到 GitHub。
    使用本機已有的 git 認證（SSH key 或 macOS Keychain），無需額外設定 Token。
    """
    import subprocess

    # 先匯出 JSON
    export_to_json(code)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    now_str  = datetime.now().strftime('%Y-%m-%d %H:%M')

    try:
        # ── 預防性清除 lock 檔（避免上次異常中斷殘留）──
        for _lf in ['HEAD.lock', 'index.lock']:
            _lp = os.path.join(base_dir, '.git', _lf)
            if os.path.exists(_lp):
                try:
                    os.remove(_lp)
                    print(f'已清除殘留 lock 檔：{_lf}')
                except Exception as _le:
                    return False, f'Lock 檔無法清除（{_lf}），請手動執行：rm -f ~/台股分析工具/.git/{_lf}'

        # ── 更新 _sync_time.py（觸發 Streamlit Cloud 自動重新部署）──
        _trigger_path = os.path.join(base_dir, '_sync_time.py')
        with open(_trigger_path, 'w', encoding='utf-8') as _f:
            _f.write(f'# 每次資料同步自動更新，用於觸發 Streamlit Cloud 重新部署，請勿手動修改\n')
            _f.write(f'LAST_SYNC = "{now_str}"\n')

        # git add data/json/ + _sync_time.py
        subprocess.run(
            ['git', 'add', 'data/json/', '_sync_time.py'],
            cwd=base_dir, check=True, capture_output=True, text=True
        )
        # git commit（若沒有變更也不報錯）
        result = subprocess.run(
            ['git', 'commit', '-m', f'sync data {now_str}'],
            cwd=base_dir, capture_output=True, text=True
        )
        if 'nothing to commit' in result.stdout or 'nothing to commit' in result.stderr:
            print('資料沒有變化，無需推送')
            return True, '資料沒有變化，無需推送'
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            print(f'git commit 失敗：{err}')
            return False, f'Commit 失敗：{err}'
        # git push
        push = subprocess.run(
            ['git', 'push'],
            cwd=base_dir, capture_output=True, text=True
        )
        if push.returncode != 0:
            err = push.stderr.strip()
            print(f'git push 失敗：{err}')
            return False, f'推送失敗：{err}'
        print(f'Git 推送成功：{now_str}')
        return True, '同步完成'
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        print(f'Git 操作失敗：{err}')
        return False, f'Git 失敗：{err}'
    except Exception as e:
        print(f'同步失敗：{e}')
        return False, str(e)


# ── 上傳到 GitHub ────────────────────────
def sync_to_github(code=None):
    if not is_github_configured():
        print('GitHub 未設定，跳過備份')
        print('如需啟用，請在 config.py 填入 GITHUB_TOKEN 和 GITHUB_REPO')
        return False

    try:
        from github import Github
        g    = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
    except Exception as e:
        print(f'GitHub 連線失敗：{e}')
        return False

    # 先匯出 JSON
    export_to_json(code)

    # 上傳所有 JSON 檔案
    success = 0
    fail    = 0

    for fname in os.listdir(JSON_DIR):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(JSON_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            github_path = f'data/json/{fname}'
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

            try:
                # 檔案已存在，更新
                existing = repo.get_contents(github_path, ref=GITHUB_BRANCH)
                repo.update_file(
                    github_path,
                    f'更新資料 {now_str}',
                    content,
                    existing.sha,
                    branch=GITHUB_BRANCH
                )
            except:
                # 檔案不存在，新增
                repo.create_file(
                    github_path,
                    f'新增資料 {now_str}',
                    content,
                    branch=GITHUB_BRANCH
                )
            success += 1
            print(f'上傳 {fname} 成功')

        except Exception as e:
            fail += 1
            print(f'上傳 {fname} 失敗：{e}')

    print(f'\nGitHub 備份完成：成功 {success} 筆，失敗 {fail} 筆')
    return fail == 0

# ── 從 GitHub 讀取資料（網頁版用）───────
def load_from_github(code):
    if not is_github_configured():
        return None
    try:
        from github import Github
        g    = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        path = f'data/{code}.json'
        file = repo.get_contents(path, ref=GITHUB_BRANCH)
        data = json.loads(file.decoded_content.decode('utf-8'))
        return data
    except Exception as e:
        print(f'從 GitHub 讀取 {code} 失敗：{e}')
        return None

# ── 從 GitHub 讀取自選股 ─────────────────
def load_watchlist_from_github():
    if not is_github_configured():
        return []
    try:
        from github import Github
        g    = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        file = repo.get_contents('data/watchlist.json', ref=GITHUB_BRANCH)
        data = json.loads(file.decoded_content.decode('utf-8'))
        return data
    except Exception as e:
        print(f'從 GitHub 讀取自選股失敗：{e}')
        return []

# ── 從 GitHub 讀取更新狀態 ───────────────
def load_meta_from_github():
    if not is_github_configured():
        return None
    try:
        from github import Github
        g    = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        file = repo.get_contents('data/meta.json', ref=GITHUB_BRANCH)
        data = json.loads(file.decoded_content.decode('utf-8'))
        return data
    except Exception as e:
        print(f'從 GitHub 讀取 meta 失敗：{e}')
        return None


# ── 雲端版：從 JSON 匯入資料到 DB ──────────
def init_cloud_data():
    """
    雲端版啟動時呼叫（由 _init_cloud_cache 包裹，版本不變時不重複執行）。
    Streamlit Cloud 部署時會 clone 整個 repo（含 data/json/），
    直接讀本地 JSON 檔案。每次 _sync_time.py 觸發重新部署後，
    本地檔案就是最新的。
    """
    from database import (save_prices, save_fundamental,
                          save_chips, save_stock_info,
                          add_watchlist, get_conn, get_tags)

    print('雲端模式：從本地 JSON 匯入資料...')

    # ── 清空 chips 資料，確保從 JSON 乾淨重寫 ──
    try:
        conn = get_conn()
        conn.execute('DELETE FROM chips')
        conn.commit()
        conn.close()
        print('  chips 資料已清空，準備從 JSON 重新匯入')
    except Exception as e:
        print(f'  清空 chips 失敗：{e}')

    # ── 股票清單（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'stocks.json'), encoding='utf-8') as f:
            stocks = json.load(f)
        for s in stocks:
            save_stock_info(s['code'], s['name'], s.get('market',''), s.get('industry',''))
        print(f'  股票清單：{len(stocks)} 筆')
    except Exception as e:
        print(f'  股票清單匯入失敗：{e}')
        stocks = []

    # ── 自訂標籤（每次更新）──
    try:
        tags_path = os.path.join(JSON_DIR, 'watchlist_tags.json')
        with open(tags_path, encoding='utf-8') as f:
            tags_list = json.load(f)
        conn = get_conn()
        conn.execute('DELETE FROM watchlist_tags')
        for i, t in enumerate(tags_list):
            conn.execute('INSERT OR IGNORE INTO watchlist_tags (name, sort_order) VALUES (?,?)', (t, i))
        conn.commit()
        conn.close()
        print(f'  自訂標籤：{len(tags_list)} 個')
    except Exception as e:
        print(f'  自訂標籤匯入失敗（使用預設值）：{e}')

    # ── 自選股清單（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'watchlist.json'), encoding='utf-8') as f:
            wl = json.load(f)
        for w in wl:
            tags_val = w.get('tags') or w.get('tag', '')
            add_watchlist(w['code'], w['name'], tags_val)
        print(f'  自選股：{len(wl)} 筆')
    except Exception as e:
        print(f'  自選股匯入失敗：{e}')

    # ── 大盤融資融券（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'market_margin.json'), encoding='utf-8') as f:
            mm = json.load(f)
        from database import save_market_margin
        for r in mm.get('rows', []):
            save_market_margin(r['date'], r)
        print(f'  大盤融資融券：{len(mm.get("rows", []))} 筆')
    except Exception as e:
        print(f'  大盤融資融券匯入失敗：{e}')

    # ── 大盤 TAIEX（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'TAIEX.json'), encoding='utf-8') as f:
            taiex = json.load(f)
        prices = taiex.get('prices', [])
        if prices:
            save_stock_info('TAIEX', '加權指數', 'TWSE', '大盤')
            save_prices('TAIEX', prices)
            print(f'  大盤 TAIEX：{len(prices)} 筆（更新至 {prices[-1]["date"]}）')
    except Exception as e:
        print(f'  TAIEX 匯入失敗：{e}')

    # ── 法人排行 T86（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 't86.json'), encoding='utf-8') as f:
            t86 = json.load(f)
        date = t86.get('date')
        if date:
            from database import save_t86_ranking
            all_rows = {}
            for key in ('trust_top', 'trust_bot', 'foreign_top',
                        'foreign_bot', 'total_top', 'total_bot'):
                for r in t86.get(key, []):
                    all_rows[r['code']] = r
            save_t86_ranking(date, list(all_rows.values()))
            print(f'  T86 法人排行：{date}，{len(all_rows)} 筆')
    except Exception as e:
        print(f'  T86 匯入失敗：{e}')

    # ── 除權息（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'exdividend.json'), encoding='utf-8') as f:
            exd = json.load(f)
        rows = exd.get('rows', [])
        if rows:
            from database import save_exdividend
            save_exdividend(rows)
            print(f'  除權息：{len(rows)} 筆')
    except Exception as e:
        print(f'  除權息匯入失敗：{e}')

    # ── 台指期三大法人未平倉（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'futures_institutional.json'), encoding='utf-8') as f:
            fut = json.load(f)
        rows = fut.get('rows', [])
        if rows:
            from database import save_futures_institutional
            for r in rows:
                save_futures_institutional(r['date'], r)
            print(f'  台指期未平倉：{len(rows)} 筆')
    except Exception as e:
        print(f'  台指期未平倉匯入失敗：{e}')

    # ── 大盤本益比（每次更新）──
    try:
        with open(os.path.join(JSON_DIR, 'market_pe.json'), encoding='utf-8') as f:
            pe = json.load(f)
        rows = pe.get('rows', [])
        if rows:
            from database import save_market_pe
            for r in rows:
                save_market_pe(r['date'], r.get('pe_ratio'), r.get('pb_ratio'), r.get('div_yield'))
            print(f'  大盤本益比：{len(rows)} 筆')
    except Exception as e:
        print(f'  大盤本益比匯入失敗：{e}')

    # ── 三大法人現貨彙總（先清空再寫入，確保資料完整）──
    try:
        agg_path = os.path.join(JSON_DIR, 'chips_market_agg.json')
        with open(agg_path, encoding='utf-8') as f:
            agg = json.load(f)
        rows = agg.get('rows', [])
        if rows:
            from database import save_chips_market_agg, get_conn as _gc_agg
            # 先清空舊資料再寫入，避免殘留舊日期
            _ac = _gc_agg()
            _ac.execute('DELETE FROM chips_market_agg')
            _ac.commit()
            _ac.close()
            save_chips_market_agg(rows)
            last_date = rows[-1]['date'] if rows else '?'
            print(f'  三大法人現貨彙總：{len(rows)} 天，最新：{last_date}')
    except Exception as e:
        print(f'  三大法人現貨彙總匯入失敗：{e}')

    # ── 選擇權 P/C 比率（每次更新）──
    try:
        pc_path = os.path.join(JSON_DIR, 'options_pc.json')
        with open(pc_path, encoding='utf-8') as f:
            pc = json.load(f)
        rows = pc.get('rows', [])
        if rows:
            from database import save_options_pc, get_conn as _gc_pc
            _pc = _gc_pc()
            _pc.execute('DELETE FROM options_pc_ratio')
            _pc.commit()
            _pc.close()
            for r in rows:
                save_options_pc(r['date'], r['call_oi'], r['put_oi'], r['pc_ratio'])
            print(f'  P/C 比率：{len(rows)} 天')
    except Exception as e:
        print(f'  P/C 比率匯入失敗：{e}')

    # ── DRAM 現貨價格（每次更新）──
    try:
        dram_path = os.path.join(JSON_DIR, 'dram_prices.json')
        with open(dram_path, encoding='utf-8') as f:
            dram_json = json.load(f)
        rows = dram_json.get('rows', [])
        if rows:
            from database import save_dram_price, get_conn as _gc_dram
            _dc = _gc_dram()
            _dc.execute('DELETE FROM dram_prices')
            _dc.commit()
            _dc.close()
            for r in rows:
                save_dram_price(r['date'], r.get('spot_price'), r.get('spot_chg_pct'),
                                r.get('contract_price'))
            print(f'  DRAM 現貨價格：{len(rows)} 筆')
    except Exception as e:
        print(f'  DRAM 現貨價格匯入失敗：{e}')

    # ── 個股季度財報（每次更新）──
    try:
        qf_path = os.path.join(JSON_DIR, 'quarterly_financials.json')
        with open(qf_path, encoding='utf-8') as f:
            qf_json = json.load(f)
        qf_data = qf_json.get('data', {})
        if qf_data:
            from database import save_quarterly_financials, get_conn as _gc_qf
            _qfc = _gc_qf()
            _qfc.execute('DELETE FROM stock_quarterly_financials')
            _qfc.commit()
            _qfc.close()
            total_q = 0
            for _code, _rows in qf_data.items():
                for r in _rows:
                    save_quarterly_financials(
                        _code, r['period'], r.get('revenue'), r.get('gross_profit'),
                        r.get('gross_margin'), r.get('operating_income'), r.get('net_income')
                    )
                    total_q += 1
            print(f'  個股季度財報：{len(qf_data)} 支股票，{total_q} 筆')
    except Exception as e:
        print(f'  個股季度財報匯入失敗：{e}')

    # ── 個股業務分部營收（每次更新）──
    try:
        sr_path = os.path.join(JSON_DIR, 'segment_revenue.json')
        with open(sr_path, encoding='utf-8') as f:
            sr_json = json.load(f)
        sr_data = sr_json.get('data', {})
        if sr_data:
            from database import save_segment_revenue, get_conn as _gc_sr
            _src = _gc_sr()
            _src.execute('DELETE FROM stock_segment_revenue')
            _src.commit()
            _src.close()
            total_s = 0
            for _code, _rows in sr_data.items():
                for r in _rows:
                    save_segment_revenue(
                        _code, r['period'], r['segment'],
                        r.get('revenue_pct', 0), r.get('revenue_abs'), r.get('note', '')
                    )
                    total_s += 1
            print(f'  個股業務分部營收：{len(sr_data)} 支股票，{total_s} 筆')
    except Exception as e:
        print(f'  個股業務分部營收匯入失敗：{e}')

    # ── 各股票歷史資料（每次都更新）──
    imported = 0
    for fname in os.listdir(JSON_DIR):
        if not fname.endswith('.json'):
            continue
        code = fname[:-5]
        if code in ('stocks', 'watchlist', 'meta', 't86', 'exdividend', 'TAIEX',
                    'market_margin', 'futures_institutional', 'market_pe', 'chips_market_agg',
                    'watchlist_tags', 'options_pc', 'dram_prices',
                    'quarterly_financials', 'segment_revenue'):
            continue
        try:
            with open(os.path.join(JSON_DIR, fname), encoding='utf-8') as f:
                data = json.load(f)
            prices = data.get('prices', [])
            if prices:
                save_prices(code, prices)
            for fd in data.get('fundamentals', []):
                save_fundamental(code, fd['date'], fd.get('eps_ttm'),
                                 fd.get('pe'), fd.get('pb'), fd.get('dividend_yield'))
            for ch in data.get('chips', []):
                save_chips(code, ch['date'], ch)
            imported += 1
        except Exception as e:
            print(f'  {code} 匯入失敗：{e}')

    print(f'雲端模式：JSON 匯入完成，{imported} 支股票')


if __name__ == '__main__':
    if is_github_configured():
        print('GitHub 已設定，可以備份')
        sync_to_github()
    else:
        print('GitHub 未設定')
        print('請在 config.py 填入：')
        print('  GITHUB_TOKEN = "your_token"')
        print('  GITHUB_REPO  = "your_account/your_repo"')
        export_to_json()
        print('已匯出 JSON 到本機')
