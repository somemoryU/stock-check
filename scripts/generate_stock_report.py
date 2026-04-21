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
        return text[:8000]
    end = -1
    for m in end_markers:
        pos = text.find(m, start)
        if pos != -1:
            end = pos
            break
    if end == -1:
        end = min(len(text), start + 5000)
    return text[start:end]


def extract_2025_value(label: str, block: str) -> str:
    idx = block.find(label)
    if idx == -1:
        return ""
    tail = block[idx: idx + 400]
    nums = re.findall(r'-?[0-9][0-9,]*(?:\.[0-9]+)?%?', tail)
    clean = [n for n in nums if '%' not in n]
    return clean[0] if clean else ""


def normalize_spaces(s: str) -> str:
    s = s.replace('\n', '')
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def extract_main_business(text: str) -> str:
    m = re.search(r'公司致力于清洁能源、新能源等领域的发展。?目前主营业务为([^。]{10,120})。', text.replace('\n', ''))
    if m:
        return '主营业务为' + m.group(1).strip()
    m = re.search(r'主营业务为([^。；\n]{10,120})', text.replace('\n', ''))
    if m:
        return '主营业务为' + m.group(1).strip(' ，,。；;')
    return ''


def extract_generation_summary(text: str) -> list[str]:
    t = text.replace('\n', '')
    out = []
    patterns = [
        (r'完成水力发电量([0-9.,]+) 万千瓦时，较上年同期([^；。]{1,40})', '水电发电量 {0} 万千瓦时，{1}。'),
        (r'完成风力发电量([0-9.,]+) 万千瓦时，较上年同期([^；。]{1,40})', '风电发电量 {0} 万千瓦时，{1}。'),
        (r'完成光伏发电量([0-9.,]+) 万千瓦时，较去年同期([^；。]{1,40})', '光伏发电量 {0} 万千瓦时，{1}。'),
    ]
    for pattern, tpl in patterns:
        m = re.search(pattern, t)
        if m:
            out.append(tpl.format(m.group(1), m.group(2)))
    return out


def extract_catalysts(text: str) -> list[str]:
    t = text.replace('\n', '')
    out = []
    m = re.search(r'陆续建成投产\s*([0-9]+) 个屋顶分布式光伏发电项目，新增装机容量\s*([0-9.]+) 兆瓦', t)
    if m:
        out.append(f'分布式光伏已落地：建成投产 {m.group(1)} 个屋顶项目，新增装机 {m.group(2)} 兆瓦。')
    if '海上风电项目稳步推进' in t:
        out.append('海上风电在推进：参与宁德深水 B-1 区项目，并协同推进霞浦海上风电场 B 区、宁德深水 A 区项目。')
    m = re.search(r'成功收购福建寿宁牛头山水电有限公司 10%股权，新增水电权益装机容量\s*([0-9.]+) 兆瓦', t)
    if m:
        out.append(f'水电权益装机有增量：并购带来新增权益装机 {m.group(1)} 兆瓦。')
    if '成功获取售电资质' in t:
        out.append('新业务在铺开：已取得售电资质，开始同步推进市场拓展与客户开发。')
    out.extend(extract_generation_summary(text))
    return out[:6]


def extract_risks(text: str) -> list[str]:
    t = text.replace('\n', '')
    out = []
    if '降雨量较上年同期减少所致' in t:
        out.append('水电波动受来水影响明显，降雨变化会直接影响发电量和售电量。')
    if '风电场风速同比增加' in t:
        out.append('风电表现与风资源相关，风况波动会影响年度产出。')
    if '强化风险排查' in t or '风险管理' in t:
        out.append('项目建设、招投标和内控执行仍需要持续压风险，管理要求不低。')
    if '房地产业务剥离三年行动计划' in t:
        out.append('非主业资产剥离仍在推进，历史包袱和处置节奏值得跟踪。')
    if '前瞻性陈述' in t:
        out.append('海风、售电等增量方向还在推进中，落地节奏和兑现力度存在不确定性。')
    return out[:5]


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate simple stock report from extracted text")
    ap.add_argument("code")
    ap.add_argument("name")
    ap.add_argument("--txt", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--selected", required=True)
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()

    txt_path = Path(args.txt)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    selected = json.loads(Path(args.selected).read_text(encoding="utf-8"))
    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    annual_block = extract_annual_metrics_block(text)

    revenue = extract_2025_value("营业收入", annual_block)
    profit = extract_2025_value("归属于上市公司股东的净利润", annual_block)
    ex_profit = extract_2025_value("归属于上市公司股东的扣除非经常性损益的净利润", annual_block)
    if not ex_profit:
        ex_profit = extract_2025_value("归属于上市公司股东的扣除非经常性损\n益的净利润", annual_block)
    cfo = extract_2025_value("经营活动产生的现金流量净额", annual_block)
    assets = extract_2025_value("总资产", annual_block)
    equity = extract_2025_value("归属于上市公司股东的净资产", annual_block)
    main_business = extract_main_business(text)
    catalysts = extract_catalysts(text)
    risks = extract_risks(text)
    dividend = selected.get("dividend", {}).get("announcementTitle", "")

    simple = f"""# {args.name}（{args.code}）体检报告（简版）

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

    simple += "\n## 一句话\n- 水电是底盘，风光是增量，海风和售电提供后续想象空间，但资源条件与项目兑现节奏都要盯。\n"

    note = f"""# {args.name}（{args.code}）体检报告（投研笔记版）

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

    outdir = Path(args.outdir) if args.outdir else txt_path.parent.parent / "final"
    outdir.mkdir(parents=True, exist_ok=True)
    simple_path = outdir / "report_simple.md"
    note_path = outdir / "report_investment_note.md"
    simple_path.write_text(simple, encoding="utf-8")
    note_path.write_text(note, encoding="utf-8")
    print(json.dumps({"simple": str(simple_path), "investment": str(note_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
