"""字段编辑规则，与数据库事务分离以便测试。"""
from copy import deepcopy
from datetime import date
from gaps import FIELDS, classify, china_today, valid_source_url

STATUSES = ('厂商官方核实', '可靠渠道核实', '待核实', '资料冲突')


def legacy_publish_check(phone):
    sources = phone.get('specFieldSources')
    sources = sources if isinstance(sources, dict) else {}
    blocked, missing = [], []
    for key, label in FIELDS.items():
        status = classify(phone.get(key), sources.get(key))
        if status == '缺失':
            missing.append(label)
        elif status not in ('厂商官方核实', '可靠渠道核实'):
            blocked.append({'field': key, 'label': label, 'status': status})
    return {'ready': not blocked, 'blocked': blocked, 'missing': missing,
            'notice': '仅允许已核实或缺失的字段；发布时不带旧价格，主图先隐藏，未核实的发布日期不展示。'}


def prepare_legacy_for_publish(phone):
    result = deepcopy(phone)
    result['price'] = None
    result['status'] = '销售状态待核实'
    result.pop('launchPrice', None)
    result.pop('launchPriceVariants', None)
    release = result.get('releaseSource')
    if not isinstance(release, dict) or release.get('status') not in ('厂商官方核实', '可靠渠道核实') or not all(
        release.get(k) for k in ('url', 'region', 'checkedAt')
    ):
        result.pop('releaseDate', None)
        result.pop('releaseSource', None)
    result['suppressLegacyImage'] = True
    return result


def update_field(phone, field, value, expected_value, expected_evidence, evidence):
    if field not in FIELDS:
        raise ValueError('不支持的字段')
    if phone.get(field) != expected_value:
        raise RuntimeError('字段已被修改，请重新读取')
    existing_sources = phone.get('specFieldSources')
    current_evidence = existing_sources.get(field) if isinstance(existing_sources, dict) else None
    if current_evidence != expected_evidence:
        raise RuntimeError('字段来源已被修改，请重新读取')
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError('字段内容必须为 1 至 2000 个字符')
    if not isinstance(evidence, dict) or evidence.get('status') not in STATUSES:
        raise ValueError('请选择核查状态')
    if not all(isinstance(evidence.get(k), str) and evidence[k].strip() for k in ('url', 'region', 'checkedAt')):
        raise ValueError('请填写来源、地区和核对日期')
    if not valid_source_url(evidence['url']):
        raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
    try:
        checked = date.fromisoformat(evidence['checkedAt'])
    except ValueError as exc:
        raise ValueError('核对日期格式应为 YYYY-MM-DD') from exc
    if checked > china_today():
        raise ValueError('核对日期不能晚于今天')
    if evidence['status'] == '资料冲突':
        if not valid_source_url(evidence.get('conflictingUrl', '')):
            raise ValueError('资料冲突时请填写另一条来源链接')
    updated = deepcopy(phone)
    sources = updated.get('specFieldSources')
    if not isinstance(sources, dict):
        sources = {}
    sources[field] = deepcopy(evidence)
    updated['specFieldSources'] = sources
    updated[field] = value.strip()
    return updated
