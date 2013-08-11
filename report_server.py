import sys
import logging
from threading    import Thread
from socketserver import TCPServer

from reporting_http_request_handler import ReportingHTTPRequestHandler

# FIXME: Thread-safe logging
logger = logging.getLogger(__name__)

class ReportServer:
    def __init__(self, port, probe_data_provider, exception_queue):
        self.port                = port
        self.probe_data_provider = probe_data_provider
        self.exception_queue     = exception_queue

    def _main(self):
        try:
            httpd = TCPServer(("", self.port), ReportingHTTPRequestHandler)

            logger.info("Starting HTTP server at port %d\n", self.port)

            httpd.probe_data_provider = self.probe_data_provider
            httpd.serve_forever()
        except:
            logger.debug("An exception has interrupted the server thread (passed to the main thread)")
            self.exception_queue.put(sys.exc_info())

    def start(self):
        thread = Thread(target = self._main)

        # Marking the tread as daemon will cause it to get killed automatically
        # when the main process exits.
        thread.daemon = True

        thread.start()

        return thread
