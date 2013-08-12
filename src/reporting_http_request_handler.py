""" Definition of ReportingHTTPRequestHandler class """

import http.client
from http.server import BaseHTTPRequestHandler

from .report_page_generator import ReportPageGenerator

class ReportingHTTPRequestHandler(BaseHTTPRequestHandler):
    """ A handler for an instance of a server from socketserver module.
        The handler uses ReportPageGenerator to serve a page with detailed
        status of the HTTP watchdog.
    """

    REPORT_PAGE_PATH = '/'

    def do_HEAD(self):
        """ Responds to HEAD request """

        if self.path == self.REPORT_PAGE_PATH:
            self.send_response(http.client.OK)
            self.send_header("Content-type", "text/html")
        else:
            self.send_response(http.client.NOT_FOUND)
            self.send_header("Content-type", "text/html")

        self.end_headers()

    def do_GET(self):
        """ Responds to GET request """

        self.do_HEAD()

        if self.path == self.REPORT_PAGE_PATH:
            probe_results = self.server.probe_data_provider.probe_results
            page_configs  = self.server.probe_data_provider.page_configs

            page_content = ReportPageGenerator.generate_report(probe_results, page_configs)
        else:
            page_content = ReportPageGenerator.generate_error_404_page(report_page_path = self.REPORT_PAGE_PATH)

        self.wfile.write(page_content.encode('utf-8'))
