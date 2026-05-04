import os


def _rotate(path: str, backup_count: int):
    if backup_count <= 0:
        return

    for i in range(backup_count, 0, -1):
        src = f"{path}.{i - 1}" if i > 1 else path
        dst = f"{path}.{i}"
        if os.path.exists(dst):
            try:
                os.remove(dst)
            except Exception:
                pass
        if os.path.exists(src):
            try:
                os.rename(src, dst)
            except Exception:
                pass


def append_with_rotation(path: str, text: str, max_bytes: int, backup_count: int, encoding: str = "utf-8"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    try:
        if os.path.exists(path) and max_bytes > 0 and os.path.getsize(path) >= max_bytes:
            _rotate(path, int(backup_count))
    except Exception:
        pass

    with open(path, "a", encoding=encoding) as f:
        f.write(text)

