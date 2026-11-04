import tempfile


def path():
    fd, name = tempfile.mkstemp(prefix="pp-")
    return fd, name
