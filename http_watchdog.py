import re
import time
import http.client
import logging
import yaml
from argparse   import ArgumentParser
from contextlib import closing

from url_utils     import split_url, join_url

DEFAULT_PROBE_INTERVAL = 10

logger = logging.getLogger(__name__)

class HttpWatchdog:
    def __init__(self, probe_interval, page_configs):
        self.probe_interval = probe_interval
        self.page_configs   = []

        logger.debug("Probing interval: %d seconds", self.probe_interval)

        for page_config in page_configs:
            (host, port, path_and_query) = split_url(page_config['url'])

            self.page_configs.append({
                'host':    host,
                'port':    port,
                'path':    path_and_query,
                'regexes': [re.compile(pattern) for pattern in page_config['patterns']]
            })
            logger.debug("Probe URL: %s", join_url(host, port, path_and_query))
            logger.debug("Probe patterns: %s", ' AND '.join(page_config['patterns']))

        logger.debug("Watchdog initialized\n")

    def probe(self):
        for page_config in self.page_configs:
            logger.debug("Probing %s", join_url(page_config['host'], page_config['port'], page_config['path']))

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
                    pattern_found = True
                    for regex in page_config['regexes']:
                        match = regex.search(page_content)
                        pattern_found &= (match != None)

                        logger.debug("Pattern '%s': %s", regex.pattern, ("match at {}".format(match.start()) if pattern_found else "no match"))

                        if not pattern_found:
                            break

                    yield {
                        'result': 'MATCH' if pattern_found else 'NO MATCH',
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
        logger.info("Starting HTTP watchdog in an infinite loop. Use Ctrl+C to stop.\n")

        probe_index = 0
        while True:
            logger.debug("Starting probe %d", probe_index + 1)

            total_http_time = 0
            for (i, result) in enumerate(self.probe()):
                url = join_url(self.page_configs[i]['host'], self.page_configs[i]['port'], self.page_configs[i]['path'])

                assert result['result'] in ['MATCH', 'NO MATCH', 'HTTP ERROR']

                if result['result'] == 'HTTP ERROR':
                    status_string = "{result} {http_status} {http_reason}".format(**result)
                else:
                    status_string = result['result']

                logger.info("%s: %s (%0.0f ms)", url, status_string, result['time'] * 1000)

                total_http_time += result['time']

            logger.info("Probe %d finished. Total HTTP time: %0.3f s\n", probe_index + 1, total_http_time)

            probe_index += 1
            time.sleep(self.probe_interval)

def configure_console_logging(level):
    root_logger = logging.getLogger()

    formatter = logging.Formatter('%(message)s')

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)

def configure_file_logging(level, log_path):
    root_logger = logging.getLogger()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    handler = logging.FileHandler(log_path)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)

def parse_command_line():
    parser = ArgumentParser(description = "A tool for monitoring remote documents available over HTTP.")
    parser.add_argument('requirement_file_path',
        help    = "The file that lists the URL to be monitored and their requirements",
        action  = 'store',
        type    = str
    )
    parser.add_argument('--probe-interval',
        help    = "The time to wait between subsequent probes. Default is {}".format(DEFAULT_PROBE_INTERVAL),
        dest    = 'probe_interval',
        action  = 'store',
        type    = int
    )

    return parser.parse_args()

if __name__ == '__main__':
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    configure_console_logging(logging.INFO)
    configure_file_logging(logging.DEBUG, 'http_watchdog.log')

    command_line_namespace = parse_command_line()

    with open(command_line_namespace.requirement_file_path) as requirement_file:
        # TODO: Validate config file with a schema
        requirements = yaml.load(requirement_file)

    if not 'pages' in requirements:
        # FIXME: Use specific exception type
        raise Exception("'pages' key missing from requirement file")

    # FIXME: Make sure it's really an integer
    if command_line_namespace.probe_interval != None:
        probe_interval = command_line_namespace.probe_interval
    elif 'probe-interval' in requirements:
        probe_interval = requirements['probe-interval']
    else:
        probe_interval = DEFAULT_PROBE_INTERVAL

    page_configs = requirements['pages']

    watchdog = HttpWatchdog(probe_interval, page_configs)

    watchdog.run_forever()
