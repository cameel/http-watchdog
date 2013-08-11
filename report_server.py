import logging
from threading    import Thread
from socketserver import TCPServer

from reporting_http_request_handler import ReportingHTTPRequestHandler

# FIXME: Thread-safe logging
logger = logging.getLogger(__name__)

class ReportServer:
    def __init__(self, port, probe_data_provider):
        self.port                = port
        self.probe_data_provider = probe_data_provider

    def _main(self):
        httpd = TCPServer(("", self.port), ReportingHTTPRequestHandler)

        logger.info("Starting HTTP server at port %d\n", self.port)

        httpd.probe_data_provider = self.probe_data_provider
        httpd.serve_forever()

    def start(self):
        thread = Thread(target = self._main)
        thread.start()

        return thread
