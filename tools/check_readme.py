# -*- coding: utf-8 -*-
"""README 体检：代码围栏/标签配对、图片与链接可达、目录锚点是否有效。"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FENCE = chr(96) * 3


def anchor_of(heading: str) -> str:
    s = heading.strip().lower()
    for ch in "：:（）()、，,。.！!？?\"'`*":
        s = s.replace(ch, "")
    return s.replace(" ", "-")


def main():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    ok = True
    print(f"行数 {len(text.splitlines())}  字符数 {len(text)}")

    n_fence = text.count(FENCE)
    print(f"代码围栏 {FENCE} 数量：{n_fence}（应为偶数）")
    ok &= n_fence % 2 == 0

    for tag in ("details", "summary", "table"):
        a, b = text.count(f"<{tag}"), text.count(f"</{tag}>")
        if a or b:
            print(f"<{tag}> {a} / </{tag}> {b}")
            ok &= a == b

    assets = set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text))
    links = set(re.findall(r"(?<!!)\[[^\]]+\]\(([^)#][^)]*)\)", text))
    for label, items in (("图片", assets), ("链接", links)):
        for p in sorted(items):
            if p.startswith("http"):
                continue
            exist = (ROOT / p).exists()
            print(("  OK   " if exist else "  MISS ") + f"{label} {p}")
            ok &= exist

    heads = re.findall(r"^##\s+(.+)$", text, re.M)
    anchors = {anchor_of(h) for h in heads}
    toc = re.findall(r"\]\(#([^)]+)\)", text)
    missing = [a for a in toc if a not in anchors]
    print("目录锚点缺失：", missing or "无")
    ok &= not missing
    print("章节：" + " / ".join(heads))

    print("\nREADME 体检：" + ("通过 ✓" if ok else "有问题 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
