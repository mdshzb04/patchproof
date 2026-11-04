def run(fn):
    try:
        return fn()
    except ValueError:
        pass
