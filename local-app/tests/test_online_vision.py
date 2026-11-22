import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import online_vision as vision


class OnlineVisionTests(unittest.TestCase):
    def test_image_validation(self):
        self.assertEqual(vision.decode_image(base64.b64encode(b'\xff\xd8\xfftest').decode()), b'\xff\xd8\xfftest')
        for value in ('!', base64.b64encode(b'not an image').decode(), base64.b64encode(b'\xff\xd8\xff'+b'x' * vision.MAX_IMAGE_BYTES).decode()):
            with self.assertRaises(ValueError): vision.decode_image(value)

    def test_filters_untrusted_urls_and_handles_no_results(self):
        doc={'responses':[{'webDetection':{'webEntities':[{'description':'手机'}], 'pagesWithMatchingImages':[{'url':'javascript:alert(1)','pageTitle':'bad'},{'url':'https://example.org/a','pageTitle':'valid'},{'url':'https://example.org/a','pageTitle':'duplicate'}]}}]}
        result=vision.extract_results(doc)
        self.assertEqual(result['labels'], ['手机'])
        self.assertEqual(result['pages'], [{'title':'valid','url':'https://example.org/a'}])
        self.assertEqual(vision.extract_results({'responses':[{}]}), {'pages':[], 'labels':[]})

    def test_limit(self):
        with vision._attempt_lock: vision._attempts.clear()
        try:
            self.assertTrue(all(vision.allow_online_request(now=100) for _ in range(6)))
            self.assertFalse(vision.allow_online_request(now=101))
            self.assertTrue(vision.allow_online_request(now=160))
        finally:
            with vision._attempt_lock: vision._attempts.clear()


if __name__ == '__main__': unittest.main()
