import json
import re
from collections import Counter
from pathlib import Path


def load_seed(path):
    text = Path(path).read_text(encoding='utf-8')
    match = re.search(r'const phones=(\[.*?\]);const phoneImages=', text, re.S)
    if not match:
        raise ValueError('无法读取原型中的机型数据')
    data = json.loads(match.group(1))
    if not isinstance(data, list) or not data:
        raise ValueError('机型数据为空')
    ids = set()
    for phone in data:
        if not isinstance(phone, dict) or not isinstance(phone.get('id'), int):
            raise ValueError('机型 ID 无效')
        if phone['id'] in ids or not phone.get('name') or not phone.get('brand'):
            raise ValueError('机型 ID 重复或名称、品牌缺失')
        ids.add(phone['id'])
    return data


def compare(seed_rows, database_rows):
    source = {item['id']: item for item in seed_rows}
    stored = {item['id']: item for item in database_rows}
    changed = []
    for phone_id in sorted(source.keys() & stored.keys()):
        left, right = source[phone_id], stored[phone_id]
        fields = sorted(key for key in left.keys() | right.keys()
                        if key not in left or key not in right or left[key] != right[key])
        if fields:
            changed.append({'id': phone_id, 'name': left.get('name'), 'fields': fields})
    return {
        'seed_count': len(source), 'database_count': len(stored),
        'seed_only': [{'id': i, 'name': source[i].get('name')} for i in sorted(source.keys() - stored.keys())],
        'database_only': [{'id': i, 'name': stored[i].get('name')} for i in sorted(stored.keys() - source.keys())],
        'changed': changed,
        'changed_field_counts': dict(sorted(Counter(field for item in changed for field in item['fields']).items())),
    }


def missing_rows(seed_rows, database_ids):
    """只选择 ID 尚未存在的机型；已有记录永不自动覆盖。"""
    existing = set(database_ids)
    return [item for item in seed_rows if item['id'] not in existing]
