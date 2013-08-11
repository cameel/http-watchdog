import os

from url_utils import split_url, join_url

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

        table_body = ""
        for (result, config) in zip(probe_results, page_configs):
            table_body += (
                "<tr>\n"
                "   <td><a href='http://{url}'>{url}</a></td>\n"
                "   <td>{status}</td>\n"
                "   <td>{time:0.0f} ms</td>\n"
                "</tr>\n"
            ).format(
                url    = join_url(config['host'], config['port'], config['path']),
                status = result['result']       if result != None else 'NOT CHECKED YET',
                time   = result['time'] * 1000  if result != None else ''
            )

        return cls.page_with_layout("HTTP watchdog report", page_template.format(table_body = table_body))

    @classmethod
    def generate_error_404_page(cls, report_page_path):
        with open(os.path.join(cls.REPORT_DIR, 'error-404.html')) as page_template_file:
            page_template = page_template_file.read()

        body = page_template.format(report_page_path = report_page_path)

        return cls.page_with_layout("HTTP watchdog report", body)
