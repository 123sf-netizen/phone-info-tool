from unittest import TestCase, main
from unittest.mock import patch, MagicMock
from email.message import Message
from urllib.error import HTTPError, URLError
import official_check as c

class OfficialCheckTests(TestCase):
    def test_url_allowlist(self):
        self.assertEqual(c.validate_url('https://www.mi.com/spec'), 'https://www.mi.com/spec')
        for url in ('http://www.mi.com/', 'https://www.mi.com.evil.test/', 'https://www.mi.com@evil.test/', 'https://www.mi.com:444/', 'https://127.0.0.1/', None):
            with self.subTest(url=url), self.assertRaises(ValueError): c.validate_url(url)

    def test_visible_text_and_field_keywords(self):
        results = c.extract_snippets('<script>电池 secret</script><p>屏幕 120Hz</p><p>电池 5000mAh</p>', 'battery')
        self.assertTrue(any('5000mAh' in x for x in results))
        self.assertFalse(any('secret' in x for x in results))
        with self.assertRaises(ValueError): c.extract_snippets('anything', 'bad')

    @patch('official_check.socket.getaddrinfo')
    @patch('official_check.build_opener')
    def test_fetch_is_bounded_and_does_not_verify(self, opener, dns):
        dns.return_value = [(None,None,None,None,('8.8.8.8',443))]
        headers = Message(); headers['Content-Type'] = 'text/html'
        response = MagicMock(); response.headers = headers; response.read.return_value = '<p>电池 5000mAh</p>'.encode()
        opener.return_value.open.return_value = response
        response.__enter__.return_value = response
        result = c.check_source('https://www.mi.com/spec', 'battery')
        self.assertIn('5000mAh', result['snippets'][0])
        self.assertIn('不能证明', result['note'])
        response.read.assert_called_once_with(c.MAX_BYTES + 1)
        dns.return_value = [(None,None,None,None,('127.0.0.1',443))]
        with self.assertRaises(RuntimeError): c.check_source('https://www.mi.com/spec', 'battery')

    @patch('official_check.socket.getaddrinfo')
    @patch('official_check.build_opener')
    def test_http_and_network_failures_are_distinct(self, opener, dns):
        dns.return_value = [(None,None,None,None,('8.8.8.8',443))]
        for status,category in [(404,'not_found'),(410,'not_found'),(403,'blocked'),(429,'rate_limited'),(503,'server_error'),(400,'http_error')]:
            opener.return_value.open.side_effect=HTTPError('https://www.mi.com/spec',status,'error',Message(),None)
            with self.subTest(status=status), self.assertRaises(c.SourceCheckError) as error:
                c.check_source('https://www.mi.com/spec','battery')
            self.assertEqual(error.exception.category,category)
            self.assertIn(str(status),str(error.exception))
        opener.return_value.open.side_effect=URLError('private detail')
        with self.assertRaises(c.SourceCheckError) as error:c.check_source('https://www.mi.com/spec','battery')
        self.assertEqual(error.exception.category,'network')
        self.assertNotIn('private detail',str(error.exception))

    @patch('official_check.socket.getaddrinfo')
    @patch('official_check.build_opener')
    def test_multi_field_fetch_once(self, opener, dns):
        dns.return_value = [(None,None,None,None,('8.8.8.8',443))]
        headers = Message(); headers['Content-Type'] = 'text/html'
        response = MagicMock(); response.headers = headers; response.read.return_value = '<p>电池 5000mAh</p><p>屏幕 120Hz</p>'.encode(); response.__enter__.return_value = response
        opener.return_value.open.return_value = response
        result = c.check_source_fields('https://www.mi.com/spec', ['battery','screen'])
        self.assertIn('5000mAh', result['snippets_by_field']['battery'][0])
        self.assertIn('120Hz', result['snippets_by_field']['screen'][0])
        self.assertEqual(opener.return_value.open.call_count,1)
        self.assertEqual(len(result['page_hash']),64)
        self.assertEqual(c.visible_text('<script>忽略</script><p>电池   5000</p>'),c.visible_text('<p>电池 5000</p>'))
        with self.assertRaises(ValueError): c.check_source_fields('https://www.mi.com/spec',['bad'])

    @patch('official_check.socket.getaddrinfo')
    @patch('official_check.build_opener')
    def test_redirects_are_limited_and_stay_on_same_https_host(self, opener, dns):
        dns.return_value = [(None,None,None,None,('8.8.8.8',443))]
        headers = Message(); headers['Content-Type'] = 'text/html'
        response = MagicMock(); response.headers = headers; response.read.return_value = '<p>电池 5000mAh</p>'.encode(); response.__enter__.return_value = response
        def redirect(location):
            headers = Message(); headers['Location'] = location
            return HTTPError('https://www.mi.com/spec', 302, 'redirect', headers, None)
        opener.return_value.open.side_effect = [redirect('/new'), response]
        result = c.check_source('https://www.mi.com/spec', 'battery')
        self.assertEqual(result['url'], 'https://www.mi.com/spec')
        self.assertEqual(result['resolved_url'], 'https://www.mi.com/new')
        self.assertEqual(dns.call_count, 2)
        for target in ('http://www.mi.com/new', 'https://www.oppo.com/new', 'https://evil.test/new'):
            opener.return_value.open.reset_mock(); opener.return_value.open.side_effect = [redirect(target)]
            with self.subTest(target=target), self.assertRaises(RuntimeError): c.check_source('https://www.mi.com/spec', 'battery')
            self.assertEqual(opener.return_value.open.call_count, 1)
        opener.return_value.open.reset_mock(); opener.return_value.open.side_effect = [redirect('/a'),redirect('/b'),redirect('/c')]
        with self.assertRaises(RuntimeError): c.check_source('https://www.mi.com/spec', 'battery')
        self.assertEqual(opener.return_value.open.call_count, 3)

if __name__ == '__main__': main()
