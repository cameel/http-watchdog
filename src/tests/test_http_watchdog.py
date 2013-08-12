import unittest
from urllib.parse import urlparse

from ..http_watchdog import HttpWatchdog, CharsetDetectionError

class HttpWatchdogTest(unittest.TestCase):
    def test_dissect_and_escape_url_should_split_valid_url(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl:81/test?a=b&c=d'))
        self.assertEqual(url_parts, ('google.pl', 81, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_work_with_https(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('https://google.pl:81/test?a=b&c=d'))
        self.assertEqual(url_parts, ('google.pl', 81, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_assume_port_80_for_http(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl/test?a=b&c=d'))
        self.assertEqual(url_parts, ('google.pl', 80, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_assume_port_443_for_https(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('https://google.pl/test?a=b&c=d'))
        self.assertEqual(url_parts, ('google.pl', 443, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_ignore_url_fragment(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl:81/test?a=b&c=d#fragment'))
        self.assertEqual(url_parts, ('google.pl', 81, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_assume_root_if_path_is_missing(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl:81'))
        self.assertEqual(url_parts, ('google.pl', 81, '/'))

    def test_dissect_and_escape_url_should_return_empty_host_if_missing(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://:81/test?a=b&c=d'))
        self.assertEqual(url_parts, ('', 81, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_convert_international_domain_names_to_punycode(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://例子.测试:81/test?a=b&c=d'))
        self.assertEqual(url_parts, ('xn--fsqu00a.xn--0zwm56d', 81, '/test?a=b&c=d'))

    def test_dissect_and_escape_url_should_convert_non_ascii_characters_in_path_to_percent_codes(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl:81/首页'))
        self.assertEqual(url_parts, ('google.pl', 81, '/%E9%A6%96%E9%A1%B5'))

    def test_dissect_and_escape_url_should_not_escape_special_path_characters(self):
        url_parts = HttpWatchdog._dissect_and_escape_url(urlparse('http://google.pl:81/首/页?软件=帮助&联络=العربي'))
        self.assertEqual(url_parts, ('google.pl', 81, '/%E9%A6%96/%E9%A1%B5?%E8%BD%AF%E4%BB%B6=%E5%B8%AE%E5%8A%A9&%E8%81%94%E7%BB%9C=%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A'))

    # TMP: Invalid urls

    def test_detect_response_charset_should_extract_charset_from_valid_content_type_headers(self):
        charset_1 = HttpWatchdog._detect_response_charset('Content-Type: text/html; charset=utf-8')
        self.assertEqual(charset_1, 'utf-8')

        charset_2 = HttpWatchdog._detect_response_charset('Content-Type: text/html; charset=latin1')
        self.assertEqual(charset_2, 'latin1')

    def test_detect_response_charset_should_respect_case(self):
        charset = HttpWatchdog._detect_response_charset('Content-Type: text/html; charset=UTF-8')
        self.assertEqual(charset, 'UTF-8')

    def test_detect_response_charset_should_return_none_if_charset_not_present(self):
        charset_1 = HttpWatchdog._detect_response_charset('Content-Type: text/html')
        self.assertEqual(charset_1, None)

        charset_2 = HttpWatchdog._detect_response_charset('')
        self.assertEqual(charset_2, None)

        charset_3 = HttpWatchdog._detect_response_charset('x = y; Content-Type: text/html; b=c, d: e')
        self.assertEqual(charset_3, None)

        charset_4 = HttpWatchdog._detect_response_charset(None)
        self.assertEqual(charset_4, None)

        charset_5 = HttpWatchdog._detect_response_charset(';;;;;;;;;;;;;;;;;;;;;;;;;')
        self.assertEqual(charset_5, None)

        charset_6 = HttpWatchdog._detect_response_charset('-------------------------')
        self.assertEqual(charset_6, None)

        charset_7 = HttpWatchdog._detect_response_charset('Content-Type: text/html; chrset=utf-8')
        self.assertEqual(charset_7, None)

    def test_detect_response_charset_should_ignore_whitespace(self):
        charset = HttpWatchdog._detect_response_charset('\tContent-Type: text/html;   charset = utf-8\t\n')
        self.assertEqual(charset, 'utf-8')

    def test_detect_response_charset_should_ignore_field_order(self):
        charset_1 = HttpWatchdog._detect_response_charset('charset=utf-8; Content-Type: text/html')
        self.assertEqual(charset_1, 'utf-8')

    def test_detect_response_charset_should_detect_duplicate_charset(self):
        with self.assertRaises(CharsetDetectionError):
            HttpWatchdog._detect_response_charset('Content-Type: text/html; charset=utf-8; charset=latin1')

        with self.assertRaises(CharsetDetectionError):
            HttpWatchdog._detect_response_charset('charset=utf-8; Content-Type: text/html; charset=utf-8')

    def test_page_configs_should_provide_access_to_a_list_of_page_configs(self):
        input_page_configs = [
            {
                'url':      'http://google.pl:80/search',
                'patterns': []
            },
            {
                'url':      'https://wikipedia.org',
                'patterns': ['home']
            },
            {
                'url':      'http://sv.wikipedia.org/wiki/Leoš_Janáček',
                'patterns': ['Leoš Janáček', 'Sånger', 'Körmusik', 'Källor']
            }
        ]

        http_watchdog = HttpWatchdog(100, input_page_configs)
        page_configs = http_watchdog.page_configs

        self.assertEqual(len(page_configs), 3)

        for i in range(len(input_page_configs)):
            self.assertEqual(page_configs[i]['url'], input_page_configs[i]['url'])

            for j in range(len(input_page_configs[i]['patterns'])):
                self.assertEqual(page_configs[i]['regexes'][j].pattern, input_page_configs[i]['patterns'][j])
