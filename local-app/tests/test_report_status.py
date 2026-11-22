import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from report_status import report_status


class ReportStatusTests(unittest.TestCase):
    def test_missing_invalid_ready_and_stale(self):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '最新缺口报告.json'
            self.assertEqual(report_status(tmp, now)['status'], 'missing')
            path.write_text('{', encoding='utf-8')
            self.assertEqual(report_status(tmp, now)['status'], 'invalid')
            def write(time, count=3):
                path.write_text(json.dumps({'生成时间UTC': time.isoformat(), '报告': {'机型数': count, '状态统计': {'缺失': 2}}}), encoding='utf-8')
            write(now - timedelta(minutes=3))
            self.assertEqual(report_status(tmp, now)['status'], 'ready')
            self.assertEqual(report_status(tmp, now)['counts']['缺失'], 2)
            write(now - timedelta(minutes=11))
            self.assertEqual(report_status(tmp, now)['status'], 'stale')
            write(now + timedelta(minutes=6))
            self.assertEqual(report_status(tmp, now)['status'], 'invalid')
            write(now, -1)
            self.assertEqual(report_status(tmp, now)['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
