""" Definition of SettingsManager class """

import logging
import yaml
from argparse     import ArgumentParser
from urllib.parse import urlparse

DEFAULT_PROBE_INTERVAL = 5 * 60
DEFAULT_PORT           = 80

logger = logging.getLogger(__name__)

class ConfigurationError(Exception): pass

class SettingsManager:
    """ A class that gathers settings from requirement file, command line and defaults,
        decides which ones have priority, validates them and stores for later access.
    """

    def __init__(self):
        """ Creates a manager with an empty set of settings """

        self._settings = {}

    def get(self, setting_name):
        """ Returns specified setting """
        assert setting_name in self._settings

        return self._settings[setting_name]

    def gather(self):
        """ Reads command line parameters, based on that finds the requirement file,
            reads it and performs validation. When it's done the manager contains a
            set of settings ready to be used.
        """

        command_line_namespace = self._parse_command_line()

        (self._settings, warnings) = self._read_and_validate(command_line_namespace)

        for warning in warnings:
            logger.warning('WARNING: %s', warning)

    @classmethod
    def _parse_command_line(cls):
        """ Parses the values passed by the user on the command line according to a set
            of internal rules. Returns a namespace object that contains all required and possibly
            some optional settings.
        """

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

    @classmethod
    def _get_optional_integer_setting(cls, setting_name, default_value, command_line_namespace, requirements):
        """ Tries to find specified setting in requirement file and on the command line.
            If neither is available, uses specified default. If both are available, the value
            from command line has higher priority.
        """

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

    @classmethod
    def _read_and_validate(cls, command_line_namespace):
        """ Reads requirements from the file specified on the command line and
            validates its contents. Returns a dict with processed settings, ready
            to be used.
        """

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

        settings['probe_interval'] = cls._get_optional_integer_setting('probe-interval', DEFAULT_PROBE_INTERVAL, command_line_namespace, requirements)
        if settings['probe_interval'] < 0:
            raise ConfigurationError("'probe-interval' must be non-negative")

        settings['port'] = cls._get_optional_integer_setting('port', DEFAULT_PORT, command_line_namespace, requirements)
        if not (0 < settings['port'] < 65535):
            raise ConfigurationError("'port' must be in range 0..65535")

        return (settings, warnings)
