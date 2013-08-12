""" Enumeration of possible results of probing a web page. """

class ProbeResult:
    MATCH            = 0 # There were no errors and all patterns were found
    NO_MATCH         = 1 # There were no errors but at least one pattern was not found
    HTTP_ERROR       = 2 # Connection was established but the request resulted in a HTTP status other than 200 OK
    CONNECTION_ERROR = 3 # Connection was not estabilished due to an error and request could not be performed
    NOT_PROBED_YET   = 4 # The site has not been probed yet

    @classmethod
    def to_str(cls, result):
        # SYNC: Keep in sync with class names in report.css
        result_strings = {
            cls.MATCH:            'MATCH',
            cls.NO_MATCH:         'NO MATCH',
            cls.HTTP_ERROR:       'HTTP ERROR',
            cls.CONNECTION_ERROR: 'CONNECTION ERROR',
            cls.NOT_PROBED_YET:   'NOT PROBED YET'
        }

        return result_strings[result]

