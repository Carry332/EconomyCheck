# -*- coding: utf-8 -*-
"""逐页抽取 cninfo 下载的年报 PDF 文本，输出到 raw/txt/<name>.txt（含页码分隔）。"""
import os
import sys
import json
import pathlib

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdf"
TXT_DIR = ROOT / "raw" / "txt"
TXT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    manifest = json.loads((ROOT / "raw" / "manifest.json").read_text(encoding="utf-8-sig"))
    for item in manifest:
        name = item["file"]
        src = PDF_DIR / name
        dst = TXT_DIR / (name + ".txt")
        if dst.exists() and dst.stat().st_size > 0:
            print(f"skip {name}")
            continue
        pages = []
        with pdfplumber.open(str(src)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                try:
                    t = page.extract_text() or ""
                except Exception as e:  # noqa: BLE001
                    t = f"<<extract error: {e}>>"
                pages.append(f"\n===== PAGE {i} =====\n{t}")
        dst.write_text("".join(pages), encoding="utf-8")
        print(f"ok   {name} pages={len(pages)} chars={dst.stat().st_size}")


if __name__ == "__main__":
    main()
