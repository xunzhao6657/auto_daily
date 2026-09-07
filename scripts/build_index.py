# -*- coding: utf-8 -*-
"""扫描 reports/ 目录，生成网站首页 index.html"""
import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#c9353f">
<link rel="manifest" href="site.webmanifest">
<link rel="icon" href="assets/icon.svg">
<title>A股每日大盘报告</title>
<style>
:root { --bg:#f7f8fa; --card:#fff; --text:#1f2329; --muted:#8a919f; --accent:#c9353f; --border:#e8eaee; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"PingFang SC","Microsoft YaHei",-apple-system,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }
.wrap { max-width:720px; margin:0 auto; padding:32px 20px 60px; }
header { text-align:center; padding:28px 0 20px; }
header h1 { font-size:26px; letter-spacing:1px; }
header h1 .accent { color:var(--accent); }
header p { color:var(--muted); font-size:14px; margin-top:6px; }
.stat-bar { display:flex; gap:12px; justify-content:center; margin:18px 0 8px; flex-wrap:wrap; }
.stat { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px 18px; text-align:center; min-width:110px; }
.stat .num { font-size:22px; font-weight:600; }
.stat .lbl { font-size:12px; color:var(--muted); }
section.month { margin-top:26px; }
section.month h2 { font-size:15px; color:var(--muted); font-weight:600; padding-bottom:8px; border-bottom:1px solid var(--border); }
.day { display:flex; justify-content:space-between; align-items:center; padding:12px 4px; border-bottom:1px dashed var(--border); flex-wrap:wrap; gap:6px; }
.date { font-size:15px; font-weight:500; }
.new { font-size:11px; color:#fff; background:var(--accent); border-radius:4px; padding:1px 6px; vertical-align:2px; }
.chip { display:inline-block; font-size:13px; color:#3347b0; background:#eef1fd; border-radius:6px; padding:3px 12px; text-decoration:none; margin-left:8px; }
.chip:hover { background:#dfe5fa; }
.go-latest { display:block; text-align:center; margin:20px auto 0; width:fit-content; background:var(--accent); color:#fff; border-radius:8px; padding:10px 28px; text-decoration:none; font-size:15px; font-weight:500; }
.go-latest:hover { opacity:.9; }
footer { text-align:center; color:var(--muted); font-size:12px; margin-top:40px; }
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>A股<span class="accent">每日大盘</span>报告</h1>
<p>盘前分析 · 收盘总结 &nbsp;|&nbsp; 每日更新</p>
</header>
<div class="stat-bar">
<div class="stat"><div class="num">{TOTAL_DAYS}</div><div class="lbl">已覆盖交易日</div></div>
<div class="stat"><div class="num">{TOTAL_REPORTS}</div><div class="lbl">报告总数</div></div>
<div class="stat"><div class="num">{LATEST_MD}</div><div class="lbl">最新一期</div></div>
</div>
<a class="go-latest" href="{LATEST}">查看最新一期报告 →</a>
{BODY}
<footer>本报告由 AI 自动生成，仅供个人研究参考，不构成投资建议</footer>
</div>
</body>
</html>"""

WEEKDAYS = "一二三四五六日"


def build():
    if not REPORTS.exists():
        (ROOT / "index.html").write_text(PAGE.replace("{TOTAL_DAYS}", "0")
                                         .replace("{TOTAL_REPORTS}", "0")
                                         .replace("{LATEST_MD}", "—")
                                         .replace("{LATEST}", "#")
                                         .replace("{BODY}", ""), encoding="utf-8")
        return

    pat = re.compile(r"^(\d{4})(\d{2})(\d{2})-(am|pm)\.html$")
    days = {}
    for f in REPORTS.glob("*.html"):
        m = pat.match(f.name)
        if m:
            days.setdefault(m.group(1) + m.group(2) + m.group(3), {})[m.group(4)] = f.name
    if not days:
        build()
        return

    keys = sorted(days.keys(), reverse=True)
    latest = keys[0]
    groups = {}
    for k in keys:
        groups.setdefault(k[:6], []).append(k)

    rows = []
    for ym in sorted(groups.keys(), reverse=True):
        rows.append('<section class="month">')
        rows.append(f'<h2>{ym[:4]}年{int(ym[4:])}月</h2><div class="day-list">')
        for k in groups[ym]:
            d = dt.date(int(k[:4]), int(k[4:6]), int(k[6:8]))
            flag = ' <span class="new">最新</span>' if k == latest else ""
            chips = ""
            if "am" in days[k]:
                chips += f'<a class="chip" href="reports/{days[k]["am"]}">盘前分析</a>'
            if "pm" in days[k]:
                chips += f'<a class="chip" href="reports/{days[k]["pm"]}">收盘总结</a>'
            rows.append(f'<div class="day"><span class="date">{d.month}月{d.day}日 · 周{WEEKDAYS[d.weekday()]}{flag}</span>'
                       f'<span class="chips">{chips}</span></div>')
        rows.append("</div></section>")

    latest_file = days[latest].get("pm") or days[latest].get("am")
    total = sum(len(v) for v in days.values())
    html = (PAGE.replace("{TOTAL_DAYS}", str(len(days)))
            .replace("{TOTAL_REPORTS}", str(total))
            .replace("{LATEST_MD}", f"{int(latest[4:6])}月{int(latest[6:])}日")
            .replace("{LATEST}", f"reports/{latest_file}")
            .replace("{BODY}", "\n".join(rows)))
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    return len(days), total


if __name__ == "__main__":
    print(build())
