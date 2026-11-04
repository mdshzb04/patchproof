import tempfile


def path():
    return tempfile.mktemp(prefix="pp-")
