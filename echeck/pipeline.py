# -*- coding: utf-8 -*-
"""端到端流程编排：下载 → 抽取文本 → 解析三大报表 → 校验 → 检验 → 出图。"""
import json
import pathlib
import re
import time

from . import cninfo, parse, pdftext, stats, viz
from .config import STATEMENT_NAMES, company_dir, ensure_dirs


class Cancelled(RuntimeError):
    pass


class PipelineError(RuntimeError):
    """带用户可读说明的流程错误：GUI 只展示说明，不展示堆栈。"""


# 项目名里混入这些东西说明版式没解析干净（章节引用、页脚签名等）
POLLUTED_LABEL = re.compile(r"第[一二三四五六七八九十百零\d]+\s*节|法定代表人|主管会计"
                            r"|会计机构负责人|股份有限公司")


class Result:
    def __init__(self):
        self.company = {}
        self.reports = []
        self.rows = []
        self.results = []
        self.validation = {}
        self.section_info = {}
        self.diag = []
        self.paths = {}
        self.warnings = []
        self.seconds = 0.0

    @property
    def main(self):
        return self.results[0] if self.results else None


def _check(cancel):
    if cancel and cancel():
        raise Cancelled("用户取消")


# manifest 允许公开的字段（其余如 local/txt/text/_flags 属于本机路径或第三方全文）
MANIFEST_FIELDS = ("period", "title", "kind", "date", "url", "file", "bytes",
                   "is_summary", "is_hk")


def safe_manifest(reports):
    """生成可公开的报告清单：只含报告期、标题、官方 URL 等，不含本机路径与正文。"""
    out = []
    for r in reports:
        item = {k: r[k] for k in MANIFEST_FIELDS if k in r}
        if "url" in item and isinstance(item["url"], str):
            item["url"] = item["url"].split("?")[0]
        out.append(item)
    return out


def _statement_counts(rows):
    c = {"BS": 0, "IS": 0, "CF": 0}
    for r in rows:
        c[r["statement"]] = c.get(r["statement"], 0) + 1
    return c


def _quality(rows, infos):
    """报表解析得是否完整：三张表都定位到、每张至少 10 个金额行、项目名没被污染。"""
    found = [x["statement"] for x in infos if x.get("found")]
    c = _statement_counts(rows)
    polluted = sum(1 for r in rows if POLLUTED_LABEL.search(r["item"]))
    ok = (len(found) == 3 and all(c.get(s, 0) >= 10 for s in ("BS", "IS", "CF"))
          and polluted <= 1)
    return ok, found, c


def _polluted(rows):
    return sum(1 for r in rows if POLLUTED_LABEL.search(r["item"]))


def _no_data_message(res, diag, texts):
    """所有报告都没解析出数据时，给用户一份可读的说明而不是堆栈。"""
    lines = ["所选报告都没能解析出报表数据。", "", "各期情况："]
    for d in diag:
        det = d.get("reason") or "未抽到金额"
        extra = ""
        if d.get("chars") is not None:
            extra = f"（文本 {d['chars']:,} 字符，汉字 {d.get('cjk', 0):,}）"
        lines.append(f"  · {d['period']}：{det}{extra}")
    scanned = any((d.get("cjk") or 0) < 500 for d in diag)
    lines += ["", "可能原因与建议："]
    if scanned:
        lines.append("  · 有的报告几乎抽不到文字，通常是扫描版 PDF，需要 OCR，本工具暂不支持；")
    lines.append("  · 确认勾选的是“年度报告全文”而不是“摘要”；")
    lines.append("  · 换其它报告期，或一次多勾几期；")
    lines.append("  · 若某期标题能定位但金额为 0，请把该期 PDF 发我以适配其版式。")
    return "\n".join(lines)


def run_analysis(company, reports, progress=None, cancel=None, base_dir=None,
                 make_chart=True):
    """company: {code,name,org_id}; reports: [{title,period,url,file,kind}]"""
    t0 = time.time()
    res = Result()
    res.company = dict(company)
    res.reports = list(reports)

    def log(step, done=0, total=0, msg=""):
        if progress:
            progress(step, done, total, msg)

    base = pathlib.Path(base_dir) if base_dir else company_dir(company["code"],
                                                               company.get("name", ""))
    dirs = ensure_dirs(base)
    res.paths = {k: str(v) for k, v in dirs.items()}
    log("准备", 0, 1, f"工作目录 {base}")

    # 1) 下载
    for i, rep in enumerate(reports, 1):
        _check(cancel)
        dest = dirs["pdf"] / rep["file"]
        log("下载报告", i, len(reports), rep["title"])

        def cb(done, total, m, _i=i, _r=rep):
            if total:
                log("下载报告", _i, len(reports),
                    f"{_r['title']} {done/1048576:.1f}/{total/1048576:.1f} MB")
        cninfo.download(rep["url"], dest, progress=cb, cancel=cancel)
        rep["bytes"] = dest.stat().st_size
        rep["local"] = str(dest)

    # 2) 抽取文本
    texts = {}
    for i, rep in enumerate(reports, 1):
        _check(cancel)
        txt = dirs["txt"] / (rep["file"] + ".txt")
        cached = False
        flags = {"current": False}
        if txt.exists() and txt.stat().st_size > 0:
            try:
                flags = pdftext.cache_flags(
                    txt.open(encoding="utf-8", errors="replace").readline())
                cached = flags.get("current", False)
            except OSError:
                cached = False
        rep["_flags"] = flags
        if not cached:
            log("解析 PDF", i, len(reports), rep["title"])
            try:
                text = pdftext.extract_text(rep["local"], cancel=cancel)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"{rep['title']} PDF 解析失败：{e}")
                continue
            pdftext.write_text_cache(txt, text)
        else:
            log("解析 PDF", i, len(reports), f"{rep['title']}（已缓存）")
        rep["txt"] = str(txt)
        texts[rep["file"]] = txt.read_text(encoding="utf-8", errors="replace")

    # 3) 解析报表金额
    rows = []
    diag = []
    for i, rep in enumerate(reports, 1):
        _check(cancel)
        text = texts.get(rep["file"])
        if text is None:
            diag.append({"period": rep["period"], "title": rep["title"], "rows": 0,
                         "reason": "PDF 文本抽取失败（文件可能损坏）"})
            continue
        log("抽取报表", i, len(reports), rep["title"])
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        r, infos = parse.rows_from_text(text, rep["period"], rep["title"])
        ok, found, cnt = _quality(r, infos)

        # 版式特殊（整页被合并成一行、项目名被污染等）时，改用 pdfplumber 复核一遍
        if not ok and not rep.get("_flags", {}).get("escalated") == "1":
            log("解析 PDF", i, len(reports),
                f"{rep['title']}：版式复杂，改用 pdfplumber 复核…")
            chosen_backend = "pypdfium2"
            try:
                text2 = pdftext.extract_text(rep["local"], backend="pdfplumber")
                r2, infos2 = parse.rows_from_text(text2, rep["period"], rep["title"])
                ok2, found2, cnt2 = _quality(r2, infos2)
                score1 = (len(found), sum(cnt.values()), -_polluted(r))
                score2 = (len(found2), sum(cnt2.values()), -_polluted(r2))
                if score2 > score1:
                    text, r, infos, ok, found, cnt = text2, r2, infos2, ok2, found2, cnt2
                    texts[rep["file"]] = text
                    chosen_backend = "pdfplumber"
                    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
                    res.warnings.append(f"{rep['title']}：版式特殊，已改用 pdfplumber 抽取")
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"{rep['title']} pdfplumber 复核失败：{e}")
            if rep.get("txt"):   # 记录“已复核过”，避免每次运行都重跑慢路径
                pdftext.write_text_cache(
                    rep["txt"],
                    pdftext.with_header(text, backend=chosen_backend, escalated=True))

        missing = [STATEMENT_NAMES[x["statement"]] for x in infos
                   if not x.get("found")]
        if not infos:
            reason = "未找到任何合并报表标题"
        elif len(missing) == 3:
            reason = ("未定位到合并资产负债表/利润表/现金流量表："
                      + ("疑似扫描版 PDF（几乎抽不到文字）" if cjk < 500
                         else "报表标题或版式与预期不符"))
        elif missing:
            reason = "未定位到：" + "、".join(missing)
        elif len(r) < 10:
            reason = "定位到报表标题，但没有抽到金额行"
        else:
            reason = ""
        diag.append({"period": rep["period"], "title": rep["title"],
                     "rows": len(r), "chars": len(text), "cjk": cjk,
                     "missing": missing, "counts": cnt, "reason": reason})
        if reason:
            res.warnings.append(f"{rep['title']}：{reason}（抽取 {len(r)} 行）")
        res.section_info[rep["period"]] = infos
        rows.extend(r)
    res.rows = rows
    res.diag = diag
    if not rows:
        raise PipelineError(_no_data_message(res, diag, texts))

    # 4) 校验
    log("数据校验", 0, 1, "会计恒等式与跨期衔接")
    res.validation = stats.validate(rows)

    # 5) 统计检验
    res.results = stats.analyze_all(rows, progress=progress)

    # 6) 输出
    log("生成结果", 0, 2, "报告与图表")
    stats.write_csv(dirs["results"] / "benford_first_digit.csv", res.results)
    stats.write_rows_csv(dirs["results"] / "amounts_raw.csv", rows)
    stats.write_report(dirs["results"] / "benford_report.md", company, reports,
                       rows, res.results, res.validation)
    stats.write_validation(dirs["results"] / "validation.md", rows, res.validation)
    # manifest 只保留可公开的字段：绝不写入本机绝对路径（local/txt）与报告全文（text）
    (dirs["results"] / "manifest.json").write_text(
        json.dumps(safe_manifest(reports), ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    if make_chart and res.main:
        try:
            viz.save_figure(dirs["results"] / "benford_first_digit.png", res.main,
                            company, periods=len(reports), datasets=res.results)
        except Exception as e:  # noqa: BLE001
            res.warnings.append(f"绘图失败：{e}")
    res.seconds = time.time() - t0
    log("完成", 1, 1, f"用时 {res.seconds:.1f}s，样本 n={res.main['n'] if res.main else 0}")
    return res
