""" Definition of ReportPageGenerator class that provides methods for assembling
    all HTML pages needed to describe the watchdog status.
"""

import os
from datetime import datetime

from .probe_result import ProbeResult

class ReportPageGenerator:
    """ The class uses a set of templates stored in REPORT_DIR to construct report and
        error pages. All pages are wrapper in a layout that contains shared pieces of HTML.
        Twitter Bootstrap is included to make the pages a bit prettier but they are meant
        to be perfectly readable even without it.

        The templates are not meant to be modified by the end-user (there is not enough
        error checking and validation to make it easy).
    """

    REPORT_DIR        = 'src/report-templates'
    BOOTSTRAP_VERSION = '2.3.2'

    @classmethod
    def page_with_layout(cls, title, body, extra_style = ''):
        """ Wraps specified content in a layout. title is the content for the <title> tag
            and extra_style is the CSS to be placed inside a <script> tag in <head>.

            Template is read from the layout.html file in REPORT_DIR.
        """

        with open(os.path.join(cls.REPORT_DIR, 'layout.html')) as layout_template_file:
            layout_template = layout_template_file.read()

        return layout_template.format(
            title             = title,
            body              = body,
            bootstrap_version = cls.BOOTSTRAP_VERSION,
            style             = extra_style
        )

    @classmethod
    def generate_report(cls, probe_results, page_configs):
        """ Generates a page detailing the results for watchdog probes.

            Template is read from the report.html file in REPORT_DIR. The CSS for the page
            is in report.css.

            probe_results and page_configs are expected to come from the properties of the same
            names on a HttpWatchdog instance.
        """

        assert len(probe_results) == len(page_configs)

        with open(os.path.join(cls.REPORT_DIR, 'report.html')) as page_template_file:
            page_template = page_template_file.read()

        with open(os.path.join(cls.REPORT_DIR, 'report.css')) as style_file:
            style = style_file.read()

        table_body = ""
        for (result, config) in zip(probe_results, page_configs):
            if result != None:
                assert result['result'] in [ProbeResult.MATCH, ProbeResult.NO_MATCH, ProbeResult.HTTP_ERROR, ProbeResult.CONNECTION_ERROR]

                status              = ProbeResult.to_str(result['result'])
                http_status         = (str(result['http_status']) if result['http_status'] != None else '') + ' ' + result['reason']
                request_duration    = '{:0.0f} ms'.format(result['request_duration'] * 1000) if result['request_duration'] != None else ''
                seconds_since_probe = '{} seconds ago'.format(round((datetime.utcnow() - result['last_probed_at']).total_seconds()))
                last_probed_at      = str(result['last_probed_at']) + " UTC"
            else:
                status              = 'NOT PROBED YET'
                http_status         = ''
                request_duration    = ''
                seconds_since_probe = ''
                last_probed_at      = 'NOT PROBED YET'

            table_body += (
                "<tr>\n"
                "   <td><a href='{url}'>{url}</a></td>\n"
                "   <td class='{status_class}'>{status}</td>\n"
                "   <td>{http_status}</td>\n"
                "   <td>{request_duration}</td>\n"
                "   <td title='{last_probed_at}'>{seconds_since_probe}</td>\n"
                "</tr>\n"
            ).format(
                url                 = config['url'],
                status              = status,
                status_class        = status.lower().replace(' ', '-'),
                http_status         = http_status,
                request_duration    = request_duration,
                last_probed_at      = last_probed_at,
                seconds_since_probe = seconds_since_probe
            )

        return cls.page_with_layout(
            "HTTP watchdog report",
            page_template.format(table_body = table_body),
            style
        )

    @classmethod
    def generate_error_404_page(cls, report_page_path):
        """ Generates a page for HTTP status 404.

            Template is read from the error-404.html file in REPORT_DIR.

            report_page_path is the path to the report page that can be used to link to it.
        """

        with open(os.path.join(cls.REPORT_DIR, 'error-404.html')) as page_template_file:
            page_template = page_template_file.read()

        body = page_template.format(report_page_path = report_page_path)

        return cls.page_with_layout("HTTP watchdog report", body)
