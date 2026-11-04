import subprocess


def archive(path):
    subprocess.run(f"tar czf backup.tar.gz {path}", shell=True, check=True)
