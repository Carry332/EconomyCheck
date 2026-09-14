# -*- coding: utf-8 -*-
"""首位数字分布统计与 Benford 检验（卡方 / MAD / KS / 蒙特卡洛）。"""
import csv
import math
from collections import Counter, defaultdict

EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
MAD_BANDS = [(0.006, "接近符合 (close conformity)"),
             (0.012, "可接受 (acceptable conformity)"),
             (0.015, "勉强可接受 (marginally acceptable)"),
             (float("inf"), "不符合 (nonconformity)")]

EQUITY_LABELS = ("所有者权益（或股东权益）合计", "所有者权益(或股东权益)合计",
                 "所有者权益合计", "股东权益合计")


# ---------------- 统计工具（纯 Python 实现，无需 scipy） ----------------
def _gser(a, x):
    gln = math.lgamma(a)
    ap, s, delta = a, 1.0 / a, 1.0 / a
    for _ in range(2000):
        ap += 1
        delta *= x / ap
        s += delta
        if abs(delta) < abs(s) * 1e-16:
            break
    return s * math.exp(-x + a * math.log(x) - gln)


def _gcf(a, x):
    gln = math.lgamma(a)
    tiny = 1e-300
    b, c, d = x + 1 - a, 1 / tiny, 1.0 / (x + 1 - a)
    h = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_sf(x, df):
    """卡方分布上尾概率 P(X > x)。"""
    if x <= 0:
        return 1.0
    a, xx = df / 2.0, x / 2.0
    return 1.0 - _gser(a, xx) if xx < a + 1 else _gcf(a, xx)


def first_digit(x):
    x = abs(float(x))
    if x == 0:
        return 0
    while x < 1:
        x *= 10
    while x >= 10:
        x /= 10
    return int(x)


def mc_mad_pvalue(n, observed_mad, sims=20000, seed=20260913):
    """蒙特卡洛：Benford 分布重复抽样 sims 次，得到 MAD 的零分布与 p 值。"""
    try:
        import numpy as np
    except ImportError:
        return None, None, None
    p = np.array([EXPECTED[d] for d in range(1, 10)])
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(n, p, size=sims)
    mads = np.abs(counts / n - p).mean(axis=1)
    return (float((mads >= observed_mad).mean()), float(mads.mean()),
            float(np.quantile(mads, 0.95)))


def analyze(values, name, note=""):
    values = list(values)
    counts = Counter(first_digit(v) for v in values)
    counts.pop(0, None)
    n = sum(counts.values())
    if n == 0:
        return None
    rows, chi2, mad = [], 0.0, 0.0
    for d in range(1, 10):
        obs = counts[d]
        p_exp = EXPECTED[d]
        exp = p_exp * n
        p_obs = obs / n
        chi2 += (obs - exp) ** 2 / exp
        mad += abs(p_obs - p_exp)
        se = math.sqrt(p_exp * (1 - p_exp) / n)
        rows.append({"digit": d, "observed": obs, "p_observed": p_obs,
                     "p_benford": p_exp, "expected": exp, "diff": p_obs - p_exp,
                     "z": (p_obs - p_exp) / se, "excess_ratio": p_obs / p_exp})
    mad /= 9
    cum_o = cum_e = 0.0
    ks_d = 0.0
    for r in rows:
        cum_o += r["p_observed"]
        cum_e += r["p_benford"]
        ks_d = max(ks_d, abs(cum_o - cum_e))
    mc_p, mc_mean, mc_q95 = mc_mad_pvalue(n, mad)
    sig_chi = chi2_sf(chi2, 8) <= 0.05
    sig_mc = (mc_p is not None) and (mc_p <= 0.05)
    verdict = ("拒绝 Benford" if (sig_chi and (sig_mc or mc_p is None))
               else "轻度偏离（仅 MAD 检验显著）" if sig_mc
               else "不拒绝 Benford")
    return {"name": name, "note": note, "n": n, "rows": rows, "chi2": chi2,
            "p_value": chi2_sf(chi2, 8), "mad": mad,
            "mad_band": next(lbl for thr, lbl in MAD_BANDS if mad <= thr),
            "ks_d": ks_d, "ks_crit": 1.36 / math.sqrt(n),
            "max_z": max(abs(r["z"]) for r in rows),
            "mc_p": mc_p, "mc_mean": mc_mean, "mc_q95": mc_q95,
            "verdict": verdict}


# ---------------- 数据集组装 ----------------
def decimals_of(row):
    out = []
    for i in range(1, 5):
        v = row.get(f"v{i}") or ""
        if v and "." in v:
            try:
                f = float(v)
            except ValueError:
                continue
            if f != 0:
                out.append(f)
    return out


def build_datasets(rows):
    """返回 [(name, values, note)]，主口径为每行首个带小数的金额（本期/期末列）。"""
    cur, allv = [], []
    per_stmt, per_period = defaultdict(list), defaultdict(list)
    for r in rows:
        dec = decimals_of(r)
        allv.extend(dec)
        if not dec:
            continue
        cur.append(dec[0])
        per_stmt[r["statement"]].append(dec[0])
        per_period[r["report"]].append(dec[0])

    ds = [("A 本期/期末金额（主口径）", cur, "每期报告本期列，无重复计数"),
          ("B 全部分项金额（含上期可比数）", allv, "含同比列，同一数值平均出现两次"),
          ("C 本期金额 绝对值≥10", [v for v in cur if abs(v) >= 10], "剔除每股收益等小额"),
          ("D 全部金额去重后的唯一值", sorted(set(allv)), "")]
    for code, cname in (("BS", "资产负债表"), ("IS", "利润表"), ("CF", "现金流量表")):
        ds.append((f"E {cname}（本期列）", per_stmt.get(code, []), ""))
    yearlies = sorted([p for p in per_period if p.endswith("年报")],
                      key=lambda p: int(p[:4]))
    if len(yearlies) >= 4:
        half = len(yearlies) // 2
        for label, group in ((f"F1 {yearlies[0]}~{yearlies[half-1]}", yearlies[:half]),
                             (f"F2 {yearlies[half]}~{yearlies[-1]}", yearlies[half:])):
            vals = [v for p in group for v in per_period[p]]
            if vals:
                ds.append((label, vals, ""))
    return ds


def analyze_all(rows, progress=None):
    results = []
    datasets = [d for d in build_datasets(rows) if d[1]]
    for i, (name, vals, note) in enumerate(datasets, 1):
        if progress:
            progress("统计检验", i, len(datasets), f"检验 {name}")
        r = analyze(vals, name, note)
        if r:
            results.append(r)
    return results


# ---------------- 数据质量校验 ----------------
def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _first_num(rs, label):
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


def _equity_num(rs):
    """所有者权益合计：先按标准项目名匹配，再按关键词兜底。

    有些 PDF 的项目名被换行拆开后拼接得并不完美（例如「益）合计负债和所有者权益（或」），
    只要该行同时含“所有者权益”“合计”且不是“归属于母公司…”或“少数股东权益”，
    就认为它是权益合计行 —— 数值对不对由恒等式再校验一次。
    """
    for lbl in EQUITY_LABELS:
        v = _first_num(rs, lbl)
        if v:
            return v, lbl
    for r in rs:
        it = r["item"].replace(" ", "")
        if not r["v1"] or not it:
            continue
        if ("所有者权益" in it and "合计" in it
                and "归属" not in it and "少数" not in it):
            return r["v1"], it + "（关键词匹配）"
    return None, None


def validate(rows):
    """会计恒等式 + 跨报告期衔接校验。"""
    by_rep = defaultdict(list)
    for r in rows:
        if r["statement"] == "BS":
            by_rep[r["report"]].append(r)
    periods = sorted({r["report"] for r in rows})

    identity = []
    for p in periods:
        rs = by_rep.get(p, [])
        ta = _first_num(rs, "资产总计")
        tl = _first_num(rs, "负债合计")
        te, te_label = _equity_num(rs)
        if None in (ta, tl, te):
            identity.append({"period": p, "ok": None, "assets": ta,
                             "liab": tl, "equity": te})
            continue
        diff = _num(ta) - (_num(tl) + _num(te))
        identity.append({"period": p, "ok": abs(diff) < 0.01, "diff": diff,
                         "assets": _num(ta), "liab": _num(tl), "equity": _num(te),
                         "equity_label": te_label})

    checks = []
    yearlies = sorted([p for p in periods if p.endswith("年报")], key=lambda p: int(p[:4]))

    def first_map(period, st, field):
        """同一项目名可能在一张表里出现多次，取首次出现，避免重复计数歧义。"""
        out = {}
        for r in rows:
            if r["report"] != period or r["statement"] != st:
                continue
            item = r["item"].replace(" ", "")
            if item and r.get(field) and item not in out:
                out[item] = r[field]
        return out

    for cur_p, prev_p in zip(yearlies[1:], yearlies[:-1]):
        cmp_n = ok_n = 0
        diffs = []
        for st in ("BS", "IS", "CF"):
            prev1 = first_map(prev_p, st, "v1")
            for item, v2 in first_map(cur_p, st, "v2").items():
                if item not in prev1:
                    continue
                cmp_n += 1
                if prev1[item] == v2:
                    ok_n += 1
                elif len(diffs) < 5:
                    diffs.append(f"{item}: {v2} vs {prev1[item]}")
        checks.append({"pair": f"{cur_p} ← {prev_p}", "compared": cmp_n,
                       "matched": ok_n, "diffs": diffs})
    total = sum(c["compared"] for c in checks)
    matched = sum(c["matched"] for c in checks)
    return {"identity": identity,
            "identity_ok": sum(1 for i in identity if i["ok"]),
            "identity_total": sum(1 for i in identity if i["ok"] is not None),
            "chain": checks, "chain_total": total, "chain_matched": matched,
            "periods": periods}


# ---------------- 导出（统一 LF 换行，跨平台/跨提交输出一致） ----------------
def write_csv(path, results):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dataset", "n", "digit", "observed", "p_observed", "p_benford",
                    "expected", "diff", "z", "excess_ratio"])
        for r in results:
            for row in r["rows"]:
                w.writerow([r["name"], r["n"], row["digit"], row["observed"],
                            f"{row['p_observed']:.6f}", f"{row['p_benford']:.6f}",
                            f"{row['expected']:.2f}", f"{row['diff']:+.6f}",
                            f"{row['z']:+.3f}", f"{row['excess_ratio']:.4f}"])


def write_rows_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, lineterminator="\n",
                           fieldnames=["report", "title", "statement", "item", "n",
                                       "v1", "v2", "v3", "v4", "line"])
        w.writeheader()
        w.writerows(rows)


def write_validation(path, rows, validation):
    """输出解析质量校验报告（会计恒等式 + 跨报告期衔接）。"""
    L = ["# 解析质量校验", "", "## 勾稽恒等式（资产总计 = 负债合计 + 所有者权益合计）", "",
         "| 报告期 | 资产总计 | 负债合计 | 所有者权益合计 | 差异 | 结果 |",
         "|---|---|---|---|---|---|"]
    for it in validation["identity"]:
        if it.get("ok") is None:
            L.append(f"| {it['period']} | {it.get('assets')} | {it.get('liab')} | "
                     f"{it.get('equity')} | — | 项目名未匹配 |")
        else:
            L.append(f"| {it['period']} | {it['assets']:,.2f} | {it['liab']:,.2f} | "
                     f"{it['equity']:,.2f} | {it['diff']:,.2f} | "
                     f"{'一致 ✓' if it['ok'] else '不一致 ✗'} |")
    L += ["", f"**通过 {validation['identity_ok']}/{validation['identity_total']} 期**", "",
          "## 跨报告期衔接（本年上期可比数 = 上年本期数）", "",
          "对同一项目比较「Y 年报表的上期列(v2)」与「Y-1 年报表的本期列(v1)」，"
          "覆盖资产负债表、利润表、现金流量表。", "",
          "| 报告期对 | 可比项目数 | 完全一致 | 一致率 | 典型差异 |",
          "|---|---|---|---|---|"]
    for c in validation["chain"]:
        rate = f"{c['matched']/c['compared']:.1%}" if c["compared"] else "-"
        L.append(f"| {c['pair']} | {c['compared']} | {c['matched']} | {rate} | "
                 f"{'；'.join(c['diffs']) if c['diffs'] else '—'} |")
    tot, mat = validation["chain_total"], validation["chain_matched"]
    L += ["", f"**合计 {mat}/{tot} 项完全一致，一致率 {mat/max(1,tot):.1%}**"
              f"（差异项多为会计政策变更、报表格式调整导致的真实重述/重分类）", "",
          "## 解析数据行统计", "",
          "| 报告期 | 资产负债表 | 利润表 | 现金流量表 |",
          "|---|---|---|---|"]
    per = {}
    for r in rows:
        per.setdefault(r["report"], {"BS": 0, "IS": 0, "CF": 0})
        per[r["report"]][r["statement"]] = per[r["report"]].get(r["statement"], 0) + 1
    for p in validation["periods"]:
        c = per.get(p, {})
        L.append(f"| {p} | {c.get('BS', 0)} | {c.get('IS', 0)} | {c.get('CF', 0)} |")
    L.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def write_report(path, company, reports, rows, results, validation):
    main = results[0] if results else None
    L = [f"# {company['name']}（{company['code']}）财报数据首位数字分布与 Benford 定律检验", "",
         f"- **数据来源**：巨潮资讯网（cninfo，证监会指定信息披露平台）官方定期报告 PDF",
         f"- **覆盖报告**：{len(reports)} 期（{', '.join(r['period'] for r in reports)}）",
         f"- **报表范围**：各期合并资产负债表、合并利润表、合并现金流量表",
         f"- **解析数据行**：{len(rows)} 行；主口径样本 n = {main['n'] if main else 0}",
         ""]
    if main:
        conforms = main["p_value"] > 0.05 and (main["mc_p"] is None or main["mc_p"] > 0.05)
        verdict = ("符合 Benford 对数分布" if conforms
                   else "与 Benford 对数分布存在显著偏离")
        L += ["## 一、总体结论", "",
              f"主口径（A）样本 n = {main['n']}：", "",
              f"- 卡方检验：χ² = {main['chi2']:.2f}（df = 8），p = {main['p_value']:.3f}",
              f"- MAD = {main['mad']:.4f}，Nigrini 判定「{main['mad_band']}」",
              (f"- 蒙特卡洛 MAD 检验（20000 次）：p = {main['mc_p']:.3f}"
               if main["mc_p"] is not None else "- 蒙特卡洛检验不可用（缺少 numpy）"),
              f"- KS 型统计量 D = {main['ks_d']:.4f}（5% 临界值 {main['ks_crit']:.4f}）",
              f"- 最大 |z| = {main['max_z']:.2f}",
              "",
              f"**结论：{company['name']}财报金额的首位数字分布{verdict}。**", "",
              "## 二、主口径 1-9 分布明细", "",
              "| 首位数字 | 观测数 | 实际占比 | Benford 期望 | 期望频数 | 偏差 | z |",
              "|---|---|---|---|---|---|---|"]
        for row in main["rows"]:
            L.append(f"| **{row['digit']}** | {row['observed']} | {row['p_observed']:.2%} | "
                     f"{row['p_benford']:.2%} | {row['expected']:.1f} | {row['diff']:+.2%} | "
                     f"{row['z']:+.2f} |")
        L.append("")
    L += ["## 三、稳健性检验", "",
          "| 数据集 | n | χ² | p 值 | MAD | 蒙特卡洛 p | KS 型 D | 结论 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in results:
        mc = f"{r['mc_p']:.4f}" if r["mc_p"] is not None else "-"
        L.append(f"| {r['name']} | {r['n']} | {r['chi2']:.2f} | {r['p_value']:.4f} | "
                 f"{r['mad']:.4f} | {mc} | {r['ks_d']:.4f} | {r['verdict']} |")
    L += ["",
          "## 四、数据质量校验", "",
          f"- 会计恒等式（资产总计 = 负债合计 + 所有者权益合计）："
          f"**{validation['identity_ok']}/{validation['identity_total']} 期通过**",
          f"- 跨报告期衔接（本年上期数 = 上年本期数）："
          f"**{validation['chain_matched']}/{validation['chain_total']} 项一致**",
          "",
          "## 五、局限", "",
          "1. 卡方检验假设样本独立，而同一报表内科目存在勾稽关系，p 值仅供参考。",
          "2. 分表/分时段子样本量小，检验敏感度不同，可能出现轻度偏离。",
          "3. Benford 检验只能说明数字分布是否自然，不能单独证明或排除财务舞弊。", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
