# 每日情报 daily-brief

个人情报网站：每天早上 7 点（北京时间）自动抓取官方一手来源，用 OpenAI 筛选打分并生成中文阅读卡片，发布为静态站点。

## 信息结构（按优先级）

| 板块 | 内容 | 状态 |
|---|---|---|
| 文献 · 合成生物学 | PubMed / bioRxiv 官方 API，摘要生成阅读卡片 + DOI 链接 | V1 已上线 |
| 政策公告 | 央行 · 深圳政府 · 国家医保局 | V2 |
| 科技 | AI · 英伟达 · 芯片 · 汽车 | V2/V3 |
| 财经 | 今日金价 · 监管公告 | V3 |

## 快速开始

### 本地测试（不花一分钱）

```bash
cd daily-brief
pip install -r requirements.txt
python run.py --mock     # 真实抓取 PubMed/bioRxiv，但不调用 OpenAI，用占位卡片
```

生成的站点在 `site/index.html`，浏览器直接打开即可。跑真实版（需要 API key）：

```bash
export OPENAI_API_KEY=sk-...
python run.py
```

### 获取 API key

**方案 A · OpenAI 官方**：platform.openai.com 注册 → 左栏 API keys → Create new secret key → Billing 充值 $10。注意：需要国际信用卡，且服务区域不含中国大陆。

**方案 B · 国内 OpenAI 兼容服务**（支付方便，推荐）：以 DeepSeek 为例：

1. platform.deepseek.com 注册并充值（支付宝/微信）
2. 创建 API key
3. 修改 `config.yaml`：
   ```yaml
   llm:
     base_url: https://api.deepseek.com
     score_model: deepseek-chat
     card_model: deepseek-chat
   ```
4. GitHub Secret `OPENAI_API_KEY` 里直接填 DeepSeek 的 key（变量名不用改，代码只认这个环境变量）

智谱 GLM、Kimi 等同理：`base_url` 分别填 `https://open.bigmodel.cn/api/paas/v4`、`https://api.moonshot.cn/v1`，模型名查各家文档。

### 部署到 GitHub Pages（一次性配置）

1. 在 GitHub 上创建公开仓库（如 `daily-brief`），把本目录推送上去：
   ```bash
   git init && git add -A && git commit -m "init: daily brief V1"
   git remote add origin git@github.com:<你的用户名>/daily-brief.git
   git push -u origin main
   ```
2. 仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加 `OPENAI_API_KEY`（值为你 platform.openai.com 的 key）。
3. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
4. 到 **Actions** 标签页手动触发一次 `Daily brief`（workflow_dispatch），验证全流程跑通。

之后每天北京时间 07:00 自动更新，无需任何人工干预。

## 修改关注方向

编辑 `config.yaml` 即可，无需改代码：

- `fetch.pubmed.queries`：PubMed 检索式（改关键词就是换关注领域）
- `fetch.biorxiv.categories / keyword_filter`：bioRxiv 分类与过滤词
- `llm.top_n`：每天最终保留几张卡片
- `llm.score_model / card_model`：OpenAI 模型型号（换代会调价，可在 openai.com/api/pricing 查看后更新）
- `scoring.boost_keywords`：mock 打分的关键词权重（真实打分由 LLM 按内置画像完成）

## 成本

- GitHub Actions / Pages：公开仓库免费
- OpenAI：mini 模型打分 + 主力模型出卡，每天约 100-200 条打分、20 张卡片，约 **每月 $3-8**；可改用 Batch API 再打五折

## 工作原理

```
GitHub Actions (cron 07:00 北京时间)
  → 抓取 PubMed E-utilities + bioRxiv API（官方一手）
  → 按 DOI/ID 与历史去重
  → OpenAI mini 模型打分（0-100，按合成生物学博士画像）
  → 取 top N，OpenAI 主力模型生成中文阅读卡片
  → data/YYYY-MM-DD/brief.json 落盘（提交回仓库，形成可检索档案）
  → Jinja2 渲染静态站 → 部署 GitHub Pages
```

阅读卡片包含：中文标题、一句话结论、关键发现、为什么重要、精读建议（★~★★★）、DOI 原文链接。是否读全文由你决定，卡片只提供决策依据。

## 路线图

- **V2**：FDA / EMA / NMPA 新药获批；央行、深圳政府、国家医保局公告抓取（需逐个验证官网页面结构）
- **V3**：科技 newsroom（NVIDIA / TSMC / OpenAI 等）、精选媒体（Endpoints News、Ars Technica）、巨潮资讯药企财报、上海黄金交易所金价

## 说明

卡片由 LLM 生成，忠于摘要但不替代原文；预印本（bioRxiv）未经同行评审。站点页脚已注明此提示。
