""" Definition of ReportServer class that runs a HTTP server in a separate thread
    and serves reports generated with ReportPageGenerator.
"""

import sys
import logging
from threading    import Thread
from socketserver import TCPServer

from .reporting_http_request_handler import ReportingHTTPRequestHandler

# NOTE: According to the docs the logging module is thread-safe:
# http://docs.python.org/3.3/library/logging.html#thread-safety
logger = logging.getLogger(__name__)

class ReportServer:
    def __init__(self, port, probe_data_provider, exception_queue):
        """ Creates an instance of the class that holds data for the server thread.

            - port: the port at which the HTTP server should be started.
            - probe_data_provider: an object with probe_results and page_configs
              properties that pass results and configuration from the watchdog.
              The properties should be safe to read from a different thread.
            - expception_queue: a thread safe queue that can be used to pass
              exception information to the main thread. Possibly an instance of
              queue.Queue.
        """

        self.port                = port
        self.probe_data_provider = probe_data_provider
        self.exception_queue     = exception_queue

    def _main(self):
        """ The main procedure of the thread. Runs server and is expected to be 
            either stopped by the user with KeyboardInterrupt or killed when the
            program exits.

            Exceptions are passed to the main thread through queue passed to
            the constructor.
        """

        try:
            httpd = TCPServer(("", self.port), ReportingHTTPRequestHandler)

            logger.info("Starting HTTP server at port %d\n", self.port)

            httpd.probe_data_provider = self.probe_data_provider
            httpd.serve_forever()
        except:
            logger.debug("An exception has interrupted the server thread (passed to the main thread)")
            self.exception_queue.put(sys.exc_info())

    def start(self):
        """ Starts the thread. Returns thread instance. """
        thread = Thread(target = self._main)

        # Marking the tread as daemon will cause it to get killed automatically
        # when the main process exits.
        thread.daemon = True

        thread.start()

        return thread
