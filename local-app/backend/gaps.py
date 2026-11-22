"""生成保守的字段核查清单；存在文本不代表已经核实。"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

FIELDS = {
    'battery': '电池容量', 'charge': '充电规格', 'screen': '屏幕',
    'chip': '处理器', 'camera': '后置影像', 'front': '前置影像',
    'weight': '机身重量', 'ip': '防护等级', 'system': '操作系统',
    'storage': '存储版本', 'updates': '系统更新支持',
}
MISSING = {'', '暂无数据', '待核实', '待补充', '未知', '未公布', '—', '-'}


def china_today(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone(timedelta(hours=8))).date()


def valid_source_url(url):
    if not isinstance(url,str) or not url or any(char.isspace() or char == '\\' for char in url): return False
    try:
        parsed=urlparse(url); _=parsed.port
        return (parsed.scheme in ('http','https') and bool(parsed.hostname) and not parsed.username and not parsed.password and '%' not in parsed.netloc)
    except (ValueError, TypeError):
        return False


def valid_evidence(evidence, today=None):
    if not isinstance(evidence,dict): return False
    region=evidence.get('region'); url=evidence.get('url'); checked=evidence.get('checkedAt')
    if not isinstance(region,str) or not region.strip() or not valid_source_url(url) or not isinstance(checked,str): return False
    try:
        checked_date=date.fromisoformat(checked)
        return checked_date.isoformat()==checked and checked_date <= (today or china_today())
    except (ValueError, TypeError):
        return False


def classify(value, evidence):
    value = '' if value is None else str(value).strip()
    evidence = evidence if isinstance(evidence, dict) else {}
    if evidence.get('status') == '资料冲突' or '资料冲突' in value:
        return '资料冲突'
    if value in MISSING:
        return '缺失'
    if evidence.get('status') in ('厂商官方核实', '可靠渠道核实'):
        if valid_evidence(evidence) and not any(
            marker in value for marker in ('待核', '待确认', '未确认', '资料冲突')
        ):
            return evidence['status']
    return '待核实'


def make_report(phones):
    totals = Counter()
    by_field = {label: Counter() for label in FIELDS.values()}
    incomplete = []
    for phone in phones:
        evidence = phone.get('specFieldSources') or {}
        if not isinstance(evidence, dict):
            evidence = {}
        fields = []
        for key, label in FIELDS.items():
            status = classify(phone.get(key), evidence.get(key))
            totals[status] += 1
            by_field[label][status] += 1
            if status in ('缺失', '待核实', '资料冲突'):
                fields.append({'field': label, 'status': status})
        if fields:
            incomplete.append({'id': phone.get('id'), 'name': phone.get('name'), 'fields': fields})
    return {'机型数': len(phones), '字段数': len(phones) * len(FIELDS),
            '状态统计': dict(totals), '各字段统计': {k: dict(v) for k, v in by_field.items()},
            '未完成机型': incomplete,
            '说明': '保守静态统计；标注已核实也不能代替人工复核，未识别到的部分数据可能需要进一步检查。'}
