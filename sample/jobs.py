import subprocess


def archive(path: str) -> None:
    subprocess.run(f"tar czf backup.tar.gz {path}", shell=True, check=True)
