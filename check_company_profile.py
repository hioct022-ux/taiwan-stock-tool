"""
檢查公開資訊觀測站「主要經營業務」抓不抓得到（2026-11-24）

個股基本面頁的「🧩 主力產品」會自動抓這個欄位。這支只印診斷、不寫入 DB，
抓不到時用它看是連線、網站改版、還是被擋。

用法：
  cd ~/台股分析工具
  python3 check_company_profile.py 2492 2330 3324
"""
import sys
import requests

from fetcher import _MOPS_T05ST03_URL, _parse_t05st03, HEADERS

codes = sys.argv[1:] or ['2492', '2330', '3324']
for code in codes:
    form = {'encodeURIComponent': 1, 'step': 1, 'firstin': 1, 'off': 1,
            'queryName': 'co_id', 'inpuType': 'co_id', 'TYPEK': 'all', 'co_id': code}
    print(f'===== {code} =====')
    try:
        r = requests.post(_MOPS_T05ST03_URL, data=form, headers=HEADERS, timeout=20)
    except Exception as e:
        print('  連線失敗：', e)
        continue
    html = r.content.decode('utf-8', errors='replace')
    if '主要經營業務' not in html:
        html = r.content.decode('cp950', errors='replace')
    print(f'  HTTP {r.status_code}　長度 {len(r.content)} bytes　'
          f'含「主要經營業務」：{"是" if "主要經營業務" in html else "否"}　'
          f'含代號 {code}：{"是" if code in html else "否"}')
    txt, err = _parse_t05st03(html, code)
    if txt:
        print('  ✅ 解析結果：')
        for line in txt.splitlines():
            print('    ' + line)
    else:
        print('  ❌', err)
        print('  回應開頭：', ' '.join(html[:300].split()))
