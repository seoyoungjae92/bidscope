#!/usr/bin/env python3
"""사전규격 측정 — 이름과 MVP 범위를 결정하는 스크립트.

    https://www.data.go.kr/data/15129437/openapi.do  ← 활용신청(자동승인) 먼저
    export G2B_KEY='디코딩_인증키'
    python3 prespec_check.py

재는 것:
  1. 사전규격 물량 (일 몇 건)
  2. 리드타임 — 사전규격이 입찰공고보다 며칠 먼저 뜨나  ← 핵심
  3. 의견 접수 마감까지 남는 시간 (규격에 개입할 수 있는 창)
  4. ICT/SW 등 타깃 분류의 비중

판정:
  리드타임 5일 이상 + 일 30건 이상  →  사전규격을 메인으로. 이름은 '입찰레이더'
  그 외                            →  공고 알림이 메인. 이름은 '입찰알리미'
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

SPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
SPEC_OPS = {
    "용역": "getPublicPrcureThngInfoServc",
    "물품": "getPublicPrcureThngInfoThng",
    "공사": "getPublicPrcureThngInfoCnstwk",
}
BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
BID_OPS = {"용역": "getBidPblancListInfoServcPPSSrch"}

DAYS = 14


def call(base, op, key, **params):
    q = {"ServiceKey": key, "type": "json", "inqryDiv": "1",
         "pageNo": "1", "numOfRows": "300", **params}
    url = f"{base}/{op}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    try:
        raw = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200] if e.fp else ""
        return None, f"HTTP {e.code} {body}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if raw.lstrip().startswith("<"):
        return None, raw[:200]
    b = json.loads(raw).get("response", {}).get("body", {})
    items = b.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    return {"total": int(b.get("totalCount", 0)), "items": items}, None


def pick(d, *names):
    for n in names:
        v = d.get(n)
        if v not in (None, "", " "):
            return v
    return None


def parse_dt(s):
    if not s:
        return None
    s = str(s).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def main():
    key = os.environ.get("G2B_KEY")
    if not key:
        sys.exit("G2B_KEY 환경변수가 없다.")
    end = datetime.now()
    bgn = end - timedelta(days=DAYS)
    win = {"inqryBgnDt": bgn.strftime("%Y%m%d0000"),
           "inqryEndDt": end.strftime("%Y%m%d2359")}

    # ── 1. 물량 ──────────────────────────────────────────────────────────
    print("=" * 62)
    print(f"1. 사전규격 물량 ({DAYS}일)")
    print("=" * 62)
    samples = {}
    for label, op in SPEC_OPS.items():
        r, err = call(SPEC_BASE, op, key, **win)
        if err:
            print(f"  {label:4} ✗  {err[:90]}")
            if "NOT_REGISTERED" in err:
                print("\n  → 15129437 활용신청이 안 돼 있다. 신청 후 다시 실행:")
                print("     https://www.data.go.kr/data/15129437/openapi.do")
                return
            continue
        samples[label] = r["items"]
        print(f"  {label:4} ✓  {r['total']:>6,}건   일 {r['total']/DAYS:>5.0f}건")
        time.sleep(0.2)

    if not samples:
        sys.exit("\n전부 실패. 엔드포인트나 키를 확인해라.")

    # ── 2. 응답 필드 ─────────────────────────────────────────────────────
    label = "용역" if "용역" in samples else next(iter(samples))
    items = samples[label]
    print("\n" + "=" * 62)
    print(f"2. 응답 필드 ({label}, 표본 {len(items)}건)")
    print("=" * 62)
    if items:
        print("  " + ", ".join(sorted(items[0].keys())))

    # ── 3. 리드타임 ← 핵심 ───────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("3. 리드타임  ← 이게 이름과 MVP 범위를 정한다")
    print("=" * 62)
    leads, opinion_windows = [], []
    for it in items:
        reg = parse_dt(pick(it, "rgstDt", "specRgstDt", "bfSpecRgstDt"))
        clse = parse_dt(pick(it, "opninRgstClseDt", "opnnRgstClseDt", "specClseDt"))
        if reg and clse:
            d = (clse - reg).days
            if 0 <= d <= 120:
                opinion_windows.append(d)
        if reg:
            leads.append(reg)
    if opinion_windows:
        opinion_windows.sort()
        mid = opinion_windows[len(opinion_windows) // 2]
        print(f"  등록 → 의견마감 중앙값 {mid}일  "
              f"(최소 {opinion_windows[0]} / 최대 {opinion_windows[-1]})")
        print("  = 규격에 의견을 낼 수 있는 창. 입찰공고는 보통 이 뒤에 난다")
    else:
        print("  등록일/의견마감일 필드를 못 찾았다. 위 필드 목록에서 직접 확인해라")

    # 사전규격 사업명이 실제 입찰공고에 뜨는지 대조
    print("\n  [대조] 사전규격 사업명으로 입찰공고를 찾아본다")
    hit = miss = 0
    for it in items[:12]:
        nm = pick(it, "prdctClsfcNoNm", "bfSpecNm", "prdctSpecNm", "asignBdgtAmtNm")
        if not nm:
            continue
        token = str(nm).split()[0][:10]
        r, err = call(BID_BASE, BID_OPS["용역"], key, bidNtceNm=token,
                      inqryBgnDt=(end - timedelta(days=60)).strftime("%Y%m%d0000"),
                      inqryEndDt=end.strftime("%Y%m%d2359"), numOfRows="1")
        if r and r["total"]:
            hit += 1
        else:
            miss += 1
        time.sleep(0.2)
    if hit + miss:
        print(f"    표본 {hit+miss}건 중 공고 발견 {hit}건 ({hit/(hit+miss)*100:.0f}%)")
        print("    ※ 사업명 표기가 달라 놓치는 경우가 있어 하한선으로 본다")

    # ── 4. 타깃 분류 비중 ────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("4. 분류 분포 (타깃이 충분히 있나)")
    print("=" * 62)
    for f in ("pubPrcrmntLrgClsfcNm", "prdctClsfcNoNm", "dminsttNm"):
        c = Counter(str(pick(it, f) or "(없음)")[:34] for it in items)
        if len(c) > 1:
            print(f"\n  [{f}] 고유값 {len(c)}개")
            for k, v in c.most_common(8):
                print(f"    {v:>4}  {k}")
            break

    # ── 판정 ─────────────────────────────────────────────────────────────
    daily = sum(len(v) for v in samples.values()) / DAYS
    lead_ok = bool(opinion_windows) and opinion_windows[len(opinion_windows) // 2] >= 5
    print("\n" + "=" * 62)
    if lead_ok and daily >= 30:
        print("판정: 사전규격을 메인으로.  이름 → 입찰레이더 / bidscope")
        print("      '미리 포착한다'가 제품의 핵심 가치가 된다")
    else:
        print("판정: 공고 알림이 메인.  이름 → 입찰알리미 / bidalarm")
        print(f"      (리드타임 {'충분' if lead_ok else '부족'}, 일 {daily:.0f}건)")
        print("      사전규격은 v1.1 보조 기능으로")
    print("=" * 62)


if __name__ == "__main__":
    main()
