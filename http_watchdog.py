import re
import time
import http.client
from contextlib   import closing
from urllib.parse import urlparse

class HttpWatchdog:
    def __init__(self, probe_interval, page_configs):
        self.probe_interval = probe_interval
        self.page_configs   = []

        print("Probe interval: {} seconds".format(self.probe_interval))

        for page_config in page_configs:
            (host, port, path_and_query) = self._split_url(page_config['url'])

            self.page_configs.append({
                'host':  host,
                'port':  port,
                'path':  path_and_query,
                'regex': re.compile(page_config['pattern'])
            })

            print("Watching url: {}".format(self._join_url(host, port, path_and_query)))

    @classmethod
    def _split_url(cls, url):
        parsed_url = urlparse(url)

        # FIXME: Don't ignore protocol
        # FIXME: Don't discard username and password
        if not ':' in parsed_url.netloc:
            host = parsed_url.netloc
            port = ''
        else:
            host, port = parsed_url.netloc.split(':')

        port = int(port) if port != '' else 80

        # The fragment part (after #) can be discarded. It's only relevant to a client.
        path           = parsed_url.path if parsed_url.path != '' else '/'
        path_and_query = path + ('?' + parsed_url.query if parsed_url.query != '' else '')

        return (host, port, path_and_query)

    @classmethod
    def _join_url(cls, host, port, path_and_query):
        return host + (':' + str(port) if port != 80 else '') + path_and_query

    def probe(self):
        for page_config in self.page_configs:
            with closing(http.client.HTTPConnection(page_config['host'], page_config['port'])) as connection:
                # NOTE: We're interested in wall-time here, not CPU time, hence time() rather than clock()
                # NOTE: getresponse() probably performs the whole operation of receiving the data from
                # the server rather than just passing the data already received by the OS and for that
                # reason it's also included in timing.
                start_time = time.time()

                connection.request("GET", page_config['path'])
                response = connection.getresponse()

                end_time = time.time()

                if response.status == http.client.OK:
                    # FIXME: What if the content is a binary file?
                    page_content  = str(response.read())
                    pattern_found = (page_config['regex'].search(page_content) != None)

                    yield {
                        'result': 'PATTERN FOUND' if pattern_found else 'PATTERN NOT FOUND',
                        'time':   end_time - start_time
                    }
                else:
                    yield {
                        'result':      'HTTP ERROR',
                        'http_status': response.status,
                        'http_reason': response.reason,
                        'time':        end_time - start_time
                    }

    def run_forever(self):
        while True:
            total_http_time = 0
            for (i, result) in enumerate(self.probe()):
                url = self._join_url(self.page_configs[i]['host'], self.page_configs[i]['port'], self.page_configs[i]['path'])

                assert result['result'] in ['PATTERN FOUND', 'PATTERN NOT FOUND', 'HTTP ERROR']

                if result['result'] == 'HTTP ERROR':
                    status_string = "{result} {http_status} {http_reason}".format(**result)
                else:
                    status_string = result['result']

                print("{}: {} ({:0.0f} ms)".format(url, status_string, result['time'] * 1000))

                total_http_time += result['time']

            print("Probe finished. Total HTTP time: {:0.3f} s\n".format(total_http_time))
            time.sleep(self.probe_interval)

if __name__ == '__main__':
    watchdog = HttpWatchdog(10, [
        {
            'url':     'http://www.google.pl',
            'pattern': r'\<\/html\>'
        },
        {
            'url':     'http://en.wikipedia.org/wiki/Python_(programming_language)',
            'pattern': r'spam'
        },
        {
            'url':     'https://en.wikipedia.org/null',
            'pattern': r'test'
        }
    ])

    watchdog.run_forever()
