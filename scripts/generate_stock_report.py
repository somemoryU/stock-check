from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def extract_annual_metrics_block(text: str) -> str:
    start_markers = [
        '六、主要会计数据和财务指标',
        '主要会计数据和财务指标',
    ]
    end_markers = [
        '八、分季度主要财务指标',
        '分季度主要财务指标',
        '九、非经常性损益项目及金额',
    ]
    start = -1
    for m in start_markers:
        start = text.find(m)
        if start != -1:
            break
    if start == -1:
        return text[:12000]
    end = -1
    for m in end_markers:
        pos = text.find(m, start)
        if pos != -1:
            end = pos
            break
    if end == -1:
        end = min(len(text), start + 9000)
    return text[start:end]


def normalize_text(text: str) -> str:
    return re.sub(r'\s+', '', text)


def is_numeric_token(s: str) -> bool:
    return bool(re.fullmatch(r'-?[0-9][0-9,]*(?:\.[0-9]+)?%?', s))


def clean_num_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if '%' in t:
            continue
        if re.fullmatch(r'20\d{2}', t):
            continue
        out.append(t)
    return out


def parse_metric_table(block: str) -> dict[str, str]:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    result: dict[str, str] = {}

    first_num = next((s for s in lines if is_numeric_token(s) and '%' not in s and not re.fullmatch(r'20\d{2}', s)), '')
    if first_num:
        result['营业收入'] = first_num

    current_label_parts: list[str] = []
    collecting = False
    i = 0
    while i < len(lines):
        s = lines[i]
        if s.startswith('七、'):
            break
        if s in {'2025 年', '2024 年', '2023 年', '2022 年', '本年比上年增减', '2025 年末', '2024 年末', '2023 年末', '2022 年末', '本年末比上年末增减'}:
            i += 1
            continue
        if not is_numeric_token(s) and '百分点' not in s and not s.startswith('□'):
            current_label_parts.append(s)
            collecting = True
            i += 1
            continue
        if collecting:
            label = ''.join(current_label_parts)
            num_tokens = []
            while i < len(lines):
                s2 = lines[i]
                if is_numeric_token(s2) or ('百分点' in s2):
                    num_tokens.append(s2)
                    i += 1
                    continue
                break
            clean = clean_num_tokens(num_tokens)
            if clean:
                result[label] = clean[0]
            current_label_parts = []
            collecting = False
            continue
        i += 1
    return result


def extract_company_name(text: str, selected: dict) -> str:
    annual = selected.get('annual_report', {})
    sec = annual.get('secName') or annual.get('tileSecName')
    if sec:
        return str(sec)
    m = re.search(r'股票简称\s*([\u4e00-\u9fffA-Za-z0-9]+)', text)
    if m:
        return m.group(1)
    m = re.search(r'公司的中文简称\s*([\u4e00-\u9fffA-Za-z0-9]+)', text)
    if m:
        return m.group(1)
    return ''


def extract_main_business(text: str) -> str:
    t = normalize_text(text)
    patterns = [
        r'截至目前，公司主营业务为([^。]{10,220})。',
        r'公司主营业务为([^。]{10,220})。',
        r'目前主营业务为([^。]{10,220})。',
        r'公司产品覆盖([^。]{10,220})。',
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            body = m.group(1).strip('，,；;：:')
            if '公司产品覆盖' in p:
                return '产品覆盖' + body
            return '主营业务为' + body
    return ''


def extract_generic_catalysts(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    patterns = [
        (r'全年实现国内央国企大型招投标项目中标规模稳居行业第([^；。]{1,8})', '国内央国企招投标中标规模位居行业第 {0}。'),
        (r'行业出货量排名全球前([^；。]{1,8})', '组件出货量排名全球前 {0}。'),
        (r'已形成([^。]{6,60}TOPCon电池产能)', '产能基础：已形成 {0}。'),
        (r'海外市场出货同比大幅增长', '海外市场出货同比大幅增长。'),
        (r'系统集成业务持续突破，([^。]{8,80})。', '系统集成业务推进：{0}。'),
        (r'累计完成([0-9]+项降本技改项目)', '降本提效推进：累计完成 {0}。'),
        (r'组件A品率提升至([0-9.]+%)', '产品良率提升：组件 A 品率提升至 {0}。'),
    ]
    for pattern, tpl in patterns:
        m = re.search(pattern, t)
        if m:
            if m.groups():
                out.append(tpl.format(*m.groups()))
            else:
                out.append(tpl)
    dedup = []
    for x in out:
        if x not in dedup:
            dedup.append(x)
    return dedup[:6]


def extract_generic_risks(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    if '产能严重大于需求' in t or '供需失衡' in t:
        out.append('行业供需失衡和价格波动仍在，盈利修复对价格环境与竞争格局比较敏感。')
    if '招投标' in t or '工程管理' in t:
        out.append('项目执行链条较长，招投标、工程管理和交付质量都会影响经营结果。')
    if '未来发展规划' in t or '前瞻性陈述' in t:
        out.append('未来规划不等于业绩兑现，新增业务和项目推进仍有节奏与落地不确定性。')
    if '海外市场' in t or '全球' in t:
        out.append('海外市场扩张带来机会，也意味着渠道、区域竞争和外部政策环境需要持续跟踪。')
    return out[:5]


def pick_metric(metrics: dict[str, str], *labels: str) -> str:
    for label in labels:
        for k, v in metrics.items():
            if label in k and len(v) > 1:
                return v
    return ''


def fallback_metric_from_text(text: str, label: str) -> str:
    t = normalize_text(text)
    m = re.search(re.escape(label) + r'[^0-9-]{0,20}(-?[0-9][0-9,]*(?:\.[0-9]+)?)', t)
    return m.group(1) if m else ''


def main() -> None:
    ap = argparse.ArgumentParser(description='Generate simple stock report from extracted text')
    ap.add_argument('code')
    ap.add_argument('name')
    ap.add_argument('--txt', required=True)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--selected', required=True)
    ap.add_argument('--outdir', default='')
    args = ap.parse_args()

    txt_path = Path(args.txt)
    meta = json.loads(Path(args.meta).read_text(encoding='utf-8'))
    selected = json.loads(Path(args.selected).read_text(encoding='utf-8'))
    text = txt_path.read_text(encoding='utf-8', errors='ignore')
    annual_block = extract_annual_metrics_block(text)
    metrics = parse_metric_table(annual_block)

    company_name = args.name if args.name and args.name != args.code else (extract_company_name(text, selected) or args.code)
    main_business = extract_main_business(text)

    revenue = pick_metric(metrics, '营业收入')
    profit = pick_metric(metrics, '归属于上市公司股东的净利润')
    ex_profit = pick_metric(metrics, '归属于上市公司股东的扣除非经常性损益的净利润')
    if not ex_profit or ex_profit in {'8', '9'}:
        ex_profit = fallback_metric_from_text(text, '归属于上市公司股东的扣除非经常性损益的净利润')
    cfo = pick_metric(metrics, '经营活动产生的现金流量净额')
    assets = pick_metric(metrics, '总资产')
    equity = pick_metric(metrics, '归属于上市公司股东的净资产')

    catalysts = extract_generic_catalysts(text)
    risks = extract_generic_risks(text)
    dividend = selected.get('dividend', {}).get('announcementTitle', '')

    simple = f"""# {company_name}（{args.code}）体检报告（简版）

## 公司画像
- {main_business or '主业待补充'}
- 交易所参数：`stockCode = \"{meta.get('stockCode','')}\"` / `orgId = \"{meta.get('orgId','')}\"` / `plate = \"{meta.get('plate','')}\"`

## 财务摘录
- 营业收入：{revenue or '待补充'}
- 归属于上市公司股东的净利润：{profit or '待补充'}
- 扣非净利润：{ex_profit or '待补充'}
- 经营活动产生的现金流量净额：{cfo or '待补充'}
- 总资产：{assets or '待补充'}
- 归属于上市公司股东的净资产：{equity or '待补充'}

## 重点公告
- 年报：{selected.get('annual_report', {}).get('announcementTitle', '未命中')}
- 半年报：{selected.get('semiannual_report', {}).get('announcementTitle', '未命中')}
- 三季报：{selected.get('q3_report', {}).get('announcementTitle', '未命中')}
- 业绩预告：{selected.get('earnings_forecast', {}).get('announcementTitle', '未命中')}
- 分红相关：{dividend or '未命中'}

## 增量看点
"""
    for line in catalysts:
        simple += f"- {line}\n"
    if not catalysts:
        simple += "- 待补充\n"

    simple += "\n## 风险点\n"
    for line in risks:
        simple += f"- {line}\n"
    if not risks:
        simple += "- 待补充\n"

    simple += "\n## 一句话\n- 这版先基于年报与公告做框架体检，后续可继续结合项目公告和经营数据补强判断。\n"

    note = f"""# {company_name}（{args.code}）体检报告（投研笔记版）

## 1. 证据底稿
- 文本来源：`{txt_path}`
- F10 元信息：`stockCode = \"{meta.get('stockCode','')}\"`, `orgId = \"{meta.get('orgId','')}\"`, `plate = \"{meta.get('plate','')}\"`
- 年报标题：{selected.get('annual_report', {}).get('announcementTitle', '未命中')}

## 2. 财务体质
- 营业收入：{revenue or '待补充'}
- 归母净利润：{profit or '待补充'}
- 扣非净利润：{ex_profit or '待补充'}
- 经营现金流：{cfo or '待补充'}
- 总资产：{assets or '待补充'}
- 归母净资产：{equity or '待补充'}

## 3. 公司定位
- {main_business or '主业待补充'}

## 4. 增量逻辑
"""
    for line in catalysts:
        note += f"- {line}\n"
    if not catalysts:
        note += "- 待补充\n"

    note += "\n## 5. 风险与约束\n"
    for line in risks:
        note += f"- {line}\n"
    if not risks:
        note += "- 待补充\n"

    outdir = Path(args.outdir) if args.outdir else txt_path.parent.parent / 'final'
    outdir.mkdir(parents=True, exist_ok=True)
    simple_path = outdir / 'report_simple.md'
    note_path = outdir / 'report_investment_note.md'
    simple_path.write_text(simple, encoding='utf-8')
    note_path.write_text(note, encoding='utf-8')
    print(json.dumps({'simple': str(simple_path), 'investment': str(note_path), 'company_name': company_name, 'metrics': metrics}, ensure_ascii=False))


if __name__ == '__main__':
    main()
