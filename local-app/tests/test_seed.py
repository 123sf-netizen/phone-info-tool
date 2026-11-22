import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from seed import compare, load_seed, missing_rows
from gaps import classify, make_report
from report_writer import write_report
from editing import update_field
from images_audit import audit_images, load_image_map
import json


class SeedTests(unittest.TestCase):
    def check(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            path.write_text(content, encoding='utf-8')
            return load_seed(path)

    def test_preserves_field_evidence(self):
        row = self.check('const phones=[{"id":1,"name":"机型","brand":"品牌","specFieldSources":{"ip":{"status":"资料冲突"}}}];const phoneImages={}')[0]
        self.assertEqual(row['specFieldSources']['ip']['status'], '资料冲突')

    def test_rejects_duplicate_id(self):
        with self.assertRaises(ValueError):
            self.check('const phones=[{"id":1,"name":"A","brand":"B"},{"id":1,"name":"C","brand":"D"}];const phoneImages={}')

    def test_rejects_missing_data(self):
        with self.assertRaises(ValueError):
            self.check('no phones here')

    def test_current_prototype_is_readable(self):
        path = Path(__file__).resolve().parents[2] / 'index.html'
        self.assertGreater(len(load_seed(path)), 0)

    def test_compare_reports_missing_and_evidence_changes_without_values(self):
        seed = [{'id': 1, 'name': 'A', 'specFieldSources': {'ip': {'status': '待核实'}}}, {'id': 2, 'name': 'B'}]
        db = [{'id': 1, 'name': 'A', 'specFieldSources': {'ip': {'status': '资料冲突'}}}, {'id': 3, 'name': 'C'}]
        report = compare(seed, db)
        self.assertEqual(report['seed_only'][0]['id'], 2)
        self.assertEqual(report['database_only'][0]['id'], 3)
        self.assertEqual(report['changed'][0]['fields'], ['specFieldSources'])
        self.assertNotIn('待核实', str(report))

    def test_missing_rows_never_selects_existing_phone(self):
        original = [{'id': 1, 'name': '已有', 'value': '新值'}, {'id': 2, 'name': '新增'}]
        self.assertEqual(missing_rows(original, [1]), [original[1]])
        self.assertEqual(missing_rows(original, [1, 2]), [])

    def test_gap_classification_requires_evidence(self):
        self.assertEqual(classify('IP68', {}), '待核实')
        self.assertEqual(classify('IP68', {'status': '厂商官方核实'}), '待核实')
        evidence = {'status': '厂商官方核实', 'url': 'https://example.com', 'region': '中国大陆', 'checkedAt': '2026-11-19'}
        self.assertEqual(classify('IP68', evidence), '厂商官方核实')
        self.assertEqual(classify('IP68，其他版本待核实', evidence), '待核实')
        self.assertEqual(classify('暂无数据', {'status': '资料冲突'}), '资料冲突')
        self.assertEqual(classify('暂无数据', {}), '缺失')

    def test_gap_report_counts_fields(self):
        report = make_report([{'id': 1, 'name': 'A', 'ip': 'IP68'}])
        self.assertEqual(report['字段数'], 11)
        self.assertEqual(report['状态统计']['缺失'], 10)
        self.assertEqual(report['状态统计']['待核实'], 1)

    def test_report_writer_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            write_report(directory, {'机型数': 1})
            write_report(directory, {'机型数': 2})
            files = list(Path(directory).iterdir())
            self.assertEqual(len(files), 1)
            result = json.loads(files[0].read_text(encoding='utf-8'))
            self.assertEqual(result['报告']['机型数'], 2)
            self.assertIn('生成时间UTC', result)

    def test_edit_preserves_other_fields_and_original(self):
        original = {'id': 1, 'ip': '暂无数据', 'battery': '5000mAh', 'specFieldSources': {'battery': {'status': '待核实'}}}
        evidence = {'status': '可靠渠道核实', 'url': 'https://example.com/spec', 'region': '中国大陆', 'checkedAt': '2026-01-01'}
        result = update_field(original, 'ip', 'IP53', '暂无数据', None, evidence)
        self.assertEqual(result['ip'], 'IP53')
        self.assertEqual(result['battery'], '5000mAh')
        self.assertEqual(result['specFieldSources']['battery'], {'status': '待核实'})
        self.assertEqual(original['ip'], '暂无数据')

    def test_edit_rejects_stale_or_unverifiable_input(self):
        phone = {'ip': 'IP53'}
        evidence = {'status': '资料冲突', 'url': 'https://example.com', 'region': '中国大陆', 'checkedAt': '2026-01-01'}
        with self.assertRaises(RuntimeError):
            update_field(phone, 'ip', 'IP54', '旧值', None, evidence)
        with self.assertRaises(ValueError):
            update_field(phone, 'ip', 'IP54', 'IP53', None, evidence)
        with self.assertRaises(ValueError):
            update_field(phone, 'name', '其他', None, None, evidence)

    def test_edit_rejects_concurrent_source_change(self):
        phone = {'ip': 'IP53', 'specFieldSources': {'ip': {'url': 'https://new.example'}}}
        with self.assertRaises(RuntimeError):
            update_field(phone, 'ip', 'IP53', 'IP53', {'url': 'https://old.example'}, {})

    def test_image_audit_distinguishes_existence_from_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.png').write_bytes(b'image')
            (root / 'b.png').write_bytes(b'image')
            phones = [{'id': n, 'name': str(n)} for n in range(1, 6)]
            images = {'1': 'images/a.png', '2': 'images/b.png', '3': 'https://example.com/a.png',
                      '4': 'images/missing.png', '5': 'images/../secret'}
            result = audit_images(phones, images, root)
            self.assertEqual([row['status'] for row in result['机型']],
                             ['本地文件存在', '本地文件存在', '外链未检查加载', '本地文件缺失', '路径无效'])
            self.assertEqual(result['重复文件候选'], [[1, 2]])
            self.assertTrue(all(row['visual_status'] == '未验收' for row in result['机型']))

    def test_read_actual_image_map(self):
        path = Path(__file__).resolve().parents[2] / 'index.html'
        self.assertGreater(len(load_image_map(path)), 0)


if __name__ == '__main__':
    unittest.main()
