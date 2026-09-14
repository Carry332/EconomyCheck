# -*- coding: utf-8 -*-
"""从年报文本中定位三大合并报表，按行抽取金额。

输出 raw/amounts_raw.csv：report, statement, page, item, n, v1..v4, line

定位策略（关键）：报表标题在正文中是独占一行的，例如
    合并资产负债表
    2025年12月31日
    编制单位：常州星宇车灯股份有限公司
因此只在“独占整行”的标题处匹配，并要求随后几行出现“编制单位/单位：元”表头，
再截取到下一个“母公司××表”标题为止。这样可避免抓到目录、审计报告或会计政策正文。
"""
import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TXT_DIR = ROOT / "raw" / "txt"
OUT = ROOT / "raw" / "amounts_raw.csv"
DEBUG = ROOT / "raw" / "sections_debug.txt"

SECTIONS = [
    ("BS", "合并资产负债表", "母公司资产负债表"),
    ("IS", "合并利润表", "母公司利润表"),
    ("CF", "合并现金流量表", "母公司现金流量表"),
]

NUM = re.compile(r"-?\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|-?\d+\.\d+|-?\d+")
PAGE = re.compile(r"^=====\s*PAGE\s*(\d+)\s*=====$")
# 附注索引列，例如 “七、1”“五、12”“七、1（2）”，必须剔除，否则会被误当成金额
NOTE_REF = re.compile(r"[一二三四五六七八九十]+\s*、\s*\d+\s*(?:[（(]\s*\d+\s*[)）])?")
UNIT_NOISE = re.compile(r"人民币|美元|欧元|日元|港币")
DATE_LINE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
                       r"|\d{4}\s*年\s*\d{1,2}\s*[—\-－~]\s*\d{1,2}\s*月"
                       r"|^\s*\d+\s*/\s*\d+\s*$")
# 表头/编制说明行，不含金额
HEADER_NOISE = re.compile(r"编制单位|单位[:：]|币种|项目\s*附注|^项目$|年度报告|季度报告|股份有限公司|公司负责人|法定代表人")
# 行首的条目编号，如 “（2）其他债权投资公允价值变动”“2.终止经营净利润”“1．不能重分类进损益…”“一、营业总收入”
ENUM_PREFIX = re.compile(
    r"^\s*(?:[（(]\s*\d+\s*[)）]|\d+\s*[.、．]"
    r"|[（(]\s*[一二三四五六七八九十]+\s*[)）]|[一二三四五六七八九十]+\s*[、.])\s*")


def norm(s: str) -> str:
    return s.replace(" ", "").replace("\u3000", "").strip()


# 所有（合并/母公司）报表标题，用于确定报表正文的结束位置。
# 季报只披露合并报表，没有母公司表，因此结束位置取“下一个任意报表标题”。
ALL_TITLES = {norm(t) for pair in SECTIONS for t in pair}


def load_manifest():
    return json.loads((ROOT / "raw" / "manifest.json").read_text(encoding="utf-8-sig"))


def report_period(title: str) -> str:
    """把公告标题规范成报告期标签：2024年报 / 2025H1 / 2026Q1。"""
    m = re.search(r"(20\d{2})年", title)
    y = m.group(1) if m else "?"
    if "半年度报告" in title:      # 必须先判半年报（其标题也含“年度报告”字样）
        return f"{y}H1"
    if "年度报告" in title:
        return f"{y}年报"
    if "第一季度报告" in title:
        return f"{y}Q1"
    if "第三季度报告" in title:
        return f"{y}Q3"
    return f"{y}?"


def find_section(lines, start_marker, end_marker):
    """返回 (start_idx, end_idx, info)。结束位置为下一个任意报表标题（母公司表或下一张表）。"""
    cands = []
    for i, line in enumerate(lines):
        if norm(line) != start_marker:
            continue
        end = None
        for j in range(i + 1, min(len(lines), i + 400)):
            if norm(lines[j]) in ALL_TITLES:
                end = j
                break
        if end is None:
            # 最后一张表（常见于季报的合并现金流量表）后面没有其它报表标题
            end = min(len(lines), i + 200)
        seg = lines[i:end]
        head = "".join(seg[:8])
        has_header = ("编制单位" in head) or ("单位：元" in head) or ("单位:元" in head)
        n_nums = sum(len(NUM.findall(x)) for x in seg)
        cands.append({"start": i, "end": end, "header": has_header,
                      "nums": n_nums, "len": len(seg)})
    if not cands:
        return None
    good = [c for c in cands if c["header"] and 20 <= c["len"] <= 400]
    pool = good or [c for c in cands if 20 <= c["len"] <= 400] or cands
    best = max(pool, key=lambda c: c["nums"])
    return best["start"], best["end"], best


def main():
    rows = []
    dbg = []
    for item in load_manifest():
        name, title = item["file"], item["title"]
        year = report_period(title)
        txt_path = TXT_DIR / (name + ".txt")
        if not txt_path.exists():
            print(f"missing txt: {name}")
            continue
        lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
        # 记录每行所属页码
        pages, cur = [], "?"
        for line in lines:
            m = PAGE.match(line.strip())
            if m:
                cur = m.group(1)
            pages.append(cur)

        for code, sm, em in SECTIONS:
            found = find_section(lines, sm, em)
            if not found:
                print(f"!! section not found: {name} {code}")
                continue
            s, e, info = found
            dbg.append(f"{year} {code} {title} lines[{s}:{e}] page={pages[s]} "
                       f"len={info['len']} nums={info['nums']} header={info['header']}")
            seg = [ln.strip() for ln in lines[s:e]]
            clean = [ENUM_PREFIX.sub("", UNIT_NOISE.sub(" ", NOTE_REF.sub(" ", ln)))
                     for ln in seg]
            for idx, raw in enumerate(seg):
                if not raw or PAGE.match(raw):
                    continue
                if HEADER_NOISE.search(raw) or DATE_LINE.search(raw):
                    continue
                cleaned = clean[idx]
                toks = NUM.findall(cleaned)
                if not toks:
                    continue
                first = NUM.search(cleaned)
                label = cleaned[: first.start()].strip(" 　:：|")
                if not label:
                    # PDF 换行把项目名拆成了上下两半，把前后片段拼回来
                    prev_txt = clean[idx - 1].strip() if idx > 0 else ""
                    next_txt = clean[idx + 1].strip() if idx + 1 < len(seg) else ""
                    if (prev_txt and not NUM.search(prev_txt)
                            and not prev_txt.endswith(("：", ":"))
                            and next_txt and not NUM.search(next_txt)
                            and len(prev_txt) + len(next_txt) <= 40):
                        label = (prev_txt + next_txt).strip(" 　:：")
                vals = [t.replace(",", "").replace("，", "") for t in toks]
                row = {"report": year, "title": title, "statement": code,
                       "item": label, "n": len(vals)}
                for i in range(4):
                    row[f"v{i+1}"] = vals[i] if i < len(vals) else ""
                row["line"] = raw
                rows.append(row)

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["report", "title", "statement", "item", "n",
                                          "v1", "v2", "v3", "v4", "line"])
        w.writeheader()
        w.writerows(rows)
    DEBUG.write_text("\n".join(dbg), encoding="utf-8")
    print(f"rows={len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
