# -*- coding: utf-8 -*-
"""按白名单生成干净的发布包（避免把本地数据、依赖、工具痕迹打进去）。

用法：
    python tools/make_release.py [--out dist] [--zip]

输出：dist/echeck-<version>/ ，并可打包为同名 zip。
所有被排除的内容都会列出来，便于人工复核。
"""
import argparse
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import __version__  # noqa: E402

# 只打包这些（相对 ROOT 的 glob）；其余一律不进发布包
ALLOW = [
    "LICENSE",
    "README.md",
    "requirements.txt",
    ".gitignore",
    "run_gui.py",
    "run_cli.py",
    "启动GUI.bat",
    "启动GUI-带日志.bat",
    "echeck/*.py",
    "tools/*.py",
    "results/*.md",
    "results/*.csv",
    "results/*.png",
    "results/*.json",
    "results/gui/*.png",
]

# 明确排除的高危项（即使误放进白名单也会被剔除）
DENY_DIRS = {".pylibs", "data", "logs", "__pycache__", "dist", "build", ".venv", "out"}
DENY_PREFIX = (".dsh-", "~$")
DENY_SUFFIX = (".pyc", ".pyo", ".part", ".tmp", ".bak", ".orig", ".pdf", ".log")


def collect():
    files, skipped = [], []
    for pattern in ALLOW:
        for p in sorted(ROOT.glob(pattern)):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            bad = (rel.parts[0] in DENY_DIRS
                   or any(seg in DENY_DIRS for seg in rel.parts)
                   or rel.name.startswith(DENY_PREFIX)
                   or rel.suffix.lower() in DENY_SUFFIX)
            (skipped if bad else files).append(rel)
    return files, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--zip", action="store_true", help="同时打包 zip")
    args = ap.parse_args()

    files, skipped = collect()
    stage = ROOT / args.out / f"echeck-{__version__}"
    if stage.parent.exists():
        shutil.rmtree(stage.parent)
    total = 0
    for rel in files:
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
        total += (ROOT / rel).stat().st_size

    print(f"发布包：{stage}")
    print(f"  文件 {len(files)} 个，{total/1024:.1f} KB")
    for rel in files:
        print(f"    + {rel}")
    if skipped:
        print("  被排除（白名单内但命中排除规则）：")
        for rel in skipped:
            print(f"    - {rel}")
    print("  未纳入发布包（本地数据/依赖/痕迹）："
          f" .pylibs/, data/, raw/pdf/, raw/txt/, logs/, __pycache__/, .dsh-*")

    if args.zip:
        zpath = stage.with_suffix(".zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in files:
                z.write(ROOT / rel, arcname=str(pathlib.Path(f"echeck-{__version__}") / rel))
        print(f"  已打包：{zpath}（{zpath.stat().st_size/1024:.1f} KB，{len(files)} 个条目）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
