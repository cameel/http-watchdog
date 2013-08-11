from urllib.parse import urlparse

def split_url(url):
    # TMP:
    from urllib.parse import urlparse
    parsed_url = urlparse(url)

    # FIXME: Don't ignore protocol
    # FIXME: Don't discard username and password
    if not ':' in parsed_url.netloc:
        host = parsed_url.netloc
        port = ''
    else:
        host, port = parsed_url.netloc.split(':')

    port = int(port) if port != '' else 80

    # The fragment part (after #) can be discarded. It's only relevant to a client.
    path           = parsed_url.path if parsed_url.path != '' else '/'
    path_and_query = path + ('?' + parsed_url.query if parsed_url.query != '' else '')

    return (host, port, path_and_query)

# This method is not currently use anywhere but I left it for completeness.
# I may be useful in the future.
def join_url(host, port, path_and_query):
    return host + (':' + str(port) if port != 80 else '') + path_and_query
