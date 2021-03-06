""" Definition of HttpWatchdog class that provides facilities for downloading web pages
    over HTTP and checking them for pattern matches.
"""

import sys
import errno
import re
import time
import http.client
import logging
from datetime     import datetime
from urllib.parse import urlparse, quote as urllib_quote

from .probe_result import ProbeResult

logger = logging.getLogger(__name__)

class CharsetDetectionError(Exception): pass

class HttpWatchdog:
    """ This ciass is a simple HTTP client that runs in infinite loop (run_forever()) which
        periodically checks a set of web pages for HTTP errors and lack of pattern matches.

        The class makes extensive use of logging to provide both information interesting for
        the end user (INFO level) and additional information useful for diagnosing problems
        (DEBUG level). Since the purpose is to alter the administrator when a site goes down,
        only problems are reported on the INFO level.
    """

    CONNECTION_TIMEOUT = 30
    DEFAULT_PORTS      = {
        'http':  80,
        'https': 443,
    }

    def __init__(self, probe_interval, page_configs):
        """ Creates a watchdog instance running specified configuration.

            page_configs is a list of dicts. Each dict represents one page to be probed.
            It should contain 'url' - full URL of the page and 'patterns' - a list of
            strings that will be interpreted as regular expression patterns.
        """

        self._probe_interval = probe_interval
        self._page_configs   = []

        logger.debug("Probing interval: %d seconds", self._probe_interval)

        for page_config in page_configs:
            self._page_configs.append({
                'url':     page_config['url'],
                'regexes': [re.compile(pattern) for pattern in page_config['patterns']]
            })
            logger.debug("Probe URL: %s", page_config['url'])
            logger.debug("Probe patterns: %s", ' AND '.join(page_config['patterns']))

        self._probe_results = [None] * len(self._page_configs)

        logger.debug("Watchdog initialized\n")

    @classmethod
    def _dissect_and_escape_url(cls, parsed_url):
        """ Splits a full URL into parts that can be used directly by the client to
            establish a connection and fetch the page. IDNs are converted to punycode
            and non-ASCII characters in the path and query are url-encoded.
        """

        assert parsed_url.scheme in cls.DEFAULT_PORTS.keys()

        if not ':' in parsed_url.netloc:
            host = parsed_url.netloc
            port = ''
        else:
            host, port = parsed_url.netloc.split(':')

        port = int(port) if port != '' else cls.DEFAULT_PORTS[parsed_url.scheme]

        # The fragment part (after #) can be discarded. It's only relevant to a client.
        path           = parsed_url.path if parsed_url.path != '' else '/'
        path_and_query = path + ('?' + parsed_url.query if parsed_url.query != '' else '')

        # TODO: Omitting '=&?/' seems enough for most cases but it's probably not a complete set of special.
        # characters. This can be made more robust.
        escaped_host           = host.encode('idna').decode('ascii')
        escaped_path_and_query = urllib_quote(path_and_query, '=&?/')

        return (escaped_host, port, escaped_path_and_query)

    @classmethod
    def _detect_response_charset(self, content_type):
        """ Extracts encoding information from a Content-Type HTTP header """

        if content_type == None:
            return None

        # TODO: Are escaped semicolons or equals signs possible here?
        # It seems to work in normal cirsumstances but should be made more robust.
        fields = content_type.split(';')
        result = None
        for field in fields:
            tokens = field.split('=')

            # I'm not sure if 'charset' supposed to be case-sensitive or not but it's highly unlikely that
            # there are multiple valid possibilities differing only with case and taking into account the current
            # tangled mess of server implementations it's better to accept any case.
            if len(tokens) == 2 and tokens[0].strip().lower() == 'charset':
                if result != None:
                    # TODO: Say which url this message pertains to
                    raise CharsetDetectionError("Found multiple charset fields in the Content-Type header: {}".format(content_type))

                result = tokens[1].strip()

        return result

    @classmethod
    def _fetch_page(cls, url):
        """ Attempts to fetch the content of specified web page. Returns a tuple containing the content
            and some additional information about eventual errors and timing.

            The tuple contains:
                - page content: the page content convert to a unicode string if the connection was successfully
                  estabilished and request returned 200 OK. None otherwise.
                - result - a value from ProbeResult enum
                - http_status - the returned HTTP status if the request was performed (i.e. there were no connection errors).
                  None otherwise.
                - reason - A textual description of 'result'. If http_status is not None this is the HTTP reason.
                - start_time - Request start time if the request was performed or None.
                - end_time - Request end time if the request was performed or None.
        """

        parsed_url = urlparse(url)
        assert parsed_url.scheme in ['http', 'https'], 'Unsupported protocols should not pass through validation performed earlier'

        (host, port, path_and_query) = cls._dissect_and_escape_url(parsed_url)
        connection_class = http.client.HTTPConnection if parsed_url.scheme == 'http' else http.client.HTTPSConnection

        result       = None
        page_content = None
        start_time   = None
        end_time     = None
        http_status  = None
        reason       = None
        try:
            connection = connection_class(host, port, timeout = cls.CONNECTION_TIMEOUT)
            logger.debug("GET %s://%s:%d%s", parsed_url.scheme, host, port, path_and_query)

            # NOTE: We're interested in wall-time here, not CPU time, hence time() rather than clock()
            # NOTE: getresponse() probably performs the whole operation of receiving the data from
            # the server rather than just passing the data already received by the OS and for that
            # reason it's also included in timing.
            start_time = time.time()

            try:
                connection.request("GET", path_and_query)
                response = connection.getresponse()
            finally:
                end_time = time.time()

            reason      = response.reason
            http_status = response.status

            if response.status == http.client.OK:
                # TODO: Add safeguards to make sure the program behaves sensibly with any input, not just text documents.
                # For example large binary files may waste a lot of bandwidth and processing power before it becomes apparent
                # that something's wrong.
                content_type     = response.getheader('Content-Type')
                response_charset = cls._detect_response_charset(content_type)
                logger.debug("Got response with 'Content-Type': '%s'; Detected charset: '%s'", content_type, response_charset)

                page_content = response.read().decode(response_charset or 'utf-8')

            connection.close()

        except (AssertionError, TypeError, SyntaxError, ValueError):
            # We're only interested in connection-related failures. There's no easy and future-proof way to
            # discern them from exceptions caused by programmer's mistakes but we can at least make our life
            # easier by excluding some common ones.
            raise
        except Exception as exception:
            # All other non-base exceptions should be caught and presented to the user. They're silenced but still
            # get logged. This is a bit heavy-handed but things can go wrong at many different levels of the stack
            # and it's hard to create a comprehensive list of possible exceptions. It's better to report an error
            # late than let the program crash here if the network goes down for a while.
            logger.debug("A GET request has been interrupted by an exception", exc_info = True)

            result      = ProbeResult.CONNECTION_ERROR
            reason      = str(exception)
            http_status = None

        return (page_content, result, http_status, reason, start_time, end_time)

    def probe(self):
        """ Iterates over all page_configs and for each one tries to fetch the page and find specified patterns.
            Only if there are no errors and all of the patterns are present, the result is ProbeResult.MATCH.
            Yields dicts describing the result (same format as in on the list returned from probe_results()).
        """

        for page_config in self._page_configs:
            logger.debug("Probing %s", page_config['url'])

            (page_content, result, http_status, reason, start_time, end_time) = self._fetch_page(page_config['url'])

            if result == None:
                if http_status == http.client.OK:
                    assert page_content != None

                    pattern_found = True
                    for regex in page_config['regexes']:
                        match = regex.search(page_content)
                        pattern_found &= (match != None)

                        if not pattern_found:
                            logger.debug("Pattern '%s': no match", regex.pattern)
                            break
                        else:
                            logger.debug("Pattern '%s': match at %d = '%s'", regex.pattern, match.start(), match.group(0))

                    result = ProbeResult.MATCH if pattern_found else ProbeResult.NO_MATCH
                else:
                    result = ProbeResult.HTTP_ERROR

            assert start_time == None and end_time == None or end_time >= start_time
            yield {
                'result':           result,
                'http_status':      http_status,
                'reason':           reason,
                'last_probed_at':   datetime.utcnow(),
                'request_duration': end_time - start_time if end_time != None else None
            }

    @property
    def probe_results(self):
        """ A list whose i-th element contains the result of probing i-th page from page_configs.
            The list should not be modified from the outside of the class.

            The watchdog never modifies the results after creating them. Every time the results are
            updated, a reference to the record is replaced with a new one that points to complete new
            record. This allows the list to be safely read asynchronously from a different thread.
        """

        return self._probe_results

    @property
    def page_configs(self):
        """ A list of configurations for the pages to be probed, obtained from the requirement file.
            The list should not be modified from the outside of the class.

            The list is never modified after watchdog construction and therefore can by safely
            read asynchronously from a different thread.
        """

        return self._page_configs

    def _process_asynchronous_exceptions(self, exception_queue):
        """ Checks specified queue for messages containing exception information from other threads.
            If there is anything in the queue, raises it.
        """

        logger.debug("Processing exceptions from other threads ({} messages)".format(exception_queue.qsize()))

        if not exception_queue.empty():
            (exc_type, exc_obj, exc_trace) = exception_queue.get_nowait()
            raise exc_type.with_traceback(exc_obj, exc_trace)

    def run_forever(self, exception_queue):
        """ Iterates probe() in a loop over and over again, sleeping between each cycle.
            Before each probe and after each cycle checks specified queue for exceptions raised by
            other threads and reraises them if there are any.

            The function never returns. It is expected to be interrupted by a KeyboardInterrupt either
            from its own thread or from the ones communication through exception_queue.
        """

        logger.info("Starting HTTP watchdog in an infinite loop. Use Ctrl+C to stop.\n")

        probe_index = 0
        while True:
            logger.debug("Starting probe %d", probe_index + 1)

            total_http_time = 0
            for (i, result) in enumerate(self.probe()):
                self._process_asynchronous_exceptions(exception_queue)

                self._probe_results[i] = result

                assert result['result'] in [ProbeResult.MATCH, ProbeResult.NO_MATCH, ProbeResult.HTTP_ERROR, ProbeResult.CONNECTION_ERROR]

                # By default inform only about the failures
                level = logging.INFO if result['result'] != ProbeResult.MATCH else logging.DEBUG
                status_string = "{} {} {}".format(
                    ProbeResult.to_str(result['result']),
                    result['http_status'] if result['http_status'] != None else '',
                    result['reason']
                )

                duration = " ({:0.0f} ms)".format(result['request_duration'] * 1000) if result['request_duration'] != None else ''
                logger.log(level, "%s: %s%s", self._page_configs[i]['url'], status_string, duration)

                total_http_time += result['request_duration'] if result['request_duration'] != None else 0

            logger.debug("Probe %d finished. Total HTTP time: %0.3f s", probe_index + 1, total_http_time)

            self._process_asynchronous_exceptions(exception_queue)

            probe_index += 1

            logger.debug("Going to sleep for %d seconds\n", self._probe_interval)
            time.sleep(self._probe_interval)
