# -*- coding: utf-8 -*-
"""从定期报告文本中定位三大合并报表并抽取金额。

定位策略：报表标题在正文中独占一行（如「合并资产负债表」），且其后数行出现
「编制单位 / 单位：元」表头；报表正文截止到下一个任意报表标题。
这样可避免误抓目录、审计报告、会计政策附注中的同名文字。
"""
import re

from .config import SECTIONS

NUM = re.compile(r"-?\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|-?\d+\.\d+|-?\d+")
PAGE = re.compile(r"^=====\s*PAGE\s*(\d+)\s*=====$")
# 附注索引列（七、1 / 五、12 / 七、1（2））
NOTE_REF = re.compile(r"[一二三四五六七八九十]+\s*、\s*\d+\s*(?:[（(]\s*\d+\s*[)）])?")
# 章节引用列，北交所等报告用“第十一节、”表示附注所在章节
SECTION_REF = re.compile(r"第\s*[一二三四五六七八九十百零\d]+\s*节\s*[、.．]?")
UNIT_NOISE = re.compile(r"人民币|美元|欧元|日元|港币")
# 日期行、页码行、期间行
DATE_LINE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
                       r"|\d{4}\s*年\s*\d{1,2}\s*[—\-－~]\s*\d{1,2}\s*月"
                       r"|^\s*\d+\s*/\s*\d+\s*$")
HEADER_NOISE = re.compile(r"编制单位|单位[:：]|币种|项目\s*附注|^项目|年度报告|季度报告"
                          r"|股份有限公司|公司负责人|法定代表人")
# 行首条目编号（（2）… / 1．… / 一、…）
ENUM_PREFIX = re.compile(
    r"^\s*(?:[（(]\s*\d+\s*[)）]|\d+\s*[.、．]"
    r"|[（(]\s*[一二三四五六七八九十]+\s*[)）]|[一二三四五六七八九十]+\s*[、.])\s*")
# 标题尾部可接受的补充说明，如“合并资产负债表（续）”
TITLE_SUFFIX = re.compile(r"^[（(]\s*(续|續|未经审计|未审计)\s*[)）]$")
# 项目名的常见结尾，用于判断被换行拆开的片段拼接是否合理
LABEL_TAIL = re.compile(r"(合计|总计|小计|净额|余额|收入|成本|费用|收益|损失|利润|现金"
                        r"|支出|资产|负债|权益|准备|储备|股本|公积|股利|利息|账款|款项"
                        r"|负债表|流量表|利润表)$")


def _norm(s: str) -> str:
    return s.replace(" ", "").replace("\u3000", "").strip()


def line_title(line: str) -> str:
    """把一行还原成“标题形态”：去空格、去行首序号。

    很多公司的报表标题带序号，例如「1、合并资产负债表」「（一）合并利润表」，
    必须去掉序号后才能与标准标题比对。
    """
    return ENUM_PREFIX.sub("", _norm(line)).strip()


def is_title(line: str, marker: str) -> bool:
    t = line_title(line)
    if t == marker:
        return True
    if t.startswith(marker):
        return bool(TITLE_SUFFIX.match(t[len(marker):]))
    return False


ALL_TITLES = {_norm(t) for pair in SECTIONS for t in pair}


def find_section(lines, start_marker: str):
    """返回 (start_idx, end_idx, info)。end 为下一个任意报表标题所在行。"""
    cands = []
    for i, line in enumerate(lines):
        if not is_title(line, start_marker):
            continue
        end = None
        for j in range(i + 1, min(len(lines), i + 400)):
            if line_title(lines[j]) in ALL_TITLES:
                end = j
                break
        if end is None:
            end = min(len(lines), i + 200)   # 季报最后一张表后面没有别的报表标题
        seg = lines[i:end]
        head = "".join(seg[:8])
        has_header = ("编制单位" in head) or ("单位：元" in head) or ("单位:元" in head)
        cands.append({"start": i, "end": end, "header": has_header,
                      "nums": sum(len(NUM.findall(x)) for x in seg), "len": len(seg)})
    if not cands:
        return None
    good = [c for c in cands if c["header"] and 20 <= c["len"] <= 400]
    pool = good or [c for c in cands if 20 <= c["len"] <= 400] or cands
    best = max(pool, key=lambda c: c["nums"])
    return best["start"], best["end"], best


def clean_line(raw: str) -> str:
    s = NOTE_REF.sub(" ", raw)
    s = SECTION_REF.sub(" ", s)
    return ENUM_PREFIX.sub("", UNIT_NOISE.sub(" ", s))


def _looks_like_label(s: str) -> bool:
    return 2 <= len(s) <= 44 and not NUM.search(s) and bool(LABEL_TAIL.search(s))


def _join(a: str, b: str) -> str:
    return (a + b).strip(" 　:：|")


def rebuild_label(clean, idx) -> str:
    """金额行的项目名为空时，从相邻行拼接回被换行拆开的项目名。

    PDF 的文本顺序并不统一，可能是「名1 / 名2 / 金额」也可能是「名1 / 金额 / 名2」，
    因此按几种候选组合依次尝试，取第一个“像项目名”（以合计/资产/费用等结尾）的组合。
    """
    prev_txt = clean[idx - 1].strip() if idx > 0 else ""
    next_txt = clean[idx + 1].strip() if idx + 1 < len(clean) else ""
    prev2 = clean[idx - 2].strip() if idx >= 2 else ""
    next2 = clean[idx + 2].strip() if idx + 2 < len(clean) else ""
    pure = lambda s: bool(s) and not NUM.search(s)          # noqa: E731
    cands = []
    if pure(prev_txt) and pure(next_txt):
        cands.append(_join(prev_txt, next_txt))
    if pure(prev2) and pure(prev_txt):
        cands.append(_join(prev2, prev_txt))
    if pure(next_txt) and pure(next2):
        cands.append(_join(next_txt, next2))
    if pure(prev_txt):
        cands.append(prev_txt.strip(" 　:：|"))
    if pure(next_txt):
        cands.append(next_txt.strip(" 　:：|"))
    for c in cands:
        if _looks_like_label(c):
            return c
    return cands[0] if cands else ""


def rows_from_text(text: str, period: str, title: str):
    """从一份报告全文抽取金额行，返回 (rows, debug_infos)。"""
    lines = text.splitlines()
    pages, cur = [], "?"
    for line in lines:
        m = PAGE.match(line.strip())
        if m:
            cur = m.group(1)
        pages.append(cur)

    rows, infos = [], []
    for code, marker, _ in SECTIONS:
        found = find_section(lines, marker)
        if not found:
            infos.append({"statement": code, "found": False})
            continue
        s, e, info = found
        infos.append({"statement": code, "found": True, "page": pages[s],
                      "start": s, "end": e, "len": info["len"], "nums": info["nums"]})
        seg = [ln.strip() for ln in lines[s:e]]
        clean = [clean_line(ln) for ln in seg]
        for idx, raw in enumerate(seg):
            if not raw or PAGE.match(raw):
                continue
            if HEADER_NOISE.search(raw) or DATE_LINE.search(raw):
                continue
            cleaned = clean[idx]
            matches = list(NUM.finditer(cleaned))
            if not matches:
                continue
            raw_vals = [m.group(0) for m in matches]
            # 有的公司附注列是纯数字，例如「货币资金 1 51,690,610,946.50 59,295,822,956.89」，
            # 那个 1 是附注编号而不是金额：当后面还有带小数的金额时把它丢掉。
            skip = 0
            v0 = raw_vals[0].lstrip("-")
            if (len(raw_vals) >= 2 and v0.isdigit() and len(v0) <= 3
                    and int(v0) <= 999
                    and any("." in v for v in raw_vals[1:])):
                skip = 1
            label = cleaned[: matches[0].start()].strip(" 　:：|")
            if not label:
                label = rebuild_label(clean, idx)
            vals = [v.replace(",", "").replace("，", "") for v in raw_vals[skip:]]
            row = {"report": period, "title": title, "statement": code,
                   "item": label, "n": len(vals)}
            for i in range(4):
                row[f"v{i+1}"] = vals[i] if i < len(vals) else ""
            row["line"] = raw
            rows.append(row)
    return rows, infos
