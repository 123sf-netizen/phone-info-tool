import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from official_check import snippets_from_text, battery_typical_candidate


class OfficialSnippetsTest(unittest.TestCase):
    def test_battery_candidate_requires_unambiguous_typical_value(self):
        self.assertEqual(battery_typical_candidate(['典型容量：5000mAh']), '5000mAh（典型值）')
        self.assertEqual(battery_typical_candidate(['电池 5000mAh（典型值）']), '5000mAh（典型值）')
        self.assertIsNone(battery_typical_candidate(['电池容量 5000mAh']))
        self.assertIsNone(battery_typical_candidate(['典型容量 5000mAh；额定容量 4880mAh']))
        self.assertIsNone(battery_typical_candidate(['典型容量 2550mAh 等效于 5100mAh']))
        self.assertIsNone(battery_typical_candidate(['典型容量 5000mAh', '典型容量 6000mAh']))

    def test_numeric_spec_later_in_page_is_prioritized(self):
        text = ('电池 服务与保养 ' + '介绍 ' * 100) * 4 + '电池典型容量 5000mAh'
        snippets = snippets_from_text(text, 'battery')
        self.assertIn('5000mAh', snippets[0])
        self.assertLessEqual(len(snippets), 3)

    def test_falls_back_without_units_and_ignores_unrelated_fields(self):
        self.assertEqual(snippets_from_text('屏幕 AMOLED 柔性直屏', 'screen'), ['屏幕 AMOLED 柔性直屏'])
        self.assertEqual(snippets_from_text('没有相应描述', 'battery'), [])
        with self.assertRaises(ValueError):
            snippets_from_text('battery', 'unknown')


if __name__ == '__main__':
    unittest.main()
