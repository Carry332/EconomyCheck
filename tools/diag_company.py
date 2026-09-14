# -*- coding: utf-8 -*-
"""诊断：某公司报告为何解析不出报表。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import config  # noqa: F401,E402
from echeck import cninfo, parse, pdftext  # noqa: E402

code = sys.argv[1] if len(sys.argv) > 1 else "001219"
comps = cninfo.search_companies(code, 5)
comp = comps[0]
print("公司:", comp)
reps = cninfo.list_reports(comp["code"], comp["org_id"], ["annual"])
reps = [r for r in reps if not r["is_hk"] and not r["is_summary"]]
reps.sort(key=lambda r: r["period"])
print("年报:", [(r["period"], r["title"]) for r in reps][-3:])

base = config.company_dir(comp["code"], comp["name"])
dirs = config.ensure_dirs(base)
print("工作目录:", base)

for rep in reps[-2:]:
    dest = dirs["pdf"] / rep["file"]
    if not (dest.exists() and dest.stat().st_size > 0):
        print(f"  下载 {rep['title']} …")
        cninfo.download(rep["url"], dest)
    size = dest.stat().st_size
    head = dest.open("rb").read(8)
    print(f"\n=== {rep['period']} {rep['title']}  {size/1024:.0f} KB  头部={head!r}")
    for backend in ("pypdfium2", "pdfplumber"):
        try:
            text = pdftext.extract_text(dest, backend=backend)
        except Exception as e:  # noqa: BLE001
            print(f"  {backend:<11} 抽取失败: {type(e).__name__}: {e}")
            continue
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        print(f"  {backend:<11} chars={len(text):>7} 汉字={cjk:>6}")
        for marker in ("合并资产负债表", "合并利润表", "合并现金流量表",
                       "资产负债表", "利润表", "现金流量表", "财务报表"):
            print(f"      {marker:<10} 出现 {text.count(marker)} 次")
        rows, infos = parse.rows_from_text(text, rep["period"], rep["title"])
        print(f"      解析行数 = {len(rows)}  sections = {infos}")
        if len(text) > 0:
            print("      文本片段:", repr(text[300:500]))
        break
