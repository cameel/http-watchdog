import sys
import errno
import logging
import yaml
from argparse     import ArgumentParser
from queue        import Queue
from urllib.parse import urlparse

from report_server import ReportServer
from http_watchdog import HttpWatchdog

DEFAULT_PROBE_INTERVAL = 5 * 60
DEFAULT_PORT           = 80

logger = logging.getLogger(__name__)

class ConfigurationError(Exception): pass

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

