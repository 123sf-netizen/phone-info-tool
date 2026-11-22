import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_schema import REQUIRED_TABLES, missing_tables, parse_table_counts, parse_table_checksums


class BackupSchemaTests(unittest.TestCase):
    def test_checksums_require_every_table_and_numeric_result(self):
        text = '\n'.join(f'phoneguide.{name}\t42' for name in REQUIRED_TABLES)
        self.assertEqual(parse_table_checksums(text)['phones'], 42)
        for invalid in (text + '\nphoneguide.phones\t42', text.replace('phoneguide.phones\t42', 'phoneguide.phones\tNULL'), 'phoneguide.phones\t42'):
            with self.assertRaises(ValueError):
                parse_table_checksums(invalid)

    def test_missing_tables_are_reported(self):
        self.assertEqual(missing_tables('\n'.join(REQUIRED_TABLES)), [])
        self.assertEqual(missing_tables('\n'.join(REQUIRED_TABLES - {'feedback_request'})), ['feedback_request'])
        self.assertEqual(len(missing_tables('')), len(REQUIRED_TABLES))

    def test_counts_require_every_table_once(self):
        text = '\n'.join(f'{name}\t12' for name in REQUIRED_TABLES)
        counts = parse_table_counts(text)
        self.assertEqual(counts['phones'], 12)
        with self.assertRaises(ValueError):
            parse_table_counts(text + '\nphones\t1')
        with self.assertRaises(ValueError):
            parse_table_counts('phones\tinvalid')
        with self.assertRaises(ValueError):
            parse_table_counts('phones\t1')


if __name__ == '__main__':
    unittest.main()
