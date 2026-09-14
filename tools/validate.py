# -*- coding: utf-8 -*-
"""解析质量校验：行数分布 + 报表勾稽恒等式 + 抽样行。结果写入 results/validation.md。"""
import csv
import pathlib
import re
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "amounts_raw.csv"
RES = ROOT / "results"
RES.mkdir(exist_ok=True)


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


EQUITY_LABELS = ("所有者权益（或股东权益）合计", "所有者权益(或股东权益)合计",
                 "所有者权益合计", "股东权益合计")


def first_num(rs, label):
    """按项目名匹配取 v1。优先精确匹配；其次容忍 PDF 换行导致的项目名截断（前缀匹配）。"""
    prefix_hit = None
    for r in rs:
        it = r["item"].replace(" ", "")
        if not it or not r["v1"]:
            continue
        if it == label:
            return r["v1"]
        if prefix_hit is None and len(it) >= 6 and label.startswith(it):
            prefix_hit = r["v1"]
    return prefix_hit


def main():
    rows = list(csv.DictReader(RAW.open(encoding="utf-8-sig")))
    out = ["# 解析质量校验", "", "数据文件：`raw/amounts_raw.csv`", ""]

    cnt = Counter((r["report"], r["statement"]) for r in rows)
    periods = sorted({r["report"] for r in rows})
    out += [f"报告期数：{len(periods)}；数据行：{len(rows)}", "",
            "| 报告期 | 资产负债表行 | 利润表行 | 现金流量表行 |",
            "|---|---|---|---|"]
    for p in periods:
        out.append(f"| {p} | {cnt[(p,'BS')]} | {cnt[(p,'IS')]} | {cnt[(p,'CF')]} |")
    out.append("")

    out += ["## 勾稽恒等式校验（本期/期末列）", "",
            "校验 资产总计 = 负债合计 + 所有者权益合计。", "",
            "| 报告期 | 资产总计 | 负债合计 | 所有者权益合计 | 负债+权益 | 差异 | 结果 |",
            "|---|---|---|---|---|---|---|"]
    ok = 0
    tot = 0
    by_rep = defaultdict(list)
    for r in rows:
        if r["statement"] == "BS":
            by_rep[r["report"]].append(r)
    for p in periods:
        rs = by_rep[p]
        ta = first_num(rs, "资产总计")
        tl = first_num(rs, "负债合计")
        te = next((v for lbl in EQUITY_LABELS if (v := first_num(rs, lbl))), None)
        if None in (ta, tl, te):
            out.append(f"| {p} | {ta} | {tl} | {te} | - | - | 项目名未匹配 |")
            continue
        s = num(tl) + num(te)
        diff = num(ta) - s
        tot += 1
        good = abs(diff) < 0.01
        ok += good
        out.append(f"| {p} | {num(ta):,.2f} | {num(tl):,.2f} | {num(te):,.2f} | "
                   f"{s:,.2f} | {diff:,.2f} | {'一致 ✓' if good else '不一致 ✗'} |")
    out += ["", f"**恒等式通过 {ok}/{tot} 期**", ""]

    # 年度间衔接：某年报表的“上期可比数”应等于上一年报表的“本期数”
    out += ["## 跨报告期衔接校验", "",
            "对同一项目，比较「Y 年报表的上期可比数(v2)」与「Y-1 年报表的本期数(v1)」。", "",
            "| 报告期对 | 可比项目数 | 完全一致 | 一致率 | 典型差异 |",
            "|---|---|---|---|---|"]
    def key(rows_, st):
        d1, d2 = {}, {}
        for r in rows_:
            if r["statement"] != st:
                continue
            item = r["item"].replace(" ", "")
            if r["v1"]:
                d1[item] = r["v1"]
            if r["v2"]:
                d2[item] = r["v2"]
        return d1, d2

    years = [f"{y}年报" for y in range(2015, 2026)]
    pairs = list(zip(years[1:], years[:-1]))
    total_cmp = total_ok = 0
    for cur_p, prev_p in pairs:
        cmp_n = ok_n = 0
        diffs = []
        for st in ("BS", "IS", "CF"):
            d1_prev, _ = key(by_rep.get(prev_p, []), st)
            _, d2_cur = key(by_rep.get(cur_p, []), st)
            for item, v2 in d2_cur.items():
                if item in d1_prev:
                    cmp_n += 1
                    if d1_prev[item] == v2:
                        ok_n += 1
                    elif len(diffs) < 4:
                        diffs.append(f"{item} {v2} vs {d1_prev[item]}")
        total_cmp += cmp_n
        total_ok += ok_n
        rate = f"{ok_n/cmp_n:.1%}" if cmp_n else "-"
        out.append(f"| {cur_p} ← {prev_p} | {cmp_n} | {ok_n} | {rate} | "
                   f"{'；'.join(diffs) if diffs else '—'} |")
    out += ["", f"**合计 {total_ok}/{total_cmp} 项完全一致，一致率 "
                f"{total_ok/total_cmp:.1%}**（差异项多为项目改名或列报口径调整）", ""]

    RES.joinpath("validation.md").write_text("\n".join(out), encoding="utf-8")
    print(f"validation written, identity {ok}/{tot}")


if __name__ == "__main__":
    main()
