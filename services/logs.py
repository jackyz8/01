import re, time, os
from config import Config
from services import sandbox

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ERR = re.compile(r"Traceback|\b(ERROR|CRITICAL|FATAL)\b|Error:|Exception:")

class LogManager:
    def path(self, p): return sandbox.log_path(p)
    def marker(self, p, msg):
        try:
            with open(self.path(p), "ab") as f:
                f.write(f"[manager {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n".encode())
        except OSError: pass
    def size(self, p):
        try: return self.path(p).stat().st_size
        except OSError: return 0
    def tail_lines(self, p, n, max_bytes=4*1048576):
        try: f = open(self.path(p), "rb")
        except OSError: return []
        with f:
            f.seek(0,2); pos = f.tell(); data = b""
            while pos > 0 and data.count(b"\n") <= n and len(data) < max_bytes:
                step = min(65536, pos); pos -= step; f.seek(pos)
                data = f.read(step) + data
        lines = data.decode("utf-8","replace").splitlines()
        if pos > 0 and lines: lines = lines[1:]
        return [ANSI.sub("", x) for x in lines[-n:]]
    def rotate(self, p):
        path = self.path(p)
        if self.size(p) > 20*1048576 and path.exists():
            os.replace(path, path.with_suffix(".log.1"))
    def last_error(self, p):
        for line in reversed(self.tail_lines(p, 300)):
            if ERR.search(line) and not line.startswith("[manager"):
                return line.strip()[:200]
        return None
    def error_lines(self, p):
        return [l for l in self.tail_lines(p, 20000, 8*1048576) if ERR.search(l)]

LOGS = LogManager()