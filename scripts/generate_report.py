# -*- coding: utf-8 -*-
"""A 股每日报告生成器（云端版）

数据源：东方财富公开接口（免费，无需 Key）
生成：调 DeepSeek API 产出盘前分析 / 收盘总结 Markdown，并渲染为 HTML
用法：
  python scripts/generate_report.py --type am          # 盘前分析
  python scripts/generate_report.py --type pm          # 收盘总结
  python scripts/generate_report.py --type am --dry-run  # 无 Key，仅输出数据底稿
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

EM_UT = "fa5fd1943c7b386f172d6893dbfba10b"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
TIMEOUT = 10
# push2 主域名不稳定，优先用 push2delay（延迟行情，日报场景足够）
EM_HOSTS = ["push2delay.eastmoney.com", "push2.eastmoney.com"]


def _get(path, params, hosts=None, rounds=2):
    """多域名 + 重试的东财接口请求"""
    for i in range(rounds):
        for h in (hosts or EM_HOSTS):
            try:
                r = requests.get(f"https://{h}{path}", params=params,
                                 headers=HEADERS, timeout=TIMEOUT)
                if r.status_code == 200 and r.text.startswith("{"):
                    return r.json()
            except Exception:
                pass
    print(f"[warn] 接口失败 {path}", file=sys.stderr)
    return None


def pct(x):
    if x is None:
        return "—"
    return f"{x:+.2f}%"


def fmt_num(x, unit=""):
    if x is None:
        return "—"
    return f"{x:,.2f}{unit}"


# ---------------- 数据抓取 ----------------

def fetch_index_quotes():
    """A 股三大指数 + 美股 + 港股 最新行情"""
    groups = [
        ("A股指数", "1.000001,0.399001,0.399006"),
        ("美股指数", "100.DJIA,100.SPX,100.NDX"),
        ("港股指数", "100.HSI,100.HSCEI,124.HSTECH"),
    ]
    out = {}
    for name, secids in groups:
        j = _get("/api/qt/ulist.np/get", {
            "secids": secids, "fields": "f2,f3,f4,f5,f6,f12,f14,f17,f18",
            "fltt": "2", "invt": "2", "ut": EM_UT,
        })
        rows = []
        if j and j.get("data"):
            for d in j["data"]["diff"]:
                rows.append({
                    "名称": d.get("f14"), "代码": d.get("f12"),
                    "最新价": d.get("f2"), "涨跌幅": d.get("f3"),
                    "开盘": d.get("f17"), "昨收": d.get("f18"),
                    "成交额(亿)": round(d["f6"] / 1e8, 1) if isinstance(d.get("f6"), (int, float)) else None,
                })
        out[name] = rows
    return out


def fetch_breadth():
    """全市场涨跌家数（沪+深）"""
    j = _get("/api/qt/ulist.np/get", {
        "secids": "1.000001,0.399001", "fields": "f104,f105,f106",
        "fltt": "2", "invt": "2", "ut": EM_UT,
    })
    if not (j and j.get("data")):
        return None
    up = down = flat = 0
    for d in j["data"]["diff"]:
        up += d.get("f104") or 0
        down += d.get("f105") or 0
        flat += d.get("f106") or 0
    if up + down + flat == 0:
        return None
    return {"涨": up, "跌": down, "平": flat}


def fetch_sectors():
    """行业板块当日涨跌榜"""
    j = _get("/api/qt/clist/get", {
        "pn": 1, "pz": 90, "po": 1, "fid": "f3", "fs": "m:90+t:2",
        "fields": "f3,f12,f14", "fltt": "2", "invt": "2", "ut": EM_UT,
    })
    if not (j and j.get("data") and j["data"].get("diff")):
        return None
    diff = j["data"]["diff"]
    if isinstance(diff, dict):  # push2delay 返回字典形式
        diff = [diff[k] for k in sorted(diff.keys(), key=int)]
    rows = [{"板块": d["f14"], "涨跌幅": d["f3"]} for d in diff if isinstance(d, dict) and d.get("f14")]
    return {"领涨": rows[:5], "领跌": sorted(rows, key=lambda x: x["涨跌幅"])[:5]}


def fetch_main_flow():
    """沪深两市主力资金净流入（最近收盘口径，沪+深合计，亿元）"""
    j = _get("/api/qt/ulist.np/get", {
        "secids": "1.000001,0.399001", "fields": "f12,f14,f62",
        "fltt": "2", "invt": "2", "ut": EM_UT,
    })
    if not (j and j.get("data")):
        return None
    total = 0.0
    got = False
    for d in j["data"]["diff"]:
        if isinstance(d.get("f62"), (int, float)):
            total += d["f62"]
            got = True
    return round(total / 1e8, 1) if got else None


def fetch_margin():
    """两融余额（最近 5 日）"""
    try:
        r = requests.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={
            "reportName": "RPTA_RZRQ_LSHJ", "columns": "ALL", "source": "WEB",
            "sortColumns": "dim_date", "sortTypes": "-1",
            "pageNumber": 1, "pageSize": 5,
        }, headers=HEADERS, timeout=TIMEOUT)
        j = r.json()
    except Exception:
        return None
    if not (j and j.get("result") and j["result"].get("data")):
        return None
    rows = []
    for d in j["result"]["data"]:
        ye = d.get("RZRQYE") or d.get("RZYE")
        if ye:
            rows.append({"日期": str(d.get("DIM_DATE", ""))[:10], "两融余额(亿)": round(float(ye) / 1e8, 1)})
    return rows or None


# ---------------- 数据底稿 ----------------

def build_digest(data, rtype, now):
    lines = [f"# 数据底稿（生成时间 {now:%Y-%m-%d %H:%M}，报告类型：{'盘前分析' if rtype == 'am' else '收盘总结'}）", ""]

    for gname, rows in data["指数"].items():
        if not rows:
            lines += [f"## {gname}", "（未获取）", ""]
            continue
        lines += [f"## {gname}（最新收盘口径）",
                  "| 名称 | 最新价 | 涨跌幅 | 成交额(亿) |", "|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['名称']} | {fmt_num(r['最新价'])} | {pct(r['涨跌幅'])} | {r['成交额(亿)'] if r['成交额(亿)'] is not None else '—'} |")
        lines.append("")

    b = data.get("涨跌家数")
    lines += ["## 全市场宽度", f"- 涨 {b['涨']} / 跌 {b['跌']} / 平 {b['平']}" if b else "- （未获取）", ""]

    s = data.get("行业板块")
    if s:
        lines += ["## 行业板块涨跌榜（当日）",
                  "| 领涨板块 | 涨跌幅 |", "|---|---|"]
        lines += [f"| {x['板块']} | {pct(x['涨跌幅'])} |" for x in s["领涨"]]
        lines += ["", "| 领跌板块 | 涨跌幅 |", "|---|---|"]
        lines += [f"| {x['板块']} | {pct(x['涨跌幅'])} |" for x in s["领跌"]]
        lines.append("")

    m = data.get("主力资金")
    if m is not None:
        lines += ["## 沪深两市主力资金净流入（亿元，最近收盘口径）", f"合计 **{m:+.1f} 亿**", ""]

    mg = data.get("两融")
    if mg:
        lines += ["## 两融余额（亿元，最近5日）", "| 日期 | 两融余额 |", "|---|---|"]
        lines += [f"| {x['日期']} | {x['两融余额(亿)']:,}" for x in mg]
        lines.append("")

    lines += ["## 数据源说明",
              "- 以上数据来自东方财富公开接口，为最近收盘口径；盘前报告使用上一交易日数据。",
              "- 中金研报观点、Wind EDB 宏观数据、南向资金明细等不在本数据源覆盖范围内，报告中不得虚构。"]
    return "\n".join(lines)


# ---------------- AI 生成 ----------------

SYSTEM_PROMPT = """你是一位买方视角的 A 股策略分析师，为个人投资者撰写每日盘面报告。
写作要求：
1. 只使用「数据底稿」中提供的数据，严禁编造或臆测任何数字；数据未覆盖的项目直接标注「（未获取）」，不估算。
2. 结论先行、证据链清晰；多用表格，少用长段落。
3. 预测一律给「中心值 + 窄区间」，并给情景概率（乐观/中性/悲观，合计100%）。
4. 风格克制、批判性，明确写出最可能证错你判断的因素。
5. 篇幅控制在 1500 字以内，Markdown 格式。"""

AM_PROMPT = """请基于以下数据底稿，生成今日 A 股盘前分析报告，结构如下：

# 每日盘前简报：{date}

## 〇、TL;DR 决策卡（表格：今日方向/置信度/中心涨跌幅、关注板块Top3、规避板块、最大风险、开盘策略）
## 一、上一交易日 A 股复盘（指数表现、宽度与量能、主力资金、行业板块）
## 二、隔夜与最新外围（美股/港股，以及对今日 A 股的传导逻辑）
## 三、今日走势预测（方向判断+证据链、多维预测表：点位/量能/风格/板块，一律中心值+窄区间）
## 四、开盘决策树与仓位纪律（高开/平开/低开三种情形的应对）
## 五、风险提示（3-5 条，第一条必须是最可能破位/证错的情形）

数据底稿：
{digest}"""

PM_PROMPT = """请基于以下数据底稿，生成今日 A 股收盘总结报告，结构如下：

# 今日 A 股收盘总结：{date}

## 〇、TL;DR 决策卡（表格：今日实际方向、量能与宽度、最强/最弱板块、明日关注点）
## 一、今日盘面复盘（指数与走势、宽度与量能、主力资金、行业板块表现）
## 二、外围市场联动（美股/港股表现与 A 股的背离或共振）
## 三、今日盘面定性（一段话：量价关系、风格特征、强弱判断）
## 四、明日展望（方向倾向+置信度、关注板块Top3、风险提示3条）

数据底稿：
{digest}"""


def call_deepseek(system, user, key):
    r = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        },
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------- 渲染 HTML ----------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#c9353f">
<link rel="manifest" href="../site.webmanifest">
<link rel="icon" href="../assets/icon.svg">
<title>{title}</title>
<style>
body {{ font-family: "PingFang SC","Microsoft YaHei",-apple-system,sans-serif;
  background:#f7f8fa; color:#1f2329; line-height:1.75; margin:0; }}
.wrap {{ max-width:820px; margin:0 auto; padding:24px 18px 60px; }}
.top {{ text-align:center; padding:16px 0 4px; }}
.top h1 {{ font-size:20px; margin:0 0 4px; }}
.top .meta {{ color:#8a919f; font-size:12px; }}
.back {{ display:inline-block; margin:0 0 12px; color:#3347b0; text-decoration:none; font-size:14px; }}
h2 {{ font-size:17px; margin:28px 0 10px; padding-bottom:6px; border-bottom:2px solid #c9353f22; }}
h3 {{ font-size:15px; margin:18px 0 8px; }}
table {{ border-collapse:collapse; width:100%; margin:10px 0; font-size:13.5px; }}
th,td {{ border:1px solid #e8eaee; padding:6px 10px; text-align:left; }}
th {{ background:#f1f2f5; font-weight:500; }}
blockquote {{ margin:10px 0; padding:8px 14px; border-left:3px solid #c9353f;
  background:#fdf3f3; color:#6b5a5a; font-size:13px; }}
code {{ background:#f1f2f5; padding:1px 5px; border-radius:4px; font-size:12.5px; }}
strong {{ color:#c9353f; }}
a {{ color:#3347b0; }}
hr {{ border:none; border-top:1px solid #e8eaee; margin:22px 0; }}
footer {{ text-align:center; color:#8a919f; font-size:12px; margin-top:40px; }}
</style>
</head>
<body>
<div class="top"><h1>{title}</h1><div class="meta">{date} · AI 自动生成</div></div>
<div class="wrap">
<a class="back" href="../index.html">← 返回报告列表</a>
{body}
<footer>数据来源：东方财富公开接口 · AI 生成，仅供个人研究参考，不构成投资建议</footer>
</div>
</body>
</html>"""


def md_to_html(md_text):
    import markdown
    return markdown.markdown(md_text, extensions=["tables"])


def save_report(rtype, md_text, now):
    REPORTS.mkdir(exist_ok=True)
    key = f"{now:%Y%m%d}-{rtype}"
    label = "盘前分析" if rtype == "am" else "收盘总结"
    (REPORTS / f"{key}.md").write_text(md_text, encoding="utf-8")
    body = md_to_html(md_text)
    title = f"{now:%Y年%m月%d日}A股{label}"
    (REPORTS / f"{key}.html").write_text(
        HTML_TEMPLATE.format(title=title, date=f"{now:%Y-%m-%d}", body=body),
        encoding="utf-8")
    return key


# ---------------- 主流程 ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["am", "pm"], default="am")
    ap.add_argument("--dry-run", action="store_true", help="不调 AI，直接用数据底稿生成报告")
    args = ap.parse_args()

    now = dt.datetime.now()
    if now.weekday() >= 5:
        print("今天是周末，跳过生成。")
        return

    print("抓取行情数据 ...")
    data = {
        "指数": fetch_index_quotes(),
        "涨跌家数": fetch_breadth(),
        "行业板块": fetch_sectors(),
        "主力资金": fetch_main_flow(),
        "两融": fetch_margin(),
    }

    # 休市判断：指数全部无涨跌且无成交 → 法定节假日
    a_idx = data["指数"].get("A股指数") or []
    if a_idx and all((r["涨跌幅"] in (0, None)) and not r["成交额(亿)"] for r in a_idx):
        print("今日休市（无成交数据），跳过生成。")
        return

    digest = build_digest(data, args.type, now)

    if args.dry_run or not os.environ.get("DEEPSEEK_API_KEY"):
        print("dry-run 模式：直接使用数据底稿作为报告")
        report_md = digest
    else:
        tpl = AM_PROMPT if args.type == "am" else PM_PROMPT
        user = tpl.format(date=f"{now:%Y-%m-%d}（{'周' + '一二三四五六日'[now.weekday()]}）", digest=digest)
        print("调用 DeepSeek 生成报告 ...")
        report_md = call_deepseek(SYSTEM_PROMPT, user, os.environ["DEEPSEEK_API_KEY"])

    key = save_report(args.type, report_md, now)
    print(f"报告已生成: reports/{key}.html")

    import build_index
    build_index.build()
    print("index.html 已更新")


if __name__ == "__main__":
    main()
