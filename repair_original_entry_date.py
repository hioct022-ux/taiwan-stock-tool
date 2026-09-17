"""
回填 positions.original_entry_date（2026-09-12 新增，一次性腳本）

═══ 背景 / 要解決的問題（陷阱47）═══
`renew_position()`（策略C 續抱）會把 `entry_date` 重設為今天，但**不動 `entry_price`**。
於是續抱過的部位，「進場日」與「進場價」對不起來。

實際資料中的證據：緯創登錄 `entry_date=2026-08-13`、`entry_price=169.5`，
但 8/12 收 193.5，台股有 10% 漲跌幅限制、8/13 跌停也只到 174.2，
**根本不可能成交在 169.5**。169.5 其實落在 2026-08-03（低 169.5）的區間內，
續抱一輪後日期被推到 8/13。六筆持倉的 `renew_count` 全都 ≥ 1，全部有這個問題。

影響分開看：
  ✅ `pnl_pct` / `entry_score` / `entry_ms` —— 都對應「最初進場」，彼此一致，統計不失真
  ❌ `entry_date` 與由它算出的「持有天數」—— 只反映本輪，會誤導

═══ 這支腳本做什麼 ═══
`renew_count = 0` 的部位：`original_entry_date = entry_date`（精確）。

`renew_count > 0` 的部位：無法直接還原，改用**兩段推估 + 價格驗證**：
  1. 先算理論值：`entry_date` 往前推 `renew_count × HOLD_DAYS` 個交易日
  2. 再用 `entry_price` 驗證——在理論值附近找「當日 low ≤ entry_price ≤ high」的交易日
  3. 找得到就用它（標 `matched`），找不到就退回理論值（標 `estimated`）

第 2 步是關鍵：進場價一定落在當日高低區間內，這個條件足以把候選日縮到一兩天。
緯創實測：理論值 7/30（低157.5 高170.5）**本身就包含 169.5**，兩種方法互相印證。

═══ 使用方式 ═══
  python3 repair_original_entry_date.py            # 試跑，只報告不寫入
  python3 repair_original_entry_date.py --apply    # 實際寫入

  執行前建議備份：cp data/stock.db data/stock.db.bak-$(date +%Y%m%d)
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_conn, init_db
from config import HOLD_DAYS

APPLY = '--apply' in sys.argv
init_db()          # 確保 original_entry_date 欄位存在


def trading_days():
    """TAIEX 的實際交易日（升序）——全專案缺口最少的日期序列。"""
    conn = get_conn()
    try:
        return [r[0] for r in conn.execute(
            "SELECT date FROM prices WHERE code='TAIEX' ORDER BY date").fetchall()]
    finally:
        conn.close()


def price_range(conn, code, date):
    r = conn.execute('SELECT low, high FROM prices WHERE code=? AND date=?',
                     (code, date)).fetchone()
    return (r[0], r[1]) if r and r[0] and r[1] else (None, None)


def infer(conn, cal, code, entry_date, entry_price, renew_count):
    """回傳 (推估的原始進場日, 依據說明)。"""
    if renew_count <= 0:
        return entry_date, '未續抱，直接沿用'

    if entry_date not in cal:
        return None, f'進場日 {entry_date} 不在 TAIEX 交易日序列中，無法推估'

    i = cal.index(entry_date)
    back = renew_count * HOLD_DAYS
    est_i = max(0, i - back)
    est = cal[est_i]

    # 用進場價驗證：在理論值附近找「當日高低區間包含 entry_price」的交易日
    for span in (5, 15):
        lo_i, hi_i = max(0, est_i - span), min(len(cal) - 1, est_i + span)
        hits = []
        for j in range(lo_i, hi_i + 1):
            lo, hi = price_range(conn, code, cal[j])
            if lo is not None and lo <= entry_price <= hi:
                hits.append((abs(j - est_i), cal[j]))
        if hits:
            hits.sort()
            best = hits[0][1]
            note = f'理論值 {est}（往前 {back} 個交易日）；'
            note += ('進場價正好落在該日高低區間內 ✅'
                     if best == est else
                     f'進場價落在 {best} 的高低區間內，採用它')
            return best, note
    return est, f'理論值 {est}（往前 {back} 個交易日）；⚠️ 附近找不到能容納 {entry_price} 的交易日'


def main():
    cal = trading_days()
    if len(cal) < 50:
        print('TAIEX 交易日資料不足，無法推估')
        return

    conn = get_conn()
    rows = conn.execute('''SELECT id, code, name, entry_date, entry_price,
                                  renew_count, status, original_entry_date
                             FROM positions ORDER BY entry_date''').fetchall()
    print(f'共 {len(rows)} 筆持倉　模式：'
          + ('★ 實際寫入' if APPLY else '試跑（不寫入，加 --apply 才會寫）'))
    print('=' * 92)

    todo = []
    for pid, code, name, ed, ep, rc, status, existing in rows:
        if existing:
            print(f'  #{pid} {code} {name}　已有 original_entry_date={existing}，略過')
            continue
        orig, why = infer(conn, cal, code, ed, ep, rc or 0)
        if orig is None:
            print(f'  #{pid} {code} {name}　❌ {why}')
            continue
        span = ''
        if orig in cal and ed in cal:
            span = f'　累計 {cal.index(ed) - cal.index(orig) + 1} 個交易日起算'
        print(f'  #{pid} {code} {name:6}[{status}] 續抱{rc}次')
        print(f'       本輪起算 {ed}　進場價 {ep}')
        print(f'       → 推估原始進場日 **{orig}**{span}')
        print(f'         依據：{why}')
        todo.append((pid, orig))

    if APPLY and todo:
        for pid, orig in todo:
            conn.execute('UPDATE positions SET original_entry_date=? WHERE id=?',
                         (orig, pid))
        conn.commit()
        print()
        print(f'✅ 已寫入 {len(todo)} 筆')
        print('※ 推估值可能不精確——持倉列的 ✏️ 編輯表單可手動修正原始進場日。')
    elif not APPLY:
        print()
        print('※ 確認上面的推估合理後，執行：python3 repair_original_entry_date.py --apply')
    conn.close()


if __name__ == '__main__':
    main()
