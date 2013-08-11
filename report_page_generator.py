import os
from datetime import datetime

class ReportPageGenerator:
    REPORT_DIR        = 'report-templates'
    BOOTSTRAP_VERSION = '2.3.2'

    @classmethod
    def page_with_layout(cls, title, body, extra_style = ''):
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
        assert len(probe_results) == len(page_configs)

        with open(os.path.join(cls.REPORT_DIR, 'report.html')) as page_template_file:
            page_template = page_template_file.read()

        with open(os.path.join(cls.REPORT_DIR, 'report.css')) as style_file:
            style = style_file.read()

        table_body = ""
        for (result, config) in zip(probe_results, page_configs):
            if result != None:
                assert result['result'] in ['MATCH', 'NO MATCH', 'HTTP ERROR', 'CONNECTION ERROR']

                status              = result['result']
                http_status         = (str(result['http_status']) if result['http_status'] != None else '') + ' ' + result['reason']
                request_duration    = '{:0.0f} ms'.format(result['request_duration'] * 1000)
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
        with open(os.path.join(cls.REPORT_DIR, 'error-404.html')) as page_template_file:
            page_template = page_template_file.read()

        body = page_template.format(report_page_path = report_page_path)

        return cls.page_with_layout("HTTP watchdog report", body)
