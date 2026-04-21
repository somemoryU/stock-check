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
        return text[:10000]
    end = -1
    for m in end_markers:
        pos = text.find(m, start)
        if pos != -1:
            end = pos
            break
    if end == -1:
        end = min(len(text), start + 8000)
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

    # 1) locate the first annual header section and capture the unlabeled first row as revenue
    first_2025 = next((i for i, s in enumerate(lines) if s == '2025 年'), -1)
    if first_2025 != -1:
        nums: list[str] = []
        j = first_2025 + 1
        while j < len(lines) and len(nums) < 4:
            s = lines[j]
            if is_numeric_token(s) or ('百分点' in s):
                nums.append(s)
            j += 1
        revenue_nums = clean_num_tokens(nums)
        if revenue_nums:
            result['营业收入'] = revenue_nums[0]

    # 2) parse labeled rows that appear as multi-line labels followed by numeric values
    current_label_parts: list[str] = []
    collecting = False
    i = 0
    while i < len(lines):
        s = lines[i]
        if s in {'2025 年', '2024 年', '2023 年', '本年比上年增减', '2025 年末', '2024 年末', '2023 年末', '本年末比上年末增减'}:
            i += 1
            continue
        if s.startswith('七、'):
            break

        if not is_numeric_token(s) and '百分点' not in s and not s.startswith('□'):
            # start/continue a label block
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
        r'截至目前，公司主营业务为([^。]{10,200})。',
        r'公司主营业务为([^。]{10,200})。',
        r'目前主营业务为([^。]{10,200})。',
        r'报告期内公司从事的主要业务([^。]{10,200})。',
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return '主营业务为' + m.group(1)
    return ''


def extract_generic_catalysts(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    patterns = [
        (r'建成投产([^。]{6,80})。', '项目建成投产：{0}。'),
        (r'稳步推进([^。]{6,80})。', '项目推进：{0}。'),
        (r'成功收购([^。]{6,80})。', '并购进展：{0}。'),
        (r'成功获取([^。]{6,80})。', '资质获取：{0}。'),
        (r'实现资金收益超([0-9]+万元)', '资金使用效率改善：实现资金收益超 {0}。'),
        (r'信用评级提升至“?([A-Z+]+)”?', '融资条件改善：公司信用评级提升至 {0}。'),
    ]
    for pattern, tpl in patterns:
        m = re.search(pattern, t)
        if m:
            val = ''.join(m.groups()).strip('，,；;：:')
            if val:
                out.append(tpl.format(*m.groups()))
    return out[:5]


def extract_generic_risks(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    if '注意风险' in t or '重大风险' in t:
        out.append('年报明确提示需关注经营中的重大风险，后续要结合具体项目和订单兑现继续跟踪。')
    if '招投标' in t or '工程管理' in t:
        out.append('项目执行链条较长，招投标、工程管理和内控执行都会影响经营质量。')
    if '剥离' in t or '非主业' in t:
        out.append('非主业资产或历史包袱处置仍需观察，节奏和结果会影响资金占用与报表表现。')
    if '前瞻性陈述' in t or '未来发展规划' in t:
        out.append('未来规划不等于业绩兑现，新增业务和项目推进仍有节奏与落地不确定性。')
    return out[:4]


def pick_metric(metrics: dict[str, str], *labels: str) -> str:
    for label in labels:
        for k, v in metrics.items():
            if label in k:
                return v
    return ''


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
