# stock-check

一个面向 A 股公告的轻量化“抓取 + 提炼 + 评分 + 报告”流水线。

它会从巨潮资讯抓取指定股票公告与年报，提取核心财务与业务要点，输出结构化事实文件和两版 markdown 报告，便于做快速投研体检。

## 功能概览

- 自动抓取 F10 页面、公告列表、年报 PDF
- 可选调用 `pdftotext` 转文本并生成报告
- 提取公司画像、财务摘要、催化点、风险点
- 输出评分字段：`total_score` / `item_scores` / `risk_level` / `explanations`
- 支持评分开关、配置覆盖和 fail-fast 校验

## 目录结构

- `scripts/`：主流程与抓取/解析脚本
- `config/`：默认配置与评分配置
- `docs/`：评分引擎文档
- `runs/<code>/`：每只股票一次运行的产物目录
  - `raw/`：原始抓取结果（html/json/pdf/txt）
  - `facts/`：结构化事实文件
  - `final/`：最终报告 markdown

## 环境要求

- Python 3.10+
- macOS/Linux
- 可访问 `cninfo.com.cn`
- 可选：`pdftotext`（用于 PDF 转文本）

安装 `pdftotext`（macOS）：

```bash
brew install poppler
```

## 快速开始

1) 进入项目目录

```bash
cd /Users/mix/.openclaw/workspace-main/projects/stock-check
```

2) 可选：加载环境变量

```bash
cp .env.example .env
# 按需编辑 .env（或直接 export 对应变量）
```

3) 运行完整流程（示例：600036）

```bash
python3 scripts/run_stock_check.py 600036 --name 招商银行
```

常用参数：

```bash
python3 scripts/run_stock_check.py 600036 \
  --name 招商银行 \
  --pages 5 \
  --max-pages 12 \
  --report-name 年度报告
```

## 输出结果

运行后可在 `runs/600036/` 看到：

- `run_summary.json`：每一步执行结果与回退信息
- `facts/core_metrics.json`：核心财务 + 评分结果
- `facts/business_summary.json`：主营摘要
- `facts/catalysts.json`：催化点
- `facts/risks.json`：风险点
- `final/report_simple.md`：简版报告
- `final/report_investment_note.md`：投研笔记版

## 评分配置

默认评分配置：`config/scoring.default.json`

- 使用 Phase2 参数化评分（非零 weight + 阈值）
- 保留 `config/scoring.phase1.default.json` 作为占位版对照

可通过环境变量覆盖：

- `STOCK_CHECK_SCORING_CONFIG=/path/to/custom_scoring.json`
- `STOCK_CHECK_SCORING_ENABLED=true|false`

相关文档见：`docs/scoring-engine-phase1.md`

## 常见问题

- `git push` 提示无远端：先配置 `origin` 再推送。
- 报告未生成：检查 `pdftotext` 路径与年报是否成功下载。
- 评分禁用后总分回到基线：这是预期行为（用于快速回滚对照）。

## 免责声明

本项目仅用于信息整理与研究辅助，不构成任何投资建议。
