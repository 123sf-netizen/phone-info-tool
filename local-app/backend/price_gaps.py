"""盘点已登记的历史价格，不推断未登记版本是否存在。"""
from collections import Counter
from gaps import valid_evidence
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse



def price_state(record):
    if not isinstance(record, dict) or not record:
        return '记录缺失或无效'
    if record.get('status') == '资料冲突':
        return '资料冲突'
    try:
        amount = Decimal(str(record.get('amount')))
        url = urlparse(str(record.get('url') or ''))
        if not amount.is_finite() or amount <= 0 or url.scheme not in ('http', 'https') or not url.netloc:
            return '记录或来源待核实'
    except (InvalidOperation, ValueError):
        return '记录或来源待核实'
    if (record.get('status') not in ('厂商官方核实', '可靠渠道核实')
            or any(not isinstance(record.get(k), str) or not record[k].strip()
                   for k in ('currency', 'variant', 'region', 'type'))
            or not valid_evidence(record)):
        return '记录或来源待核实'
    return record['status']


def price_report(phones):
    coverage, record_counts, rows = Counter(), Counter(), []
    for phone in phones:
        primary = phone.get('launchPrice')
        variants = phone.get('launchPriceVariants')
        records = []
        if primary:
            records.append(('主价格', primary))
        if variants is not None and not isinstance(variants, list):
            records.append(('其他版本', None))
        elif isinstance(variants, list):
            records.extend((f'其他版本 {index + 1}', record) for index, record in enumerate(variants))
        coverage['未登记价格' if not records else '仅一条记录' if len(records) == 1 else '多条记录'] += 1
        issues = []
        if not primary and records:
            issues.append('缺少主价格')
        for label, record in records:
            state = price_state(record)
            record_counts[state] += 1
            if state not in ('厂商官方核实', '可靠渠道核实'):
                issues.append(f'{label}：{state}')
        if not records:
            issues.append('未登记历史价格')
        rows.append({'id': phone['id'], 'name': phone['name'], 'record_count': len(records),
                     'issues': issues, 'discontinued': any(s in str(phone.get('status') or '')
                                                            for s in ('停售', '停产', '下架'))})
    return {'机型数': len(phones), '机型记录覆盖': dict(coverage), '价格记录状态': dict(record_counts),
            '机型': rows, '说明': '仅统计已登记的历史价格与元数据；单条不等于仅有一个版本，未重新查验来源，不代表当前渠道价格。'}
