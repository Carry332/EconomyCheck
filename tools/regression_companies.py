# -*- coding: utf-8 -*-
"""跨公司回归：不同交易所/不同年报版式下，三大报表都能解析出来。

用法：python tools/regression_companies.py [公司代码 ...]
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import config  # noqa: F401,E402
from echeck import cninfo, parse, pdftext, stats  # noqa: E402

DEFAULT = ["601799", "001219", "000100", "300750", "600519", "000625",
           "833171", "688981"]


def check(code):
    comps = cninfo.search_companies(code, 5)
    if not comps:
        return f"{code}: 搜索无结果", False
    comp = comps[0]
    if not cninfo.is_supported(comp):
        return f"{code} {comp['name']}: 非 A 股，跳过", True
    reps = [r for r in cninfo.list_reports(comp["code"], comp["org_id"], ["annual"])
            if not r["is_hk"] and not r["is_summary"]]
    reps.sort(key=lambda r: r["period"])
    rep = reps[-1]
    base = config.company_dir(comp["code"], comp["name"])
    dirs = config.ensure_dirs(base)
    dest = dirs["pdf"] / rep["file"]
    if not (dest.exists() and dest.stat().st_size > 0):
        cninfo.download(rep["url"], dest)
    text = pdftext.extract_text(dest)
    rows, infos = parse.rows_from_text(text, rep["period"], rep["title"])
    cnt = {}
    for r in rows:
        cnt[r["statement"]] = cnt.get(r["statement"], 0) + 1
    val = stats.validate(rows)
    ok_ident = (val["identity_total"] > 0 and val["identity_ok"] == val["identity_total"])
    ok = (len(rows) > 30 and all(cnt.get(k, 0) >= 10 for k in ("BS", "IS", "CF"))
          and ok_ident)
    detail = (f"{code} {comp['name']:<6} {rep['period']:<8} "
              f"行数 {len(rows):>4} (BS {cnt.get('BS',0):>3}/IS {cnt.get('IS',0):>3}"
              f"/CF {cnt.get('CF',0):>3})  恒等式 "
              f"{val['identity_ok']}/{val['identity_total']}")
    if not ok:
        detail += "  缺: " + ",".join(k for k in ("BS", "IS", "CF") if cnt.get(k, 0) < 10)
    return detail, ok


def main():
    codes = sys.argv[1:] or DEFAULT
    bad = 0
    for c in codes:
        try:
            line, ok = check(c)
        except Exception as e:  # noqa: BLE001
            line, ok = f"{c}: 异常 {type(e).__name__}: {e}", False
        print(("  OK  " if ok else "  FAIL") + " " + line, flush=True)
        bad += (not ok)
    print(f"\n回归结果：{len(codes) - bad}/{len(codes)} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
