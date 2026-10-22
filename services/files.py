import os, stat
from pathlib import Path

def safe_join(base: Path, rel: str) -> Path:
    base_r = Path(os.path.realpath(base))
    rel = (rel or "").replace("\\","/").strip("/")
    if "\x00" in rel: raise ValueError("Invalid path")
    target = Path(os.path.realpath(base_r / rel)) if rel else base_r
    if target != base_r and base_r not in target.parents:
        raise ValueError("Path escapes project directory")
    return target

def list_dir(path: Path, base: Path):
    base_r = Path(os.path.realpath(base))
    items = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                    if e.is_symlink():
                        real = Path(os.path.realpath(e.path))
                        if real != base_r and base_r not in real.parents: continue
                        st = e.stat()
                    items.append({"name": e.name, "dir": stat.S_ISDIR(st.st_mode),
                                  "size": st.st_size, "mtime": st.st_mtime})
                except OSError: continue
    except OSError: return []
    items.sort(key=lambda i: (not i["dir"], i["name"].lower()))
    return items

def dir_size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try: total += os.lstat(os.path.join(root, f)).st_size
            except OSError: pass
    return total