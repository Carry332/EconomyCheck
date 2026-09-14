# -*- coding: utf-8 -*-
"""验证 pypdfium2 与 pdfplumber 两条抽取路径对最终统计结果是否等价。

用 raw/pdf 下已下载的 PDF，分别用两种后端抽取并解析，比较：
  每期数据行数、合并后的样本量、主口径卡方/MAD。
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from echeck import config  # noqa: F401,E402
from echeck import parse, pdftext, stats  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDFS = sorted((ROOT / "raw" / "pdf").glob("*.PDF"))


def collect(backend):
    rows = []
    t0 = time.time()
    for pdf in PDFS:
        px = pdf.name.replace(".PDF", "")
        # 期间标签从 raw/txt 里的标题推断过于麻烦，这里用文件名当键
        text = pdftext.extract_text(pdf, backend=backend)
        r, _ = parse.rows_from_text(text, px, pdf.name)
        rows.extend(r)
    return rows, time.time() - t0


def summarize(tag, rows, secs):
    res = stats.analyze_all(rows)
    main = res[0]
    print(f"{tag:<12} 用时 {secs:6.1f}s  行数 {len(rows):>5}  n={main['n']:>5}  "
          f"χ²={main['chi2']:6.2f}  p={main['p_value']:.4f}  MAD={main['mad']:.4f}  "
          f"子样本 {len(res)}")
    return main


r1, t1 = collect("pypdfium2")
m1 = summarize("pypdfium2", r1, t1)
r2, t2 = collect("pdfplumber")
m2 = summarize("pdfplumber", r2, t2)

print("\n逐行数对比（按文件）：")
from collections import Counter  # noqa: E402
c1 = Counter(r["title"] for r in r1)
c2 = Counter(r["title"] for r in r2)
bad = 0
for k in sorted(set(c1) | set(c2)):
    same = c1[k] == c2[k]
    bad += (not same)
    if not same:
        print(f"  差异 {k}: pypdfium={c1[k]} plumber={c2[k]}")
print(f"  行数完全一致的文件：{len(set(c1)|set(c2)) - bad}/{len(set(c1)|set(c2))}")

print("\n首位数字分布对比：")
print("  位   pypdfium    plumber")
for a, b in zip(m1["rows"], m2["rows"]):
    print(f"  {a['digit']}   {a['p_observed']:>8.2%}   {b['p_observed']:>8.2%}")
