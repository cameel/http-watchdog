""" Main block of code. Creates all necessary object instances and puts things in motion. """

import sys
import errno
import logging
from queue import Queue

from .report_server    import ReportServer
from .http_watchdog    import HttpWatchdog
from .settings_manager import SettingsManager, ConfigurationError

logger = logging.getLogger(__name__)

def configure_console_logging(logger, level):
    """ Makes specified logger print information to the console """
    formatter = logging.Formatter('%(message)s')

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)

def configure_file_logging(logger, level, log_path):
    """ Makes specified logger print information to specified file.
        The file will be appended to if it already exists.
    """

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    handler = logging.FileHandler(log_path)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)

def configure_logging():
    """ Configures the top-level logger """

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    configure_console_logging(root_logger, logging.INFO)
    configure_file_logging(root_logger, logging.DEBUG, 'http_watchdog.log')

def gather_settings():
    """ Creates SettingsManager and orders it to gather setting values from requirement file, command line and defaults """

    try:
        settings_manager = SettingsManager()
        settings_manager.gather()
    except ConfigurationError as exception:
        logger.error("There are errors in the requirement file or command-line values:")
        logger.error(str(exception))
        logger.debug("", exc_info = True)
        sys.exit(1)

    return settings_manager

def create_watchdog(settings_manager):
    """ Creates an instance of the watchdog """

    return HttpWatchdog(settings_manager.get('probe_interval'), settings_manager.get('pages'))

def start_report_server(settings_manager, watchdog):
    """ Starts a HTTP server that serves a page describing latest probing results """

    exception_queue = Queue()
    report_server = ReportServer(settings_manager.get('port'), watchdog, exception_queue)
    report_server.start()

    return (report_server, exception_queue)

def run_watchdog(settings_manager, watchdog, exception_queue):
    """ Starts an infinite loop executing watchdog probes """

    try:
        watchdog.run_forever(exception_queue)
    except PermissionError as exception:
        assert exception.errno in [errno.EACCES, errno.EPERM]
        logger.error("ERROR: %s. Are you sure you have enough privileges to bind to port %d? You can use --port option to select a different port.", str(exception), settings_manager.get('port'))
    except OSError as exception:
        if exception.errno == errno.EADDRINUSE:
            logger.error("ERROR: Port %d is in use by a different server or is still in TIME_WAIT state after previous use. Please select a different one or wait a while.", settings_manager.get('port'))
        else:
            raise
    except KeyboardInterrupt:
        logger.info("Caught KeyboardInterrupt. Exiting.")

        # Exit without error. Ctrl+C is the expected way of closing
        # this application.
        sys.exit(0)

def main():
    """ Runs the application """

    configure_logging()

    settings_manager                 = gather_settings()
    watchdog                         = create_watchdog(settings_manager)
    (report_server, exception_queue) = start_report_server(settings_manager, watchdog)

    run_watchdog(settings_manager, watchdog, exception_queue)
