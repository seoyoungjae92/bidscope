#!/usr/bin/env python3
"""스크린샷을 토스 규격(세로 636×1048)으로 맞춘다.

    python3 shot.py <입력파일> [출력이름] [--top 0.0]

세로가 길면 잘라야 한다 — 늘리면 화면이 찌그러진다.
--top 은 어디서부터 자를지의 비율이다 (0 = 맨 위, 1 = 맨 아래).
좌우 빈 여백은 자동으로 잘라낸다 (--no-trim 으로 끌 수 있다).
"""
import sys

from PIL import Image

W, H = 636, 1048


def trim_sides(im, tol=6):
    """좌우 여백을 잘라낸다.

    맥 창 캡처는 콘텐츠 양옆에 빈 공간이 넓게 남아서, 그대로 줄이면
    가로가 먼저 맞고 세로가 모자라 흰 띠가 생긴다.
    """
    bg = im.getpixel((2, im.height // 2))
    px = im.load()
    step = max(1, im.height // 160)      # 세로는 샘플링만 해도 충분하다

    def has_content(x):
        for y in range(0, im.height, step):
            p = px[x, y]
            if sum(abs(a - b) for a, b in zip(p, bg)) > tol:
                return True
        return False

    left = 0
    while left < im.width - 1 and not has_content(left):
        left += 1
    right = im.width - 1
    while right > left and not has_content(right):
        right -= 1
    if right - left < im.width * 0.3:    # 너무 많이 잘리면 원본을 둔다
        return im
    return im.crop((left, 0, right + 1, im.height))


def fit(src, dst, top=0.0, trim=True):
    im = Image.open(src).convert("RGB")
    if trim:
        before = im.width
        im = trim_sides(im)
        if im.width != before:
            print(f"    좌우 여백 {before - im.width}px 제거")
    # 너비를 636에 맞춰 축소한 뒤, 높이 1048만 잘라낸다
    scale = W / im.width
    im = im.resize((W, round(im.height * scale)), Image.LANCZOS)
    if im.height < H:
        # 짧으면 흰 여백을 위아래로 채운다 (늘리지 않는다)
        pad = Image.new("RGB", (W, H), "white")
        pad.paste(im, (0, (H - im.height) // 2))
        im = pad
    else:
        y = round((im.height - H) * max(0.0, min(1.0, top)))
        im = im.crop((0, y, W, y + H))
    im.save(dst, "PNG", optimize=True)
    print(f"  {dst}  {im.size[0]}×{im.size[1]}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    top = 0.0
    for a in sys.argv[1:]:
        if a.startswith("--top"):
            top = float(a.split("=", 1)[1]) if "=" in a else 0.0
    if not args:
        sys.exit(__doc__)
    fit(args[0], args[1] if len(args) > 1 else "shot.png", top,
        trim="--no-trim" not in sys.argv)
