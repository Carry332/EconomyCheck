# -*- coding: utf-8 -*-
"""按交付口径（星宇股份 2015-2025 年报 + 2026H1 + 2026Q1）用新工具链复算，与交付结果对账。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import config  # noqa: F401,E402
from echeck import cninfo, pipeline  # noqa: E402

EXPECT = {"n": 1400, "chi2": 7.33, "mad": 0.0069}


def main():
    comps = cninfo.search_companies("601799", 5)
    comp = next(c for c in comps if c["code"] == "601799")
    reps = [r for r in cninfo.list_reports(comp["code"], comp["org_id"],
                                           ["annual", "semi", "q1"])
            if not r["is_hk"] and not r["is_summary"]]
    sel = [r for r in reps
           if (r["kind"] == "annual" and 2015 <= int(r["period"][:4]) <= 2025)
           or r["period"] in ("2026H1", "2026Q1")]
    sel.sort(key=lambda r: r["period"])
    print("报告期：", ", ".join(r["period"] for r in sel), f"（{len(sel)} 期）")

    res = pipeline.run_analysis(comp, sel,
                                progress=lambda s, d, t, m: None)
    m = res.main
    print(f"数据行 {len(res.rows)}  主口径 n={m['n']}  χ²={m['chi2']:.2f}  "
          f"p={m['p_value']:.4f}  MAD={m['mad']:.4f}  MCp={m['mc_p']:.4f}  D={m['ks_d']:.4f}")
    v = res.validation
    print(f"恒等式 {v['identity_ok']}/{v['identity_total']}；"
          f"跨期衔接 {v['chain_matched']}/{v['chain_total']}")
    print(f"子样本 {[ (r['name'][:12], r['n']) for r in res.results ]}")
    ok = (m["n"] == EXPECT["n"] and abs(m["chi2"] - EXPECT["chi2"]) < 0.01
          and abs(m["mad"] - EXPECT["mad"]) < 0.0001)
    print(("与交付结果一致 ✓" if ok else f"与交付结果不同 ✗（交付 n={EXPECT['n']} "
          f"χ²={EXPECT['chi2']} MAD={EXPECT['mad']}）"))
    for w in res.warnings:
        print("[警告]", w)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
