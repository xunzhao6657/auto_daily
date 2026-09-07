# A股每日大盘报告 · auto_daily

访问即取数的 A 股日报站：打开网址 → 实时抓取行情 → 展示全部数据，配置 DeepSeek Key 后可一键生成 AI 分析报告。

**主部署方案：Streamlit Community Cloud（免费）**；附赠 GitHub Pages 静态站 + Actions 定时生成方案（可选双轨）。

## 目录结构

```
auto_daily/
├── app.py                    # Streamlit 主应用（Cloud 上跑的就是它）
├── requirements.txt          # Python 依赖
├── .streamlit/
│   ├── config.toml           # 主题配置（涨红跌绿）
│   └── secrets.toml.example  # Key 模板（真实 Key 填在 Cloud 后台，不进仓库）
├── scripts/
│   ├── generate_report.py    # 数据抓取 + AI 报告生成（本地/Actions 用）
│   └── build_index.py        # 静态首页生成（GitHub Pages 方案用）
├── reports/                  # 历史报告存档（随仓库分发）
├── .github/workflows/daily.yml  # 交易日 07:15/16:05 自动生成（可选）
├── index.html                # 静态站首页（GitHub Pages 方案用）
├── assets/ · site.webmanifest  # PWA 图标与配置
```

## 一、部署到 Streamlit Community Cloud（约 5 分钟）

1. **推送仓库到 GitHub**（本机已 commit，只需执行）：
   ```bash
   cd "E:/finance agent/auto_daily"
   git remote add origin https://github.com/<你的用户名>/auto-daily.git
   git push -u origin main
   ```
   （先到 github.com → New repository → 建空仓库 `auto-daily`，不要勾选初始化 README）

2. **部署**：到 https://share.streamlit.io 登录（用 GitHub 账号）→
   New app → Repository 选 `auto-daily` → Branch `main` →
   Main file path `app.py` → Deploy。约 2 分钟后拿到
   `https://<app名>.streamlit.app` 公网地址。

3. **配置 AI Key（可选）**：App 页面右下角 **Settings → Secrets**，粘贴：
   ```toml
   DEEPSEEK_API_KEY = "sk-你的key"
   ```
   保存后自动重启，即可在「AI 分析报告」页一键生成报告（Key 只存在 Cloud 后台，不进代码）。

4. **手机使用**：手机浏览器打开网址 →「添加到主屏幕」，即得带图标的准 App。

### 说明与限制

- **访问即取数**：每次打开页面实时抓东财接口（缓存 5 分钟），不需要定时任务，也不会漏数据。
- **AI 报告按「当天+类型」缓存 1 小时**，同一时段多次访问不重复扣 Token。
- Community Cloud 免费额度：App 闲置约一周会休眠，访问时自动唤醒（首次约 30 秒）；公开仓库部署无限制。
- Cloud 容器文件系统是临时的：AI 生成的报告在页面上缓存展示，**长期存档**请把报告文件提交回仓库 `reports/`（或用下面的 Actions 方案自动做）。

## 二、（可选）GitHub Pages 静态站 + 每日自动生成

与 Streamlit 并行，纯静态、永远在线：

1. 仓库 **Settings → Secrets → Actions** 添加 `DEEPSEEK_API_KEY`
2. **Settings → Pages → Source 选 GitHub Actions**
3. 之后每个交易日北京时间 07:15（盘前）/ 16:05（收盘）自动生成报告并发布到
   `https://<用户名>.github.io/auto-daily/`

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py                      # Web 版
python scripts/generate_report.py --type am --dry-run   # 命令行版（无 Key）
```

## 数据源说明

东方财富公开接口（免费、无 Key）：三大指数、美股/港股、行业板块、涨跌家数、主力资金、两融余额。延迟约 15 分钟。中金研报观点、Wind EDB 宏观、南向资金明细不在覆盖范围。

**免责声明**：内容仅供个人研究参考，不构成投资建议。
