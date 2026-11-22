"""Read scheduler output without modifying reports or phone data."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def report_status(directory, now=None):
    path = Path(directory) / '最新缺口报告.json'
    try:
        with path.open(encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {'status': 'missing'}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {'status': 'invalid'}
    try:
        generated = datetime.fromisoformat(data['生成时间UTC'])
        report = data['报告']
        if generated.tzinfo is None or not isinstance(report, dict):
            raise ValueError('invalid report')
        total, counts = report['机型数'], report['状态统计']
        if type(total) is not int or total < 0 or not isinstance(counts, dict):
            raise ValueError('invalid counts')
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError('invalid counts')
        timestamp = generated.astimezone(timezone.utc)
        now = now or datetime.now(timezone.utc)
        if timestamp > now + timedelta(minutes=5):
            return {'status': 'invalid'}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {'status': 'invalid'}
    return {'status': 'stale' if now - timestamp > timedelta(minutes=10) else 'ready',
            'generated_at': timestamp.isoformat(), 'phone_count': total, 'counts': counts}
