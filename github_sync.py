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


def load_meta_raw():
    """從 GitHub 讀取更新狀態（不需要 Token）"""
    return load_raw('data/json/meta.json')

# ── 檢查是否設定 GitHub ──────────────────
def is_github_configured():
    return bool(GITHUB_TOKEN and GITHUB_REPO)

# ── 匯出資料為 JSON ──────────────────────
def export_to_json(code=None):
    from database import (get_prices, get_fundamentals,
                          get_chips, get_watchlist, get_last_update)

    os.makedirs(JSON_DIR, exist_ok=True)

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

    print(f'JSON 匯出完成，路徑：{JSON_DIR}')

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
