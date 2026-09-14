# -*- coding: utf-8 -*-
"""首位数字分布对比图（Pillow 绘制，不依赖 matplotlib）。"""
import math

from .config import FONT_REG, FONT_BOLD
from .stats import EXPECTED

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


def _font(size, bold=False):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    except OSError:
        return ImageFont.load_default()


def render_figure(main, company, periods=None, datasets=None):
    """main: analyze() 的结果；返回 PIL.Image。"""
    from PIL import Image, ImageDraw

    obs = [r["p_observed"] for r in main["rows"]]
    exp = [r["p_benford"] for r in main["rows"]]
    diffs = [r["diff"] for r in main["rows"]]
    zs = [r["z"] for r in main["rows"]]
    n = main["n"]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    name = f"{company['name']}（{company['code']}）" if company else ""
    d.text((MARGIN + 6, 26), f"{name} 财报金额首位数字分布 vs Benford 定律",
           font=_font(30, True), fill=INK)
    sub = (f"数据来源：巨潮资讯网(cninfo)官方定期报告 · 三大合并报表 · 本期金额样本 n={n} · "
           f"MAD={main['mad']:.4f} · χ²={main['chi2']:.2f}（df=8, p={main['p_value']:.3f}）")
    if periods:
        sub = f"覆盖 {periods} 期 · " + sub
    d.text((MARGIN + 6, 70), sub, font=_font(16), fill=GREY)

    # ---- 左：分组柱状 ----
    L, T, LW, LH = 96, 132, 840, 520
    top = 0.55
    for k in range(6):
        v = top * k / 5
        y = T + LH - (v / top) * LH
        d.line((L, y, L + LW, y), fill=GRID, width=1)
        d.text((L - 52, y - 9), f"{v*100:.0f}%", font=_font(14), fill=GREY)
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
            d.text((x0 + bw / 2, y1 - 20), f"{val*100:.1f}%", font=_font(13),
                   fill=INK if color is BLUE else AMBER_EDGE, anchor="ma")
        d.text((cx, T + LH + 12), str(dig), font=_font(19, True), fill=INK, anchor="ma")
    d.text((L + LW / 2, T + LH + 48), "首位数字", font=_font(16), fill=INK, anchor="ma")
    lx, ly = L + 10, T - 34
    d.rectangle((lx, ly + 3, lx + 18, ly + 17), fill=BLUE)
    d.text((lx + 26, ly), "实际占比", font=_font(15), fill=INK)
    d.rectangle((lx + 118, ly + 3, lx + 136, ly + 17), fill=AMBER, outline=AMBER_EDGE)
    d.text((lx + 144, ly), "Benford 期望", font=_font(15), fill=INK)

    # ---- 右：偏离 ----
    RL, RT, RW, RH = L + LW + 110, T, 450, LH
    d.text((RL, RT - 34), "实际 − 期望 的偏离", font=_font(17, True), fill=INK)
    lim = max(0.02, max(abs(x) for x in diffs) * 1.35)

    for k in (-1, -0.5, 0, 0.5, 1):
        y = RT + RH / 2 - (lim * k) / lim * (RH / 2)
        d.line((RL, y, RL + RW, y), fill=GRID if k else (150, 155, 160),
               width=1 if k else 2)
        d.text((RL + RW + 8, y - 9), f"{lim*k*100:+.1f}%", font=_font(13), fill=GREY)
    slot2 = RW / 9
    bw2 = slot2 * 0.5
    for i, dig in enumerate(range(1, 10)):
        cx = RL + slot2 * i + slot2 / 2
        val = diffs[i]
        y1 = RT + RH / 2 - val / lim * (RH / 2)
        y0 = RT + RH / 2
        color = RED if abs(zs[i]) > 1.96 else BLUE
        d.rectangle((cx - bw2 / 2, min(y0, y1), cx + bw2 / 2, max(y0, y1)), fill=color)
        d.text((cx, y1 - 20 if val >= 0 else y1 + 4), f"z={zs[i]:+.1f}",
               font=_font(12), fill=color, anchor="ma")
        d.text((cx, RT + RH + 12), str(dig), font=_font(19, True), fill=INK, anchor="ma")
    d.text((RL + RW / 2, RT + RH + 48), "首位数字", font=_font(16), fill=INK, anchor="ma")
    d.text((RL, RT + RH + 78),
           "红色表示 |z|>1.96（5% 水平显著偏离）", font=_font(13), fill=GREY)

    # ---- 底部：数据集结论 ----
    if datasets:
        y = 748
        cols = []
        for r in datasets[:5]:
            mc = f"{r['mc_p']:.3f}" if r["mc_p"] is not None else "-"
            cols.append(f"{r['name'].split(' ')[0]} n={r['n']} p={r['p_value']:.3f} "
                        f"MC={mc} {r['verdict']}")
        d.text((MARGIN + 6, y), "  |  ".join(cols), font=_font(14), fill=GREY)
    return img


def save_figure(path, main, company, periods=None, datasets=None):
    img = render_figure(main, company, periods, datasets)
    img.save(path)
    return path


def mad_p_curve(n, sims=20000):
    """（保留接口）模拟 MAD 的 95% 分位，供解读参考。"""
    try:
        import numpy as np
    except ImportError:
        return None
    p = np.array([EXPECTED[d] for d in range(1, 10)])
    rng = np.random.default_rng(1)
    counts = rng.multinomial(n, p, size=sims)
    return float(np.quantile(np.abs(counts / n - p).mean(axis=1), 0.95))


def _unused(x):
    return math.log10(x)
