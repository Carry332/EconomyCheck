# -*- coding: utf-8 -*-
"""用 Pillow 绘制首位数字分布对比图（不依赖 matplotlib）。

输出：results/benford_first_digit.png
"""
import csv
import math
import pathlib
import sys
from collections import Counter

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck.config import FONT_BOLD, FONT_REG  # noqa: E402  运行时探测中文字体

RAW = ROOT / "raw" / "amounts_raw.csv"
OUT = ROOT / "results" / "benford_first_digit.png"

EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

W, H = 1560, 820
MARGIN = 34
BG = (255, 255, 255)
INK = (33, 37, 41)
GREY = (120, 128, 136)
GRID = (226, 230, 234)
BLUE = (43, 108, 176)
AMBER = (246, 173, 85)
AMBER_EDGE = (192, 86, 33)
RED = (197, 48, 48)


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    except OSError:
        return ImageFont.truetype(FONT_REG, size)


def first_digit(x):
    x = abs(x)
    while x < 1:
        x *= 10
    while x >= 10:
        x /= 10
    return int(x)


def load():
    rows = list(csv.DictReader(RAW.open(encoding="utf-8-sig")))
    cur = []
    for r in rows:
        for i in range(1, 5):
            v = r[f"v{i}"]
            if v and "." in v and float(v) != 0:
                cur.append(float(v))
                break
    return rows, cur


def main():
    rows, values = load()
    counts = Counter(first_digit(v) for v in values)
    n = sum(counts.values())
    obs = [counts[d] / n for d in range(1, 10)]
    exp = [EXPECTED[d] for d in range(1, 10)]
    diffs = [o - e for o, e in zip(obs, exp)]
    mad = sum(abs(d) for d in diffs) / 9
    chi2 = sum((obs[i] - exp[i]) ** 2 / exp[i] for i in range(9)) * n

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 标题
    d.text((MARGIN + 6, 26), "星宇股份（601799）财报金额首位数字分布 vs Benford 定律",
           font=font(30, True), fill=INK)
    periods = len({r["report"] for r in rows})
    d.text((MARGIN + 6, 70),
           f"数据来源：巨潮资讯网(cninfo)官方定期报告 {periods} 期 · 合并资产负债表/利润表/现金流量表 · "
           f"本期金额样本 n={n} · MAD={mad:.4f} · χ²={chi2:.2f}(df=8, p>0.05)",
           font=font(16), fill=GREY)

    # ---- 左图：分组柱状 ----
    L, T, LW, LH = 96, 132, 840, 520
    top = 0.55
    maxv = max(max(obs), max(exp)) * 1.08

    # 坐标轴与网格
    for k in range(6):
        v = top * k / 5
        y = T + LH - (v / top) * LH
        d.line((L, y, L + LW, y), fill=GRID, width=1)
        d.text((L - 52, y - 9), f"{v*100:.0f}%", font=font(14), fill=GREY)
    d.line((L, T, L, T + LH), fill=GREY, width=2)
    d.line((L, T + LH, L + LW, T + LH), fill=GREY, width=2)

    slot = LW / 9
    bw = slot * 0.34
    for i, dig in enumerate(range(1, 10)):
        cx = L + slot * i + slot / 2
        for off, val, color in ((-bw / 2, obs[i], BLUE), (bw / 2, exp[i], AMBER)):
            x0 = cx + off - bw / 2
            y1 = T + LH - (val / top) * LH
            d.rectangle((x0, y1, x0 + bw, T + LH), fill=color,
                        outline=AMBER_EDGE if color is AMBER else None,
                        width=1 if color is AMBER else 0)
            d.text((x0 + bw / 2, y1 - 20), f"{val*100:.1f}%", font=font(13),
                   fill=INK if color is BLUE else AMBER_EDGE, anchor="ma")
        d.text((cx, T + LH + 12), str(dig), font=font(19, True), fill=INK, anchor="ma")
    d.text((L + LW / 2, T + LH + 48), "首位数字", font=font(16), fill=INK, anchor="ma")
    # 图例
    lx, ly = L + 10, T - 34
    d.rectangle((lx, ly + 3, lx + 18, ly + 17), fill=BLUE)
    d.text((lx + 26, ly), "实际占比", font=font(15), fill=INK)
    d.rectangle((lx + 118, ly + 3, lx + 136, ly + 17), fill=AMBER, outline=AMBER_EDGE)
    d.text((lx + 144, ly), "Benford 期望", font=font(15), fill=INK)

    # ---- 右图：偏差 ----
    RL, RT, RW, RH = L + LW + 110, T, 450, LH
    d.text((RL, RT - 34), "实际 − 期望 的偏离", font=font(17, True), fill=INK)
    lim = max(0.02, max(abs(x) for x in diffs) * 1.35)

    def ydev(v):
        return RT + RH / 2 - v / lim * (RH / 2)

    for k in (-1, -0.5, 0, 0.5, 1):
        y = ydev(lim * k)
        d.line((RL, y, RL + RW, y), fill=GRID if k else (150, 155, 160), width=1 if k else 2)
        d.text((RL + RW + 8, y - 9), f"{lim*k*100:+.1f}%", font=font(13), fill=GREY)
    slot2 = RW / 9
    bw2 = slot2 * 0.5
    for i, dig in enumerate(range(1, 10)):
        cx = RL + slot2 * i + slot2 / 2
        val = diffs[i]
        y1, y0 = ydev(val), ydev(0)
        color = RED if abs(val) / math.sqrt(exp[i] * (1 - exp[i]) / n) > 1.96 else BLUE
        d.rectangle((cx - bw2 / 2, min(y0, y1), cx + bw2 / 2, max(y0, y1)), fill=color)
        z = val / math.sqrt(exp[i] * (1 - exp[i]) / n)
        ty = y1 - 20 if val >= 0 else y1 + 4
        d.text((cx, ty), f"z={z:+.1f}", font=font(12), fill=color, anchor="ma")
        d.text((cx, RT + RH + 12), str(dig), font=font(19, True), fill=INK, anchor="ma")
    d.text((RL + RW / 2, RT + RH + 48), "首位数字", font=font(16), fill=INK, anchor="ma")
    d.text((RL, RT + RH + 78), "红色表示 |z|>1.96（5% 水平显著偏离）；本图中无显著项",
           font=font(13), fill=GREY)

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT)
    print(f"chart -> {OUT}  n={n} mad={mad:.4f} chi2={chi2:.2f}")


if __name__ == "__main__":
    main()
