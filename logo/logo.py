#!/usr/bin/env python3
"""앱 로고 생성.  python3 logo.py

토스 콘솔 요구: 600×600 PNG · 정사각형 · 둥근 모서리 불가(토스가 자체 마스킹)
· 배경색 필수 · 라이트/다크 2종.

컨셉: 레이더. 스윕이 지나간 자리에 블립 하나가 켜져 있다 —
공고가 뜨기 전에 포착한다는 제품 그대로다.
4배로 그린 뒤 축소해 안티앨리어싱을 얻는다.
"""
import math

from PIL import Image, ImageDraw

SIZE, S = 600, 4
N = SIZE * S

THEMES = {
    # 이름: (배경, 링, 스윕, 블립)
    "light": ((49, 130, 246), (255, 255, 255, 105), (255, 255, 255), (255, 255, 255)),
    # 다크 UI에서 눈부시지 않게 채도와 밝기를 낮춘다
    "dark": ((23, 50, 94), (120, 170, 235, 110), (150, 195, 245), (120, 200, 255)),
}

SWEEP_DEG = 78          # 스윕 부채꼴 각도
BLIP_ANGLE = -52        # 스윕 선의 각도 (12시 기준 시계방향)


def radar(bg, ring, sweep, blip):
    """72px에서 읽히는 게 기준이다. 링은 2겹만, 두껍게.
    블립은 스윕 선에서 충분히 떨어뜨려 형태가 겹치지 않게 한다."""
    img = Image.new("RGB", (N, N), bg)
    d = ImageDraw.Draw(img, "RGBA")
    cx = cy = N // 2
    R = int(N * 0.335)

    # 스윕: 선 뒤로 잔상이 남는 부채꼴. 작은 크기에서도 보이게 진하게.
    steps = 24
    for i in range(steps):
        a1 = BLIP_ANGLE - 90
        a0 = a1 - SWEEP_DEG * (i + 1) / steps
        alpha = int(88 * (1 - i / steps) ** 1.4) + 8
        d.pieslice((cx - R, cy - R, cx + R, cy + R), a0, a1, fill=sweep + (alpha,))

    # 링 2겹 — 3겹은 72px에서 흐릿한 원 하나로 뭉친다
    for f in (1.00, 0.56):
        r = int(R * f)
        d.ellipse((cx - r, cy - r, cx + r, cy + r),
                  outline=ring, width=int(N * 0.038))

    # 스윕 선
    a = math.radians(BLIP_ANGLE - 90)
    d.line((cx, cy, cx + R * math.cos(a), cy + R * math.sin(a)),
           fill=sweep, width=int(N * 0.032))

    # 중심점
    c = int(N * 0.022)
    d.ellipse((cx - c, cy - c, cx + c, cy + c), fill=sweep)

    # 블립 — 스윕 선에서 멀찍이. 겹치면 뭉쳐 보인다.
    ba = math.radians(BLIP_ANGLE - 90 - 128)
    bx = cx + R * 0.66 * math.cos(ba)
    by = cy + R * 0.66 * math.sin(ba)
    glow = int(N * 0.090)
    d.ellipse((bx - glow, by - glow, bx + glow, by + glow), fill=blip + (85,))
    dot = int(N * 0.052)
    d.ellipse((bx - dot, by - dot, bx + dot, by + dot), fill=blip)

    return img


def main():
    for name, (bg, ring, sweep, blip) in THEMES.items():
        img = radar(bg, ring, sweep, blip).resize((SIZE, SIZE), Image.LANCZOS)
        img.save(f"logo-{name}.png", "PNG", optimize=True)
        img.resize((72, 72), Image.LANCZOS).save(f"logo-{name}-72.png", "PNG")
        print(f"  logo-{name}.png  600×600  ({'밝은 UI용' if name == 'light' else '어두운 UI용'})")
    print("\n*-72.png는 실제 노출 크기 확인용. 콘솔엔 600×600을 올린다.")


if __name__ == "__main__":
    main()
