import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('image_backup', Path(__file__).resolve().parents[1] / 'image_backup.py')
image_backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_backup)


class ImageBackupTests(unittest.TestCase):
    def test_compare_detects_added_missing_and_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'images'
            source.mkdir()
            (source / 'same.png').write_bytes(b'same')
            (source / 'changed.png').write_bytes(b'old')
            (source / 'removed.png').write_bytes(b'removed')
            target = root / 'backup.zip'
            image_backup.make_backup(source, target)
            (source / 'changed.png').write_bytes(b'new')
            (source / 'removed.png').unlink()
            (source / 'added.png').write_bytes(b'added')
            self.assertEqual(image_backup.compare_with_source(target, source), {
                '新增': ['added.png'], '当前缺少': ['removed.png'], '内容变化': ['changed.png']})

    def test_round_trip_and_detect_changed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'images'
            (source / '子目录').mkdir(parents=True)
            (source / '子目录' / '图片.png').write_bytes(b'original')
            target = root / 'backup.zip'
            self.assertEqual(image_backup.make_backup(source, target), 1)
            self.assertEqual(image_backup.verify_backup(target), 1)
            with zipfile.ZipFile(target) as archive:
                manifest = json.loads(archive.read('manifest.json'))
            with zipfile.ZipFile(target, 'w') as archive:
                archive.writestr('images/子目录/图片.png', b'altered')
                archive.writestr('manifest.json', json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, '校验失败'):
                image_backup.verify_backup(target)

    def test_empty_source_does_not_leave_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'images'
            source.mkdir()
            target = Path(directory) / 'backup.zip'
            with self.assertRaises(ValueError):
                image_backup.make_backup(source, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
