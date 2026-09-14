# -*- coding: utf-8 -*-
"""路径与运行环境。"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYLIBS = ROOT / ".pylibs"
DATA_ROOT = ROOT / "data"

# 依赖装在 .pylibs 里（不污染全局环境），导入前先挂到 sys.path
if PYLIBS.is_dir() and str(PYLIBS) not in sys.path:
    sys.path.insert(0, str(PYLIBS))


def _font_dirs():
    """字体目录候选：运行时探测，避免把本机绝对路径写死在代码里。"""
    dirs = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(pathlib.Path(windir) / "Fonts")
    home = pathlib.Path.home()
    dirs += [home / "AppData/Local/Microsoft/Windows/Fonts",
             pathlib.Path("/usr/share/fonts"), pathlib.Path("/usr/local/share/fonts"),
             pathlib.Path("/System/Library/Fonts"), pathlib.Path("/Library/Fonts")]
    return [d for d in dirs if d.is_dir()]


CN_FONTS = ("msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc", "Deng.ttf",
            "NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf", "wqy-microhei.ttc")
CN_FONTS_BOLD = ("msyhbd.ttc", "msyh.ttc", "simhei.ttf")


def find_font(names) -> str:
    """在常见字体目录里找第一个存在的中文字体；找不到返回空串（调用方回退默认字体）。"""
    for d in _font_dirs():
        for name in names:
            for cand in (d / name, d / "truetype" / name, d / "opentype" / name):
                if cand.is_file():
                    return str(cand)
    return ""


FONT_REG = find_font(CN_FONTS)
FONT_BOLD = find_font(CN_FONTS_BOLD) or FONT_REG

# 三大合并报表：(代码, 起始标题, 结束标题)
SECTIONS = [
    ("BS", "合并资产负债表", "母公司资产负债表"),
    ("IS", "合并利润表", "母公司利润表"),
    ("CF", "合并现金流量表", "母公司现金流量表"),
]
STATEMENT_NAMES = {"BS": "资产负债表", "IS": "利润表", "CF": "现金流量表"}


def company_dir(code: str, name: str = "") -> pathlib.Path:
    safe = "".join(ch for ch in (name or "") if ch not in '\\/:*?"<>|').strip()
    return DATA_ROOT / (f"{code}_{safe}" if safe else str(code))


def ensure_dirs(base: pathlib.Path) -> dict:
    d = {
        "base": base,
        "pdf": base / "pdf",
        "txt": base / "txt",
        "results": base / "results",
    }
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d
