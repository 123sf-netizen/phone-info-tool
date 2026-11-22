import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from back_references import available_references, inspect_reference_file


class BackReferenceTests(unittest.TestCase):
    def test_matching_file_and_phone_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / 'images'
            images.mkdir()
            image = images / 'back.png'
            image.write_bytes(b'verified')
            record = {'phoneId': 1, 'phoneName': '测试机', 'image': 'images/back.png',
                      'sha256': hashlib.sha256(b'verified').hexdigest(), 'region': '中国大陆',
                      'color': '白色', 'source': 'https://example.com', 'checkedAt': '2026-01-01'}
            manifest = root / 'references.json'
            manifest.write_text(json.dumps({'version': 1, 'references': [record]}), encoding='utf-8')
            self.assertEqual(len(available_references(manifest, images, [{'id': 1, 'name': '测试机'}])), 1)
            self.assertEqual(available_references(manifest, images, [{'id': 1, 'name': '不同型号'}]), [])
            image.write_bytes(b'changed')
            self.assertEqual(available_references(manifest, images, [{'id': 1, 'name': '测试机'}]), [])
            record['image'] = 'images/../references.json'
            manifest.write_text(json.dumps({'version': 1, 'references': [record]}), encoding='utf-8')
            self.assertEqual(available_references(manifest, images, [{'id': 1, 'name': '测试机'}]), [])

    def test_inspection_checks_type_and_stays_in_image_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / 'images'
            images.mkdir()
            (images / 'a.png').write_bytes(b'\x89PNG\r\n\x1a\ncontent')
            self.assertEqual(inspect_reference_file(images, 'images/a.png'),
                             hashlib.sha256(b'\x89PNG\r\n\x1a\ncontent').hexdigest())
            (images / 'fake.png').write_bytes(b'not an image')
            with self.assertRaises(ValueError):
                inspect_reference_file(images, 'images/fake.png')
            with self.assertRaises(ValueError):
                inspect_reference_file(images, 'images/../fake.png')
            with self.assertRaises(ValueError):
                inspect_reference_file(images, 'images/a.png?other')


if __name__ == '__main__':
    unittest.main()
