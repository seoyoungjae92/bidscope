"""나라장터 수집 + 조건 매칭 배치.

    python3 g2b.py collect          # 증분 수집 (커서 이후 신규 공고)
    python3 g2b.py match            # 신규 공고 → 조건 매칭 → 알림 큐
    python3 g2b.py run              # collect + match (크론에 이것만 걸면 된다)

증분 조회(inqryBgnDt/inqryEndDt)가 실측으로 정확히 동작하므로 스냅샷 diff는 없다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import db

BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
SPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
SPEC_OPS = {
    "용역": "getPublicPrcureThngInfoServc",
    "물품": "getPublicPrcureThngInfoThng",
    "공사": "getPublicPrcureThngInfoCnstwk",
}
OPS = {
    "용역": "getBidPblancListInfoServcPPSSrch",
    "물품": "getBidPblancListInfoThngPPSSrch",
    "공사": "getBidPblancListInfoCnstwkPPSSrch",
    "외자": "getBidPblancListInfoFrgcptPPSSrch",
}
# MVP는 용역만. 분류체계가 채워져 오는 유일한 업무유형이다(VERIFIED.md).
ACTIVE_TYPES = os.environ.get("BIDNOTE_TYPES", "용역").split(",")

ROWS = 300          # 페이지당. 일 400여건이라 넉넉하다
MAX_PAGES = 20      # 안전장치: 백필 폭주 방지
BACKFILL_DAYS = 3   # 커서가 없을 때 처음 긁을 기간

# 푸시 피로 방지. 실측상 넓은 조건은 일 180건까지 나온다(VERIFIED.md).
DAILY_CAP = 20
# 마감 임박 알림 창. 좁으면 준비할 시간이 없고, 넓으면 잊는다.
CLOSING_MIN_H, CLOSING_MAX_H = 6, 48


# 공고 시각은 KST. 컨테이너가 UTC면 매칭 창이 9시간 어긋난다.
# 컨테이너에 tzdata가 없으면 TZ를 줘도 tzset()이 UTC로 폴백한다.
# 그래서 시스템 타임존에 기대지 않고 오프셋을 직접 쓴다.
os.environ["TZ"] = "Asia/Seoul"
time.tzset()
KST = timezone(timedelta(hours=9))


def now_kst():
    """나라장터 API의 조회 구간은 KST 기준이다.
    naive datetime.now()를 쓰면 컨테이너(UTC)에서 9시간 전 구간을 조회해
    공고가 9시간씩 늦게 들어온다."""
    return datetime.now(KST)


def _key():
    k = os.environ.get("G2B_KEY")
    if not k:
        sys.exit("G2B_KEY 환경변수가 없다.")
    return k


def fetch(op, bgn, end, page, key, base=None):
    """한 페이지 조회. (items, total) 반환."""
    q = {
        "ServiceKey": key, "type": "json", "inqryDiv": "1",
        "inqryBgnDt": bgn, "inqryEndDt": end,
        "pageNo": str(page), "numOfRows": str(ROWS),
    }
    url = f"{base or BASE}/{op}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200] if e.fp else ""
            raise RuntimeError(f"HTTP {e.code} {detail}")
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"{type(e).__name__}: {e}")
            time.sleep(2 ** attempt)
    body = json.loads(raw).get("response", {}).get("body", {})
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0))


def _amt(v):
    """추정가격은 문자열로 오고 빈값·소수점이 섞인다."""
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _dt(v):
    """'2026-09-17 14:30' 형태로 통일. 빈값은 None."""
    s = (v or "").strip()
    return s if s else None


def row_of(item, work_type):
    return (
        item.get("bidNtceNo", ""),
        str(item.get("bidNtceOrd", "0")),
        work_type,
        item.get("bidNtceNm", ""),
        item.get("ntceInsttNm"),
        item.get("dminsttNm"),
        item.get("pubPrcrmntLrgClsfcNm"),
        item.get("pubPrcrmntMidClsfcNm"),
        item.get("cntrctCnclsMthdNm"),
        _amt(item.get("presmptPrce")),
        _dt(item.get("bidNtceDt")),
        _dt(item.get("bidClseDt")),
        _dt(item.get("opengDt")),
        item.get("bidNtceDtlUrl") or item.get("bidNtceUrl"),
        json.dumps(item, ensure_ascii=False),
    )


def collect(con, key):
    """커서 이후 신규 공고를 적재. 적재 건수 반환."""
    now = now_kst()
    end = now.strftime("%Y%m%d%H%M")
    inserted = 0

    for wt in ACTIVE_TYPES:
        op = OPS.get(wt)
        if not op:
            print(f"  {wt}: 알 수 없는 업무유형, 건너뜀")
            continue

        cur = con.execute("select last_dt from cursor where work_type=?", (wt,)).fetchone()
        bgn = cur["last_dt"] if cur else (now - timedelta(days=BACKFILL_DAYS)).strftime("%Y%m%d%H%M")
        if bgn >= end:
            print(f"  {wt}: 커서가 현재 이후({bgn}), 건너뜀")
            continue

        page, got, total = 1, 0, None
        while page <= MAX_PAGES:
            items, total = fetch(op, bgn, end, page, key)
            if not items:
                break
            rows = [row_of(i, wt) for i in items if i.get("bidNtceNo")]
            con.executemany(
                """insert or replace into notice
                   (bid_ntce_no,bid_ntce_ord,work_type,bid_ntce_nm,ntce_instt_nm,
                    dminstt_nm,lrg_clsfc,mid_clsfc,cntrct_mthd,presmpt_prce,
                    bid_ntce_dt,bid_clse_dt,openg_dt,detail_url,raw)
                   values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
            got += len(rows)
            if got >= (total or 0):
                break
            page += 1
            time.sleep(0.2)

        # 커서는 조회 성공 후에만 전진. 실패하면 다음 실행이 같은 구간을 다시 긁는다.
        con.execute(
            "insert into cursor(work_type,last_dt) values(?,?) "
            "on conflict(work_type) do update set last_dt=excluded.last_dt", (wt, end))
        con.commit()
        inserted += got
        print(f"  {wt}: {bgn}~{end}  {got}건 (전체 {total})")

    return inserted


def collect_prespec(con, key):
    """사전규격 수집. 공고보다 중앙값 7일 먼저 뜬다.

    커서는 공고와 따로 둔다(work_type에 접미사). 한쪽이 실패해도
    다른 쪽 커서가 잘못 전진하지 않는다.
    """
    now = now_kst()
    end = now.strftime("%Y%m%d%H%M")
    total_got = 0

    for wt in ACTIVE_TYPES:
        op = SPEC_OPS.get(wt)
        if not op:
            continue
        ck = wt + ":spec"
        cur = con.execute("select last_dt from cursor where work_type=?", (ck,)).fetchone()
        bgn = cur["last_dt"] if cur else (now - timedelta(days=BACKFILL_DAYS)).strftime("%Y%m%d%H%M")
        if bgn >= end:
            continue

        page, got, total = 1, 0, None
        while page <= MAX_PAGES:
            items, total = fetch(op, bgn, end, page, key, base=SPEC_BASE)
            if not items:
                break
            rows = []
            for i in items:
                no = (i.get("bfSpecRgstNo") or "").strip()
                if not no:
                    continue
                rows.append((
                    no, wt, i.get("prdctClsfcNoNm") or "", i.get("orderInsttNm"),
                    i.get("bsnsDivNm"), 1 if i.get("swBizObjYn") == "Y" else 0,
                    _amt(i.get("asignBdgtAmt")), _dt(i.get("rgstDt")),
                    _dt(i.get("opninRgstClseDt")),
                    (i.get("bidNtceNoList") or "").strip() or None,
                    i.get("specDocFileUrl1") or None,
                    json.dumps(i, ensure_ascii=False),
                ))
            con.executemany(
                """insert or replace into prespec
                   (spec_no,work_type,spec_nm,order_instt,bsns_div,sw_biz,budget,
                    rgst_dt,opnin_clse_dt,bid_ntce_no,doc_url,raw)
                   values (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
            got += len(rows)
            if got >= (total or 0):
                break
            page += 1
            time.sleep(0.2)

        con.execute("insert into cursor(work_type,last_dt) values(?,?) "
                    "on conflict(work_type) do update set last_dt=excluded.last_dt", (ck, end))
        con.commit()
        total_got += got
        print(f"  {wt} 사전규격: {bgn}~{end}  {got}건 (전체 {total})")

    return total_got


# 사전규격에는 대/중분류가 없다(실측). 쓸 수 있는 축은 사업명·SW여부·예산뿐이라
# 조건을 근사한다: 키워드가 있으면 사업명 매칭, 없으면 ICT 계열은 SW사업으로.
# ponytail: 근사 매칭이다. 사용자가 사전규격용 키워드를 따로 넣게 하고 싶어지면 컬럼을 판다.
_PRESPEC_BODY = """
select c.id, p.spec_no
  from condition c
  join prespec p
    on p.work_type = c.work_type
   and (c.amt_min = 0 or p.budget >= c.amt_min)
   and (c.amt_max = 0 or p.budget <= c.amt_max)
   and (
        (c.keyword is not null and p.spec_nm like '%' || c.keyword || '%')
     or (c.keyword is null and c.lrg_clsfc = 'ICT 서비스' and p.sw_biz = 1)
       )
 where c.active = 1 and c.want_prespec = 1
   -- 의견 마감이 지났으면 규격에 개입할 수 없다. 알릴 이유가 사라진다
   and (p.opnin_clse_dt is null or p.opnin_clse_dt >= datetime('now','+9 hours'))
"""

PRESPEC_MATCH_SQL = ("insert or ignore into prespec_notified (condition_id, spec_no)"
                     + _PRESPEC_BODY
                     + " and p.seen_at >= datetime('now','+9 hours','-1 day')")

PRESPEC_BACKFILL_SQL = (
    "insert or ignore into prespec_notified (condition_id, spec_no, sent_at)"
    + _PRESPEC_BODY.replace("select c.id, p.spec_no",
                            "select c.id, p.spec_no, datetime('now','+9 hours')")
    + " and c.id = ?")


def match_prespec(con):
    before = con.execute("select count(*) c from prespec_notified").fetchone()["c"]
    con.execute(PRESPEC_MATCH_SQL)
    con.commit()
    return con.execute("select count(*) c from prespec_notified").fetchone()["c"] - before


def prespec_digest(con, cap=DAILY_CAP):
    rows = con.execute("""
        select u.id user_id, u.toss_key, c.label,
               p.spec_no, p.spec_nm, p.budget, p.opnin_clse_dt, p.order_instt
          from prespec_notified t
          join condition c on c.id = t.condition_id
          join app_user  u on u.id = c.user_id
          join prespec   p on p.spec_no = t.spec_no
         where t.sent_at is null and u.push_ok = 1 and c.active = 1
           and (p.opnin_clse_dt is null or p.opnin_clse_dt >= datetime('now','+9 hours'))
         order by u.id, p.opnin_clse_dt
    """).fetchall()
    out = {}
    for r in rows:
        v = out.setdefault(r["user_id"], {"toss_key": r["toss_key"], "items": [], "total": 0})
        v["total"] += 1
        if len(v["items"]) < cap:
            v["items"].append(dict(r))
    return out


def mark_prespec_sent(con, user_ids):
    con.executemany("""
        update prespec_notified set sent_at = datetime('now','+9 hours')
         where sent_at is null and condition_id in
               (select id from condition where user_id = ?)""",
        [(u,) for u in user_ids])
    con.commit()


# 조건 ↔ 공고 매칭. 전부 SQL 한 방으로 끝난다.
# notice_latest 뷰를 보므로 변경공고(차수 1~5)가 재알림되지 않는다.
_MATCH_BODY = """
select c.id, n.bid_ntce_no
  from condition c
  join notice_latest n
    on n.work_type = c.work_type
   and (c.lrg_clsfc   is null or n.lrg_clsfc   = c.lrg_clsfc)
   and (c.mid_clsfc   is null or n.mid_clsfc   = c.mid_clsfc)
   and (c.cntrct_mthd is null or n.cntrct_mthd = c.cntrct_mthd)
   and (c.amt_min = 0 or n.presmpt_prce >= c.amt_min)
   and (c.amt_max = 0 or n.presmpt_prce <= c.amt_max)
   and (c.keyword is null or n.bid_ntce_nm like '%' || c.keyword || '%')
 where c.active = 1
   -- 이미 마감된 공고는 알리지 않는다. 마감일시가 없는 건(14%)은 통과시킨다
   and (n.bid_clse_dt is null or n.bid_clse_dt >= datetime('now','+9 hours'))
"""

# 배치: 최근 수집분만 본다. 이미 처리한 공고를 매번 다시 훑지 않는다.
MATCH_SQL = ("insert or ignore into notified (condition_id, bid_ntce_no)"
             + _MATCH_BODY
             + " and n.seen_at >= datetime('now','+9 hours','-1 day')")

# 백필: 조건을 새로 만든 직후 기존 공고를 한 번에 채운다.
# sent_at을 미리 박아 푸시는 안 나가게 한다 — 등록하자마자 수십 건이
# 푸시로 쏟아지면 그대로 알림을 끈다.
BACKFILL_SQL = ("insert or ignore into notified (condition_id, bid_ntce_no, sent_at)"
                + _MATCH_BODY.replace("select c.id, n.bid_ntce_no",
                                      "select c.id, n.bid_ntce_no, datetime('now','+9 hours')")
                + " and c.id = ?")

def match(con):
    """신규 공고를 조건에 매칭해 알림 큐에 넣는다. 큐 적재 건수 반환."""
    before = con.execute("select count(*) c from notified").fetchone()["c"]
    con.execute(MATCH_SQL)
    con.commit()
    return con.execute("select count(*) c from notified").fetchone()["c"] - before


def backfill_condition(con, condition_id):
    """조건을 새로 만들면 기존 공고·사전규격을 즉시 채운다.

    이게 없으면 등록 직후 빈 화면을 본다 — 첫 세션에서 실제 공고를
    보여주는 게 이 앱에서 가장 중요한 순간이다.
    발송 완료로 표시해 푸시는 내보내지 않는다.
    """
    con.execute(BACKFILL_SQL, (condition_id,))
    con.execute(PRESPEC_BACKFILL_SQL, (condition_id,))
    con.commit()
    return (
        con.execute("select count(*) c from notified where condition_id=?",
                    (condition_id,)).fetchone()["c"],
        con.execute("select count(*) c from prespec_notified where condition_id=?",
                    (condition_id,)).fetchone()["c"],
    )


def pending_digest(con, cap=DAILY_CAP):
    """발송 대기분을 사용자별로 묶는다. 푸시는 사용자당 1건 다이제스트.

    cap은 푸시 본문에 실을 상위 건수다. total은 실제 전체 건수라
    "N건 중 상위 20건" 식으로 안내할 수 있다.
    """
    rows = con.execute("""
        select u.id user_id, u.toss_key, c.id cond_id, c.label,
               n.bid_ntce_no, n.bid_ntce_nm, n.presmpt_prce, n.bid_clse_dt
          from notified t
          join condition    c on c.id = t.condition_id
          join app_user     u on u.id = c.user_id
          join notice_latest n on n.bid_ntce_no = t.bid_ntce_no
         where t.sent_at is null and u.push_ok = 1
           and (n.bid_clse_dt is null or n.bid_clse_dt >= datetime('now','+9 hours'))
         order by u.id, (n.bid_clse_dt is null), n.bid_clse_dt
    """).fetchall()
    out = {}
    for r in rows:
        v = out.setdefault(r["user_id"], {"toss_key": r["toss_key"], "items": [], "total": 0})
        v["total"] += 1
        if len(v["items"]) < cap:
            v["items"].append(dict(r))
    return out


def closing_digest(con, cap=DAILY_CAP):
    """마감이 임박한 공고를 사용자별로 묶는다.

    이미 신규 알림을 받은 공고만 대상이다 — 처음 보는 공고를
    "곧 마감"이라고만 알리면 맥락이 없다.
    """
    rows = con.execute(f"""
        select u.id user_id, u.toss_key, c.id cond_id, c.label,
               n.bid_ntce_no, n.bid_ntce_nm, n.presmpt_prce, n.bid_clse_dt
          from notified t
          join condition    c on c.id = t.condition_id
          join app_user     u on u.id = c.user_id
          join notice_latest n on n.bid_ntce_no = t.bid_ntce_no
         where t.sent_at is not null
           and t.closing_sent_at is null
           and u.push_ok = 1
           and c.active = 1
           and n.bid_clse_dt is not null
           and n.bid_clse_dt >  datetime('now','+9 hours','+{CLOSING_MIN_H} hours')
           and n.bid_clse_dt <= datetime('now','+9 hours','+{CLOSING_MAX_H} hours')
         order by u.id, n.bid_clse_dt
    """).fetchall()
    out = {}
    for r in rows:
        v = out.setdefault(r["user_id"], {"toss_key": r["toss_key"], "items": [], "total": 0})
        v["total"] += 1
        if len(v["items"]) < cap:
            v["items"].append(dict(r))
    return out


def mark_closing_sent(con, user_ids):
    """마감 임박 발송 완료. 창을 벗어난 건도 함께 닫는다 —
    안 그러면 이미 마감된 공고가 큐에 영원히 남는다."""
    con.executemany(f"""
        update notified set closing_sent_at = datetime('now','+9 hours')
         where closing_sent_at is null and sent_at is not null
           and condition_id in (select id from condition where user_id = ?)
           and bid_ntce_no in (
                 select bid_ntce_no from notice_latest
                  where bid_clse_dt is not null
                    and bid_clse_dt <= datetime('now','+9 hours','+{CLOSING_MAX_H} hours'))""",
        [(u,) for u in user_ids])
    con.commit()


def mark_sent(con, user_ids):
    """발송 완료 처리. 상한 때문에 본문에 안 실린 건도 함께 소진한다
    (다음 배치에 밀리면 계속 쌓여서 영영 안 끝난다)."""
    con.executemany("""
        update notified set sent_at = datetime('now','+9 hours')
         where sent_at is null and condition_id in
               (select id from condition where user_id = ?)""",
        [(u,) for u in user_ids])
    con.commit()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    con = db.init()

    if cmd in ("collect", "run"):
        print("[수집]")
        key = _key()
        n = collect(con, key)
        n += collect_prespec(con, key)
        print(f"  총 {n}건 적재\n")

    if cmd in ("match", "run"):
        print("[매칭]")
        print(f"  공고 알림 큐 {match(con)}건 신규")
        print(f"  사전규격 큐 {match_prespec(con)}건 신규\n")
        d = pending_digest(con)
        print(f"[신규 발송 대기] 사용자 {len(d)}명")
        for uid, v in list(d.items())[:5]:
            print(f"  user {uid}: {v['total']}건")
        cd = closing_digest(con)
        print(f"[마감 임박 대기] 사용자 {len(cd)}명")
        for uid, v in list(cd.items())[:5]:
            print(f"  user {uid}: {v['total']}건")
        pd = prespec_digest(con)
        print(f"[사전규격 대기] 사용자 {len(pd)}명")
        for uid, v in list(pd.items())[:5]:
            print(f"  user {uid}: {v['total']}건")

    if cmd not in ("collect", "match", "run"):
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
