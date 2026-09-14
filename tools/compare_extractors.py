# -*- coding: utf-8 -*-
"""比较 pdfplumber 与 pypdfium2 的抽取速度与文本质量。"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import config  # noqa: F401,E402
from echeck import parse  # noqa: E402

# 不写死绝对路径：默认取 raw/pdf 下第一份 PDF，也可用命令行参数指定
_default = sorted((ROOT / "raw" / "pdf").glob("*.PDF"))
PDF = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
    _default[0] if _default else ROOT / "raw" / "pdf" / "example.PDF")


def run(name, fn):
    t = time.time()
    try:
        text = fn()
    except Exception as e:  # noqa: BLE001
        print(f"{name}: FAILED {type(e).__name__}: {e}")
        return None
    dt = time.time() - t
    lines = text.splitlines()
    nums = len(re.findall(r"-?\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?", text))
    rows, infos = parse.rows_from_text(text, "2025年报", "test")
    found = [i["statement"] for i in infos if i.get("found")]
    print(f"{name}: {dt:6.2f}s  chars={len(text):>8}  lines={len(lines):>6}  "
          f"金额={nums:>6}  报表={found}  解析行={len(rows)}")
    return text


def pl():
    import pdfplumber
    out = []
    with pdfplumber.open(str(PDF)) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            out.append(f"\n===== PAGE {i} =====\n{p.extract_text() or ''}")
    return "".join(out)


def pf():
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(PDF))
    out = []
    for i in range(len(pdf)):
        out.append(f"\n===== PAGE {i+1} =====\n{pdf[i].get_textpage().get_text_range()}")
    return "".join(out)


t1 = run("pdfplumber", pl)
t2 = run("pypdfium2 ", pf)
if t1 and t2:
    a = [l.strip() for l in t1.splitlines() if l.strip()]
    b = [l.strip() for l in t2.splitlines() if l.strip()]
    print(f"\n行数：plumber={len(a)} pypdfium={len(b)}")
    same = sum(1 for x, y in zip(a, b) if x == y)
    print(f"逐行相同：{same}/{min(len(a), len(b))}")
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            print("首个差异行：")
            print("  plumber :", repr(x[:110]))
            print("  pypdfium:", repr(y[:110]))
            break
