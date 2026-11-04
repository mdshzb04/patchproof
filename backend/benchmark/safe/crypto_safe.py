import hashlib


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checksum(data):
    return hashlib.md5(data, usedforsecurity=False).hexdigest()
