import os, re, stat, zipfile
from pathlib import Path
from config import Config

class ZipError(Exception): pass

def safe_extract(zip_path: Path, dest: Path, progress: dict = None,
                 strip_top=True, keep=None) -> int:
    if progress is None: progress = {}
    max_total = Config.MAX_UNZIPPED_MB * 1048576
    max_file = Config.MAX_FILE_MB * 1048576
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ZipError("Not a valid ZIP archive")
    with zf:
        infos = [i for i in zf.infolist()
                 if not i.filename.startswith("__MACOSX/")
                 and os.path.basename(i.filename.rstrip("/")) != ".DS_Store"]
        if not infos: raise ZipError("Archive is empty")
        if len(infos) > Config.MAX_ZIP_FILES:
            raise ZipError(f"Too many entries ({len(infos)})")
        if sum(i.file_size for i in infos) > max_total:
            raise ZipError(f"Uncompressed size exceeds {Config.MAX_UNZIPPED_MB} MB")
        names = [i.filename.replace("\\","/") for i in infos]
        prefix = ""
        if strip_top:
            tops = {n.split("/")[0] for n in names if n}
            if len(tops) == 1:
                top = next(iter(tops))
                if all(n == top+"/" or n.startswith(top+"/") for n in names):
                    prefix = top + "/"
        dest.mkdir(parents=True, exist_ok=True)
        dest_r = Path(os.path.realpath(dest))
        total = written = 0
        for idx, info in enumerate(infos):
            progress["done"] = idx
            name = info.filename.replace("\\","/")
            if info.flag_bits & 0x1: raise ZipError("Encrypted entries unsupported")
            if name.startswith("/") or "\x00" in name or re.match(r"^[A-Za-z]:", name):
                raise ZipError(f"Unsafe path: {name!r}")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if ".." in parts: raise ZipError(f"Path traversal: {name!r}")
            if prefix and name.startswith(prefix):
                parts = [p for p in name[len(prefix):].split("/") if p not in ("", ".")]
            if not parts: continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode and mode not in (stat.S_IFREG, stat.S_IFDIR):
                progress["skipped"] = progress.get("skipped", 0) + 1
                continue
            target = Path(os.path.realpath(dest_r.joinpath(*parts)))
            if target != dest_r and dest_r not in target.parents:
                raise ZipError(f"Unsafe path: {name!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True); continue
            if keep and target.exists() and keep(parts):
                progress["kept"] = progress.get("kept", 0) + 1; continue
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with zf.open(info) as src, open(target, "wb") as out:
                while True:
                    buf = src.read(65536)
                    if not buf: break
                    size += len(buf); total += len(buf)
                    if size > max_file or total > max_total:
                        raise ZipError("Exceeds allowed size (zip bomb?)")
                    out.write(buf)
            os.chmod(target, 0o755 if (info.external_attr >> 16) & 0o111 else 0o644)
            written += 1; progress["bytes"] = total
        progress["done"] = len(infos)
    return written