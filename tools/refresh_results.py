# -*- coding: utf-8 -*-
"""用 echeck 工具包重算已解析数据（raw/amounts_raw.csv）的结果，刷新 results/。

这样交付的 results/* 与 GUI/CLI 运行结果完全一致。
"""
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from echeck import config  # noqa: F401,E402
from echeck import stats, viz  # noqa: E402
from echeck.pipeline import Result  # noqa: E402

RES = ROOT / "results"


def main():
    rows = list(csv.DictReader((ROOT / "raw" / "amounts_raw.csv").open(encoding="utf-8-sig")))
    company = {"code": "601799", "name": "星宇股份", "org_id": "9900017668"}
    periods = sorted({r["report"] for r in rows})
    reports = [{"period": p, "title": f"星宇股份{p}", "kind": "annual",
                "date": "", "file": f"{p}.PDF", "url": ""} for p in periods]

    res = Result()
    res.company = company
    res.reports = reports
    res.rows = rows
    res.results = stats.analyze_all(rows)
    res.validation = stats.validate(rows)

    stats.write_csv(RES / "benford_first_digit.csv", res.results)
    stats.write_report(RES / "benford_report.md", company, reports, rows,
                       res.results, res.validation)
    stats.write_validation(RES / "validation.md", rows, res.validation)
    viz.save_figure(RES / "benford_first_digit.png", res.main, company,
                    periods=len(reports), datasets=res.results)

    v = res.validation
    print(f"主口径 n={res.main['n']}  χ²={res.main['chi2']:.2f}  p={res.main['p_value']:.4f}  "
          f"MAD={res.main['mad']:.4f}  MC p={res.main['mc_p']:.4f}  D={res.main['ks_d']:.4f}")
    print(f"会计恒等式 {v['identity_ok']}/{v['identity_total']}；"
          f"跨期衔接 {v['chain_matched']}/{v['chain_total']} "
          f"({v['chain_matched']/max(1,v['chain_total']):.1%})")
    for c in v["chain"]:
        print(f"  {c['pair']:<24} {c['matched']}/{c['compared']}"
              + (("   " + "；".join(c["diffs"][:2])) if c["diffs"] else ""))


if __name__ == "__main__":
    main()
