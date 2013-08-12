import sys
import errno
import re
import time
import http.client
import logging
import yaml
from datetime     import datetime
from argparse     import ArgumentParser
from queue        import Queue
from urllib.parse import urlparse, quote as urllib_quote

from report_server import ReportServer
from probe_result  import ProbeResult

DEFAULT_PROBE_INTERVAL = 5 * 60
DEFAULT_PORT           = 80

logger = logging.getLogger(__name__)

class ConfigurationError(Exception):    pass
class CharsetDetectionError(Exception): pass

class HttpWatchdog:
    CONNECTION_TIMEOUT = 30
    DEFAULT_PORTS      = {
        'http':  80,
        'https': 443,
    }

    def __init__(self, probe_interval, page_configs):
        self._probe_interval = probe_interval
        self._page_configs   = []

        logger.debug("Probing interval: %d seconds", self._probe_interval)

        for page_config in page_configs:
            self._page_configs.append({
                'url':     page_config['url'],
                'regexes': [re.compile(pattern) for pattern in page_config['patterns']]
            })
            logger.debug("Probe URL: %s", page_config['url'])
            logger.debug("Probe patterns: %s", ' AND '.join(page_config['patterns']))

        self._probe_results = [None] * len(self._page_configs)

        logger.debug("Watchdog initialized\n")

    @classmethod
    def _dissect_and_escape_url(cls, parsed_url):
        assert parsed_url.scheme in cls.DEFAULT_PORTS.keys()

        if not ':' in parsed_url.netloc:
            host = parsed_url.netloc
            port = ''
        else:
            host, port = parsed_url.netloc.split(':')

        port = int(port) if port != '' else cls.DEFAULT_PORTS[parsed_url.scheme]

        # The fragment part (after #) can be discarded. It's only relevant to a client.
        path           = parsed_url.path if parsed_url.path != '' else '/'
        path_and_query = path + ('?' + parsed_url.query if parsed_url.query != '' else '')

        # TODO: Omitting '=&?/' seems enough for most cases but it's probably not a complete set of special.
        # characters. This can be made more robust.
        escaped_host           = host.encode('idna').decode('ascii')
        escaped_path_and_query = urllib_quote(path_and_query, '=&?/')

        return (escaped_host, port, escaped_path_and_query)

    @classmethod
    def _detect_response_charset(cls, content_type):
        if content_type == None:
            return None

        # FIXME: Are escaped semicolons or equals signs possible here?
        fields = content_type.split(';')
        result = None
        for field in fields:
            tokens = field.split('=')

            # I'm not sure if 'charset' supposed to be case-sensitive or not but it's highly unlikely that
            # there are multiple valid possibilities differing only with case and taking into account the current
            # tangled mess of server implementations it's better to accept any case.
            if len(tokens) == 2 and tokens[0].strip().lower() == 'charset':
                if result != None:
                    # TODO: Say which url this message pertains to
                    raise CharsetDetectionError("Found multiple charset fields in the Content-Type header: {}".format(content_type))

                return tokens[1].strip()

        return None

    def probe(self):
        for page_config in self._page_configs:
            logger.debug("Probing %s", page_config['url'])

            parsed_url = urlparse(page_config['url'])
            assert parsed_url.scheme in ['http', 'https'], 'Unsupported protocols should not pass through validation performed earlier'

            (host, port, path_and_query) = self._dissect_and_escape_url(parsed_url)
            connection_class = http.client.HTTPConnection if parsed_url.scheme == 'http' else http.client.HTTPSConnection

            result       = None
            page_content = None
            start_time   = None
            end_time     = None
            try:
                connection = connection_class(host, port, timeout = self.CONNECTION_TIMEOUT)
                logger.debug("GET %s://%s:%d%s", parsed_url.scheme, host, port, path_and_query)

                # NOTE: We're interested in wall-time here, not CPU time, hence time() rather than clock()
                # NOTE: getresponse() probably performs the whole operation of receiving the data from
                # the server rather than just passing the data already received by the OS and for that
                # reason it's also included in timing.
                start_time = time.time()

                try:
                    connection.request("GET", path_and_query)
                    response = connection.getresponse()
                finally:
                    end_time = time.time()

                if response.status == http.client.OK:
                    # FIXME: What if the content is a binary file?
                    content_type     = response.getheader('Content-Type')
                    response_charset = self._detect_response_charset(content_type)
                    logger.debug("Got response with 'Content-Type': '%s'; Detected charset: '%s'", content_type, response_charset)

                    page_content = response.read().decode(response_charset or 'utf-8')

                connection.close()

            except (AssertionError, TypeError, SyntaxError, ValueError):
                # We're only interested in connection-related failures. There's no easy and future-proof way to
                # discern them from exceptions caused by programmer's mistakes but we can at least make our life
                # easier by excluding some common ones.
                raise
            except Exception as exception:
                # All other non-base exceptions should be caught and presented to the user. They're silenced but still
                # get logged. This is a bit heavy-handed but things can go wrong at many different levels of the stack
                # and it's hard to create a comprehensive list of possible exceptions. It's better to report an error
                # late than let the program crash here if the network goes down for a while.
                logger.debug("A GET request has been interrupted by an exception", exc_info = True)

                result      = ProbeResult.CONNECTION_ERROR
                reason      = str(exception)
                http_status = None

            if result == None:
                if response.status == http.client.OK:
                    assert page_content != None

                    pattern_found = True
                    for regex in page_config['regexes']:
                        match = regex.search(page_content)
                        pattern_found &= (match != None)

                        if not pattern_found:
                            logger.debug("Pattern '%s': no match", regex.pattern)
                            break
                        else:
                            logger.debug("Pattern '%s': match at %d = '%s'", regex.pattern, match.start(), match.group(0))

                    result = ProbeResult.MATCH if pattern_found else ProbeResult.NO_MATCH
                else:
                    result = ProbeResult.HTTP_ERROR

                reason      = response.reason
                http_status = response.status

            assert start_time == None and end_time == None or end_time >= start_time
            yield {
                'result':           result,
                'http_status':      http_status,
                'reason':           reason,
                'last_probed_at':   datetime.utcnow(),
                'request_duration': end_time - start_time if end_time != None else None
            }

    @property
    def probe_results(self):

        return self._probe_results

    @property
    def page_configs(self):

        return self._page_configs

    def process_asynchronous_exceptions(self, exception_queue):
        logger.debug("Processing exceptions from other threads ({} messages)".format(exception_queue.qsize()))

        while not exception_queue.empty():
            (exc_type, exc_obj, exc_trace) = exception_queue.get_nowait()
            raise exc_type.with_traceback(exc_obj, exc_trace)

    def run_forever(self, exception_queue):
        logger.info("Starting HTTP watchdog in an infinite loop. Use Ctrl+C to stop.\n")

        probe_index = 0
        while True:
            logger.debug("Starting probe %d", probe_index + 1)

            total_http_time = 0
            for (i, result) in enumerate(self.probe()):
                self.process_asynchronous_exceptions(exception_queue)

                self._probe_results[i] = result

                assert result['result'] in [ProbeResult.MATCH, ProbeResult.NO_MATCH, ProbeResult.HTTP_ERROR, ProbeResult.CONNECTION_ERROR]

                # By default inform only about the failures
                level = logging.INFO if result['result'] != ProbeResult.MATCH else logging.DEBUG
                status_string = "{} {} {}".format(
                    ProbeResult.to_str(result['result']),
                    result['http_status'] if result['http_status'] != None else '',
                    result['reason']
                )

                duration = " ({:0.0f} ms)".format(result['request_duration'] * 1000) if result['request_duration'] != None else ''
                logger.log(level, "%s: %s%s", self._page_configs[i]['url'], status_string, duration)

                total_http_time += result['request_duration'] if result['request_duration'] != None else 0

            logger.debug("Probe %d finished. Total HTTP time: %0.3f s", probe_index + 1, total_http_time)

            self.process_asynchronous_exceptions(exception_queue)

            probe_index += 1

            logger.debug("Going to sleep for %d seconds\n", self._probe_interval)
            time.sleep(self._probe_interval)

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
    parser.add_argument('--port',
        help    = "Port for the report server. Default is {}".format(DEFAULT_PORT),
        dest    = 'port',
        action  = 'store',
        type    = int
    )

    return parser.parse_args()

def get_optional_integer_setting(setting_name, default_value, command_line_namespace, requirements):
    internal_setting_name = setting_name.replace('-', '_')

    command_line_value = getattr(command_line_namespace, internal_setting_name)

    try:
        if command_line_value != None:
            return int(command_line_value)
        elif setting_name in requirements:
            return int(requirements[setting_name])
        else:
            return default_value
    except ValueError as exception:
        raise ConfigurationError("'{}' must be a an integer".format(setting_name)) from exception

def read_settings():
    command_line_namespace = parse_command_line()

    with open(command_line_namespace.requirement_file_path) as requirement_file:
        requirements = yaml.load(requirement_file)

    settings = {}
    warnings = []

    if not 'pages' in requirements:
        raise ConfigurationError("'pages' key missing from requirement file")

    settings['pages'] = requirements['pages']

    if not isinstance(settings['pages'], (list, tuple)):
        # The intention here is to check whether 'pages' was a YAML collection. If it was, it
        # should get converted to list (added also tuple just in case it changes in the future).
        # A more comprehensive check that includes list/tuple-like objects not necessarily inheriting from
        # list or tuple, excludes string-like objects and is future-proof is hard to devise if not impossible.
        # Let's just leave things simple - if pyyaml decides to start using a different type
        # we'll notice it anyway because the program will stop working with existing requirement files.
        # And no, trying to use the object and checking for TypeError is not an acceptable solution because there
        # are too many other things that can cause TypeError that we wouldn't like silently ignored.
        raise ConfigurationError("'pages' must be a collection (got {} of type {})".format(settings['pages'], type(settings['pages'])))

    if len(settings['pages']) == 0:
        raise ConfigurationError("No page configurations specified.")

    for page_config in settings['pages']:
        for key in ['url', 'patterns']:
            if not key in page_config:
                raise ConfigurationError("At least one of the page configs is missing '{}' key".format(key))

        if not isinstance(page_config['url'], str):
            raise configurationerror("'url' must be a string (got {} of type {})".format(page_config['url'], type(page_config['url'])))

        parsed_url = urlparse(page_config['url'])
        if not parsed_url.scheme in ['http', 'https']:
            raise ConfigurationError("Unsupported protocol: '{}'".format(parsed_url.scheme))

        if parsed_url.username != None or parsed_url.password != None:
            raise ConfigurationError("URL contains username and/or password. This program does not support HTTP authentication. URL in question: '{}'".format(page_config['url']))

        if not isinstance(page_config['patterns'], (list, tuple)):
            raise ConfigurationError("'patterns' must be a collection (got {} of type {})".format(page_config['patterns'], type(page_config['patterns'])))

        for pattern in page_config['patterns']:
            if not isinstance(pattern, str):
                raise ConfigurationError("'patterns' must be a string (got {} of type {})".format(pattern, type(pattern)))

        if len(page_config['patterns']) == 0:
            warnings.append("No patterns specified for url {}.".format(page_config['url']))

    settings['probe_interval'] = get_optional_integer_setting('probe-interval', DEFAULT_PROBE_INTERVAL, command_line_namespace, requirements)
    if settings['probe_interval'] < 0:
        raise ConfigurationError("'probe-interval' must be non-negative")

    settings['port'] = get_optional_integer_setting('port', DEFAULT_PORT, command_line_namespace, requirements)
    if not (0 < settings['port'] < 65535):
        raise ConfigurationError("'port' must be in range 0..65535")

    return (settings, warnings)

if __name__ == '__main__':
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    configure_console_logging(logging.INFO)
    configure_file_logging(logging.DEBUG, 'http_watchdog.log')

    try:
        (settings, warnings) = read_settings()
    except ConfigurationError as exception:
        logger.error("There are errors in the requirement file or command-line values:")
        logger.error(str(exception))
        logger.debug("", exc_info = True)
        sys.exit(1)

    for warning in warnings:
        logger.warning('WARNING: %s', warning)

    watchdog = HttpWatchdog(settings['probe_interval'], settings['pages'])

    exception_queue = Queue()
    report_server = ReportServer(settings['port'], watchdog, exception_queue)
    report_server.start()

    try:
        watchdog.run_forever(exception_queue)
    except OSError as exception:
        if exception.errno == errno.EADDRINUSE:
            logger.error("ERROR: Port %d is in use by a different server or is still in TIME_WAIT state after previous use. Please select a different one or wait a while.", settings['port'])
        else:
            raise
    except KeyboardInterrupt:
        logger.info("Caught KeyboardInterrupt. Exiting.")

        # Exit without error. Ctrl+C is the expected way of closing
        # this application.
        sys.exit(0)
