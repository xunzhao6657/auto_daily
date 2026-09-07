# -*- coding: utf-8 -*-
"""A 股每日大盘报告 · Streamlit Cloud 版

访问即取数：打开页面实时抓取东方财富公开接口，展示全量行情数据；
配置 DEEPSEEK_API_KEY 后可一键生成 AI 分析报告。
"""
import datetime as dt
import os
import re
import sys
from pathlib import Path

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT / "scripts"))
import generate_report as gr  # noqa: E402

st.set_page_config(
    page_title="A股每日大盘报告",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 中国股市惯例：涨红跌绿
st.markdown("""
<style>
.metric-card{background:#fff;border:1px solid #e8eaee;border-radius:10px;
  padding:14px 18px;text-align:center;}
.metric-card .name{font-size:13px;color:#6b7280;margin-bottom:4px;}
.metric-card .price{font-size:24px;font-weight:700;}
.metric-card .chg{font-size:13px;margin-top:2px;}
.up{color:#c9353f;} .down{color:#0a8a4a;} .flat{color:#6b7280;}
section[data-testid="stSidebar"]{border-right:1px solid #e8eaee;}
.stTabs [data-baseweb="tab-list"]{gap:8px;}
/* 历史报告隔离样式（避免污染整站） */
.rpt{font-size:14px;line-height:1.7;}
.rpt h1{font-size:19px;margin:18px 0 8px;}
.rpt h2{font-size:16px;margin:20px 0 8px;padding-bottom:4px;border-bottom:1px solid #eee;}
.rpt h3{font-size:14px;margin:14px 0 6px;}
.rpt table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px;}
.rpt th,.rpt td{border:1px solid #e8eaee;padding:4px 8px;text-align:left;}
.rpt th{background:#f1f2f5;font-weight:500;}
.rpt blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid #c9353f;
  background:#fdf3f3;color:#6b5a5a;font-size:13px;}
.rpt code{background:#f1f2f5;padding:1px 4px;border-radius:4px;font-size:12px;}
.rpt strong{color:#c9353f;}
.rpt hr{border:none;border-top:1px solid #e8eaee;margin:16px 0;}
</style>
""", unsafe_allow_html=True)

# 可选：若在 Secrets 里设置了 APP_PASSWORD，则整站要求密码（私密模式）
_APP_PW = None
try:
    _APP_PW = st.secrets.get("APP_PASSWORD")
except Exception:
    pass
if _APP_PW and not st.session_state.get("_pw_ok"):
    st.markdown("### 🔒 本网站已设为私密，请输入访问密码")
    pw = st.text_input("访问密码", type="password", key="_pw_in")
    if pw:
        if pw == _APP_PW:
            st.session_state["_pw_ok"] = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()


def _cls(v):
    if v is None:
        return "flat", "—"
    if v > 0:
        return "up", f"+{v:.2f}%"
    if v < 0:
        return "down", f"{v:.2f}%"
    return "flat", "0.00%"


def _card(name, price, chg):
    c, txt = _cls(chg)
    return (f'<div class="metric-card"><div class="name">{name}</div>'
            f'<div class="price">{price:,.2f}</div>'
            f'<div class="chg {c}">{txt}</div></div>')


@st.cache_data(ttl=300, show_spinner="正在抓取实时行情…")
def fetch_all():
    return {
        "指数": gr.fetch_index_quotes(),
        "涨跌家数": gr.fetch_breadth(),
        "行业板块": gr.fetch_sectors(),
        "主力资金": gr.fetch_main_flow(),
        "两融": gr.fetch_margin(),
    }


@st.cache_data(ttl=3600, show_spinner="AI 正在撰写报告…")
def ai_report(rtype: str, day: str, digest: str, key: str) -> str:
    """提示词来自 skills/ashare-daily-report（与本地 dsh 链路 v4.2 同源），
    自动注入昨日晨报（供多维评判）与修正建议库（自修正闭环）。"""
    now = dt.datetime.now()
    user = gr.build_user_prompt(rtype, now, digest)
    return gr.call_deepseek(gr.load_system_prompt(), user, key)


def get_api_key():
    """Key 优先级：网页会话输入 > 服务端 Secrets > 环境变量。"""
    if st.session_state.get("_dk"):
        return st.session_state["_dk"]
    try:
        if "DEEPSEEK_API_KEY" in st.secrets:
            return st.secrets["DEEPSEEK_API_KEY"]
    except Exception:
        pass
    return os.environ.get("DEEPSEEK_API_KEY", "")


def check_key(k):
    """通过 DeepSeek /models 接口验证 Key 是否可用。"""
    if not k.strip():
        return False, "未输入 Key"
    try:
        r = requests.get("https://api.deepseek.com/models",
                         headers={"Authorization": f"Bearer {k.strip()}"}, timeout=20)
        if r.status_code == 200:
            return True, "连接成功 ✓"
        if r.status_code == 401:
            return False, "无效的 Key（401）"
        return False, f"服务返回状态码 {r.status_code}"
    except Exception as e:
        return False, f"请求异常：{e}"


def _body_of(html_text):
    """抽取全量 HTML 文档的 <body> 内部内容，其余（<head>/<style>）丢弃以免污染站内样式。"""
    m = re.search(r"<body[^>]*>(.*)</body>", html_text, re.S)
    return m.group(1) if m else html_text


def render_report(f):
    """用 st.html 渲染一份历史报告 HTML（body 内容 + 隔离样式）。"""
    html_text = f.read_text(encoding="utf-8")
    st.html(f'<div class="rpt">{_body_of(html_text)}</div>')


def list_reports():
    if not REPORTS.exists():
        return []
    items = []
    for f in sorted(REPORTS.glob("*.html"), reverse=True):
        stem = f.stem  # e.g. 20260907-am
        if "-" not in stem:
            continue
        d, t = stem.rsplit("-", 1)
        if len(d) == 8 and d.isdigit() and t in ("am", "pm"):
            items.append((f, d, t))
    return items


# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.title("📈 A股日报站")
    st.caption("数据：东方财富公开接口 · 访问即实时抓取")
    if st.button("🔄 立即刷新数据", use_container_width=True):
        fetch_all.clear()
        st.rerun()
    st.divider()

    with st.expander("🔑 API Key 配置", expanded=False):
        cur = get_api_key()
        st.caption("状态：" + ("✅ 已配置可用 Key" if cur else "未配置"))
        val = st.text_input(
            "粘贴 DeepSeek Key（仅存于本次会话内存，不写盘、不进仓库）",
            type="password", key="_key_input")
        if st.button("测试连接", use_container_width=True):
            ok, msg = check_key(val)
            st.session_state["_key_test"] = (ok, msg)
            if ok and val.strip():
                st.session_state["_dk"] = val.strip()
        if "_key_test" in st.session_state:
            ok, msg = st.session_state["_key_test"]
            (st.success if ok else st.error)(msg)
            if ok:
                st.caption("本会话已启用该 Key（刷新页面即清除）。")
        st.caption("也可用服务端 Secrets 配置 `DEEPSEEK_API_KEY`，或设置 "
                   "`APP_PASSWORD` 将整站设为私密。")

data = fetch_all()
now = dt.datetime.now()

# ---------------- 页头 ----------------
st.title(f"A股每日大盘 · {now:%Y年%m月%d日}")
weekday = "周" + "一二三四五六日"[now.weekday()]
st.caption(f"今天是 {weekday} · 数据缓存 5 分钟，刷新页面即更新最新行情")

tab_live, tab_ai, tab_hist = st.tabs(["📊 实时行情", "🤖 AI 分析报告", "🗂 历史报告"])

# ---------------- Tab 1: 实时行情 ----------------
with tab_live:
    idx = data["指数"]

    st.subheader("A股三大指数")
    cols = st.columns(3)
    for col, r in zip(cols, (idx.get("A股指数") or [])[:3]):
        with col:
            if r and isinstance(r.get("最新价"), (int, float)):
                st.markdown(_card(r["名称"], r["最新价"], r["涨跌幅"]),
                            unsafe_allow_html=True)
                if r.get("成交额(亿)") is not None:
                    st.caption(f"成交额 {r['成交额(亿)']:.0f} 亿")
            else:
                st.info("未获取")

    left, right = st.columns(2)
    with left:
        st.subheader("隔夜外围 · 美股")
        rows = idx.get("美股指数") or []
        if rows:
            st.markdown(
                "<table><tr><th>指数</th><th>最新</th><th>涨跌幅</th></tr>" +
                "".join(f'<tr><td>{r["名称"]}</td><td>{r["最新价"]:,.2f}</td>'
                        f'<td class="{_cls(r["涨跌幅"])[0]}">{_cls(r["涨跌幅"])[1]}</td></tr>'
                        for r in rows if isinstance(r.get("最新价"), (int, float))) +
                "</table>", unsafe_allow_html=True)
        else:
            st.info("未获取")

        b = data.get("涨跌家数")
        if b:
            st.subheader("全市场宽度")
            t = b["涨"] + b["跌"] + b["平"]
            st.markdown(
                f'<div class="metric-card">'
                f'<span class="up">▲ 涨 {b["涨"]}</span> · '
                f'<span class="down">▼ 跌 {b["跌"]}</span> · '
                f'<span class="flat">— 平 {b["平"]}</span> '
                f'（共 {t} 家）</div>', unsafe_allow_html=True)

        m = data.get("主力资金")
        if m is not None:
            st.subheader("沪深主力资金净流入")
            c = "up" if m > 0 else "down" if m < 0 else "flat"
            st.markdown(f'<div class="metric-card"><span class="{c}">'
                        f'{m:+.1f} 亿元</span>（最近收盘口径）</div>',
                        unsafe_allow_html=True)
    with right:
        st.subheader("港股")
        rows = idx.get("港股指数") or []
        if rows:
            st.markdown(
                "<table><tr><th>指数</th><th>最新</th><th>涨跌幅</th></tr>" +
                "".join(f'<tr><td>{r["名称"]}</td><td>{r["最新价"]:,.2f}</td>'
                        f'<td class="{_cls(r["涨跌幅"])[0]}">{_cls(r["涨跌幅"])[1]}</td></tr>'
                        for r in rows if isinstance(r.get("最新价"), (int, float))) +
                "</table>", unsafe_allow_html=True)
        else:
            st.info("未获取")

        mg = data.get("两融")
        if mg:
            st.subheader("两融余额（亿元）")
            st.markdown(
                "<table><tr><th>日期</th><th>余额</th></tr>" +
                "".join(f'<tr><td>{x["日期"]}</td><td>{x["两融余额(亿)"]:,}</td></tr>'
                       for x in mg) + "</table>", unsafe_allow_html=True)

    s = data.get("行业板块")
    if s:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("今日领涨板块")
            st.markdown(
                "<table><tr><th>板块</th><th>涨跌幅</th></tr>" +
                "".join(f'<tr><td>{x["板块"]}</td><td class="{_cls(x["涨跌幅"])[0]}">'
                        f'{_cls(x["涨跌幅"])[1]}</td></tr>' for x in s["领涨"]) +
                "</table>", unsafe_allow_html=True)
        with c2:
            st.subheader("今日领跌板块")
            st.markdown(
                "<table><tr><th>板块</th><th>涨跌幅</th></tr>" +
                "".join(f'<tr><td>{x["板块"]}</td><td class="{_cls(x["涨跌幅"])[0]}">'
                        f'{_cls(x["涨跌幅"])[1]}</td></tr>' for x in s["领跌"]) +
                "</table>", unsafe_allow_html=True)

    st.divider()
    with st.expander("查看数据底稿（原始 Markdown）"):
        st.markdown(gr.build_digest(data, "pm", now))

# ---------------- Tab 2: AI 分析报告 ----------------
with tab_ai:
    key = get_api_key()
    rtype = st.radio("报告类型", ["am", "pm"],
                     format_func=lambda x: "🌅 盘前分析" if x == "am" else "🌇 收盘总结",
                     horizontal=True)
    if not key:
        st.warning("尚未配置 `DEEPSEEK_API_KEY`。可在左侧「🔑 API Key 配置」粘贴 Key "
                   "并点「测试连接」；或到 Secrets 配置（服务端更安全）。")
        st.caption("未配置期间，可先看「实时行情」页底部的数据底稿。")
    else:
        if st.button(f"🤖 生成{'盘前分析' if rtype == 'am' else '收盘总结'}（AI）",
                     type="primary"):
            digest = gr.build_digest(data, rtype, now)
            try:
                md = ai_report(rtype, f"{now:%Y%m%d}", digest, key)
                st.session_state[f"ai_{rtype}"] = md
            except Exception as e:
                st.error(f"生成失败：{e}")

    md = st.session_state.get(f"ai_{rtype}")
    if md:
        st.markdown(md)
        st.download_button("下载 Markdown", md,
                           file_name=f"daily-{now:%Y%m%d}-{rtype}.md")
        st.info("⚠️ 存档说明：Streamlit 免费版为临时文件系统，网页上生成的报告**不会自动写入仓库**。"
                "需长期存档请：① 点上方按钮下载 .md，或 ② 移入仓库 `reports/` 后提交推送，"
                "或 ③ 用仓库内的 GitHub Actions 每日定时生成并提交。")
        st.caption("报告按「当天 + 类型」缓存 1 小时，避免重复消耗 Token。")

# ---------------- Tab 3: 历史报告 ----------------
with tab_hist:
    items = list_reports()
    if not items:
        st.info("reports/ 目录暂无历史报告。")
    else:
        dates = sorted({d for _, d, _ in items})
        pick = st.select_slider("选择日期（最新在右）", options=dates, value=dates[-1])
        day_items = {t: f for f, d, t in items if d == pick}
        if len(day_items) == 2:
            pick_t = st.radio("时段", ["am", "pm"],
                              format_func=lambda x: "盘前分析" if x == "am" else "收盘总结",
                              horizontal=True)
        else:
            pick_t = next(iter(day_items))
        f = day_items.get(pick_t) or next(iter(day_items.values()))
        st.caption(f"共 {len(dates)} 个交易日存档 · 点击下方🔽 下载 HTML 原文")
        with st.expander("查看完整报告", expanded=True):
            try:
                render_report(f)
            except Exception as e:
                st.error(f"渲染失败：{e}")
        with st.expander("⬇️ 下载 / 存档", expanded=False):
            st.download_button("下载本报告 HTML", f.read_bytes(),
                               file_name=f.name)
            st.caption("历史报告随仓库永久存档；新增报告需提交到 `reports/` 或由 Actions 自动生成。")

st.divider()
st.caption("数据来源：东方财富公开接口（延迟约 15 分钟） · AI 生成内容仅供个人研究参考，"
           "不构成投资建议。")
