# -*- coding: utf-8 -*-
"""PDF 转文本（逐页，保留 PAGE 标记）。

后端策略（auto）：
  1. 用 pypdfium2 快速抽取全部页面（比 pdfplumber 快约 40 倍）；
  2. 检测“整页被合并成一行”的页面（部分 PDF 的表格页会这样），
     只对这些页面用 pdfplumber 重新抽取并替换 —— 兼顾速度与准确度。
"""
import pathlib
import re

PAGE_MARK = "===== PAGE {n} ====="
# 文本缓存格式版本：升级解析逻辑后自增，pipeline 会据此丢弃旧缓存
CACHE_VERSION = 4


def normalize(text: str) -> str:
    """统一成 LF 换行。

    否则在 Windows 上写文件时 ``\\n`` 会被转换成 ``\\r\\n``，
    读回来行结构就变了，同一份 PDF 会解析出不同结果。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text_cache(path, text) -> None:
    """原样写入（不做换行转换），保证读回来与写出去完全一致。"""
    pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")


def cache_header(repaired=0, backend="pypdfium2", escalated=False) -> str:
    return (f"#EXTRACTOR v{CACHE_VERSION} backend={backend} "
            f"repaired={repaired} escalated={1 if escalated else 0}\n")


def cache_flags(text: str) -> dict:
    """解析缓存头，返回 {current: bool, backend: str, escalated: '0'/'1', ...}。"""
    first = (text or "").split("\n", 1)[0]
    if not first.startswith("#EXTRACTOR "):
        return {"current": False}
    flags = {"current": first.startswith(f"#EXTRACTOR v{CACHE_VERSION} ")}
    for kv in first.split()[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            flags[k] = v
    return flags


def with_header(text: str, repaired=0, backend="pypdfium2", escalated=False) -> str:
    body = text.split("\n", 1)[1] if text.startswith("#EXTRACTOR ") else text
    return cache_header(repaired, backend, escalated) + normalize(body)


def is_current_cache(text: str) -> bool:
    return text.startswith(f"#EXTRACTOR v{CACHE_VERSION} ")


def extract_text(pdf_path, progress=None, cancel=None, backend="auto") -> str:
    """返回带 `===== PAGE n =====` 分隔的全文（首行为缓存版本标记，统一 LF 换行）。"""
    pdf_path = pathlib.Path(pdf_path)
    if backend == "pdfplumber":
        body, _ = _with_pdfplumber(pdf_path, progress, cancel)
        return cache_header(0, "pdfplumber") + normalize(body)
    try:
        body, repaired = _with_pypdfium2(pdf_path, progress, cancel,
                                         repair=(backend == "auto"))
        return cache_header(repaired, "pypdfium2") + normalize(body)
    except ImportError:
        body, _ = _with_pdfplumber(pdf_path, progress, cancel)
        return cache_header(0, "pdfplumber") + normalize(body)


def _looks_merged(text: str) -> bool:
    """判断一页是否被抽成“一行到底”（表格页常见）。"""
    if len(text) < 500:
        return False
    newlines = text.count("\n")
    return newlines < max(3, len(text) / 250)


def _with_pdfplumber(pdf_path, progress, cancel):
    import pdfplumber
    parts, pages_done = [], 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            if cancel and cancel():
                raise RuntimeError("用户取消")
            try:
                t = page.extract_text() or ""
            except Exception as e:  # noqa: BLE001
                t = f"<<extract error: {e}>>"
            parts.append(f"\n{PAGE_MARK.format(n=i)}\n{t}")
            pages_done = i
            if progress:
                progress(i, total, "解析 PDF")
    return "".join(parts), pages_done


def _with_pypdfium2(pdf_path, progress, cancel, repair=True):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    n = len(pdf)
    pages, suspicious = [], []
    for i in range(n):
        if cancel and cancel():
            raise RuntimeError("用户取消")
        t = pdf[i].get_textpage().get_text_range()
        if repair and _looks_merged(t):
            suspicious.append(i)
        pages.append(t)
        if progress:
            progress(i + 1, n, "解析 PDF")

    repaired = 0
    if suspicious:
        try:
            import pdfplumber
        except ImportError:
            pdfplumber = None
        if pdfplumber is not None:
            if progress:
                progress(len(suspicious), len(suspicious),
                         f"修复 {len(suspicious)} 个表格页（换用 pdfplumber 重抽）")
            try:
                with pdfplumber.open(str(pdf_path)) as pl:
                    for i in suspicious:
                        if cancel and cancel():
                            raise RuntimeError("用户取消")
                        try:
                            t2 = pl.pages[i].extract_text() or ""
                        except Exception:  # noqa: BLE001
                            continue
                        # 只有确实拆出了更多行才替换
                        if t2.count("\n") > pages[i].count("\n"):
                            pages[i] = t2
                            repaired += 1
            except Exception:  # noqa: BLE001
                pass

    parts = [f"\n{PAGE_MARK.format(n=i+1)}\n{t}" for i, t in enumerate(pages)]
    return "".join(parts), repaired


def text_path(txt_dir: pathlib.Path, pdf_name: str) -> pathlib.Path:
    return pathlib.Path(txt_dir) / (pdf_name + ".txt")


PAGE_RE = re.compile(r"^=====\s*PAGE\s*(\d+)\s*=====$")
