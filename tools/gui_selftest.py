# -*- coding: utf-8 -*-
"""GUI 自检：用已有真实数据灌入界面，逐步截图，验证布局与渲染不报错。

用法：python tools/gui_selftest.py [输出目录]
"""
import csv
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from echeck import config  # noqa: F401,E402
from echeck import cninfo, stats  # noqa: E402
from echeck.gui import App  # noqa: E402
from echeck.pipeline import Result  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}
OUT = pathlib.Path(ARGS[0]) if ARGS else ROOT / "results" / "gui"
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = "--shots" in FLAGS


def build_fake_result():
    # 优先用工具链产出的 results/amounts_raw.csv（与 README 数字一致），退回早期 raw/
    src = ROOT / "results" / "amounts_raw.csv"
    if not src.exists():
        src = ROOT / "raw" / "amounts_raw.csv"
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    res = Result()
    res.company = {"code": "601799", "name": "星宇股份", "org_id": "9900017668"}
    periods = sorted({r["report"] for r in rows}, reverse=True)
    res.reports = [{"period": p, "title": f"星宇股份{p}", "kind": "annual",
                    "date": "2026-03-20", "file": "x.PDF",
                    "url": "http://static.cninfo.com.cn/finalpage/x.PDF"}
                   for p in periods]
    res.rows = rows
    res.results = stats.analyze_all(rows)
    res.validation = stats.validate(rows)
    res.paths = {"base": str(ROOT / "data" / "601799_星宇股份"),
                 "results": str(ROOT / "results")}
    res.seconds = 12.3
    return res


def pump(app, n=8, dt=0.05):
    for _ in range(n):
        app.update()
        time.sleep(dt)


def shot(app, name):
    """截图：只取窗口客户区。

    GetWindowRect 返回的矩形含 DWM 不可见边框与阴影，直接按它截图会把窗口外的
    桌面（例如侧边栏）带进画面；因此改用 Tk 报告的客户区坐标，并校验它落在窗口矩形内。
    """
    import ctypes
    from ctypes import wintypes
    from PIL import ImageGrab
    u = ctypes.windll.user32
    app.lift()
    app.attributes("-topmost", True)
    app.focus_force()
    pump(app, 10, 0.08)
    app.update_idletasks()

    hwnd = u.GetAncestor(app.winfo_id(), 2)  # GA_ROOT
    rect = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    cx, cy = app.winfo_rootx(), app.winfo_rooty()
    cw, ch = app.winfo_width(), app.winfo_height()
    inside = (rect.left <= cx and rect.top <= cy
              and cx + cw <= rect.right and cy + ch <= rect.bottom)
    if inside and cw > 100 and ch > 100:
        box = (cx, cy, cx + cw, cy + ch)          # 客户区：保证只有本程序内容
        note = "client"
    else:                                          # 兜底：窗口矩形内缩，去掉不可见边框
        pad = 16
        box = (rect.left + pad, rect.top + pad, rect.right - pad, rect.bottom - pad)
        note = "frame-inset"
    img = ImageGrab.grab(bbox=box)
    p = OUT / name
    img.save(p)
    print(f"  screenshot -> {p}  ({img.size[0]}x{img.size[1]})  [{note}]  "
          f"client=({cx},{cy},{cw},{ch}) frame=({rect.left},{rect.top},"
          f"{rect.right},{rect.bottom})")


def main():
    res = build_fake_result()
    app = App()
    pump(app, 10)

    # 1) 公司搜索页：灌入假搜索结果
    app.companies = [
        {"code": "601799", "name": "星宇股份", "org_id": "9900017668",
         "pinyin": "xygf", "category": "A股", "delisted": False},
        {"code": "000625", "name": "长安汽车", "org_id": "gssz0000625",
         "pinyin": "caqc", "category": "A股", "delisted": False},
        {"code": "300750", "name": "宁德时代", "org_id": "GD165627",
         "pinyin": "ndsd", "category": "A股", "delisted": False},
    ]
    app.tv_company.delete(*app.tv_company.get_children())
    for i, c in enumerate(app.companies):
        app.tv_company.insert("", "end", iid=f"c{i}",
                              values=(c["code"], c["name"], c["pinyin"], "正常"))
    app.var_kw.set("601799")
    pump(app)
    if SHOTS:
        shot(app, "01_companies.png")

    # 2) 报告列表页
    app.reports = [
        {"code": "601799", "title": f"星宇股份{y}年年度报告全文", "kind": "annual",
         "period": f"{y}年报", "date": f"{y+1}-03-20", "is_summary": False,
         "is_hk": False, "file": f"{y}.PDF",
         "url": f"http://static.cninfo.com.cn/finalpage/{y}.PDF"}
        for y in range(2015, 2026)
    ] + [
        {"code": "601799", "title": "星宇股份2026年半年度报告", "kind": "semi",
         "period": "2026H1", "date": "2026-08-27", "is_summary": False,
         "is_hk": False, "file": "h1.PDF", "url": "x"},
        {"code": "601799", "title": "星宇股份2025年年度报告摘要", "kind": "annual",
         "period": "2025年报", "date": "2025-03-20", "is_summary": True,
         "is_hk": False, "file": "s.PDF", "url": "x"},
    ]
    app.company = res.company
    app.lbl_company.configure(text="当前公司：星宇股份（601799）  orgId=9900017668")
    app._fill_reports()
    app.select_recommended()
    app.nb.select(1)
    pump(app)
    if SHOTS:
        shot(app, "02_reports.png")

    # 3) 结果页各子标签
    app.result = res          # 实际运行时由消息队列设置，自检里手动注入
    app._show_result(res)
    pump(app, 12)

    # 图表断言：canvas 里确实画上了图，且保存出来与显示的是同一张
    assert app._chart_img is not None, "图表未生成"
    assert len(app.canvas.find_all()) > 0, "canvas 未绘制图像"
    chart_out = OUT / "00_chart_as_displayed.png"
    app._chart_img.save(chart_out)
    print(f"  图表断言 OK：显示图像 {app._chart_img.size} -> {chart_out}")
    # 末位数字分布图断言
    assert getattr(app, "_last_chart_img", None) is not None, "末位数字分布图未生成"
    assert len(app.canvas2.find_all()) > 0, "末位数字画布未绘制图像"
    print(f"  末位数字图断言 OK：显示图像 {app._last_chart_img.size}")
    print(f"  画布 {app.canvas.winfo_width()}x{app.canvas.winfo_height()}，"
          f"绘制尺寸 {getattr(app, '_last_draw', None)}，"
          f"窗口 {app.winfo_width()}x{app.winfo_height()}")
    bb = app.canvas.bbox("all")
    assert bb and (bb[2] - bb[0]) <= app.canvas.winfo_width() + 20 \
        and (bb[3] - bb[1]) <= app.canvas.winfo_height() + 20, f"图表超出画布: {bb}"
    print(f"  画布内容包围盒 {bb}（在画布内，未溢出）")

    if SHOTS:
        shot(app, "03_result_chart.png")
    for idx, name in ((1, "04_result_stats.png"), (2, "05_result_digits.png"),
                      (3, "06_result_validation.png")):
        inner = [w for w in app.nb.nametowidget(app.nb.select()).winfo_children()
                 if w.winfo_class() == "TNotebook"]
        if inner:
            inner[0].select(idx)
        pump(app, 8)
        if SHOTS:
            shot(app, name)

    # 4) 明细数据页
    app.nb.select(3)
    app.var_filter.set("货币资金")
    app._fill_details()
    pump(app, 8)
    n_detail = len(app.tv_rows.get_children())
    assert n_detail > 0, "明细筛选无结果"
    print(f"  明细筛选 OK：'货币资金' 命中 {n_detail} 行")
    if SHOTS:
        shot(app, "07_details.png")

    # 5) 日志页
    app.nb.select(4)
    app._append_log("[自检] 界面渲染正常")
    pump(app, 8)
    if SHOTS:
        shot(app, "08_log.png")

    # 6) 交互：勾选切换
    kids = app.tv_report.get_children()
    if kids:
        app._toggle(kids[0])
        print(f"  勾选切换 OK，已选 {len(app._selected_reports())} 期")

    # 7) 搜索无结果 / 非 A 股的反馈
    empty_state_test(app)

    app.destroy()
    print("GUI 自检通过（离线渲染路径）")


def online_test():
    """真实联网 + 多线程路径：搜索 → 加载报告 → 跑一次完整分析。"""
    app = App()
    pump(app, 10)

    # 先复现用户场景：搜索非上市公司
    app.var_kw.set("字节跳动")
    app.do_search()
    wait_for(app, lambda a: app.lbl_found.cget("text") != "正在搜索「字节跳动」…",
             60, "搜索非上市公司")
    settle(app)
    print(f"  搜索「字节跳动」-> {app.lbl_found.cget('text').strip()}；"
          f"提示条={'已显示' if app.lbl_empty.winfo_ismapped() else '未显示'}")
    assert "未找到" in app.lbl_found.cget("text")
    assert app.lbl_empty.winfo_ismapped()
    if SHOTS:
        shot(app, "10_search_notfound.png")

    app.var_kw.set("601799")
    app.do_search()
    app.companies = wait_for(app, lambda a: a.companies, 60, "搜索公司")
    print(f"  联网搜索 OK：{app.companies[0]['name']}（{app.companies[0]['code']}）")

    app.tv_company.selection_set("c0")
    app.use_company()
    wait_for(app, lambda a: a.reports, 60, "加载报告列表")
    print(f"  报告列表 OK：{len(app.reports)} 份，已选 {len(app._selected_reports())} 期")

    # 只留近 2 期年报（示例仓库里已缓存，跑得很快）
    annual = [i for i, r in enumerate(app._visible_reports())
              if r["kind"] == "annual" and not r["is_summary"]]
    annual.sort(key=lambda i: app._visible_reports()[i]["period"], reverse=True)
    keep = set(annual[:2])
    for i, iid in enumerate(app.tv_report.get_children()):
        app.selected[iid] = i in keep
        vals = list(app.tv_report.item(iid, "values"))
        vals[0] = "☑" if i in keep else "☐"
        app.tv_report.item(iid, values=vals)
    app._update_pick()

    app.start_analysis()
    res = wait_for(app, lambda a: a.result, 600, "运行分析")
    main = res.main
    print(f"  分析 OK：{res.company['name']} {len(res.reports)} 期，数据行 {len(res.rows)}，"
          f"n={main['n']}，χ²={main['chi2']:.2f}，p={main['p_value']:.4f}，"
          f"结论={main['verdict']}")
    assert app.canvas.bbox("all"), "结果页未绘图"
    print(f"  结果页渲染 OK：画布内容 {app.canvas.bbox('all')}")
    if SHOTS:
        shot(app, "09_online_result.png")
    app.destroy()
    print("GUI 联网自检通过（含多线程与完整流程）")


def settle(app, n=6):
    """页签切换/布局后需要几个事件循环才稳定（真实程序是持续事件循环）。"""
    for _ in range(n):
        app.update()


def wait_for(app, cond, timeout, what):
    """在保持事件循环转动的前提下等待条件成立。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.update()
        v = cond(app)
        if v:
            return v
        time.sleep(0.1)
    raise TimeoutError(f"等待「{what}」超时（{timeout}s）")


def empty_state_test(app):
    """搜索无结果 / 非 A 股证券时必须有可见反馈，且不得进入分析流程。"""
    app.nb.select(0)          # 隐藏的页签里控件不会被 map，先切到①页
    settle(app)
    app._handle(("companies", [], "字节跳动"))
    settle(app)
    assert "未找到" in app.lbl_found.cget("text"), app.lbl_found.cget("text")
    assert app.lbl_empty.winfo_ismapped(), "空结果提示条未显示"
    assert "字节跳动" in app.lbl_empty.cget("text")
    print("  空结果反馈 OK：" + app.lbl_found.cget("text").strip()
          + " / 提示条已显示")

    app._handle(("companies", [{"code": "00700", "name": "腾讯控股",
                                "org_id": "gshk0000700", "pinyin": "txkg",
                                "category": "港股", "delisted": False}], "腾讯"))
    settle(app)
    found = app.lbl_found.cget("text")
    assert "非 A 股" in found, found
    before = app.company
    app.tv_company.selection_set("c0")
    app.use_company()
    settle(app)
    assert app.company == before, "港股不应被当作可分析标的使用"
    assert "不支持" in app.lbl_empty.cget("text") or "港股" in app.lbl_empty.cget("text")
    print("  非 A 股拦截 OK：" + found.strip() + " / 未进入分析流程")

    # 报告为空时的提示
    app.nb.select(1)
    app.reports = []
    app._fill_reports()
    settle(app)
    assert app.lbl_rep_hint.winfo_ismapped(), "空报告列表提示未显示"
    print("  空报告提示 OK：" + app.lbl_rep_hint.cget("text")[:24] + "…")

    # 恢复：正常 A 股搜索结果
    app.nb.select(0)
    app.reports = []
    app._handle(("companies", [
        {"code": "601799", "name": "星宇股份", "org_id": "9900017668",
         "pinyin": "xygf", "category": "A股", "delisted": False}], "601799"))
    settle(app)
    assert "找到 1 家" in app.lbl_found.cget("text"), app.lbl_found.cget("text")
    assert not app.lbl_empty.winfo_ismapped(), "正常结果不应显示空提示条"
    print("  正常结果反馈 OK：" + app.lbl_found.cget("text").strip())


if __name__ == "__main__":
    if "--online" in FLAGS:
        online_test()
    else:
        main()
