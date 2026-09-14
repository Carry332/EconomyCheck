# -*- coding: utf-8 -*-
"""tkinter 图形界面：搜索公司 → 选择报告 → 自动分析 → 可视化展示。"""
import os
import pathlib
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from datetime import date
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import cninfo, pipeline
from .config import ROOT, company_dir
from .stats import EXPECTED

APP_TITLE = "财报 Benford 分析器 · 巨潮资讯网官方数据"
UI_FONT = ("Microsoft YaHei UI", 9)
UI_FONT_B = ("Microsoft YaHei UI", 9, "bold")
MONO = ("Consolas", 9)


def _log(msg):
    """写 logs/gui.log，便于 pythonw 无控制台时排查。"""
    try:
        import datetime
        p = pathlib.Path(__file__).resolve().parent.parent / "logs" / "gui.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] GUI {msg}\n")
    except Exception:  # noqa: BLE001
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        # 自适应屏幕：小屏笔记本（如 1280x720）也能完整显示
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1280, sw - 30), min(840, sh - 70)
        self.geometry(f"{w}x{h}+20+15")
        self.minsize(min(940, sw - 30), min(600, sh - 90))

        self.q = queue.Queue()
        self.companies = []
        self.company = None
        self.reports = []
        self.selected = {}
        self.result = None
        self.cancel_flag = False
        self.worker = None
        self._img_ref = None
        self._chart_img = None
        self._detail_rows = []

        self._init_style()
        self._build()
        self.report_callback_exception = self._on_tk_error
        self.after(100, self._poll)
        _log(f"窗口已创建 {w}x{h}（屏幕 {sw}x{sh}）")

    def _on_tk_error(self, exc, val, tb):
        """Tk 回调里的异常默认只打到 stderr（pythonw 下会丢失），这里记入界面与日志。"""
        txt = "".join(traceback.format_exception(exc, val, tb))
        _log("Tk 回调异常\n" + txt)
        try:
            self._append_log("[异常] " + txt)
        except Exception:  # noqa: BLE001
            pass

    # ---------------- 样式 ----------------
    def _init_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(".", font=UI_FONT)
        style.configure("Treeview", rowheight=24, font=UI_FONT)
        style.configure("Treeview.Heading", font=UI_FONT_B)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Hint.TLabel", foreground="#5a6570")
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    def _build(self):
        # 顶部搜索栏
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="公司搜索", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="代码 / 简称 / 拼音", style="Hint.TLabel").pack(
            side="left", padx=(10, 4))
        self.var_kw = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.var_kw, width=28, font=UI_FONT)
        ent.pack(side="left")
        ent.bind("<Return>", lambda e: self.do_search())
        ttk.Button(top, text="搜索", command=self.do_search).pack(side="left", padx=6)
        self.lbl_found = ttk.Label(top, text="", style="Hint.TLabel")
        self.lbl_found.pack(side="left", padx=10)
        self.lbl_company = ttk.Label(top, text="未选择公司", style="Hint.TLabel")
        self.lbl_company.pack(side="left", padx=6)

        # 主 Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._build_tab_company()
        self._build_tab_reports()
        self._build_tab_results()
        self._build_tab_details()
        self._build_tab_log()

        # 底部状态栏
        bottom = ttk.Frame(self, padding=(10, 4))
        bottom.pack(fill="x")
        self.pb = ttk.Progressbar(bottom, mode="determinate", length=380)
        self.pb.pack(side="left")
        self.lbl_status = ttk.Label(bottom, text="就绪", style="Hint.TLabel")
        self.lbl_status.pack(side="left", padx=10)
        self.btn_cancel = ttk.Button(bottom, text="停止", command=self.do_cancel,
                                     state="disabled")
        self.btn_cancel.pack(side="right")
        self.btn_open = ttk.Button(bottom, text="打开工作目录", command=self.open_workdir)
        self.btn_open.pack(side="right", padx=6)

    # ---------------- Tab1 公司 ----------------
    def _build_tab_company(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=" ① 选择公司 ")
        ttk.Label(f, text="搜索后在下方列表中双击（或选中后点“使用该公司”）即可加载其定期报告列表。"
                          "本工具只覆盖上市公司（A 股，含沪/深/北）。",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 6))
        # 空结果提示条（默认隐藏）
        self.lbl_empty = tk.Label(
            f, justify="left", anchor="w", background="#fff8e1",
            foreground="#8a5a00", padx=10, pady=8,
            font=("Microsoft YaHei UI", 9), text="")
        self.lbl_empty.pack(side="top", fill="x", pady=(0, 6))
        self.lbl_empty.pack_forget()          # 默认隐藏，搜索无结果时再显示
        cols = ("code", "name", "pinyin", "state")
        self.tv_company = ttk.Treeview(f, columns=cols, show="headings", height=14)
        for c, t, w in zip(cols, ("代码", "名称", "拼音", "状态"),
                           (110, 220, 140, 120)):
            self.tv_company.heading(c, text=t)
            self.tv_company.column(c, width=w, anchor="w")
        self.tv_company.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tv_company.yview)
        sb.pack(side="left", fill="y")
        self.tv_company.configure(yscrollcommand=sb.set)
        self.tv_company.bind("<Double-1>", lambda e: self.use_company())
        bar = ttk.Frame(f)
        bar.pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="使用该公司", command=self.use_company).pack(fill="x")
        ttk.Button(bar, text="按代码直连",
                   command=self.use_by_code).pack(fill="x", pady=6)
        ttk.Label(bar, text="提示：\n支持沪深京 A 股，\n如 601799、300750、833171。",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=10)

    # ---------------- Tab2 报告 ----------------
    def _build_tab_reports(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=" ② 选择报告 ")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self.var_kinds = {}
        for key, label in (("annual", "年度报告"), ("semi", "半年度报告"),
                           ("q1", "一季报"), ("q3", "三季报")):
            v = tk.BooleanVar(value=(key == "annual"))
            self.var_kinds[key] = v
            ttk.Checkbutton(bar, text=label, variable=v).pack(side="left")
        self.var_summary = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="包含摘要", variable=self.var_summary).pack(side="left", padx=6)
        self.var_hk = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="包含港股公告", variable=self.var_hk).pack(side="left")
        ttk.Label(bar, text="  起始年份", style="Hint.TLabel").pack(side="left", padx=(14, 2))
        self.var_from = tk.StringVar(value="2015")
        ttk.Combobox(bar, textvariable=self.var_from, width=6, values=
                     [str(y) for y in range(1998, 2027)]).pack(side="left")
        ttk.Label(bar, text="结束", style="Hint.TLabel").pack(side="left", padx=(8, 2))
        self.var_to = tk.StringVar(value=str(date.today().year + 1))
        ttk.Combobox(bar, textvariable=self.var_to, width=6, values=
                     [str(y) for y in range(1998, 2027)]).pack(side="left")
        ttk.Button(bar, text="查询报告", command=self.load_reports).pack(side="left", padx=8)

        self.lbl_rep_hint = tk.Label(
            f, justify="left", anchor="w", background="#fff8e1",
            foreground="#8a5a00", padx=10, pady=6, font=("Microsoft YaHei UI", 9), text="")
        self.lbl_rep_hint.pack(side="top", fill="x", pady=(6, 0))
        self.lbl_rep_hint.pack_forget()

        cols = ("sel", "period", "kind", "title", "date")
        self.tv_report = ttk.Treeview(f, columns=cols, show="headings", height=18)
        for c, t, w, a in (("sel", "选", 40, "center"), ("period", "报告期", 90, "w"),
                           ("kind", "类型", 90, "w"), ("title", "标题", 560, "w"),
                           ("date", "公告日期", 100, "w")):
            self.tv_report.heading(c, text=t)
            self.tv_report.column(c, width=w, anchor=a)
        self.tv_report.pack(fill="both", expand=True, pady=6)
        self.tv_report.bind("<Button-1>", self._on_report_click)
        self.tv_report.bind("<space>", self._toggle_focus_rows)

        bar2 = ttk.Frame(f)
        bar2.pack(fill="x")
        ttk.Button(bar2, text="全选", command=lambda: self.select_all(True)).pack(side="left")
        ttk.Button(bar2, text="全不选", command=lambda: self.select_all(False)).pack(side="left", padx=6)
        ttk.Button(bar2, text="仅选年报", command=self.select_annual).pack(side="left")
        ttk.Button(bar2, text="推荐（近 8 期年报）",
                   command=self.select_recommended).pack(side="left", padx=6)
        ttk.Label(bar2, text="建议至少 6 期年报（样本 n≥600）",
                  style="Hint.TLabel").pack(side="left", padx=8)
        self.btn_run = ttk.Button(bar2, text="▶ 开始分析", style="Big.TButton",
                                  command=self.start_analysis)
        self.btn_run.pack(side="right")
        self.lbl_pick = ttk.Label(bar2, text="已选 0 期", style="Hint.TLabel")
        self.lbl_pick.pack(side="right", padx=12)

    # ---------------- Tab3 结果 ----------------
    def _build_tab_results(self):
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text=" ③ 分析结果 ")
        inner = ttk.Notebook(f)
        inner.pack(fill="both", expand=True)

        # 图
        g = ttk.Frame(inner)
        inner.add(g, text=" 首位数字分布图 ")
        self.canvas = tk.Canvas(g, background="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw_chart())
        gb = ttk.Frame(g)
        gb.pack(fill="x")
        ttk.Button(gb, text="导出图片", command=self.export_chart).pack(side="left")
        ttk.Label(gb, text="（红色 = 该首位数字偏离超过 5% 显著水平）",
                  style="Hint.TLabel").pack(side="left", padx=10)

        # 检验结论
        c = ttk.Frame(inner)
        inner.add(c, text=" 检验结论 ")
        self.tv_datasets = ttk.Treeview(
            c, columns=("name", "n", "chi2", "p", "mad", "mcp", "d", "verdict"),
            show="headings", height=9)
        for col, t, w in (("name", "数据集", 250), ("n", "n", 60), ("chi2", "χ²", 70),
                          ("p", "p 值", 80), ("mad", "MAD", 70),
                          ("mcp", "蒙特卡洛 p", 90), ("d", "KS D", 70),
                          ("verdict", "结论", 170)):
            self.tv_datasets.heading(col, text=t)
            self.tv_datasets.column(col, width=w, anchor="w")
        self.tv_datasets.pack(fill="x")
        self.tv_datasets.bind("<<TreeviewSelect>>", lambda e: self._show_digits())
        self.txt_summary = ScrolledText(c, height=14, font=UI_FONT, wrap="word")
        self.txt_summary.pack(fill="both", expand=True, pady=6)

        # 分布明细
        dm = ttk.Frame(inner)
        inner.add(dm, text=" 分布明细 ")
        pick = ttk.Frame(dm)
        pick.pack(fill="x")
        ttk.Label(pick, text="数据集", style="Hint.TLabel").pack(side="left")
        self.var_ds = tk.StringVar()
        self.cmb_ds = ttk.Combobox(pick, textvariable=self.var_ds, width=40,
                                   state="readonly")
        self.cmb_ds.pack(side="left", padx=6)
        self.cmb_ds.bind("<<ComboboxSelected>>", lambda e: self._show_digits())
        ttk.Button(pick, text="导出 CSV", command=self.export_csv).pack(side="left", padx=8)
        self.tv_digits = ttk.Treeview(
            dm, columns=("d", "obs", "po", "pe", "exp", "diff", "z", "ratio"),
            show="headings", height=12)
        for col, t, w in (("d", "首位数字", 80), ("obs", "观测数", 80),
                          ("po", "实际占比", 90), ("pe", "Benford 期望", 110),
                          ("exp", "期望频数", 90), ("diff", "偏差", 90),
                          ("z", "z 统计量", 90), ("ratio", "实际/期望", 90)):
            self.tv_digits.heading(col, text=t)
            self.tv_digits.column(col, width=w, anchor="center")
        self.tv_digits.pack(fill="both", expand=True, pady=4)

        # 质量校验
        v = ttk.Frame(inner)
        inner.add(v, text=" 质量校验 ")
        self.txt_valid = ScrolledText(v, font=MONO, wrap="none")
        self.txt_valid.pack(fill="both", expand=True)

    # ---------------- Tab4 明细 ----------------
    def _build_tab_details(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=" ④ 明细数据 ")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="筛选（项目/报告期）", style="Hint.TLabel").pack(side="left")
        self.var_filter = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.var_filter, width=30)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda ev: self._fill_details())
        ttk.Button(bar, text="筛选", command=self._fill_details).pack(side="left")
        ttk.Button(bar, text="导出全部明细 CSV",
                   command=self.export_rows).pack(side="left", padx=8)
        self.lbl_cnt = ttk.Label(bar, text="", style="Hint.TLabel")
        self.lbl_cnt.pack(side="left", padx=10)

        cols = ("report", "st", "item", "v1", "v2", "line")
        self.tv_rows = ttk.Treeview(f, columns=cols, show="headings")
        for c, t, w, a in (("report", "报告期", 80, "w"), ("st", "报表", 90, "w"),
                           ("item", "项目", 260, "w"), ("v1", "本期/期末", 150, "e"),
                           ("v2", "上期/期初", 150, "e"), ("line", "原始行", 420, "w")):
            self.tv_rows.heading(c, text=t)
            self.tv_rows.column(c, width=w, anchor=a)
        self.tv_rows.pack(fill="both", expand=True, pady=6)

    # ---------------- Tab5 日志 ----------------
    def _build_tab_log(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=" 运行日志 ")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="导出结果到指定目录",
                   command=self.export_all).pack(side="left")
        ttk.Button(bar, text="清空日志", command=lambda: self.txt_log.delete("1.0", "end")
                   ).pack(side="left", padx=6)
        self.txt_log = ScrolledText(f, font=MONO, wrap="none")
        self.txt_log.pack(fill="both", expand=True, pady=6)

    # ================= 交互逻辑 =================
    def log(self, msg):
        self.q.put(("log", msg))

    def do_search(self):
        kw = self.var_kw.get().strip()
        if not kw:
            self._show_search_hint("请输入股票代码（如 601799）或上市公司简称（如 星宇股份）。")
            return
        self._show_search_hint("")
        self.lbl_found.configure(text=f"正在搜索「{kw}」…", foreground="#5a6570")
        self.log(f"[搜索] {kw}")
        self._run_bg(self._search_worker, kw)

    def _show_search_hint(self, text):
        """在①页顶部显示/隐藏空结果提示条。"""
        if text:
            self.lbl_empty.configure(text=text)
            self.lbl_empty.pack(side="top", fill="x", pady=(0, 6), before=self.tv_company)
        else:
            self.lbl_empty.pack_forget()

    def _search_worker(self, kw):
        try:
            comps = cninfo.search_companies(kw, 20)
            self.q.put(("companies", comps, kw))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"搜索失败：{e}"))

    def use_company(self):
        sel = self.tv_company.selection()
        if not sel:
            messagebox.showinfo("提示", "请先搜索并选中一家公司")
            return
        idx = self.tv_company.index(sel[0])
        self._set_company(self.companies[idx])

    def use_by_code(self):
        code = self.var_kw.get().strip()
        if not code.isdigit():
            messagebox.showinfo("提示", "请先在上方输入 6 位股票代码")
            return
        self._run_bg(self._direct_worker, code)

    def _direct_worker(self, code):
        try:
            comps = cninfo.search_companies(code, 5)
            hit = next((c for c in comps if c["code"] == code), None)
            if not hit:
                self.q.put(("error", f"未找到代码 {code}"))
                return
            self.q.put(("companies", comps))
            self.q.put(("use_company", hit))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"查询失败：{e}"))

    def _set_company(self, comp):
        if not cninfo.is_supported(comp):
            note = cninfo.market_note(comp)
            self.lbl_company.configure(text=f"{comp['name']}（{comp['code']}）：非 A 股，不支持")
            self._show_search_hint(
                f"「{comp['name']}（{comp['code']}）」{note}。\n"
                "请改选一家 A 股上市公司（沪市 6xxxxx / 深市 0xxxxx、3xxxxx / 北交所 4xxxxx、8xxxxx）。")
            self.lbl_found.configure(text="所选证券不在支持范围", foreground="#c53030")
            self._append_log(f"[不支持] {comp['name']}（{comp['code']}）{note}")
            self.nb.select(0)
            return
        self.company = comp
        self._show_search_hint("")
        self.lbl_company.configure(
            text=f"当前公司：{comp['name']}（{comp['code']}）  orgId={comp['org_id']}")
        self._append_log(f"[选择] {comp['name']}（{comp['code']}）")
        self.nb.select(1)
        self.load_reports()

    def load_reports(self):
        if not getattr(self, "company", None):
            messagebox.showinfo("提示", "请先选择公司")
            return
        kinds = [k for k, v in self.var_kinds.items() if v.get()]
        if not kinds:
            messagebox.showinfo("提示", "请至少勾选一种报告类型")
            return
        self.log(f"[查询报告] {self.company['code']} {kinds}")
        self._run_bg(self._reports_worker, self.company, kinds)

    def _reports_worker(self, comp, kinds):
        try:
            reps = cninfo.list_reports(comp["code"], comp["org_id"], kinds)
            self.q.put(("reports", reps))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"查询报告失败：{e}"))

    def _visible_reports(self):
        try:
            y0 = int(self.var_from.get())
            y1 = int(self.var_to.get())
        except ValueError:
            y0, y1 = 1990, 2100
        out = []
        for r in self.reports:
            if r["is_summary"] and not self.var_summary.get():
                continue
            if r["is_hk"] and not self.var_hk.get():
                continue
            m = r["period"][:4]
            if m.isdigit() and not (y0 <= int(m) <= y1):
                continue
            out.append(r)
        return out

    def _fill_reports(self):
        self.tv_report.delete(*self.tv_report.get_children())
        self.selected.clear()
        vis = self._visible_reports()
        for i, r in enumerate(vis):
            iid = f"r{i}"
            self.tv_report.insert("", "end", iid=iid,
                                  values=("☐", r["period"],
                                          cninfo.CATEGORIES.get(r["kind"], ("", "其他"))[1],
                                          r["title"], r["date"]))
        if vis:
            self._show_report_hint("")
        elif self.reports:
            self._show_report_hint(
                "当前筛选条件下没有报告：请勾选更多报告类型，或放宽年份区间后重新查询。")
        else:
            self._show_report_hint(
                "该公司在所选类型下没有查到定期报告。可勾选更多报告类型后点「查询报告」，"
                "或确认所选公司是否正确。")
        self._update_pick()

    def _show_report_hint(self, text):
        if text:
            self.lbl_rep_hint.configure(text=text)
            self.lbl_rep_hint.pack(side="top", fill="x", pady=(6, 0),
                                   before=self.tv_report)
        else:
            self.lbl_rep_hint.pack_forget()

    def _on_report_click(self, event):
        if self.tv_report.identify_column(event.x) == "#1":
            iid = self.tv_report.identify_row(event.y)
            if iid:
                self._toggle(iid)
                return "break"

    def _toggle(self, iid):
        self.selected[iid] = not self.selected.get(iid, False)
        vals = list(self.tv_report.item(iid, "values"))
        vals[0] = "☑" if self.selected[iid] else "☐"
        self.tv_report.item(iid, values=vals)
        self._update_pick()

    def _toggle_focus_rows(self, event):
        for iid in self.tv_report.selection():
            self._toggle(iid)
        return "break"

    def select_all(self, flag):
        for iid in self.tv_report.get_children():
            self.selected[iid] = flag
            vals = list(self.tv_report.item(iid, "values"))
            vals[0] = "☑" if flag else "☐"
            self.tv_report.item(iid, values=vals)
        self._update_pick()

    def select_annual(self):
        vis = self._visible_reports()
        for i, iid in enumerate(self.tv_report.get_children()):
            flag = vis[i]["kind"] == "annual" and not vis[i]["is_summary"]
            self.selected[iid] = flag
            vals = list(self.tv_report.item(iid, "values"))
            vals[0] = "☑" if flag else "☐"
            self.tv_report.item(iid, values=vals)
        self._update_pick()

    def select_recommended(self):
        vis = self._visible_reports()
        annual = [i for i, r in enumerate(vis)
                  if r["kind"] == "annual" and not r["is_summary"]]
        annual.sort(key=lambda i: vis[i]["period"], reverse=True)
        keep = set(annual[:8])
        for i, iid in enumerate(self.tv_report.get_children()):
            flag = i in keep
            self.selected[iid] = flag
            vals = list(self.tv_report.item(iid, "values"))
            vals[0] = "☑" if flag else "☐"
            self.tv_report.item(iid, values=vals)
        self._update_pick()

    def _selected_reports(self):
        vis = self._visible_reports()
        return [vis[i] for i, iid in enumerate(self.tv_report.get_children())
                if self.selected.get(iid)]

    def _update_pick(self):
        self.lbl_pick.configure(text=f"已选 {len(self._selected_reports())} 期")

    # ---------------- 运行分析 ----------------
    def start_analysis(self):
        reps = self._selected_reports()
        if not reps:
            messagebox.showinfo("提示", "请先勾选要分析的报告")
            return
        self.cancel_flag = False
        self.btn_cancel.configure(state="normal")
        self.btn_run.configure(state="disabled")
        self.txt_summary.configure(state="normal")
        self.txt_summary.delete("1.0", "end")
        self._run_bg(self._analysis_worker, dict(self.company), reps)

    def _analysis_worker(self, comp, reps):
        try:
            res = pipeline.run_analysis(
                comp, reps,
                progress=lambda *a: self.q.put(("progress",) + a),
                cancel=lambda: self.cancel_flag)
            self.q.put(("result", res))
        except pipeline.Cancelled:
            self.q.put(("cancelled", None))
        except pipeline.PipelineError as e:
            # 预期内的失败（如版式不匹配、扫描件）：只给可读说明，不丢堆栈给用户
            self.q.put(("error", str(e), False))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"分析失败：{e}", True, traceback.format_exc()))

    def do_cancel(self):
        self.cancel_flag = True
        self.log("[停止] 已请求取消，等待当前步骤结束…")

    # ---------------- 后台线程与轮询 ----------------
    def _run_bg(self, fn, *args):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("提示", "上一个任务还在运行，请稍候")
            return
        self.worker = threading.Thread(target=fn, args=args, daemon=True)
        self.worker.start()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "log":
            self._append_log(msg[1])
        elif kind == "progress":
            _, step, done, total, text = msg
            if total:
                self.pb.configure(mode="determinate", maximum=total, value=done)
            else:
                self.pb.configure(mode="indeterminate")
                self.pb.start(60)
            self.lbl_status.configure(text=f"{step} {done}/{total} {text}")
        elif kind == "companies":
            self.companies = msg[1]
            kw = msg[2] if len(msg) > 2 else self.var_kw.get().strip()
            self.tv_company.delete(*self.tv_company.get_children())
            for i, c in enumerate(self.companies):
                state = ("已退市" if c["delisted"] else
                         "正常" if cninfo.is_supported(c) else c.get("category", ""))
                self.tv_company.insert("", "end", iid=f"c{i}",
                                       values=(c["code"], c["name"], c["pinyin"], state))
            supported = [c for c in self.companies if cninfo.is_supported(c)]
            others = len(self.companies) - len(supported)
            if not self.companies:
                self.lbl_found.configure(text="未找到匹配的上市公司", foreground="#c53030")
                self._show_search_hint(
                    f"未找到「{kw}」匹配的上市公司。\n"
                    "巨潮资讯网只收录上市公司的披露文件；非上市公司（如字节跳动、华为）"
                    "没有公开定期报告，无法做财报 Benford 分析。\n"
                    "可尝试：6 位股票代码（如 601799）或上市公司简称（如 星宇股份、宁德时代）。")
                self._append_log(f"[搜索] 「{kw}」无匹配结果：该公司可能未上市，"
                                 f"或名称不准确（可改用 6 位股票代码）")
            elif not supported:
                self.lbl_found.configure(text=f"找到 {others} 家，均非 A 股", foreground="#c53030")
                self._show_search_hint(
                    f"「{kw}」匹配到的都是非 A 股证券（如港股），"
                    "其定期报告不在巨潮 A 股披露库中，本工具暂不支持分析。")
                self._append_log(f"[搜索] 「{kw}」匹配 {others} 家，但都不是 A 股")
            else:
                extra = f"（另有 {others} 家非 A 股，不支持）" if others else ""
                self.lbl_found.configure(text=f"找到 {len(supported)} 家上市公司{extra}",
                                         foreground="#1a7f37")
                self._show_search_hint("")
                self._append_log(f"[搜索] 「{kw}」找到 {len(supported)} 家 A 股上市公司{extra}")
                if len(supported) == 1:
                    self._set_company(supported[0])
        elif kind == "use_company":
            self._set_company(msg[1])
        elif kind == "reports":
            self.reports = msg[1]
            self._fill_reports()
            self.select_recommended()
            if self.reports:
                self._append_log(f"[报告] 查到 {len(self.reports)} 份，默认勾选近 8 期年报")
            else:
                self._append_log("[报告] 未查到定期报告，请调整报告类型或年份后重试")
        elif kind == "result":
            self.pb.stop()
            self.pb.configure(mode="determinate", value=0)
            self.result = msg[1]
            self._show_result(self.result)
            self.btn_run.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
        elif kind == "cancelled":
            self.pb.stop()
            self.lbl_status.configure(text="已取消")
            self.btn_run.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            self._append_log("[已取消]")
        elif kind == "error":
            self.pb.stop()
            self.pb.configure(mode="determinate", value=0)
            self.btn_run.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            text = msg[1]
            with_tb = msg[2] if len(msg) > 2 else True
            tb = msg[3] if len(msg) > 3 else ""
            if tb:
                self._append_log(tb)
            self._append_log("[错误] " + text.replace("\n", "\n        "))
            self.lbl_status.configure(text="分析失败")
            head = text.split("\n", 1)[0]
            if with_tb:
                head = "分析失败：" + head
            messagebox.showerror("无法完成分析", head + "\n\n"
                                 + (text if len(text) < 1200 else text[:1200] + "…")
                                 + "\n\n（完整信息见「运行日志」页）")

    def _append_log(self, s):
        self.txt_log.insert("end", s + "\n")
        self.txt_log.see("end")

    # ---------------- 结果展示 ----------------
    def _show_result(self, res):
        main = res.main
        for w in res.warnings:
            self._append_log("[警告] " + w)
        for d in getattr(res, "diag", []):
            note = f" — {d['reason']}" if d.get("reason") else ""
            self._append_log(f"[报告] {d['period']}：解析 {d['rows']} 行{note}")
        self._append_log(
            f"[完成] {res.company['name']} {len(res.reports)} 期报告，"
            f"数据行 {len(res.rows)}，用时 {res.seconds:.1f}s")
        self.lbl_status.configure(text=f"完成：{len(res.reports)} 期 / n={main['n']}")

        # 数据集表
        self.tv_datasets.delete(*self.tv_datasets.get_children())
        names = []
        for i, r in enumerate(res.results):
            mc = f"{r['mc_p']:.4f}" if r["mc_p"] is not None else "-"
            self.tv_datasets.insert("", "end", iid=f"d{i}", values=(
                r["name"], r["n"], f"{r['chi2']:.2f}", f"{r['p_value']:.4f}",
                f"{r['mad']:.4f}", mc, f"{r['ks_d']:.4f}", r["verdict"]))
            names.append(r["name"])
        self.cmb_ds.configure(values=names)
        if names:
            self.cmb_ds.current(0)

        # 结论文字
        t = self.txt_summary
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", f"公司：{res.company['name']}（{res.company['code']}）\n")
        t.insert("end", f"报告：{', '.join(r['period'] for r in res.reports)}\n")
        t.insert("end", f"数据行：{len(res.rows)}　主口径样本 n = {main['n']}\n")
        t.insert("end", "─" * 62 + "\n")
        t.insert("end", f"卡方检验   χ² = {main['chi2']:.2f} (df=8)   p = {main['p_value']:.4f}\n")
        t.insert("end", f"MAD        {main['mad']:.4f}   判定：{main['mad_band']}\n")
        if main["mc_p"] is not None:
            t.insert("end", f"蒙特卡洛   p = {main['mc_p']:.4f}"
                            f"（模拟均值 {main['mc_mean']:.4f}，95% 分位 {main['mc_q95']:.4f}）\n")
        t.insert("end", f"KS 型 D    {main['ks_d']:.4f}   5% 临界值 {main['ks_crit']:.4f}\n")
        t.insert("end", f"最大 |z|   {main['max_z']:.2f}\n")
        t.insert("end", "─" * 62 + "\n")
        ok = main["p_value"] > 0.05 and (main["mc_p"] is None or main["mc_p"] > 0.05)
        t.insert("end", "结论：" + ("符合 Benford 对数分布 ✔" if ok else
                                   "与 Benford 分布存在显著偏离 ✘") + "\n")
        if main["n"] < 500:
            t.insert("end", f"⚠ 样本量偏小（n={main['n']}），结论不稳定；"
                            f"建议多勾选几期报告（n≥1000 更可靠）。\n")
        t.insert("end", "\n")
        t.insert("end", "首位数字分布（主口径）：\n")
        t.insert("end", "  首位   观测数   实际占比   Benford   偏差\n")
        for row in main["rows"]:
            t.insert("end", f"   {row['digit']}    {row['observed']:>6}   "
                            f"{row['p_observed']:>7.2%}   {row['p_benford']:>7.2%}   "
                            f"{row['diff']:>+7.2%}\n")
        t.configure(state="disabled")

        # 校验文本
        v = res.validation
        self.txt_valid.configure(state="normal")
        self.txt_valid.delete("1.0", "end")
        self.txt_valid.insert("end",
            f"会计恒等式（资产总计 = 负债合计 + 所有者权益合计）：\n"
            f"  通过 {v['identity_ok']}/{v['identity_total']} 期\n\n")
        for it in v["identity"]:
            flag = "✔" if it.get("ok") else ("?" if it.get("ok") is None else "✘")
            diff = f"{it.get('diff', 0):,.2f}" if it.get("ok") is not None else "—"
            self.txt_valid.insert("end", f"  {flag} {it['period']:<9} 差异 {diff}\n")
        self.txt_valid.insert("end",
            f"\n跨报告期衔接（本年上期数 = 上年本期数）：\n"
            f"  一致 {v['chain_matched']}/{v['chain_total']} 项"
            f"（{v['chain_matched']/max(1,v['chain_total']):.1%}）\n\n")
        for c in v["chain"]:
            self.txt_valid.insert("end",
                f"  {c['pair']:<24} {c['matched']}/{c['compared']}"
                + (("   差异示例：" + "；".join(c["diffs"][:2])) if c["diffs"] else "") + "\n")
        self.txt_valid.configure(state="disabled")

        self._fill_details()
        self._render_chart()
        self._show_digits()
        self.nb.select(2)

    def _render_chart(self):
        if not self.result or not self.result.main:
            return
        from . import viz
        try:
            img = viz.render_figure(self.result.main, self.result.company,
                                    periods=len(self.result.reports),
                                    datasets=self.result.results)
        except Exception as e:  # noqa: BLE001
            self._append_log(f"[警告] 绘图失败：{e}")
            return
        self._chart_img = img
        self._redraw_chart()

    def _redraw_chart(self):
        if self._chart_img is None:
            return
        from PIL import Image, ImageTk
        cw = max(self.canvas.winfo_width(), 200) - 16
        ch = max(self.canvas.winfo_height(), 200) - 16
        iw, ih = self._chart_img.size
        s = min(cw / iw, ch / ih)
        if s <= 0:
            return
        size = (max(1, int(iw * s)), max(1, int(ih * s)))
        img = self._chart_img.resize(size, Image.LANCZOS)
        self._img_ref = ImageTk.PhotoImage(img)
        self._last_draw = size
        self.canvas.delete("all")
        self.canvas.create_image(cw / 2 + 8, ch / 2 + 8, image=self._img_ref)

    def _show_digits(self):
        if not self.result:
            return
        idx = self.cmb_ds.current()
        if idx < 0 or idx >= len(self.result.results):
            return
        r = self.result.results[idx]
        self.tv_digits.delete(*self.tv_digits.get_children())
        for row in r["rows"]:
            self.tv_digits.insert("", "end", values=(
                row["digit"], row["observed"], f"{row['p_observed']:.2%}",
                f"{row['p_benford']:.2%}", f"{row['expected']:.1f}",
                f"{row['diff']:+.2%}", f"{row['z']:+.2f}",
                f"{row['excess_ratio']:.3f}"))

    def _fill_details(self):
        if not self.result:
            return
        kw = self.var_filter.get().strip()
        rows = self.result.rows
        if kw:
            rows = [r for r in rows if kw in r["item"] or kw in r["report"]]
        self._detail_rows = rows
        self.tv_rows.delete(*self.tv_rows.get_children())
        for i, r in enumerate(rows[:5000]):
            self.tv_rows.insert("", "end", values=(
                r["report"], self._st_name(r["statement"]), r["item"],
                r["v1"], r["v2"], r["line"][:120]))
        self.lbl_cnt.configure(text=f"共 {len(rows)} 行"
                                    + ("（仅显示前 5000 行）" if len(rows) > 5000 else ""))

    @staticmethod
    def _st_name(code):
        return {"BS": "资产负债表", "IS": "利润表", "CF": "现金流量表"}.get(code, code)

    # ---------------- 导出 ----------------
    def _workdir(self):
        if not getattr(self, "company", None):
            return None
        return company_dir(self.company["code"], self.company["name"])

    def open_workdir(self):
        d = self._workdir()
        if not d or not d.exists():
            messagebox.showinfo("提示", "还没有工作目录，请先运行一次分析")
            return
        try:
            os.startfile(str(d))  # noqa: S606
        except Exception:  # noqa: BLE001
            subprocess.Popen(["explorer", str(d)])

    def export_chart(self):
        if self._chart_img is None:
            messagebox.showinfo("提示", "还没有图")
            return
        p = filedialog.asksaveasfilename(defaultextension=".png",
                                         filetypes=[("PNG", "*.png")],
                                         initialfile="benford_first_digit.png")
        if p:
            self._chart_img.save(p)
            self._append_log(f"[导出] {p}")

    def _need_result(self):
        if not self.result:
            messagebox.showinfo("提示", "请先运行一次分析")
            return False
        return True

    def export_csv(self):
        if not self._need_result():
            return
        from . import stats
        p = filedialog.asksaveasfilename(defaultextension=".csv",
                                         filetypes=[("CSV", "*.csv")],
                                         initialfile="benford_first_digit.csv")
        if p:
            stats.write_csv(p, self.result.results)
            self._append_log(f"[导出] {p}")

    def export_rows(self):
        if not self._need_result():
            return
        from . import stats
        p = filedialog.asksaveasfilename(defaultextension=".csv",
                                         filetypes=[("CSV", "*.csv")],
                                         initialfile="amounts_raw.csv")
        if p:
            stats.write_rows_csv(p, self.result.rows)
            self._append_log(f"[导出] {p}")

    def export_all(self):
        if not self._need_result():
            return
        d = filedialog.askdirectory(title="选择导出目录")
        if not d:
            return
        import shutil
        src = pathlib.Path(self.result.paths["results"])
        n = 0
        for f in src.glob("*"):
            if f.is_file():
                shutil.copy2(f, pathlib.Path(d) / f.name)
                n += 1
        self._append_log(f"[导出] {n} 个文件 → {d}")


def main():
    _log("创建 App …")
    app = App()
    if len(sys.argv) > 1:
        app.var_kw.set(sys.argv[1])
        app.after(300, app.do_search)
    _log("进入 mainloop")
    try:
        app.mainloop()
    finally:
        _log("mainloop 退出")


if __name__ == "__main__":
    main()
