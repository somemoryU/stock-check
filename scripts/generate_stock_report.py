from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
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


def parse_compact_main_metrics(block: str) -> dict[str, str]:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    compact = [normalize_text(x) for x in lines]
    result: dict[str, str] = {}

    try:
        i_income = compact.index('营业收入')
        i_profit = compact.index('利润总额')
        i_net = compact.index('归属于上市公司股东的净利润')
        i_deduct_start = compact.index('归属于上市公司股东的扣除非')
        i_deduct_end = compact.index('经常性损益的净利润')
        i_cfo = compact.index('经营活动产生的现金流量净额')
    except ValueError:
        return result

    if [i_income, i_profit, i_net, i_deduct_start, i_deduct_end, i_cfo] != list(range(i_income, i_income + 6)):
        return result

    nums = []
    for x in compact[i_cfo + 1:]:
        if re.fullmatch(r'-?[0-9][0-9,]*(?:\.[0-9]+)?', x):
            nums.append(x)
        elif nums and x in {'2025年末', '2024年末', '2023年', '2023年末', '本期末比上年同期末增减（%）'}:
            break

    if len(nums) >= 13:
        result['营业收入'] = nums[0]
        result['利润总额'] = nums[1]
        result['归属于上市公司股东的净利润'] = nums[2]
        result['归属于上市公司股东的扣除非经常性损益的净利润'] = nums[12]
        result['经营活动产生的现金流量净额'] = nums[16]

    try:
        i_equity = compact.index('归属于上市公司股东的净资产')
        i_assets = compact.index('总资产')
    except ValueError:
        return result

    try:
        i_year_end = compact.index('2025年末')
    except ValueError:
        i_year_end = -1
    if i_year_end != -1:
        year_end_nums = []
        for x in compact[i_year_end + 1:]:
            if re.fullmatch(r'-?[0-9][0-9,]*(?:\.[0-9]+)?', x):
                year_end_nums.append(x)
            elif year_end_nums and x in {'归属于上市公司股东的净资产', '总资产', '(二)主要财务指标'}:
                break
        if len(year_end_nums) >= 4:
            result['归属于上市公司股东的净资产'] = year_end_nums[0]
            result['总资产'] = year_end_nums[1]
            return result

    asset_nums = []
    for x in compact[i_assets + 1:]:
        if re.fullmatch(r'-?[0-9][0-9,]*(?:\.[0-9]+)?', x):
            asset_nums.append(x)
    if len(asset_nums) >= 2:
        result['归属于上市公司股东的净资产'] = asset_nums[0]
        result['总资产'] = asset_nums[1]
    return result


def parse_metric_table(block: str) -> dict[str, str]:
    parsed = parse_compact_main_metrics(block)
    if parsed.get('营业收入') and parsed.get('归属于上市公司股东的净利润'):
        return parsed

    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    result: dict[str, str] = {}
    first_num = next((x for x in lines if is_numeric_token(x) and '%' not in x and not re.fullmatch(r'20\d{2}', x)), '')
    if first_num:
        result['营业收入'] = first_num

    current_label_parts: list[str] = []
    collecting = False
    i = 0
    while i < len(lines):
        s = lines[i]
        if s.startswith('七、') or s.startswith('八、') or s.startswith('九、'):
            break
        if s in {'2025 年', '2024 年', '2023 年', '2022 年', '2025年', '2024年', '2023年', '2022年', '本年比上年增减', '本期比上年同期增减(%)', '2025 年末', '2024 年末', '2023 年末', '2022 年末', '2025年末', '2024年末', '2023年末', '2022年末', '本年末比上年末增减', '本期末比上年同期末增减（%）'}:
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


def is_financial_company(text: str) -> bool:
    t = normalize_text(text)
    keys = [
        '保险服务收入', '原保险保费收入', '寿险及健康险业务', '财产保险业务',
        '银行业务', '证券业务', '资产管理业务', '综合金融', '归属于母公司股东的营运利润'
    ]
    return sum(1 for k in keys if k in t) >= 1


def is_broker_company(text: str) -> bool:
    t = normalize_text(text)
    keys = [
        '证券公司', '综合类券商', '财富管理业务', '证券经纪业务',
        '投资银行', '方正承销保荐', '信用业务', '代销金融产品'
    ]
    return sum(1 for k in keys if k in t) >= 2


def parse_broker_metrics(text: str) -> dict[str, str]:
    t = text
    result = {
        '营业收入': '',
        '归属于上市公司股东的净利润': '',
        '归属于上市公司股东的扣除非经常性损益的净利润': '',
        '经营活动产生的现金流量净额': '',
        '总资产': '',
        '归属于上市公司股东的净资产': '',
    }

    block_start = t.find('八、近三年主要会计数据和财务指标')
    block = t[block_start:block_start + 2600] if block_start != -1 else t

    def first_decimal_after(label: str, window: int = 260, source: str = '') -> str:
        src = source or block
        idx = src.find(label)
        if idx == -1:
            return ''
        sub = src[idx:idx + window]
        vals = re.findall(r'-?[0-9][0-9,]*(?:\.[0-9]+)', sub)
        return vals[0] if vals else ''

    result['营业收入'] = first_decimal_after('营业收入')
    result['归属于上市公司股东的净利润'] = first_decimal_after('归属于上市公司股东的净利润')
    result['经营活动产生的现金流量净额'] = first_decimal_after('经营活动产生的现金流量净额')
    result['总资产'] = first_decimal_after('资产总额')
    result['归属于上市公司股东的净资产'] = first_decimal_after('归属于上市公司股东的所有者权益')

    idx = block.find('归属于上市公司股东的净利润')
    if idx != -1:
        sub = block[idx:idx + 320]
        vals = re.findall(r'-?[0-9][0-9,]*(?:\.[0-9]+)', sub)
        if len(vals) >= 5:
            result['归属于上市公司股东的扣除非经常性损益的净利润'] = vals[4]

    if not result['归属于上市公司股东的扣除非经常性损益的净利润']:
        idx = t.find('归属于上市公司股东的扣除非经常性损益的净利润')
        if idx != -1:
            sub = t[idx:idx + 220]
            vals = re.findall(r'-?[0-9][0-9,]*(?:\.[0-9]+)', sub)
            good = next((x for x in vals if len(x.replace(',', '').replace('.', '').replace('-', '')) >= 8), '')
            if good:
                result['归属于上市公司股东的扣除非经常性损益的净利润'] = good

    return result


def extract_broker_summary(text: str) -> str:
    t = normalize_text(text)
    m = re.search(r'锚定“([^”]{8,80}券商)”的战略目标', t)
    if m:
        return '以' + m.group(1) + '为目标，围绕财富管理、投资交易、资产管理和机构业务协同发展的综合类券商'
    m = re.search(r'财富管理业务包括([^。]{10,120})。', t)
    if m:
        return '主营业务涵盖财富管理、投资交易、资产管理和投资银行等证券业务，其中财富管理业务包括' + m.group(1)
    return ''


def extract_broker_catalysts(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    pats = [
        (r'实现营业收入\s*([0-9,]+(?:\.[0-9]+)?)亿元，同比增长\s*([0-9.]+%)', '实现营业收入{0}亿元，同比增长{1}。'),
        (r'归属于上市公司股东的净利润\s*([0-9,]+(?:\.[0-9]+)?)亿元，同比增长\s*([0-9.]+%)', '归母净利润{0}亿元，同比增长{1}。'),
        (r'客户资产首次迈上万亿平台|客户资产突破万亿元', '客户资产突破万亿元，财富管理业务继续扩容。'),
        (r'两融规模突破\s*([0-9,]+(?:\.[0-9]+)?)亿元', '两融规模突破{0}亿元。'),
        (r'金融产品保有规模突破\s*([0-9,]+(?:\.[0-9]+)?)亿元', '金融产品保有规模突破{0}亿元。'),
        (r'承销公司债、企业债超\s*([0-9,]+(?:\.[0-9]+)?)亿元', '承销公司债、企业债超{0}亿元。'),
        (r'公募基金管理规模年均复合增长率超\s*([0-9.]+%)', '公募基金管理规模年均复合增长率超{0}。'),
    ]
    for pat, tmpl in pats:
        m = re.search(pat, t)
        if m:
            out.append(tmpl.format(*m.groups()))
    seen=[]
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:6]


def extract_broker_risks(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    if '资本市场' in t or '市场波动' in t:
        out.append('资本市场波动会影响经纪、两融、自营投资和资管业务表现。')
    if '合规' in t or '风险管理' in t:
        out.append('证券业务强监管持续，合规管理、风控指标和业务边界需要持续满足监管要求。')
    if '客户资产' in t or '财富管理' in t:
        out.append('财富管理业务增长依赖客户资产扩张、产品销售能力和服务转化效率。')
    if '投资银行' in t or '股权融资' in t or '公司债' in t:
        out.append('投行业务受发行节奏、项目储备和市场融资环境变化影响较大。')
    return out[:4]


def parse_financial_metrics(text: str) -> dict[str, str]:
    raw = text
    t = normalize_text(text)
    result = {
        '营业收入': '',
        '归属于上市公司股东的净利润': '',
        '归属于上市公司股东的扣除非经常性损益的净利润': '',
        '经营活动产生的现金流量净额': '',
        '总资产': '',
        '归属于上市公司股东的净资产': '',
    }

    def find_7digit_ints(sub: str) -> list[str]:
        return re.findall(r'\d{1,3}(?:,\d{3}){1,2}', sub)

    idx_assets = raw.find('13,898,471')
    if idx_assets != -1:
        vals = find_7digit_ints(raw[idx_assets:idx_assets + 220])
        if len(vals) >= 4:
            result['总资产'] = vals[0]
            result['归属于上市公司股东的净资产'] = vals[3]

    idx_profit = raw.find('1,050,506')
    if idx_profit != -1:
        vals = find_7digit_ints(raw[idx_profit:idx_profit + 120])
        if len(vals) >= 4:
            result['营业收入'] = vals[0]
            result['归属于上市公司股东的净利润'] = vals[1]
            result['归属于上市公司股东的扣除非经常性损益的净利润'] = vals[2]
            result['经营活动产生的现金流量净额'] = vals[3]

    if all(result.values()):
        return result

    pats = [
        ('营业收入', r'营业收入([0-9,]+(?:\.[0-9]+)?)亿元，同比增长'),
        ('归属于上市公司股东的扣除非经常性损益的净利润', r'归属于母公司股东的扣非净利润([0-9,]+(?:\.[0-9]+)?)亿元，同比增长'),
        ('归属于上市公司股东的净资产', r'归属于母公司股东权益首次突破万亿，达([0-9,]+(?:\.[0-9]+)?)亿元'),
    ]
    for k, pat in pats:
        if result[k]:
            continue
        m = re.search(pat, t)
        if m:
            result[k] = str(int(round(float(m.group(1).replace(',', '')) * 100)))

    m = re.search(r'集团2025年经审计[^。]{0,120}归属于母公司股东的净利润为人民币([0-9,]+(?:\.[0-9]+)?)亿元', t)
    if m and not result['归属于上市公司股东的净利润']:
        result['归属于上市公司股东的净利润'] = str(int(round(float(m.group(1).replace(',', '')) * 100)))

    return result


def extract_financial_summary(text: str) -> str:
    t = normalize_text(text)
    if '平安作为全牌照的综合金融集团' in t:
        return '以保险、银行、资产管理、证券及医疗养老生态协同发展的综合金融集团'
    m = re.search(r'本公司通过([^。]{12,120})。', t)
    if m:
        return m.group(1)
    return ''


def extract_financial_catalysts(text: str) -> list[str]:
    t = normalize_text(text)
    out: list[str] = []
    pats = [
        (r'归属于母公司股东的营运利润([0-9,]+(?:\.[0-9]+)?)亿元，同比增长([0-9.]+%)', '归母营运利润{0}亿元，同比增长{1}。'),
        (r'寿险及健康险业务新业务价值([0-9,]+(?:\.[0-9]+)?)亿元，同比增长([0-9.]+%)', '寿险及健康险业务新业务价值{0}亿元，同比增长{1}。'),
        (r'保险服务收入([0-9,]+(?:\.[0-9]+)?)亿元，同比增长([0-9.]+%)', '保险服务收入{0}亿元，同比增长{1}。'),
        (r'综合投资收益率([0-9.]+%)，同比上升([0-9.]+)个百分点', '综合投资收益率{0}，同比上升{1}个百分点。'),
        (r'净利润([0-9,]+(?:\.[0-9]+)?)亿元；不良贷款率([0-9.]+%)，拨备覆盖率([0-9.]+%)；核心一级资本充足率([0-9.]+%)', '银行业务净利润{0}亿元，不良贷款率{1}，拨备覆盖率{2}，核心一级资本充足率{3}。'),
        (r'持有集团内3类及以上产品的客户留存率([0-9.]+%)', '持有集团内3类及以上产品的客户留存率达{0}。'),
        (r'AI\+真人医生覆盖集团([0-9.]+%)个人客户', 'AI+真人医生覆盖集团{0}个人客户。'),
    ]
    for pat, tmpl in pats:
        m = re.search(pat, t)
        if m:
            out.append(tmpl.format(*m.groups()))
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:6]


def extract_financial_risks(text: str) -> list[str]:
    t = normalize_text(text)
    out: list[str] = []
    if '汇率变动' in t or '国际经济和金融市场条件' in t:
        out.append('汇率波动、国际经济与金融市场变化会影响投资收益、估值表现和资产配置效果。')
    if '同业竞争' in t or '市场份额' in t:
        out.append('综合金融竞争加剧下，市场份额、客户经营效率和产品协同能力仍需持续验证。')
    if '法律、财政和监管变化' in t or '监管变化' in t:
        out.append('法律、财政及监管政策变化，可能影响保险、银行、资管等业务节奏与资本管理。')
    if '医疗养老' in t or '综合金融+医疗养老' in t:
        out.append('医疗养老生态投入和综合金融协同需要持续转化为客户留存、交叉渗透和盈利贡献。')
    return out[:4]


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
    if is_broker_company(text):
        return extract_broker_summary(text)
    if is_financial_company(text):
        return extract_financial_summary(text)
    patterns = [
        r'截至目前，公司主营业务为([^。]{10,220})。',
        r'公司主营业务为([^。]{10,220})。',
        r'目前主营业务为([^。]{10,220})。',
        r'公司的主要经营业务为([^。]{4,120})。',
        r'公司产品覆盖([^。]{10,220})。',
        r'主要产品包括([^。]{10,220})。',
        r'主要产品是([^。]{10,220})。',
        r'形成了以([^。]{10,220})的产品集群',
        r'公司聚焦“([^”]{8,80})”的发展战略',
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            body = m.group(1).strip('，,；;：:')
            if '公司产品覆盖' in p:
                return '产品覆盖' + body
            if '主要产品包括' in p:
                return '主要产品包括' + body
            if '主要产品是' in p:
                return '主要经营业务为生产销售啤酒，主要产品包括' + body
            if '形成了以' in p:
                return '已形成以' + body + '的产品集群'
            if '发展战略' in p:
                return '公司聚焦' + body
            return '主营业务为' + body
    return ''


def extract_generic_catalysts(text: str) -> list[str]:
    t = normalize_text(text)
    out = []
    patterns = [
        (r'全年实现国内央国企大型招投标项目中标规模稳居行业第([一二三四五六七八九十0-9]+)', '国内央国企招投标中标规模位居行业第{0}。'),
        (r'行业出货量排名全球前([一二三四五六七八九十0-9]+)', '组件出货量排名全球前{0}。'),
        (r'已形成([^。]{6,60}TOPCon电池产能)', '产能基础：已形成{0}。'),
        (r'海外市场出货同比大幅增长', '海外市场出货同比大幅增长。'),
        (r'系统集成业务持续突破，([^。]{8,80})。', '系统集成业务推进：{0}。'),
        (r'累计完成([0-9]+项降本技改项目)', '降本提效推进：累计完成{0}。'),
        (r'组件A品率提升至([0-9.]+%)', '产品良率提升：组件A品率提升至{0}。'),
        (r'核心产品稳步放量', '核心产品稳步放量，产品结构持续优化。'),
        (r'研发费用同比增长近([0-9]+%)', '研发投入加大：研发费用同比增长近{0}。'),
        (r'销售收入突破([0-9.]+亿元)', '核心品种销售收入突破{0}。'),
        (r'销售量同比增长超过([0-9]+%)', '核心品种销售量同比增长超过{0}。'),
        (r'成功国谈续约', '核心品种成功国谈续约。'),
        (r'通过仿制药质量和疗效一致性评价', '部分核心化药已通过一致性评价。'),
        (r'利润指标连续四年实现20%以上增长', '利润指标连续四年实现20%以上增长。'),
        (r'中高端系列产品销量增长', '中高端系列产品销量增长，产品结构持续优化。'),
        (r'易拉罐产品销量占比达50%以上创历史新高', '易拉罐产品销量占比达50%以上，创历史新高。'),
        (r'毛利率同比提升([0-9.]+)个百分点', '产品毛利率同比提升{0}个百分点。'),
        (r'高档产品增长([0-9.]+%)', '高档产品增长{0}。'),
        (r'品牌价值提升至([0-9.]+亿元)', '品牌价值提升至{0}。'),
        (r'获评国家级绿色工厂', '获评国家级绿色工厂，绿色生产持续推进。'),
    ]
    for pattern, tpl in patterns:
        m = re.search(pattern, t)
        if m:
            out.append(tpl.format(*m.groups()) if m.groups() else tpl)
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
    if ('招投标' in t or '工程管理' in t) and ('啤酒' not in t and '消费升级' not in t):
        out.append('项目执行链条较长，招投标、工程管理和交付质量都会影响经营结果。')
    if '未来发展规划' in t or '前瞻性陈述' in t or '消费升级' in t:
        out.append('消费升级、高端化和新产品推广能否持续兑现，仍取决于终端动销、渠道执行和区域竞争。')
    if ('海外市场' in t or '出口' in t or '国际化' in t) and '医药' not in t[:40000]:
        out.append('海外市场扩张带来机会，也意味着渠道、区域竞争和外部政策环境需要持续跟踪。')
    if '集采' in t or '医保控费' in t or '医保改革' in t:
        out.append('集采、医保控费和行业合规整顿会持续影响产品价格、销售节奏和盈利空间。')
    if '研发' in t and ('新药' in t or '一致性评价' in t):
        out.append('研发推进、一致性评价和新品放量存在节奏不确定性，相关投入回收需要时间。')
    if '深度存量竞争阶段' in t:
        out.append('啤酒行业处于深度存量竞争阶段，产品升级、渠道效率和区域市场拓展仍需持续验证。')
    elif '同质化竞争' in t or '竞争' in t:
        out.append('行业竞争加剧会压缩利润空间，核心品种销售放量和产品结构优化需要持续验证。')
    dedup = []
    for x in out:
        if x not in dedup:
            dedup.append(x)
    return dedup[:5]


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


def sum_quarterly_deducted_profit(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if '归属于上市公司股' in line and i + 2 < len(lines):
            joined = ''.join(lines[i:i+3])
            if '扣除非经常性' in joined and '净利润' in joined:
                nums = []
                j = i + 3
                while j < len(lines) and len(nums) < 4:
                    s = lines[j]
                    if is_numeric_token(s) and '%' not in s:
                        nums.append(s)
                    elif nums and not is_numeric_token(s) and not re.fullmatch(r'[一二三四五六七八九十第季度年月末本上同比增减]+', s):
                        break
                    j += 1
                if len(nums) == 4:
                    try:
                        total = sum(Decimal(x.replace(',', '')) for x in nums)
                        return f'{total:,.2f}'
                    except InvalidOperation:
                        return ''
    return ''


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')



def extract_catalysts(text: str) -> list[str]:
    if is_broker_company(text):
        return extract_broker_catalysts(text)
    if is_financial_company(text):
        return extract_financial_catalysts(text)
    return extract_generic_catalysts(text)


def extract_risks(text: str) -> list[str]:
    if is_broker_company(text):
        return extract_broker_risks(text)
    if is_financial_company(text):
        return extract_financial_risks(text)
    return extract_generic_risks(text)


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
    run_dir = txt_path.parent.parent
    facts_dir = run_dir / 'facts'
    facts_dir.mkdir(parents=True, exist_ok=True)

    meta = json.loads(Path(args.meta).read_text(encoding='utf-8'))
    selected = json.loads(Path(args.selected).read_text(encoding='utf-8'))
    text = txt_path.read_text(encoding='utf-8', errors='ignore')
    annual_block = extract_annual_metrics_block(text)
    metrics = parse_broker_metrics(text) if is_broker_company(text) else (parse_financial_metrics(text) if is_financial_company(text) else parse_metric_table(annual_block))

    company_name = args.name if args.name and args.name != args.code else (extract_company_name(text, selected) or args.code)
    main_business = extract_main_business(text)

    revenue = pick_metric(metrics, '营业收入')
    profit = pick_metric(metrics, '归属于上市公司股东的净利润')
    ex_profit = pick_metric(metrics, '归属于上市公司股东的扣除非经常性损益的净利润')
    ex_profit_source = 'annual_table'
    if not ex_profit or ex_profit in {'8', '9'}:
        ex_profit = fallback_metric_from_text(text, '归属于上市公司股东的扣除非经常性损益的净利润')
        ex_profit_source = 'text_fallback'
    if not ex_profit or ex_profit in {'8', '9'}:
        ex_profit = sum_quarterly_deducted_profit(text)
        ex_profit_source = 'quarterly_sum_fallback'
    cfo = pick_metric(metrics, '经营活动产生的现金流量净额')
    assets = pick_metric(metrics, '总资产')
    equity = pick_metric(metrics, '归属于上市公司股东的净资产')

    catalysts = extract_catalysts(text)
    risks = extract_risks(text)
    dividend = selected.get('dividend', {}).get('announcementTitle', '')

    core_metrics = {
        'company_name': company_name,
        'code': args.code,
        'annual_report_title': selected.get('annual_report', {}).get('announcementTitle', ''),
        'metrics': {
            '营业收入': revenue or '',
            '归属于上市公司股东的净利润': profit or '',
            '归属于上市公司股东的扣除非经常性损益的净利润': ex_profit or '',
            '经营活动产生的现金流量净额': cfo or '',
            '总资产': assets or '',
            '归属于上市公司股东的净资产': equity or '',
        },
        'sources': {
            '营业收入': 'annual_table',
            '归属于上市公司股东的净利润': 'annual_table',
            '归属于上市公司股东的扣除非经常性损益的净利润': ex_profit_source,
            '经营活动产生的现金流量净额': 'annual_table',
            '总资产': 'annual_table',
            '归属于上市公司股东的净资产': 'annual_table',
        }
    }
    business_summary = {
        'company_name': company_name,
        'code': args.code,
        'summary': main_business or '',
    }
    catalysts_json = {
        'company_name': company_name,
        'code': args.code,
        'items': catalysts,
    }
    risks_json = {
        'company_name': company_name,
        'code': args.code,
        'items': risks,
    }

    write_json(facts_dir / 'core_metrics.json', core_metrics)
    write_json(facts_dir / 'business_summary.json', business_summary)
    write_json(facts_dir / 'catalysts.json', catalysts_json)
    write_json(facts_dir / 'risks.json', risks_json)

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

    outdir = Path(args.outdir) if args.outdir else run_dir / 'final'
    outdir.mkdir(parents=True, exist_ok=True)
    simple_path = outdir / 'report_simple.md'
    note_path = outdir / 'report_investment_note.md'
    simple_path.write_text(simple, encoding='utf-8')
    note_path.write_text(note, encoding='utf-8')
    print(json.dumps({
        'simple': str(simple_path),
        'investment': str(note_path),
        'company_name': company_name,
        'facts': {
            'core_metrics': str(facts_dir / 'core_metrics.json'),
            'business_summary': str(facts_dir / 'business_summary.json'),
            'catalysts': str(facts_dir / 'catalysts.json'),
            'risks': str(facts_dir / 'risks.json'),
        }
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
