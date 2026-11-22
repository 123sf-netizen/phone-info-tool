"""保守盘点独立发布日期；其他日期不能等同于发布日期。"""
from collections import Counter
from gaps import china_today, valid_evidence
from datetime import date


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def release_state(phone):
    value = phone.get('releaseDate')
    label = phone.get('releaseDateLabel') or '发布日期'
    source = phone.get('releaseSource')
    source = source if isinstance(source, dict) else {}
    if source.get('status') == '资料冲突':
        return '资料冲突'
    if not value:
        return '缺失'
    if label != '发布日期':
        return '其他日期，发布日期待核实'
    if not valid_date(value) or date.fromisoformat(value) > china_today():
        return '日期不完整或待核实'
    if source.get('status') not in ('厂商官方核实', '可靠渠道核实') or not valid_evidence(source):
        return '来源或核实状态待核实'
    return source['status']


def release_report(phones):
    counts = Counter()
    incomplete = []
    for phone in phones:
        status = release_state(phone)
        counts[status] += 1
        if status not in ('厂商官方核实', '可靠渠道核实'):
            incomplete.append({'id': phone['id'], 'name': phone['name'], 'status': status,
                               'label': phone.get('releaseDateLabel') or '发布日期',
                               'value': phone.get('releaseDate'),
                               'evidence': phone.get('releaseSource') if isinstance(phone.get('releaseSource'), dict) else None})
    return {'机型数': len(phones), '状态统计': dict(counts), '未完成机型': incomplete,
            '说明': '按已登记日期、标签和来源元数据保守盘点；不代表重新核实了来源内容。'}
