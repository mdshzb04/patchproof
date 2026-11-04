def run(fn):
    try:
        return fn()
    except Exception:
        pass
