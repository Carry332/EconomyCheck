# -*- coding: utf-8 -*-
"""路径与运行环境。"""
import os
import pathlib
import sys

def is_frozen() -> bool:
    """是否运行在打包后的可执行文件里（PyInstaller 等）。"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> pathlib.Path:
    """应用目录。

    - 源码运行：项目根目录；
    - 打包运行：可执行文件所在目录 —— 数据/日志/结果都写在 exe 旁边，便于便携使用。
    """
    if is_frozen():
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent.parent


ROOT = app_dir()
PYLIBS = ROOT / ".pylibs"
DATA_ROOT = ROOT / "data"

# 依赖装在 .pylibs 里（不污染全局环境），导入前先挂到 sys.path；
# 打包后依赖已在包内，不需要也不应再找 .pylibs。
if not is_frozen() and PYLIBS.is_dir() and str(PYLIBS) not in sys.path:
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

# 三大合并报表：(代码, 合并报表标题候选, 母公司报表标题候选)
# 中文标题为主；同时支持英文版年报（部分公司在巨潮同时披露英文版）
SECTIONS = [
    ("BS",
     ("合并资产负债表", "Consolidated Balance Sheet",
      "Consolidated Statements of Financial Position",
      "Consolidated Statement of Financial Position"),
     ("母公司资产负债表", "公司资产负债表", "Parent Company Balance Sheet",
      "Balance Sheet of the Parent Company")),
    ("IS",
     ("合并利润表", "Consolidated Income Statement",
      "Consolidated Statements of Profit or Loss",
      "Consolidated Statement of Profit or Loss",
      "Consolidated Statement of Operations"),
     ("母公司利润表", "公司利润表", "Parent Company Income Statement",
      "Income Statement of the Parent Company")),
    ("CF",
     ("合并现金流量表", "Consolidated Cash Flow Statement",
      "Consolidated Statement of Cash Flows",
      "Consolidated Statements of Cash Flows"),
     ("母公司现金流量表", "公司现金流量表", "Parent Company Cash Flow Statement",
      "Cash Flow Statement of the Parent Company")),
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
