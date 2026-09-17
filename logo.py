#!/usr/bin/env python3
"""앱 로고 생성.  python3 logo.py

토스 콘솔 요구: 600×600 PNG · 정사각형 · 둥근 모서리 불가 · 배경색 필수.
(토스가 자체 마스킹을 하므로 우리가 모서리를 깎으면 이중으로 깎인다)

컨셉: 많은 공고 중 '내 것' 하나만 파랗게. 제품이 하는 일 그대로다.
4배로 그린 뒤 축소해서 안티앨리어싱을 얻는다.
"""
from PIL import Image, ImageDraw

SIZE = 600
S = 4                      # 슈퍼샘플링 배율
BLUE = (49, 130, 246)      # 토스 브랜드 #3182F6
WHITE = (255, 255, 255)
GREY = (205, 213, 223)
INK = (25, 31, 40)


def rounded(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def card_variant(bg, card, line_dim, line_hi):
    """문서 카드 + 강조된 한 줄."""
    img = Image.new("RGB", (SIZE * S, SIZE * S), bg)
    d = ImageDraw.Draw(img)
    n = SIZE * S

    # 문서 카드 (여기 모서리는 둥글어도 된다 — 아이콘 외곽이 아니라 그림이다)
    cw, ch = int(n * 0.50), int(n * 0.60)
    cx, cy = (n - cw) // 2, (n - ch) // 2
    rounded(d, (cx, cy, cx + cw, cy + ch), int(n * 0.045), card)

    # 안쪽 줄: 위 2개는 흐리게, 3번째가 내 공고
    pad = int(cw * 0.16)
    lh = int(ch * 0.075)
    gap = int(ch * 0.135)
    top = cy + int(ch * 0.20)
    widths = [0.68, 0.52, 0.80, 0.44]
    for i, w in enumerate(widths):
        y = top + i * (lh + gap)
        hi = i == 2
        x2 = cx + pad + int((cw - pad * 2) * w)
        rounded(d, (cx + pad, y, x2, y + (lh if not hi else int(lh * 1.25))),
                lh, line_hi if hi else line_dim)
    return img


def bell_variant():
    """종 실루엣. 더 단순해서 작은 크기에서 강하다."""
    n = SIZE * S
    img = Image.new("RGB", (n, n), BLUE)
    d = ImageDraw.Draw(img)
    cx = n // 2
    # 몸통
    top, bot = int(n * 0.26), int(n * 0.63)
    w = int(n * 0.34)
    d.pieslice((cx - w, top, cx + w, top + w * 2), 180, 360, fill=WHITE)
    d.rectangle((cx - w, top + w, cx + w, bot), fill=WHITE)
    # 아랫단
    d.rounded_rectangle((cx - int(n * 0.40), bot, cx + int(n * 0.40),
                         bot + int(n * 0.055)), radius=int(n * 0.03), fill=WHITE)
    # 추
    d.ellipse((cx - int(n * 0.055), bot + int(n * 0.075),
               cx + int(n * 0.055), bot + int(n * 0.185)), fill=WHITE)
    # 손잡이
    d.ellipse((cx - int(n * 0.045), int(n * 0.195),
               cx + int(n * 0.045), int(n * 0.285)), fill=WHITE)
    return img


VARIANTS = {
    # 이름: (이미지, 설명)
    "logo-card-blue": (lambda: card_variant(BLUE, WHITE, GREY, BLUE),
                       "블루 배경 · 흰 문서 · 파란 강조줄"),
    "logo-card-white": (lambda: card_variant(WHITE, (244, 246, 249), GREY, BLUE),
                        "흰 배경 · 회색 문서 · 파란 강조줄"),
    "logo-card-ink": (lambda: card_variant(INK, (38, 46, 58), (80, 92, 108), BLUE),
                      "잉크 배경 · 파란 강조줄"),
    "logo-bell": (bell_variant, "블루 배경 · 흰 종"),
}


def main():
    for name, (make, desc) in VARIANTS.items():
        img = make().resize((SIZE, SIZE), Image.LANCZOS)
        img.save(f"{name}.png", "PNG", optimize=True)
        # 작은 크기에서 읽히는지 미리보기
        img.resize((72, 72), Image.LANCZOS).save(f"{name}-72.png", "PNG")
        print(f"  {name}.png  600×600  — {desc}")
    print("\n작은 크기 확인용 *-72.png도 같이 만들었다. 콘솔엔 600×600을 올린다.")


if __name__ == "__main__":
    main()
