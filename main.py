import sys
import errno
import logging
from queue import Queue

from report_server    import ReportServer
from http_watchdog    import HttpWatchdog
from settings_manager import SettingsManager, ConfigurationError

logger = logging.getLogger(__name__)

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

if __name__ == '__main__':
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    configure_console_logging(logging.INFO)
    configure_file_logging(logging.DEBUG, 'http_watchdog.log')

    try:
        settings_manager = SettingsManager()
        settings_manager.gather()
    except ConfigurationError as exception:
        logger.error("There are errors in the requirement file or command-line values:")
        logger.error(str(exception))
        logger.debug("", exc_info = True)
        sys.exit(1)

    watchdog = HttpWatchdog(settings_manager.get('probe_interval'), settings_manager.get('pages'))

    exception_queue = Queue()
    report_server = ReportServer(settings_manager.get('port'), watchdog, exception_queue)
    report_server.start()

    try:
        watchdog.run_forever(exception_queue)
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

