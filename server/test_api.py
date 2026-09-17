"""API 자체 점검. 서버를 띄우고 실제 HTTP로 때린다.  python3 test_api.py"""
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

os.environ["BIDNOTE_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

import api  # noqa: E402  (DB 경로를 먼저 잡아야 한다)
import db   # noqa: E402

PORT = 8931
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = f"https://{api.APP_NAME}.apps.tossmini.com"


def req(method, path, body=None, key="user-a", origin=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if key:
        r.add_header("X-Toss-Key", key)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if origin:
        r.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None), resp.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None), e.headers


def seed():
    con = db.init()
    for i, (nm, lrg, mid, amt, clse) in enumerate([
        ("SW 개발 용역", "ICT 서비스", "SW 및 시스템 개발", 50_000_000, "2099-01-01 00:00:00"),
        ("유지관리 용역", "ICT 서비스", "운영 및 유지관리", 20_000_000, "2099-01-01 00:00:00"),
        ("청소 용역", "시설물관리 및 청소서비스", "청소", 10_000_000, "2099-01-01 00:00:00"),
        ("지난 SW 용역", "ICT 서비스", "SW 및 시스템 개발", 30_000_000, "2020-01-01 00:00:00"),
    ]):
        con.execute("""insert into notice(bid_ntce_no,bid_ntce_ord,work_type,bid_ntce_nm,
                       lrg_clsfc,mid_clsfc,cntrct_mthd,presmpt_prce,bid_clse_dt,raw)
                       values(?,'0','용역',?,?,?,'일반경쟁',?,?,'{}')""",
                    (f"N{i}", nm, lrg, mid, amt, clse))
    con.commit()
    con.close()


def main():
    seed()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), api.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    try:
        s, b, _ = req("GET", "/health")
        assert s == 200 and b["ok"] and b["notices"] == 4, b

        # 인증
        s, b, _ = req("GET", "/conditions", key=None)
        assert s == 401, (s, b)

        # 분류 트리
        s, b, _ = req("GET", "/classifications")
        assert s == 200 and len(b) == 2, b
        ict = [x for x in b if x["name"] == "ICT 서비스"][0]
        assert {c["name"] for c in ict["children"]} == {"SW 및 시스템 개발", "운영 및 유지관리"}

        # 분류도 키워드도 없으면 거부 (일 180건 소음 방지)
        s, b, _ = req("POST", "/conditions", {"cntrct_mthd": "수의계약"})
        assert s == 422, (s, b)

        # 잘못된 업무유형
        s, b, _ = req("POST", "/conditions", {"lrg_clsfc": "ICT 서비스", "work_type": "헛소리"})
        assert s == 422, (s, b)

        # 정상 등록
        s, b, _ = req("POST", "/conditions",
                      {"label": "SW개발", "lrg_clsfc": "ICT 서비스",
                       "mid_clsfc": "SW 및 시스템 개발", "amt_max": 100_000_000})
        assert s == 201, (s, b)
        cid = b["id"]

        s, b, _ = req("GET", "/conditions")
        assert s == 200 and len(b) == 1 and b[0]["label"] == "SW개발", b

        # 무료 한도
        for _ in range(api.FREE_CONDITIONS - 1):
            assert req("POST", "/conditions", {"lrg_clsfc": "ICT 서비스"})[0] == 201
        s, b, _ = req("POST", "/conditions", {"lrg_clsfc": "ICT 서비스"})
        assert s == 402, (s, b)

        # 유저 격리 — 다른 키는 남의 조건이 안 보인다
        s, b, _ = req("GET", "/conditions", key="user-b")
        assert s == 200 and b == [], b

        # 매칭 후 공고 조회: 마감 지난 건은 빠진다
        import g2b
        con = db.connect()
        con.execute("update app_user set push_ok=1")
        con.commit()
        g2b.match(con)
        con.close()

        s, b, _ = req("GET", "/notices")
        names = {x["bid_ntce_nm"] for x in b}
        assert "지난 SW 용역" not in names, names
        assert "SW 개발 용역" in names, names

        s, b2, _ = req("GET", f"/notices?cond_id={cid}")
        assert {x["bid_ntce_nm"] for x in b2} == {"SW 개발 용역"}, b2

        # 남의 조건 id로는 못 본다
        s, b3, _ = req("GET", f"/notices?cond_id={cid}", key="user-b")
        assert b3 == [], b3

        # 푸시 동의
        assert req("POST", "/push-consent", {"agreed": False})[0] == 204
        con = db.connect()
        assert con.execute("select push_ok from app_user where toss_key='user-a'"
                           ).fetchone()["push_ok"] == 0
        con.close()

        # 삭제 + 남의 것 삭제 불가
        assert req("DELETE", f"/conditions/{cid}", key="user-b")[0] == 404
        assert req("DELETE", f"/conditions/{cid}")[0] == 204
        assert req("DELETE", f"/conditions/{cid}")[0] == 404

        # CORS
        _, _, h = req("GET", "/health", origin=ORIGIN)
        assert h["Access-Control-Allow-Origin"] == ORIGIN, dict(h)
        _, _, h = req("GET", "/health", origin="https://evil.example")
        assert h["Access-Control-Allow-Origin"] != "https://evil.example", dict(h)

        # 404 / 깨진 JSON
        assert req("GET", "/nope")[0] == 404
        r = urllib.request.Request(BASE + "/conditions", data=b"{oops", method="POST")
        r.add_header("X-Toss-Key", "user-a")
        try:
            urllib.request.urlopen(r, timeout=5)
            raise AssertionError("깨진 JSON이 통과했다")
        except urllib.error.HTTPError as e:
            assert e.code == 400, e.code

        print("통과. 엔드포인트 6종 · 검증 21건")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
