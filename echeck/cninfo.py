# -*- coding: utf-8 -*-
"""巨潮资讯网（cninfo，证监会指定信息披露平台）官方接口封装。

- 搜索公司：POST /new/information/topSearch/query
- 列定期报告：POST /new/hisAnnouncement/query
- 下载报告：http://static.cninfo.com.cn/<adjunctUrl>
"""
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://www.cninfo.com.cn"
STATIC = "http://static.cninfo.com.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CATEGORIES = {
    "annual": ("category_ndbg_szsh", "年度报告"),
    "semi": ("category_bndbg_szsh", "半年度报告"),
    "q1": ("category_yjdbg_szsh", "第一季度报告"),
    "q3": ("category_sjdbg_szsh", "第三季度报告"),
}

# 本工具的定期报告通道基于巨潮 A 股披露库，只有 A 股（含沪/深/北）可用。
# 港股、海外上市、非上市公司在 cninfo 的这套分类接口下拿不到定期报告。
SUPPORTED_CATEGORY = "A股"

_TAG = re.compile(r"<[^>]+>")


def is_supported(comp) -> bool:
    return (comp or {}).get("category") == SUPPORTED_CATEGORY


def market_note(comp) -> str:
    """给出能否分析的人类可读说明。"""
    cat = (comp or {}).get("category") or "未知"
    if cat == SUPPORTED_CATEGORY:
        return "A 股，可分析"
    if cat == "港股":
        return "港股：定期报告在香港交易所披露，不在巨潮 A 股库中，本工具暂不支持"
    return f"{cat}：不在巨潮 A 股定期报告库中，本工具暂不支持"


class CninfoError(RuntimeError):
    pass


def _request(url, data=None, timeout=60, retries=3):
    body = urllib.parse.urlencode(data, encoding="utf-8").encode() if data else None
    headers = {
        "User-Agent": UA,
        "Referer": BASE + "/new/commonUrl?url=disclosure/list/notice",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }
    if body:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise CninfoError(f"请求失败 {url}: {type(last).__name__}: {last}")


def _post_json(url, data):
    raw = _request(url, data)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise CninfoError(f"接口返回非 JSON：{raw[:200]!r}") from e


def market_column(code: str) -> str:
    """按代码前缀推断 cninfo 的 column 参数。"""
    code = (code or "").strip()
    if code.startswith(("6", "9")):
        return "sse"
    if code.startswith(("0", "2", "3")):
        return "szse"
    if code.startswith(("4", "8")):
        return "bj"
    return "szse"


def search_companies(keyword: str, max_num: int = 20) -> list:
    """按代码/简称/拼音搜索公司，返回 [{code, name, org_id, pinyin, delisted}]。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    data = _post_json(f"{BASE}/new/information/topSearch/query",
                      {"keyWord": keyword, "maxNum": str(max_num)})
    out = []
    for it in data or []:
        out.append({
            "code": it.get("code", ""),
            "name": it.get("zwjc", ""),
            "org_id": it.get("orgId", ""),
            "pinyin": it.get("pinyin", ""),
            "category": it.get("category", ""),
            "delisted": it.get("delisted") == "true",
        })
    return out


def report_kind(title: str) -> str:
    if "半年度报告" in title:
        return "semi"
    if "年度报告" in title:
        return "annual"
    if "第一季度报告" in title:
        return "q1"
    if "第三季度报告" in title:
        return "q3"
    return "other"


def period_label(title: str, kind: str = None) -> str:
    """报告期标签：2024年报 / 2025H1 / 2026Q1。"""
    m = re.search(r"(20\d{2})\s*年", title)
    year = m.group(1) if m else "?"
    kind = kind or report_kind(title)
    return {"annual": f"{year}年报", "semi": f"{year}H1",
            "q1": f"{year}Q1", "q3": f"{year}Q3"}.get(kind, f"{year}其他")


def list_reports(code: str, org_id: str, kinds=("annual",), page_size: int = 50,
                 max_pages: int = 6) -> list:
    """列出某公司的定期报告。kinds 取 CATEGORIES 的键。"""
    column = market_column(code)
    stock = f"{code},{org_id}" if org_id else code
    out, seen = [], set()
    for kind in kinds:
        category, _ = CATEGORIES[kind]
        for page in range(1, max_pages + 1):
            data = _post_json(f"{BASE}/new/hisAnnouncement/query", {
                "pageNum": page, "pageSize": page_size, "column": column,
                "tabName": "fulltext", "plate": "", "stock": stock,
                "searchkey": "", "secid": "", "category": category,
                "trade": "", "seDate": "", "sortName": "", "sortType": "",
                "isHLtitle": "true",
            })
            anns = (data or {}).get("announcements") or []
            if not anns:
                break
            for a in anns:
                title = _TAG.sub("", a.get("announcementTitle", "")).strip()
                url = a.get("adjunctUrl", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                ts = a.get("announcementTime")
                date = time.strftime("%Y-%m-%d", time.localtime(ts / 1000)) if ts else ""
                k = report_kind(title)
                out.append({
                    "code": code,
                    "title": title,
                    "kind": k,
                    "period": period_label(title, k),
                    "date": date,
                    "is_summary": "摘要" in title,
                    "is_hk": "港股" in title or "H股" in title,
                    "file": url.split("/")[-1],
                    "url": f"{STATIC}/{url}",
                    "bytes": 0,
                })
            if not (data or {}).get("hasMore"):
                break
    # 同一报告期常有“全文”和“正文”两个版本（正文不含完整报表），只保留全文
    def rank(title: str) -> int:
        if "全文" in title:
            return 2
        if "正文" in title:
            return 1
        return 0

    best = {}
    for r in out:
        key = (r["kind"], r["period"], r["is_summary"], r["is_hk"])
        cur = best.get(key)
        if cur is None or rank(r["title"]) > rank(cur["title"]):
            best[key] = r
    out = list(best.values())
    out.sort(key=lambda r: (r["date"], r["title"]), reverse=True)
    return out


def download(url: str, dest: pathlib.Path, progress=None, cancel=None) -> pathlib.Path:
    """下载到 dest；若已存在且非空则跳过。progress(done, total) 可为 None。"""
    dest = pathlib.Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        if progress:
            progress(dest.stat().st_size, dest.stat().st_size, "已缓存")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": BASE + "/"})
    with urllib.request.urlopen(req, timeout=180) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel and cancel():
                tmp.unlink(missing_ok=True)
                raise CninfoError("用户取消")
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total, "下载中")
    tmp.replace(dest)
    return dest
