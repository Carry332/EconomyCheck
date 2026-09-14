# -*- coding: utf-8 -*-
"""打包成 Windows 可执行文件（PyInstaller）。

用法：
    python tools/build_exe.py                # 同时产出便携包(onedir)与单文件包(onefile)
    python tools/build_exe.py --mode onedir  # 只做便携包（启动快，已验证）
    python tools/build_exe.py --mode onefile # 只做单文件版
    python tools/build_exe.py --no-zip

产物：
    build/exe-onedir/EconomyCheck/EconomyCheck.exe          图形界面（推荐，启动快）
    build/exe-onedir/EconomyCheck-CLI/EconomyCheck-CLI.exe  命令行
    build/exe-onefile/EconomyCheck.exe                      单文件版（解包到临时目录）
    build/release/EconomyCheck-v<版本>-win64-portable.zip   便携包（推荐）
    build/release/EconomyCheck-v<版本>-onefile.zip          单文件包
    build/release/SHA256SUMS.txt
"""
import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echeck import __version__  # noqa: E402

PYLIBS = ROOT / ".pylibs"
BUILD = ROOT / "build"
RELEASE = BUILD / "release"
ICON = ROOT / "assets" / "icon.ico"
DIST = {"onedir": BUILD / "exe-onedir", "onefile": BUILD / "exe-onefile"}

TARGETS = [
    ("EconomyCheck", "run_gui.py", "--windowed"),      # 图形界面，双击即用
    ("EconomyCheck-CLI", "run_cli.py", "--console"),   # 命令行版
]

# 明确排除用不到的大件（避免把全局 site-packages 里的无关库打进来）
EXCLUDES = ["matplotlib", "pandas", "scipy", "pytest", "IPython", "pygame",
            "notebook", "jupyter", "sqlite3", "lib2to3", "pydoc_data"]

README_EXE = """EconomyCheck —— A 股财报 Benford 分析器 v{ver}
====================================================

【推荐】便携包 portable 版
    解压后进入 EconomyCheck 目录，双击 EconomyCheck.exe 即可（无需安装 Python）
    命令行版在 EconomyCheck-CLI 目录
    · 首次运行会在所在目录创建 data/ 与 logs/
    · 分析结果写入 data/<代码>_<简称>/results/
    · 启动失败时查看 logs/gui.log

【可选】单文件版 onefile
    EconomyCheck.exe / EconomyCheck-CLI.exe 双击即用，启动时会先解压到 %TEMP%
    （便于拷贝单个文件，但启动慢几秒；若系统限制临时目录可能无法启动，
      此时请改用便携包版本）

【命令行用法】
    EconomyCheck-CLI.exe 601799 --kinds annual --last 8
    EconomyCheck-CLI.exe 宁德时代 --from-year 2018
    EconomyCheck-CLI.exe --help

【运行要求】
    · Windows 10/11 64 位
    · 需要联网：数据来自巨潮资讯网(cninfo)官方披露，程序会下载报告 PDF

【注意】
    · 未做代码签名，首次运行 Windows SmartScreen 可能提示"未知发布者"，
      选择"更多信息 → 仍要运行"即可
    · 本程序只做数据分析，不构成任何投资建议；数据请以官方披露原文为准

【校验】
    certutil -hashfile <文件> SHA256
    与 SHA256SUMS.txt 中的值比对
"""


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_one(name: str, entry: str, mode: str, kind: str) -> bool:
    cmd = [sys.executable, "-m", "PyInstaller",
           "--name", name, mode,
           "--onedir" if kind == "onedir" else "--onefile",
           "--noconfirm", "--clean", "--noupx",
           "--paths", str(PYLIBS),
           "--distpath", str(DIST[kind]),
           "--workpath", str(BUILD / f"pyi-{kind}" / name),
           "--specpath", str(BUILD / f"spec-{kind}"),
           "--collect-all", "pypdfium2",     # pdfium 原生 DLL
           "--collect-all", "pdfminer",      # CJK 用的 cmap 数据
           "--collect-all", "pdfplumber",
           ]
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]
    if ICON.is_file():
        cmd += ["--icon", str(ICON)]
    cmd.append(str(ROOT / entry))
    print(f"\n=== [{kind}] {name} <- {entry} ===", flush=True)
    env = dict(os.environ, PYTHONPATH=str(PYLIBS), PYTHONUTF8="1")
    return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode == 0


def collect(kind: str):
    if kind == "onedir":
        return [DIST[kind] / n for n, _, _ in TARGETS]
    return [DIST[kind] / f"{n}.exe" for n, _, _ in TARGETS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["both", "onedir", "onefile"], default="both")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()

    if not PYLIBS.is_dir():
        print(f"找不到依赖目录 {PYLIBS}，请先安装 requirements")
        return 2
    if not ICON.is_file():
        print("图标缺失，先运行：python tools/make_icon.py")

    kinds = ["onedir", "onefile"] if args.mode == "both" else [args.mode]
    for d in list(DIST.values()) + [RELEASE]:
        if d.exists():
            shutil.rmtree(d)
    RELEASE.mkdir(parents=True, exist_ok=True)

    for kind in kinds:
        for name, entry, mode in TARGETS:
            if not build_one(name, entry, mode, kind):
                print(f"\n[{kind}] 打包失败：{name}")
                return 1

    print("\n=== 产物 ===")
    artifacts = {}
    for kind in kinds:
        items = collect(kind)
        for it in items:
            if not it.exists():
                print(f"  缺失：{it}")
                return 1
            size = (sum(f.stat().st_size for f in it.rglob("*") if f.is_file())
                    if it.is_dir() else it.stat().st_size)
            print(f"  [{kind}] {it.name:<26} {size/1024/1024:6.1f} MB")
        artifacts[kind] = items

    if args.no_zip:
        return 0

    (RELEASE / "README-EXE.txt").write_text(README_EXE.format(ver=__version__),
                                            encoding="utf-8", newline="\n")
    sums = []
    if "onedir" in artifacts:
        zp = RELEASE / f"EconomyCheck-v{__version__}-win64-portable.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for d in artifacts["onedir"]:
                for f in d.rglob("*"):
                    if f.is_file():
                        z.write(f, arcname=str(pathlib.Path(d.name) / f.relative_to(d)))
            z.write(RELEASE / "README-EXE.txt", arcname="README-EXE.txt")
        sums.append(f"{sha256(zp)}  {zp.name}")
        print(f"\n便携包：{zp}  ({zp.stat().st_size/1024/1024:.1f} MB)")
    if "onefile" in artifacts:
        zp = RELEASE / f"EconomyCheck-v{__version__}-onefile.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for e in artifacts["onefile"]:
                z.write(e, arcname=e.name)
            z.write(RELEASE / "README-EXE.txt", arcname="README-EXE.txt")
        sums.append(f"{sha256(zp)}  {zp.name}")
        print(f"单文件包：{zp}  ({zp.stat().st_size/1024/1024:.1f} MB)")

    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                            encoding="utf-8", newline="\n")
    print(f"校验和：{RELEASE / 'SHA256SUMS.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
