# -*- coding: utf-8 -*-
"""生成程序图标（Benford 风格：递减柱状图），输出 assets/icon.ico 与 icon.png。

用法：python tools/make_icon.py
"""
import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
SIZES = [16, 24, 32, 48, 64, 128, 256]
BLUE = (43, 108, 176, 255)
WHITE = (255, 255, 255, 255)


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1],
                        radius=max(2, int(size * 0.2)), fill=BLUE)
    # Benford 首位数字分布：1 最多、逐位递减
    heights = [0.64, 0.47, 0.34, 0.28, 0.23, 0.19, 0.16, 0.13, 0.11]
    n = len(heights)
    pad = size * 0.15
    gap = max(1, int(size * 0.035))
    bw = (size - 2 * pad - (n - 1) * gap) / n
    base = size - pad
    for i, h in enumerate(heights):
        x0 = pad + i * (bw + gap)
        y0 = base - h * (size - 2 * pad)
        d.rounded_rectangle([x0, y0, x0 + bw, base],
                            radius=max(1, int(bw * 0.3)), fill=WHITE)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = render(256)
    ico = OUT / "icon.ico"
    base.save(ico, format="ICO", sizes=[(s, s) for s in SIZES])
    png = OUT / "icon.png"
    base.save(png, format="PNG")
    print(f"图标已生成：{ico} ({ico.stat().st_size/1024:.1f} KB)")
    print(f"           {png} ({png.stat().st_size/1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
