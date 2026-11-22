import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_checksum import digest_file, verify_checksum


class BackupChecksumTests(unittest.TestCase):
    def test_missing_valid_altered_and_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            backup = Path(d) / 'backup.sql'
            backup.write_bytes(b'first')
            sidecar = backup.with_suffix('.sql.sha256')
            self.assertEqual(verify_checksum(backup), 'missing')
            sidecar.write_text(digest_file(backup), encoding='ascii')
            self.assertEqual(verify_checksum(backup), 'ok')
            backup.write_bytes(b'changed')
            self.assertEqual(verify_checksum(backup), 'mismatch')
            sidecar.write_text('bad', encoding='ascii')
            self.assertEqual(verify_checksum(backup), 'invalid')


if __name__ == '__main__':
    unittest.main()
