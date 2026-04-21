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
    # first numeric token after the label row is the 2025 value
    return clean[0] if clean else ""


def extract_main_business(text: str) -> str:
    patterns = [
        r"公司主要从事([^。；\n]{10,120})",
        r"主要从事([^。；\n]{10,120})",
        r"主营业务([^。；\n]{10,120})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip(" ：:，,")
    return ""


def pick_lines(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if any(k in s for k in keywords):
            out.append(s)
        if len(out) >= limit:
            break
    return out


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

    catalysts = pick_lines(text, ["风电", "光伏", "储能", "海上风电", "虚拟电厂", "售电", "碳资产", "分布式"], 10)
    risks = pick_lines(text, ["风险", "降雨", "来水", "风况", "政策", "减值", "不确定", "波动"], 10)
    dividend = selected.get("dividend", {}).get("announcementTitle", "")

    simple = f"""# {args.name}（{args.code}）体检报告（简版）

## 公司画像
- 主业：{main_business or '待补充'}
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
    for line in catalysts[:6]:
        simple += f"- {line}\n"
    if not catalysts:
        simple += "- 待补充\n"

    simple += "\n## 风险点\n"
    for line in risks[:6]:
        simple += f"- {line}\n"
    if not risks:
        simple += "- 待补充\n"

    simple += "\n## 一句话\n- 基于年报与公告链路，属于可证据化分析标的；后续可继续补公告正文和更多季度材料。\n"

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

## 3. 主业与增量
- 主业概括：{main_business or '待补充'}
"""
    for line in catalysts[:8]:
        note += f"- {line}\n"
    if not catalysts:
        note += "- 待补充\n"

    note += "\n## 4. 风险与约束\n"
    for line in risks[:8]:
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
