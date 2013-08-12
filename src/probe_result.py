class ProbeResult:
    MATCH            = 0
    NO_MATCH         = 1
    HTTP_ERROR       = 2
    CONNECTION_ERROR = 3
    NOT_PROBED_YET   = 4

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

