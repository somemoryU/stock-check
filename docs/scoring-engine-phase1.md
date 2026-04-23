# Scoring Engine Phase 1

## 目标与范围
- 目标：以旁路方式补齐评分数据结构，不改变现有体检文案语义。
- 范围：仅在 `facts/core_metrics.json` 新增评分字段；旧字段 `metrics` 和 `sources` 保持不变。
- 当前接入指标（4个）：
  - 营业收入
  - 归属于上市公司股东的净利润
  - 归属于上市公司股东的扣除非经常性损益的净利润
  - 经营活动产生的现金流量净额

## 字段定义
输出文件：`runs/<code>/facts/core_metrics.json`

- `total_score: number`
  - 总分，范围 `[0, 100]`。
  - Phase 1 默认中性基线分 50。
- `item_scores: array<object>`
  - 分项评分明细。
  - 每项包含：
    - `id: string` 规则ID
    - `metric: string` 指标名
    - `raw_value: string` 原始指标值
    - `score: number` 分项分
    - `applied: boolean` 是否应用（数据可用）
    - `passed: boolean` 是否通过阈值（applied=true时存在）
    - `threshold: number` 规则阈值（applied=true时存在）
    - `direction: string` 比较方向（applied=true时存在）
    - `weight: number` 权重（applied=true时存在）
- `risk_level: string`
  - 风险等级：`low | medium | high`。
  - 默认阈值：`low >= 70`，`medium >= 40`，其余为 `high`。
- `explanations: array<string>`
  - 每条规则的人类可读解释。
- `confidence: number`
  - 置信度，范围 `[0,1]`，定义为“可用规则输入数 / 启用规则数”。
- `degraded_reasons: array<string>`
  - 降级原因列表。
  - 典型值：
    - `scoring_engine_disabled`
    - `missing_or_invalid_metric:<rule_id>`
    - `no_enabled_rules`
    - `no_valid_rule_inputs`

## 配置与覆盖
默认配置：`config/scoring.default.json`

配置结构：
- `engine.enabled: boolean`
- `engine.baseline_score: number`
- `risk_levels.low_risk_min: number`
- `risk_levels.medium_risk_min: number`
- `rules: array<object>`
  - `id`
  - `metric`
  - `enabled`
  - `weight`
  - `threshold`
  - `direction` (`higher_is_better | lower_is_better`)
  - `explanation_template`

覆盖优先级：
1. `config/scoring.default.json`
2. `config/scoring.local.json`（可选）或 `STOCK_CHECK_SCORING_CONFIG` 指定文件
3. `STOCK_CHECK_SCORING_ENABLED`（布尔开关）

Fail-fast 规则：
- `scoring.default.json` 缺失 => 立即退出。
- `STOCK_CHECK_SCORING_CONFIG` 指向不存在文件 => 立即退出。
- 配置缺字段、类型不符、规则ID重复、direction非法 => 立即退出。

## 回滚说明
最快回滚方式（不改代码）：关闭评分引擎开关。

```bash
STOCK_CHECK_SCORING_ENABLED=false python3 scripts/generate_stock_report.py <code> <name> --txt <txt> --meta <meta> --selected <selected> --outdir <outdir>
```

关闭后行为：
- `total_score=50`
- `item_scores=[]`
- `confidence=0.0`
- `degraded_reasons=["scoring_engine_disabled"]`
- 旧字段保持原语义。

## 一键 Smoke 验证
脚本：`scripts/smoke_scoring_phase1.sh`

覆盖三种场景：
1. 开启评分引擎（默认）
2. 关闭评分引擎（开关回滚）
3. fail-fast（缺失 override 配置）

运行：
```bash
scripts/smoke_scoring_phase1.sh
# 或指定样本
scripts/smoke_scoring_phase1.sh 600036 招商银行
```

## 已知限制
- Phase 1 使用“中性占位规则”：默认 `weight=0`，因此总分不会因规则通过/不通过变化。
- 风险等级当前主要反映基线分与风险分段阈值，不代表完整投研风险模型。
- 指标仅接入4个稳定字段，其它指标仍沿用旧路径，尚未纳入评分。

## 下一步参数化计划
1. 参数标定：为已接入4项配置非零权重与业务阈值（按行业分层）。
2. 规则扩展：分批接入更多稳定指标（不一次性全量切换）。
3. 解释增强：模板中加入“阈值差距/方向影响”说明。
4. 质量门禁：将 smoke 脚本纳入 CI，并补充规则单测（边界值、缺失值、异常值）。
5. 兼容治理：为后续下游消费方提供评分版本号字段（如 `score_version`）。
