class NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def acquire_lock(_name: str) -> NullLock:
    return NullLock()
