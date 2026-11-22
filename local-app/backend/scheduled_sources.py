"""Low-frequency, read-only checks of already registered official sources."""
import json
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gaps import FIELDS, classify
from official_check import check_source_fields, validate_url, battery_typical_candidate

FILE = '官网线索自动检查.json'
INTERVAL = timedelta(minutes=30)
COOLDOWN = timedelta(days=7)
MAX_RECORDS = 4000


def retry_interval(record):
    if record.get('outcome') == '检查中断或尚未完成': return timedelta(hours=6)
    if record.get('outcome') == '检查失败':
        kind=record.get('error_kind')
        if kind in ('network','server_error'): return timedelta(hours=6)
        if kind == 'not_found': return timedelta(days=30)
    return COOLDOWN


def read_state(directory):
    path = Path(directory) / FILE
    try:
        with path.open(encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {'last_attempt': None, 'records': []}
    if not isinstance(data, dict) or not isinstance(data.get('records'), list) or len(data['records']) > MAX_RECORDS:
        raise ValueError('自动检查记录格式无效，已暂停以免覆盖记录')
    return data


OUTCOMES = {'发现关键词', '未提取到关键词', '检查失败', '检查中断或尚未完成'}
FIELD_CHANGES = {'首次提取字段摘录', '字段摘录未变化', '字段摘录有变化', '本次未提取到字段摘录', '页面地址变化，字段摘录待复核', '未记录字段比较'}


def official_record_cursor(record):
    keys=('attempted_at','phone_id','field','url')
    if not isinstance(record,dict) or type(record.get('phone_id')) is not int or any(not isinstance(record.get(k),str) or not record[k] for k in ('attempted_at','field','url')):
        raise ValueError('自动检查记录格式无效')
    stable=json.dumps([record[k] for k in keys],ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(stable).hexdigest()


def official_records_page(records, before=None, limit=50, keyword='', outcome='', field_change=''):
    if not isinstance(records,list) or not 1<=limit<=100: raise ValueError('分页参数无效')
    if outcome and outcome not in OUTCOMES: raise ValueError('检查结果筛选无效')
    if field_change and field_change not in FIELD_CHANGES: raise ValueError('字段比较筛选无效')
    keyword=keyword.strip().casefold();selected=[];seen=set()
    for record in reversed(records):
        cursor=official_record_cursor(record)
        if cursor in seen: raise ValueError('自动检查记录存在重复标识')
        seen.add(cursor)
        if outcome and record.get('outcome') != outcome: continue
        if field_change and (record.get('field_change') or '未记录字段比较') != field_change: continue
        if keyword and keyword not in ' '.join(str(record.get(k) or '') for k in ('phone_name','phone_id','label','field')).casefold(): continue
        selected.append((cursor,record))
    start=0
    if before is not None:
        if len(before)!=64 or any(c not in '0123456789abcdef' for c in before): raise ValueError('分页游标无效')
        matches=[i for i,(cursor,_) in enumerate(selected) if cursor==before]
        if not matches: raise LookupError('记录已变化或筛选条件已改变，请重新读取')
        start=matches[0]+1
    part=selected[start:start+limit]
    return {'records':[record for _,record in part],
            'next_cursor':part[-1][0] if part and start+len(part)<len(selected) else None,
            'total':len(selected)}


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def candidate_url(phone, field):
    sources = phone.get('specFieldSources') or {}
    evidence = sources.get(field) if isinstance(sources, dict) else None
    for value in ((evidence or {}).get('url') if isinstance(evidence, dict) else None, phone.get('specUrl')):
        if value:
            try:
                return validate_url(value)
            except ValueError:
                pass
    return None


def eligible_candidates(phones, records, now):
    latest = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        t = timestamp(record.get('attempted_at'))
        key = (record.get('phone_id'), record.get('field'), record.get('url'))
        if t and (key not in latest or t > latest[key][0]):
            latest[key] = (t,record)
    candidates = []
    for phone in phones:
        if not isinstance(phone, dict) or type(phone.get('id')) is not int:
            continue
        sources = phone.get('specFieldSources') or {}
        sources = sources if isinstance(sources, dict) else {}
        for field, label in FIELDS.items():
            state = classify(phone.get(field), sources.get(field))
            if state not in ('缺失', '待核实', '资料冲突'):
                continue
            url = candidate_url(phone, field)
            if not url:
                continue
            last = latest.get((phone['id'], field, url))
            if last is not None and (last[0] > now or now - last[0] < retry_interval(last[1])):
                continue
            candidates.append((0 if state == '缺失' else 1, phone['id'], field, label, phone.get('name', ''), url, state))
    return sorted(candidates)


def pick_candidate(phones, records, now):
    return next(iter(eligible_candidates(phones, records, now)), None)


def save_state(directory, state):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.sources-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        os.replace(name, directory / FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run_once(directory, phones, now=None, checker=check_source_fields):
    now = now or datetime.now(timezone.utc)
    state = read_state(directory)
    last = timestamp(state.get('last_attempt'))
    if state.get('last_attempt') and last is None:
        raise ValueError('自动检查时间无效，已暂停以免重复访问')
    if last and (last > now or now - last < INTERVAL):
        return None
    candidates = eligible_candidates(phones, state['records'], now)
    if not candidates:
        return None
    _, phone_id, _, _, _, url, _ = candidates[0]
    previous = next((r for r in reversed(state['records']) if isinstance(r,dict) and r.get('phone_id') == phone_id and r.get('url') == url and isinstance(r.get('page_hash'),str) and len(r['page_hash']) == 64), None)
    previous_fields = {}
    for old in reversed(state['records']):
        if (not isinstance(old,dict) or old.get('phone_id') != phone_id or old.get('url') != url
                or old.get('outcome') not in ('发现关键词','未提取到关键词')
                or not isinstance(old.get('field'),str)
                or not isinstance(old.get('snippets'),list) or len(old['snippets']) > 3
                or any(not isinstance(x,str) for x in old['snippets'])):
            continue
        previous_fields.setdefault(old.get('field'),old)
    group = [c for c in candidates if c[1] == phone_id and c[5] == url]
    records = [{'phone_id': c[1], 'phone_name': c[4], 'field': c[2], 'label': c[3],
                'field_state': c[6], 'url': c[5], 'attempted_at': now.isoformat(),
                'outcome': '检查中断或尚未完成', 'next_retry_at': (now+timedelta(hours=6)).isoformat()} for c in group]
    # Record each attempt before requesting the page, including interrupted checks.
    state['last_attempt'] = now.isoformat()
    state['records'] = (state['records'] + records)[-MAX_RECORDS:]
    save_state(directory, state)
    try:
        result = checker(url, [r['field'] for r in records])
        by_field = result['snippets_by_field']
        page_hash=result.get('page_hash');resolved=result.get('resolved_url',url)
        if not page_hash: change='页面未提取到文字，无法比较'
        elif previous is None: change='首次有效检查'
        elif previous.get('resolved_url',url)!=resolved: change='页面地址变化'
        elif previous['page_hash']==page_hash: change='页面文字未变化'
        else: change='页面文字有变化'
        for record in records:
            snippets = by_field[record['field']]
            record['outcome'] = '发现关键词' if snippets else '未提取到关键词'
            record.pop('next_retry_at',None)
            record['snippets'] = snippets
            if record['field'] == 'battery' and record['field_state'] != '资料冲突':
                candidate = battery_typical_candidate(snippets)
                if candidate:
                    record['candidate'] = {'value': candidate, 'status': '待核实',
                                           'note': '仅按摘录识别，须核对型号、地区、版本及原文。'}
            record['resolved_url'] = resolved
            record['page_hash'] = page_hash
            record['page_change'] = change
            old=previous_fields.get(record['field'])
            if old:
                record['previous_field_at']=old.get('attempted_at')
                record['previous_snippets']=list(old['snippets'])
                record['previous_resolved_url']=old.get('resolved_url') or url
            if not old: field_change='首次提取字段摘录' if snippets else '本次未提取到字段摘录'
            elif old.get('resolved_url',url)!=resolved: field_change='页面地址变化，字段摘录待复核'
            elif not snippets: field_change='本次未提取到字段摘录'
            elif old['snippets']==snippets: field_change='字段摘录未变化'
            else: field_change='字段摘录有变化'
            record['field_change']=field_change
    except (ValueError, RuntimeError) as exc:
        for record in records:
            record['outcome'] = '检查失败'
            record['error'] = str(exc)
            record['error_kind'] = getattr(exc,'category','other')
            record['next_retry_at'] = (now+retry_interval(record)).isoformat()
    save_state(directory, state)
    return {**records[0], 'field_count': len(records)}
