import subprocess


def archive(path):
    subprocess.run(["tar", "czf", "backup.tar.gz", path], check=True)
