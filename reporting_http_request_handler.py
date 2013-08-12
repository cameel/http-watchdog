import http.client
from http.server import BaseHTTPRequestHandler

from report_page_generator import ReportPageGenerator

class ReportingHTTPRequestHandler(BaseHTTPRequestHandler):
    REPORT_PAGE_PATH = '/'

    def do_HEAD(self):
        if self.path == self.REPORT_PAGE_PATH:
            self.send_response(http.client.OK)
            self.send_header("Content-type", "text/html")
        else:
            self.send_response(http.client.NOT_FOUND)
            self.send_header("Content-type", "text/html")

        self.end_headers()

    def do_GET(self):
        self.do_HEAD()

        if self.path == self.REPORT_PAGE_PATH:
            probe_results = self.server.probe_data_provider.probe_results
            page_configs  = self.server.probe_data_provider.page_configs

            page_content = ReportPageGenerator.generate_report(probe_results, page_configs)
        else:
            page_content = ReportPageGenerator.generate_error_404_page(report_page_path = self.REPORT_PAGE_PATH)

        self.wfile.write(page_content.encode('utf-8'))
