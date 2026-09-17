#!/usr/bin/env python3
"""나라장터 입찰공고 API 1주차 검증 — 만들기 전에 접을지 결정하는 스크립트.

사용:
    export G2B_KEY='디코딩된_서비스키'
    python3 g2b_check.py              # 전체 검증
    python3 g2b_check.py --days 30    # 조회 기간 변경

판정 기준: 키워드 하나당 월 30건 이상 나와야 알림 서비스로 성립한다.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta

BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"

# 업무유형별 오퍼레이션. 공사/외자는 문서 미확인이라 실패하면 리포트에 남는다.
OPS = {
    "물품": "getBidPblancListInfoThngPPSSrch",
    "용역": "getBidPblancListInfoServcPPSSrch",
    "공사": "getBidPblancListInfoCnstwkPPSSrch",
    "외자": "getBidPblancListInfoFrgcptPPSSrch",
}

# 가상 유저의 관심 키워드. 실제 타깃에 맞게 바꿔가며 돌려라.
KEYWORDS = [
    "홈페이지", "소프트웨어", "시스템 유지관리", "정보화", "데이터",
    "청소", "경비", "급식", "인쇄", "전산장비",
]

# 푸시 문구/매칭에 쓸 수 있어야 하는 필드. 실제로 채워져 오는지 본다.
WANT = [
    "bidNtceNo", "bidNtceNm", "ntceInsttNm", "dminsttNm",
    "bidNtceDt", "bidClseDt", "opengDt",
    "presmptPrce", "asignBdgtAmt",
    "bidNtceDtlUrl", "rgstDt",
]


def call(op, params, key, timeout=20):
    q = {"ServiceKey": key, "type": "json", "inqryDiv": "1", **params}
    # ServiceKey는 이미 디코딩된 값이므로 quote_via로 한 번만 인코딩
    url = f"{BASE}/{op}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # data.go.kr은 인증·한도 오류를 HTTP 4xx/5xx 본문에 XML로 담아 보낸다
        detail = e.read().decode("utf-8", "replace")[:300] if e.fp else ""
        return None, f"HTTP {e.code} {detail}".strip()
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if raw.lstrip().startswith("<"):           # 에러는 XML로 온다
        return None, raw[:300]
    try:
        body = json.loads(raw).get("response", {}).get("body", {})
    except json.JSONDecodeError:
        return None, f"JSON 아님: {raw[:200]}"
    items = body.get("items") or []
    if isinstance(items, dict):                 # 1건일 때 dict로 오는 경우
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return {"total": int(body.get("totalCount", 0)), "items": items}, None


def window(days):
    end = datetime.now()
    return (end - timedelta(days=days)).strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="조회 기간(일)")
    ap.add_argument("--rows", type=int, default=999)
    args = ap.parse_args()

    key = os.environ.get("G2B_KEY")
    if not key:
        sys.exit("G2B_KEY 환경변수가 없다.  export G2B_KEY='디코딩된_서비스키'")

    bgn, end = window(args.days)
    print(f"조회 기간: {bgn} ~ {end}  ({args.days}일)\n")
    calls = 0

    # ── 1. 오퍼레이션 4종이 살아있는지 + 전체 물량 ────────────────────────
    print("=" * 62)
    print("1. 업무유형별 전체 공고량")
    print("=" * 62)
    alive, totals = {}, {}
    for label, op in OPS.items():
        res, err = call(op, {"inqryBgnDt": bgn, "inqryEndDt": end,
                             "pageNo": "1", "numOfRows": "1"}, key)
        calls += 1
        if err:
            print(f"  {label:4} ✗  {err.strip()[:110]}")
            continue
        alive[label], totals[label] = op, res["total"]
        per_day = res["total"] / args.days
        print(f"  {label:4} ✓  {res['total']:>7,}건   (일 {per_day:>7,.0f}건)")
        time.sleep(0.2)

    if not alive:
        sys.exit("\n모든 오퍼레이션 실패. 키 활성화(최대 1영업일) 또는 인코딩 확인.")

    # ── 2. 응답 필드가 실제로 채워져 오는가 ───────────────────────────────
    print("\n" + "=" * 62)
    print("2. 필드 충족률  (푸시 문구·매칭에 쓸 수 있는지)")
    print("=" * 62)
    label = "용역" if "용역" in alive else next(iter(alive))
    res, err = call(alive[label], {"inqryBgnDt": bgn, "inqryEndDt": end,
                                   "pageNo": "1", "numOfRows": "100"}, key)
    calls += 1
    if err:
        print("  샘플 조회 실패:", err[:120])
    else:
        n = len(res["items"])
        print(f"  표본 {n}건 ({label})\n")
        filled = Counter()
        for it in res["items"]:
            for f in WANT:
                v = it.get(f)
                if v not in (None, "", " "):
                    filled[f] += 1
        for f in WANT:
            pct = filled[f] / n * 100 if n else 0
            mark = "✓" if pct >= 90 else ("△" if pct >= 30 else "✗")
            print(f"    {mark} {f:<18} {pct:5.1f}%")
        extra = sorted(set(res["items"][0]) - set(WANT)) if res["items"] else []
        if extra:
            print(f"\n  그 외 응답 필드: {', '.join(extra)}")

    # ── 3. 키워드별 밀도 — 이게 본 판정이다 ──────────────────────────────
    print("\n" + "=" * 62)
    print(f"3. 키워드별 공고 밀도  ← 판정 기준: 월 30건 이상")
    print("=" * 62)
    print(f"  {'키워드':<16}{'기간내':>8}{'월환산':>9}   판정")
    print("  " + "-" * 46)
    verdict = {}
    for kw in KEYWORDS:
        total = 0
        for op in alive.values():
            res, err = call(op, {"inqryBgnDt": bgn, "inqryEndDt": end,
                                 "bidNtceNm": kw, "pageNo": "1",
                                 "numOfRows": "1"}, key)
            calls += 1
            if res:
                total += res["total"]
            time.sleep(0.2)
        monthly = total / args.days * 30
        verdict[kw] = monthly
        mark = "✓ 충분" if monthly >= 30 else ("△ 애매" if monthly >= 10 else "✗ 부족")
        print(f"  {kw:<16}{total:>8,}{monthly:>9,.0f}   {mark}")

    # ── 4. 증분 조회가 되는가 (아키텍처 전제) ─────────────────────────────
    print("\n" + "=" * 62)
    print("4. 증분 조회 동작 확인  (diff 없이 갈 수 있는지)")
    print("=" * 62)
    op = alive.get("용역") or next(iter(alive.values()))
    y0 = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    a, _ = call(op, {"inqryBgnDt": y0 + "0000", "inqryEndDt": y0 + "1159",
                     "pageNo": "1", "numOfRows": "1"}, key)
    b, _ = call(op, {"inqryBgnDt": y0 + "1200", "inqryEndDt": y0 + "2359",
                     "pageNo": "1", "numOfRows": "1"}, key)
    c, _ = call(op, {"inqryBgnDt": y0 + "0000", "inqryEndDt": y0 + "2359",
                     "pageNo": "1", "numOfRows": "1"}, key)
    calls += 3
    if a and b and c:
        ok = abs((a["total"] + b["total"]) - c["total"]) <= max(2, c["total"] * 0.02)
        print(f"  오전 {a['total']} + 오후 {b['total']} = {a['total']+b['total']}  vs  종일 {c['total']}")
        print("  → 시간 단위 증분 조회 " + ("✓ 동작 (스냅샷 diff 불필요)" if ok
              else "✗ 불일치 — diff 필요할 수 있음"))
    else:
        print("  확인 실패")

    # ── 판정 ─────────────────────────────────────────────────────────────
    good = [k for k, v in verdict.items() if v >= 30]
    print("\n" + "=" * 62)
    print(f"API 호출 {calls}건 사용 (개발계정 한도 1,000건/일)")
    print("=" * 62)
    print(f"월 30건 넘는 키워드: {len(good)}/{len(KEYWORDS)}개")
    if good:
        print("  " + ", ".join(good))
    print()
    if len(good) >= len(KEYWORDS) * 0.4:
        print("판정: 진행.  다음은 발견성 검증 — 토스 앱에서 B2B 니치 앱 순위를 직접 확인한다.")
    elif good:
        print("판정: 조건부.  되는 키워드가 일부뿐이다. 타깃을 그 업종으로 좁힐 수 있는지 본다.")
    else:
        print("판정: 중단.  알림 밀도가 안 나온다. 아파트 실거래가와 같은 함정이다.")


if __name__ == "__main__":
    main()
