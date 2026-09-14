# -*- coding: utf-8 -*-
"""启动图形界面。

用法：
    python run_gui.py                # 直接打开
    python run_gui.py 601799         # 打开并自动搜索该代码

说明：用 pythonw 无控制台启动时，任何异常都会被写进 logs/gui.log，
      并弹出提示框，避免"双击后一闪而过、什么也看不到"。
"""
import datetime
import pathlib
import sys
import traceback

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from echeck import config  # noqa: E402,F401  （把工作区内的 .pylibs 挂到 sys.path）

LOGDIR = BASE / "logs"
LOGFILE = LOGDIR / "gui.log"


def _log(msg):
    try:
        LOGDIR.mkdir(parents=True, exist_ok=True)
        with LOGFILE.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


class _LogWriter:
    """pythonw 下 sys.stdout/stderr 为 None，print 会直接抛异常，这里转写日志文件。"""

    def write(self, s):
        if s and s.strip():
            _log("OUT " + s.rstrip())

    def flush(self):
        pass


def _fatal(text):
    _log("FATAL\n" + text)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f"启动失败：\n\n{text[-1500:]}\n\n完整日志：\n{LOGFILE}",
            "财报 Benford 分析器", 0x10)
    except Exception:  # noqa: BLE001
        pass


def _excepthook(t, v, tb):
    _fatal("".join(traceback.format_exception(t, v, tb)))


def check_deps():
    """检查依赖；缺什么就给出可复制的安装命令。"""
    missing = []
    for mod, pkg in (("PIL", "pillow"), ("pdfplumber", "pdfplumber"),
                     ("pypdfium2", "pypdfium2")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    try:
        import numpy  # noqa: F401   （可选：缺了只是没有蒙特卡洛检验）
    except ImportError:
        _log("提示：未安装 numpy，蒙特卡洛 MAD 检验将不可用")
    if missing:
        msg = ("缺少依赖：" + ", ".join(missing) + "\n\n"
               "请在项目目录下执行（装到工作区内的 .pylibs，不影响全局环境）：\n"
               '  $env:PIP_USER="0"\n'
               "  python -m pip install --no-user --target .\\.pylibs "
               + " ".join(missing))
        print(msg)
        _log(msg)
        return False
    _log(f"依赖检查通过（sys.path 含 {config.PYLIBS}）")
    return True


def main():
    if sys.stdout is None:          # pythonw：没有控制台
        sys.stdout = _LogWriter()
    if sys.stderr is None:
        sys.stderr = _LogWriter()
    sys.excepthook = _excepthook
    _log("启动 GUI，argv=" + repr(sys.argv))
    try:
        if not check_deps():
            _fatal("依赖不完整，无法启动界面。\n\n"
                   "请按以下步骤安装后再启动：\n\n"
                   '$env:PIP_USER="0"\n'
                   "python -m pip install --no-user --target .\\.pylibs "
                   "pdfplumber pillow pypdfium2")
            return 1
        from echeck.gui import main as gui_main
        gui_main()
        _log("GUI 正常退出")
        return 0
    except BaseException:  # noqa: BLE001
        _fatal(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
