import os
import subprocess
import json
import requests


# Unchanged credential. Still pre-existing. The patch does not touch it.
BACKUP_TOKEN = "sk-live-OLDTOKEN1234567890"


def archive(path):
    subprocess.run(["tar", "czf", "backup.tar.gz", path], check=True)


def load_cache(blob):
    return json.loads(blob)


def fetch_manifest(url):
    return requests.get(url, timeout=10)


def debug_eval(expr):
    return eval(expr)
