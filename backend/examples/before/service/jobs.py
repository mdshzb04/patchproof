import os
import subprocess


# Unchanged credential. PatchProof must not call this a new finding.
BACKUP_TOKEN = "sk-live-OLDTOKEN1234567890"


def archive(path):
    subprocess.run(["tar", "czf", "backup.tar.gz", path], check=True)


def load_cache(blob):
    return {"raw": blob}


def debug_eval(expr):
    return eval(expr)
