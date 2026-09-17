"""미니앱이 부르는 REST API. 의존성 없음 — python3 api.py 로 뜬다.

    python3 api.py            # 0.0.0.0:8000
    PORT=9000 python3 api.py

사용자 식별은 토스 익명키(X-Toss-Key 헤더). 로그인·사업자등록 없이 동작한다.
앞단 TLS는 Caddy가 처리한다(README).
"""
import json
import os
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import db

APP_NAME = os.environ.get("APP_NAME", "bidscope")  # 콘솔에서 확정한 appName
ORIGINS = [
    f"https://{APP_NAME}.apps.tossmini.com",
    f"https://{APP_NAME}.private-apps.tossmini.com",
]
FREE_CONDITIONS = 3
WORK_TYPES = {"용역", "물품", "공사", "외자"}

ROUTES = []


def route(method, pattern):
    rx = re.compile(f"^{pattern}$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


class Err(Exception):
    def __init__(self, status, msg):
        self.status, self.msg = status, msg


def user_id(con, req):
    key = req.headers.get("X-Toss-Key", "").strip()
    if not key:
        raise Err(401, "X-Toss-Key 헤더가 없어요")
    row = con.execute("select id from app_user where toss_key=?", (key,)).fetchone()
    if row:
        return row["id"]
    uid = con.execute("insert into app_user(toss_key) values(?)", (key,)).lastrowid
    con.commit()
    return uid


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@route("GET", "/health")
def health(con, req, m, q, body):
    n = con.execute("select count(*) c from notice_latest").fetchone()["c"]
    cur = {r["work_type"]: r["last_dt"] for r in con.execute("select * from cursor")}
    return {"ok": True, "notices": n, "cursors": cur}


@route("GET", "/classifications")
def classifications(con, req, m, q, body):
    """조건 등록 화면용 분류 트리. 실제 공고에 있는 것만 내려준다."""
    wt = (q.get("work_type") or ["용역"])[0]
    rows = con.execute("""
        select lrg_clsfc, mid_clsfc, count(*) n
          from notice_latest
         where work_type=? and lrg_clsfc is not null
         group by 1,2 order by lrg_clsfc, n desc""", (wt,)).fetchall()
    tree = {}
    for r in rows:
        tree.setdefault(r["lrg_clsfc"], []).append(
            {"name": r["mid_clsfc"], "count": r["n"]})
    return [{"name": k, "children": v} for k, v in tree.items()]


@route("GET", "/conditions")
def list_conditions(con, req, m, q, body):
    uid = user_id(con, req)
    return [dict(r) for r in con.execute(
        "select * from condition where user_id=? and active=1 order by id desc", (uid,))]


@route("POST", "/conditions")
def add_condition(con, req, m, q, body):
    uid = user_id(con, req)
    lrg = body.get("lrg_clsfc") or None
    kw = (body.get("keyword") or "").strip() or None
    # 실측: 분류 없이 계약방법만 걸면 일 180건이 잡힌다. 알림이 아니라 소음이 된다.
    if not lrg and not kw:
        raise Err(422, "분류를 고르거나 키워드를 넣어주세요")
    wt = body.get("work_type") or "용역"
    if wt not in WORK_TYPES:
        raise Err(422, "업무유형이 올바르지 않아요")
    n = con.execute("select count(*) c from condition where user_id=? and active=1",
                    (uid,)).fetchone()["c"]
    if n >= FREE_CONDITIONS:
        # ponytail: 무료 한도 하드코딩. 구독 붙일 때 plan 컬럼으로 뺀다
        raise Err(402, f"무료는 조건 {FREE_CONDITIONS}개까지예요")
    cid = con.execute("""
        insert into condition
          (user_id,label,work_type,lrg_clsfc,mid_clsfc,amt_min,amt_max,cntrct_mthd,keyword)
        values (?,?,?,?,?,?,?,?,?)""",
        (uid, (body.get("label") or "")[:12] or None, wt, lrg,
         body.get("mid_clsfc") or None,
         int(body.get("amt_min") or 0), int(body.get("amt_max") or 0),
         body.get("cntrct_mthd") or None, kw[:40] if kw else None)).lastrowid
    con.commit()
    return {"id": cid}, 201


@route("DELETE", r"/conditions/(\d+)")
def del_condition(con, req, m, q, body):
    uid = user_id(con, req)
    # active=1 조건이 없으면 이미 지운 것도 rowcount 1이 나와 204가 된다
    cur = con.execute(
        "update condition set active=0 where id=? and user_id=? and active=1",
        (int(m.group(1)), uid))
    con.commit()
    if not cur.rowcount:
        raise Err(404, "없는 조건이에요")
    return None, 204


@route("GET", "/notices")
def notices(con, req, m, q, body):
    """내 조건에 매칭된 공고. 마감 임박순, 마감분 제외."""
    uid = user_id(con, req)
    sql = """
        select distinct n.bid_ntce_no, n.bid_ntce_nm, n.ntce_instt_nm, n.lrg_clsfc,
               n.mid_clsfc, n.cntrct_mthd, n.presmpt_prce, n.bid_ntce_dt,
               n.bid_clse_dt, n.detail_url, c.id cond_id, c.label
          from notified t
          join condition c on c.id=t.condition_id and c.user_id=? and c.active=1
          join notice_latest n on n.bid_ntce_no=t.bid_ntce_no
         where (n.bid_clse_dt is null or n.bid_clse_dt >= datetime('now','localtime'))"""
    args = [uid]
    if q.get("cond_id"):
        sql += " and c.id=?"
        args.append(int(q["cond_id"][0]))
    sql += " order by (n.bid_clse_dt is null), n.bid_clse_dt limit ?"
    args.append(min(int((q.get("limit") or [30])[0]), 100))
    return [dict(r) for r in con.execute(sql, args)]


@route("GET", "/prespecs")
def prespecs(con, req, m, q, body):
    """내 조건에 걸린 사전규격(공고 예고). 의견 마감 임박순."""
    uid = user_id(con, req)
    return [dict(r) for r in con.execute("""
        select distinct p.spec_no, p.spec_nm, p.order_instt, p.budget,
               p.opnin_clse_dt, p.bid_ntce_no, p.doc_url, c.id cond_id, c.label
          from prespec_notified t
          join condition c on c.id=t.condition_id and c.user_id=? and c.active=1
          join prespec   p on p.spec_no=t.spec_no
         where (p.opnin_clse_dt is null or p.opnin_clse_dt >= datetime('now','localtime'))
         order by (p.opnin_clse_dt is null), p.opnin_clse_dt limit ?""",
        (uid, min(int((q.get("limit") or [30])[0]), 100)))]


@route("POST", "/push-consent")
def push_consent(con, req, m, q, body):
    """Notification.requestAgreement() 결과를 서버에 저장."""
    uid = user_id(con, req)
    con.execute("update app_user set push_ok=? where id=?",
                (1 if body.get("agreed", True) else 0, uid))
    con.commit()
    return None, 204


# ── 서버 ─────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "bidnote"

    def log_message(self, fmt, *a):
        print(f"{self.address_string()} {fmt % a}")

    def _cors(self):
        origin = self.headers.get("Origin", "")
        self.send_header("Access-Control-Allow-Origin",
                         origin if origin in ORIGINS else ORIGINS[0])
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Toss-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def _send(self, status, payload):
        data = b"" if payload is None else json.dumps(
            payload, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        if data:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, None)

    def _handle(self, method):
        u = urlparse(self.path)
        con = None
        try:
            body = {}
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                body = json.loads(self.rfile.read(n) or b"{}")
            for meth, rx, fn in ROUTES:
                if meth != method:
                    continue
                m = rx.match(u.path)
                if m:
                    con = db.connect()
                    out = fn(con, self, m, parse_qs(u.query), body)
                    payload, status = out if isinstance(out, tuple) else (out, 200)
                    return self._send(status, payload)
            self._send(404, {"error": "not found"})
        except Err as e:
            self._send(e.status, {"error": e.msg})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})
        except Exception:
            traceback.print_exc()
            self._send(500, {"error": "internal"})
        finally:
            if con:
                con.close()

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")


def main():
    db.init()
    port = int(os.environ.get("PORT", 8000))
    print(f"bidnote api :{port}  (appName={APP_NAME})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
