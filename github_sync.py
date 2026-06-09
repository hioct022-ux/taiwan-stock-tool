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
            stock_data = {
                'code':         c,
                'prices':       get_prices(c, days=400),
                'fundamentals': get_fundamentals(c, days=400),
                'chips':        get_chips(c, days=65),
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
        import os
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
def _cj(name):
    """雲端專用：從 GitHub raw URL 直接抓 JSON，繞過部署時的靜態檔案"""
    data = load_raw(f'data/json/{name}')
    if data is None:
        raise RuntimeError(f'無法從 GitHub 取得 {name}')
    return data


def init_cloud_data():
    """
    雲端版啟動時呼叫（由 _init_cloud_cache 包裹，版本不變時不重複執行）。
    直接從 GitHub raw URL 抓最新 JSON，不依賴部署時的靜態檔案。
    """
    from database import (save_prices, save_fundamental,
                          save_chips, save_stock_info,
                          add_watchlist, get_conn, get_tags)

    print('雲端模式：從 GitHub 直接匯入最新 JSON...')

    # ── 清空 chips 資料，確保從 JSON 乾淨重寫 ──
    try:
        conn = get_conn()
        conn.execute('DELETE FROM chips')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'  清空 chips 失敗：{e}')

    # ── 股票清單（每次更新）──
    stocks = []
    try:
        stocks = _cj('stocks.json')
        for s in stocks:
            save_stock_info(s['code'], s['name'], s.get('market', ''), s.get('industry', ''))
        print(f'  股票清單：{len(stocks)} 筆')
    except Exception as e:
        print(f'  股票清單匯入失敗：{e}')

    # ── 自訂標籤（每次更新）──
    try:
        tags_list = _cj('watchlist_tags.json')
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
        wl = _cj('watchlist.json')
        for w in wl:
            tags_val = w.get('tags') or w.get('tag', '')
            add_watchlist(w['code'], w['name'], tags_val)
        print(f'  自選股：{len(wl)} 筆')
    except Exception as e:
        print(f'  自選股匯入失敗：{e}')

    # ── 大盤融資融券（每次更新）──
    try:
        mm = _cj('market_margin.json')
        from database import save_market_margin
        for r in mm.get('rows', []):
            save_market_margin(r['date'], r)
        print(f'  大盤融資融券：{len(mm.get("rows", []))} 筆')
    except Exception as e:
        print(f'  大盤融資融券匯入失敗：{e}')

    # ── 大盤 TAIEX（每次更新）──
    try:
        taiex = _cj('TAIEX.json')
        prices = taiex.get('prices', [])
        if prices:
            save_stock_info('TAIEX', '加權指數', 'TWSE', '大盤')
            save_prices('TAIEX', prices)
            print(f'  大盤 TAIEX：{len(prices)} 筆（更新至 {prices[-1]["date"]}）')
    except Exception as e:
        print(f'  TAIEX 匯入失敗：{e}')

    # ── 法人排行 T86（每次更新）──
    try:
        t86 = _cj('t86.json')
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
        exd = _cj('exdividend.json')
        rows = exd.get('rows', [])
        if rows:
            from database import save_exdividend
            save_exdividend(rows)
            print(f'  除權息：{len(rows)} 筆')
    except Exception as e:
        print(f'  除權息匯入失敗：{e}')

    # ── 台指期三大法人未平倉（每次更新）──
    try:
        fut = _cj('futures_institutional.json')
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
        pe = _cj('market_pe.json')
        rows = pe.get('rows', [])
        if rows:
            from database import save_market_pe
            for r in rows:
                save_market_pe(r['date'], r.get('pe_ratio'), r.get('pb_ratio'), r.get('div_yield'))
            print(f'  大盤本益比：{len(rows)} 筆')
    except Exception as e:
        print(f'  大盤本益比匯入失敗：{e}')

    # ── 三大法人現貨彙總（每次更新）──
    try:
        agg = _cj('chips_market_agg.json')
        rows = agg.get('rows', [])
        if rows:
            from database import save_chips_market_agg
            save_chips_market_agg(rows)
            print(f'  三大法人現貨彙總：{len(rows)} 天')
    except Exception as e:
        print(f'  三大法人現貨彙總匯入失敗：{e}')

    # ── 各股票歷史資料（從 stocks 清單迭代，不依賴本地目錄）──
    imported = 0
    for s in stocks:
        code = s.get('code', '')
        if not code:
            continue
        try:
            data = _cj(f'{code}.json')
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
            # 非自選股可能沒有個股 JSON，靜默忽略
            pass

    print(f'雲端模式：GitHub JSON 匯入完成，{imported} 支股票')


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
