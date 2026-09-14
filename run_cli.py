# -*- coding: utf-8 -*-
"""命令行版（无界面），便于批处理 / 定时任务。

示例：
    python run_cli.py 601799 --annual --last 8
    python run_cli.py 宁德时代 --annual --from-year 2018
    python run_cli.py 300750 --kinds annual,semi --out .\\out\\catl
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from echeck import cninfo, pipeline  # noqa: E402


def fix_console_encoding():
    """控制台/管道编码兜底。

    Windows 中文控制台默认 GBK，打印「χ²」这类字符会抛 UnicodeEncodeError；
    输出重定向到文件/管道时同样会中招（曾导致打包后的 exe 跑完分析最后一步崩溃）。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")          # 真控制台：保留原生行为
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")  # 重定向：给 UTF-8
        except Exception:  # noqa: BLE001
            pass


def parse_args():
    ap = argparse.ArgumentParser(description="上市公司财报首位数字 Benford 检验")
    ap.add_argument("company", help="股票代码或公司简称/拼音")
    ap.add_argument("--kinds", default="annual",
                    help="报告类型，逗号分隔：annual,semi,q1,q3（默认 annual）")
    ap.add_argument("--from-year", type=int, default=None, help="起始年份")
    ap.add_argument("--to-year", type=int, default=None, help="结束年份")
    ap.add_argument("--last", type=int, default=None, help="只取最近 N 期")
    ap.add_argument("--out", default=None, help="输出目录（默认 data/<代码>_<简称>）")
    ap.add_argument("--include-summary", action="store_true", help="包含报告摘要")
    ap.add_argument("--list-only", action="store_true", help="只列出报告，不下载分析")
    return ap.parse_args()


def main():
    fix_console_encoding()
    args = parse_args()
    comps = cninfo.search_companies(args.company, 10)
    if not comps:
        print(f"未找到与 {args.company!r} 匹配的上市公司。")
        print("提示：巨潮资讯网只收录上市公司披露文件；非上市公司（如字节跳动、华为）"
              "没有公开定期报告，无法做财报 Benford 分析。")
        print("      可改用 6 位股票代码（如 601799）或上市公司简称（如 星宇股份）。")
        return 2
    exact = next((c for c in comps if c["code"] == args.company), None)
    comp = exact or comps[0]
    if not cninfo.is_supported(comp):
        print(f"不支持：{comp['name']}（{comp['code']}）{cninfo.market_note(comp)}")
        others = [c for c in comps if cninfo.is_supported(c)]
        if others:
            print("可改为：" + "，".join(f"{c['code']} {c['name']}" for c in others[:5]))
        return 2
    print(f"公司：{comp['name']}（{comp['code']}）orgId={comp['org_id']}")

    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    reps = cninfo.list_reports(comp["code"], comp["org_id"], kinds)
    reps = [r for r in reps if not r["is_hk"] and (args.include_summary or not r["is_summary"])]
    if args.from_year:
        reps = [r for r in reps if r["period"][:4].isdigit()
                and int(r["period"][:4]) >= args.from_year]
    if args.to_year:
        reps = [r for r in reps if r["period"][:4].isdigit()
                and int(r["period"][:4]) <= args.to_year]
    reps.sort(key=lambda r: r["period"])
    if args.last:
        reps = reps[-args.last:]
    print(f"待处理报告 {len(reps)} 期：{', '.join(r['period'] for r in reps)}")
    if args.list_only:
        for r in reps:
            print(f"  {r['period']:<9} {r['date']}  {r['title']}  {r['url']}")
        return 0
    if not reps:
        print("没有符合条件的报告")
        return 1

    state = {"last": ""}

    def progress(step, done, total, msg):
        line = f"[{step}] {done}/{total} {msg}"
        if line != state["last"]:
            print(line, flush=True)
            state["last"] = line

    try:
        res = pipeline.run_analysis(comp, reps, progress=progress, base_dir=args.out)
    except pipeline.PipelineError as e:
        print("\n[无法完成分析]")
        print(e)
        return 1
    except pipeline.Cancelled:
        print("\n[已取消]")
        return 1
    print("\n" + "=" * 66)
    main_r = res.main
    print(f"{comp['name']}（{comp['code']}）  数据行 {len(res.rows)}  样本 n={main_r['n']}")
    print(f"χ²={main_r['chi2']:.2f}  p={main_r['p_value']:.4f}  MAD={main_r['mad']:.4f}  "
          f"KS D={main_r['ks_d']:.4f}  最大|z|={main_r['max_z']:.2f}")
    print(f"结论：{main_r['verdict']}")
    print("─" * 66)
    print("首位  观测数   实际占比   Benford   偏差      z")
    for r in main_r["rows"]:
        print(f"  {r['digit']}  {r['observed']:>6}   {r['p_observed']:>7.2%}   "
              f"{r['p_benford']:>7.2%}  {r['diff']:>+7.2%}  {r['z']:>+6.2f}")
    print("─" * 66)
    print(f"各子样本：")
    for r in res.results:
        mc = f"{r['mc_p']:.4f}" if r["mc_p"] is not None else "-"
        print(f"  {r['name']:<28} n={r['n']:<6} p={r['p_value']:.4f} "
              f"MCp={mc:<8} MAD={r['mad']:.4f}  {r['verdict']}")
    v = res.validation
    print(f"校验：会计恒等式 {v['identity_ok']}/{v['identity_total']} 期；"
          f"跨期衔接 {v['chain_matched']}/{v['chain_total']} 项")
    print(f"结果目录：{res.paths['results']}")
    for w in res.warnings:
        print(f"[警告] {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
