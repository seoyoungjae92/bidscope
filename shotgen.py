#!/usr/bin/env python3
"""콘솔용 스크린샷 3장을 만든다.  python3 shotgen.py

앱 화면을 날것으로 올리면 목록에서 읽히지 않는다. 검색 결과에 이미지가
노출될 때 문구가 먼저 읽히도록, 캡처 위에 한 줄을 얹은 형태로 만든다.

토스 규격: 세로 636×1048 PNG, 최소 3장.
의존성 0 — HTML을 쓰고 크롬 헤드리스로 렌더한다(PIL은 이 맥의 3.9에서 빌드가 안 된다).

원본 캡처는 shots/raw/ 에 둔다. 앱 화면이 바뀌면 거기에 새로 캡처를 넣고
(python3 shot.py 로 636×1048에 맞춘 뒤) 이 스크립트를 다시 돌린다.
"""
import html
import pathlib
import shutil
import subprocess
import sys

W, H = 636, 1048
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = pathlib.Path("shots")
RAW = OUT / "raw"

# (출력이름, 원본캡처, 배지, 큰 문구, 설명)
# 문구는 VERIFIED.md의 실측에서만 가져온다 — 사전규격 중앙값 7일 선행.
PANELS = [
    ("01-lead.png", "03-notices.png", "공고 예고",
     "공고 뜨기 전에<br>미리 알려드려요",
     "사전규격은 입찰공고보다 보통 7일 먼저 올라와요"),
    ("02-setup.png", "01-setup.png", "조건 등록",
     "분야만 고르면<br>끝이에요",
     "내 조건에 맞는 공고만 골라서 보여드려요"),
    ("03-alert.png", "02-home.png", "알림",
     "새 공고가 뜨면<br>알림으로",
     "매일 아침 한 번. 마감 임박도 놓치지 않게"),
]

PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {w}px; height: {h}px; overflow: hidden;
    font-family: "Apple SD Gothic Neo", -apple-system, sans-serif;
    background: #fff;
  }}
  /* 위는 브랜드 블루, 아래는 흰색. 카드가 경계에 걸치게 둔다 */
  .hero {{
    position: absolute; left: 0; right: 0; top: 0; height: 468px;
    background: linear-gradient(180deg, #3182f6 0%, #1f68dd 100%);
  }}
  .top {{ position: relative; padding: 64px 52px 0; color: #fff; }}
  .badge {{
    display: inline-block; padding: 7px 16px; border-radius: 999px;
    background: rgba(255,255,255,.22); font-size: 21px; font-weight: 700;
    letter-spacing: -.02em; margin-bottom: 22px;
  }}
  h1 {{ font-size: 46px; font-weight: 800; line-height: 1.28; letter-spacing: -.035em; }}
  p  {{ margin-top: 16px; font-size: 22px; line-height: 1.5;
        letter-spacing: -.02em; color: rgba(255,255,255,.86); }}
  /* 기기 화면. 위쪽만 보여주고 아래는 자연스럽게 잘리게 둔다 */
  .device {{
    position: absolute; left: 68px; right: 68px; top: 452px; bottom: 0;
    border-radius: 26px 26px 0 0; overflow: hidden;
    background: #fff; box-shadow: 0 18px 48px rgba(16,42,86,.28);
  }}
  .device img {{ width: 100%; display: block; }}
</style></head><body>
  <div class="hero"></div>
  <div class="top">
    <span class="badge">{badge}</span>
    <h1>{head}</h1>
    <p>{sub}</p>
  </div>
  <div class="device"><img src="{img}"></div>
</body></html>"""


def main():
    if not pathlib.Path(CHROME).exists():
        sys.exit("크롬이 없어요. CHROME 경로를 고치세요.")
    RAW.mkdir(parents=True, exist_ok=True)
    # 처음 한 번: 기존 캡처를 raw/로 옮긴다
    for _, src, *_ in PANELS:
        if (OUT / src).exists() and not (RAW / src).exists():
            shutil.move(str(OUT / src), str(RAW / src))

    tmp = pathlib.Path("/tmp/bidscope-shots")
    tmp.mkdir(exist_ok=True)
    for name, src, badge, head, sub in PANELS:
        img = (RAW / src).resolve()
        if not img.exists():
            sys.exit(f"원본 캡처가 없어요: {img}")
        page = tmp / (name + ".html")
        page.write_text(PAGE.format(w=W, h=H, badge=html.escape(badge),
                                    head=head, sub=html.escape(sub),
                                    img=img.as_uri()), encoding="utf-8")
        dst = OUT / name
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={W},{H}",
                        "--allow-file-access-from-files",
                        f"--screenshot={dst.resolve()}", page.as_uri()],
                       check=True, capture_output=True)
        print(f"  {dst}  {W}×{H}")
    print("\n원본 캡처는 shots/raw/ 에 있어요. 콘솔엔 shots/0*.png 3장을 올려요.")


if __name__ == "__main__":
    main()
